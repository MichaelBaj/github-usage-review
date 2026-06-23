"""Tests for billing-usage flattener + AI-credit analytics."""
from __future__ import annotations

import pytest

from app import analytics, db
from app.snapshot import _flatten_billing_usage


def _payload() -> dict:
    """Build a sample enhanced-billing-usage API response."""
    return {
        "usageItems": [
            {
                "date": "2026-06-01",
                "product": "Copilot",
                "sku": "Copilot Premium Request",
                "unitType": "request",
                "quantity": 12,
                "grossAmount": 0.48,
                "discountAmount": 0,
                "netAmount": 0.48,
                "username": "Alice",
                "repositoryName": "",
            },
            {
                "date": "2026-06-01",
                "product": "Copilot",
                "sku": "Copilot Premium Request",
                "unitType": "request",
                "quantity": 5,
                "grossAmount": 0.20,
                "netAmount": 0.20,
                "username": "bob",
            },
            {
                "date": "2026-06-02",
                "product": "Copilot",
                "sku": "Copilot Premium Request",
                "unitType": "request",
                "quantity": 8,
                "grossAmount": 0.32,
                "netAmount": 0.32,
                "username": "alice",
            },
            {
                # Non-Copilot SKU should still flatten but not surface in copilot rollups.
                "date": "2026-06-02",
                "product": "Actions",
                "sku": "Actions Linux",
                "unitType": "minute",
                "quantity": 100,
                "grossAmount": 0.80,
                "netAmount": 0.80,
            },
        ]
    }


def test_flatten_billing_usage_lowercases_login_and_defaults_fields() -> None:
    """Logins are normalized; missing fields default to safe values."""
    # Act
    rows = _flatten_billing_usage(_payload())

    # Assert
    assert len(rows) == 4
    alice_rows = [r for r in rows if r["login"] == "alice"]
    assert len(alice_rows) == 2  # case-folded "Alice" + "alice"
    actions = next(r for r in rows if r["product"] == "Actions")
    assert actions["login"] == ""
    assert actions["repository_name"] == ""


def test_flatten_billing_usage_skips_items_without_date() -> None:
    """Items missing both ``date`` and ``usageAt`` are skipped."""
    # Act
    rows = _flatten_billing_usage({"usageItems": [{"product": "Copilot", "sku": "x", "quantity": 1}]})

    # Assert
    assert rows == []


@pytest.fixture
def billing_db() -> None:
    """Seed the DB with billing rows + a seat record for transparency."""
    db.init_db()
    db.replace_billing_usage(_flatten_billing_usage(_payload()))


def test_ai_credits_summary_aggregates_org_total(billing_db: None) -> None:
    """Org rollup sums quantity across all Copilot billable rows."""
    # Act
    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-02")

    # Assert
    assert out["available"] is True
    assert out["total_ai_credits"] == pytest.approx(25.0)  # 12 + 5 + 8
    assert out["total_ai_credit_cost_usd"] == pytest.approx(1.00)
    assert out["tokens_available"] is False
    assert "token" in out["tokens_note"].lower()


def test_ai_credits_summary_lists_top_users(billing_db: None) -> None:
    """Top-users list ranks logins by credit count."""
    # Act
    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-02")

    # Assert
    top_logins = [u["login"] for u in out["top_users"]]
    assert top_logins[0] == "alice"
    assert "bob" in top_logins


def test_ai_credits_for_user_filters_by_login(billing_db: None) -> None:
    """Per-user view filters and case-folds the login."""
    # Act
    out = analytics.ai_credits_for_user("alice", start="2026-06-01", end="2026-06-02")

    # Assert
    assert out["ai_credits"] == pytest.approx(20.0)  # 12 + 8
    assert len(out["daily_ai_credits"]) == 2


def test_ai_credits_for_team_sums_member_usage(billing_db: None) -> None:
    """Team rollup includes only billing rows belonging to team members."""
    # Arrange
    db.replace_team_members("alpha", ["alice", "bob"])

    # Act
    out = analytics.ai_credits_for_team("alpha", start="2026-06-01", end="2026-06-02")

    # Assert
    assert out["ai_credits"] == pytest.approx(25.0)
    assert out["members"] == 2


def test_ai_credits_summary_marks_unavailable_when_db_empty() -> None:
    """With zero billing rows, ``available`` reports False so the UI can degrade."""
    # Arrange
    db.init_db()

    # Act
    out = analytics.ai_credits_summary()

    # Assert
    assert out["available"] is False
    assert out["total_ai_credits"] == 0.0


def test_model_from_sku_parses_model_suffix() -> None:
    """``_model_from_sku`` returns the trailing model name when present."""
    # Act + Assert
    assert (
        analytics._model_from_sku("Copilot Premium Request - Claude 3.5 Sonnet")
        == "Claude 3.5 Sonnet"
    )
    assert analytics._model_from_sku("Copilot Premium Request - GPT-4.1") == "GPT-4.1"
    assert analytics._model_from_sku("Copilot Premium Request") == "unspecified"
    assert analytics._model_from_sku("") == "unspecified"
    assert analytics._model_from_sku(None) == "unspecified"


def test_ai_credits_for_user_groups_by_model() -> None:
    """``by_model`` aggregates quantity + cost per parsed model and totals to 100%."""
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        _flatten_billing_usage(
            {
                "usageItems": [
                    {
                        "date": "2026-06-01",
                        "username": "alice",
                        "product": "Copilot",
                        "sku": "Copilot Premium Request - Claude 3.5 Sonnet",
                        "unitType": "request",
                        "quantity": 30,
                        "netAmount": 1.20,
                    },
                    {
                        "date": "2026-06-01",
                        "username": "alice",
                        "product": "Copilot",
                        "sku": "Copilot Premium Request - GPT-4.1",
                        "unitType": "request",
                        "quantity": 10,
                        "netAmount": 0.40,
                    },
                    {
                        "date": "2026-06-02",
                        "username": "alice",
                        "product": "Copilot",
                        "sku": "Copilot Premium Request - Claude 3.5 Sonnet",
                        "unitType": "request",
                        "quantity": 10,
                        "netAmount": 0.40,
                    },
                ]
            }
        )
    )

    # Act
    out = analytics.ai_credits_for_user(
        "alice", start="2026-06-01", end="2026-06-02"
    )

    # Assert
    assert out["ai_credits"] == pytest.approx(50.0)
    by_model = {row["model"]: row for row in out["by_model"]}
    assert by_model["Claude 3.5 Sonnet"]["ai_credits"] == pytest.approx(40.0)
    assert by_model["GPT-4.1"]["ai_credits"] == pytest.approx(10.0)
    assert by_model["Claude 3.5 Sonnet"]["share"] == pytest.approx(0.8)
    assert by_model["GPT-4.1"]["share"] == pytest.approx(0.2)
    # Sorted descending by AI-credit count
    assert out["by_model"][0]["model"] == "Claude 3.5 Sonnet"
