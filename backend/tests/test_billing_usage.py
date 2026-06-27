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


def test_ai_credits_summary_sku_table_uses_billable_rows_and_normalizes_labels() -> None:
    """By-SKU rows must match billable totals and collapse naming variants."""
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-06-02",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 100,
                "gross_amount_usd": 4.00,
                "net_amount_usd": 4.00,
            },
            {
                "date": "2026-06-02",
                "login": "bob",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "quantity": 50,
                "gross_amount_usd": 2.00,
                "net_amount_usd": 2.00,
            },
            {
                "date": "2026-06-02",
                "login": "carol",
                "product": "Copilot Enterprise",
                "sku": "copilot_enterprise",
                "quantity": 900,
                "gross_amount_usd": 9.00,
                "net_amount_usd": 9.00,
            },
        ]
    )

    # Act
    out = analytics.ai_credits_summary(start="2026-06-02", end="2026-06-02")

    # Assert
    assert out["total_ai_credits"] == pytest.approx(150.0)
    assert len(out["skus"]) == 1
    row = out["skus"][0]
    assert row["sku"] == "copilot_ai_credit"
    assert row["product"] == "copilot"
    assert row["quantity"] == pytest.approx(150.0)


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


def test_ai_credits_summary_groups_top_users_per_model() -> None:
    """Per-model rollup returns top 5 users with percentage share."""
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-06-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 60,
                "net_amount_usd": 2.40,
                "model": "Claude Opus 4.6",
            },
            {
                "date": "2026-06-01",
                "login": "bob",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 40,
                "net_amount_usd": 1.60,
                "model": "Claude Opus 4.6",
            },
            {
                "date": "2026-06-01",
                "login": "bob",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 20,
                "net_amount_usd": 0.80,
                "model": "GPT-5.4",
            },
            {
                "date": "2026-06-01",
                "login": "charlie",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 5,
                "net_amount_usd": 0.20,
                "model": "GPT-5.4",
            },
        ]
    )

    # Act
    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-01")

    # Assert
    by_model = {row["model"]: row for row in out["top_users_per_model"]}
    assert by_model["Claude Opus 4.6"]["total_ai_credits"] == pytest.approx(100.0)
    assert by_model["Claude Opus 4.6"]["top_users"][0]["login"] == "alice"
    assert by_model["Claude Opus 4.6"]["top_users"][0]["ai_credits"] == pytest.approx(60.0)
    assert by_model["Claude Opus 4.6"]["top_users"][0]["percentage"] == pytest.approx(60.0)
    assert by_model["GPT-5.4"]["total_ai_credits"] == pytest.approx(25.0)
    assert by_model["GPT-5.4"]["top_users"][0]["login"] == "bob"


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


def test_ai_credits_summary_returns_balanced_users() -> None:
    """Balanced users require >=20% high-tier and >=20% low-tier usage."""
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-06-01",
                "login": "balanced",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 60,
                "net_amount_usd": 2.40,
                "model": "Claude Opus 4.6",
            },
            {
                "date": "2026-06-01",
                "login": "balanced",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 40,
                "net_amount_usd": 1.60,
                "model": "Claude Sonnet 4.6",
            },
            {
                "date": "2026-06-01",
                "login": "high_only",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 100,
                "net_amount_usd": 4.00,
                "model": "GPT-5.4",
            },
        ]
    )

    # Act
    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-01")

    # Assert
    assert out["balanced_user_threshold_pct"] == pytest.approx(20.0)
    assert out["balanced_users"][0]["login"] == "balanced"
    assert out["balanced_users"][0]["high_pct"] == pytest.approx(60.0)
    assert out["balanced_users"][0]["low_pct"] == pytest.approx(40.0)
    assert all(user["login"] != "high_only" for user in out["balanced_users"])


def test_model_tier_auto_gpt54_counts_as_high() -> None:
    """High-tier model matches should override the generic Auto:* low-tier bucket."""
    # Act + Assert
    assert analytics._model_tier("Auto: GPT-5.4") == "high"
    assert analytics._model_tier("Auto: GPT-5.3-Codex") == "low"


def test_ai_credits_summary_deduplicates_overlapping_sources() -> None:
    """When model-attributed rows exist, non-model duplicates must be excluded.

    Billing data can be imported from multiple CSV sources that overlap:
    - csv_ai_usage_report: per-user, per-model (has model attribution)
    - csv_usage_report: per-user aggregate (model='')
    - API snapshot: org-level aggregate (model='', login='')

    Only model-attributed rows should be counted when they are available.
    """
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        [
            # Source 1: model-attributed rows (csv_ai_usage_report)
            {
                "date": "2026-06-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 60,
                "net_amount_usd": 2.40,
                "model": "Claude Opus 4.6",
                "source": "csv_ai_usage_report",
            },
            {
                "date": "2026-06-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 40,
                "net_amount_usd": 1.60,
                "model": "GPT-5.4",
                "source": "csv_ai_usage_report",
            },
            # Source 2: per-user aggregate WITHOUT model (csv_usage_report)
            # Same total as alice's model rows — this is a duplicate aggregate.
            {
                "date": "2026-06-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 100,
                "net_amount_usd": 4.00,
                "model": "",
                "source": "csv_usage_report",
            },
            # Source 3: org-level aggregate (API snapshot)
            {
                "date": "2026-06-01",
                "login": "",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 100,
                "net_amount_usd": 4.00,
                "model": "",
                "source": "",
            },
        ]
    )

    # Act
    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-01")

    # Assert — should be 100 (60+40), NOT 300 (triple-counted)
    assert out["total_ai_credits"] == pytest.approx(100.0)
    assert out["total_ai_credit_cost_usd"] == pytest.approx(4.00)
    assert len(out["skus"]) == 1
    assert out["skus"][0]["quantity"] == pytest.approx(100.0)
    # Per-user should also be deduped
    assert len(out["top_users"]) == 1
    assert out["top_users"][0]["ai_credits"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Headline AI-credit aggregate (ai_credit/usage endpoint)
# ---------------------------------------------------------------------------


def test_ai_credits_summary_includes_headline_from_meta(billing_db: None) -> None:
    """When headline meta keys are set, ai_credits_summary exposes them."""
    db.set_meta("ai_credit_headline_qty", "806917.98")
    db.set_meta("ai_credit_headline_net_usd", "1234.98")
    db.set_meta("ai_credit_headline_gross_usd", "8069.18")
    db.set_meta("ai_credit_headline_at", "2026-06-26T12:00:00+00:00")

    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-02")

    assert out["headline_ai_credits"] == pytest.approx(806917.98)
    assert out["headline_ai_credit_cost_usd"] == pytest.approx(1234.98)
    assert out["headline_ai_credit_gross_usd"] == pytest.approx(8069.18)
    assert out["headline_fetched_at"] == "2026-06-26T12:00:00+00:00"
    # Row-level totals still present alongside headline.
    assert out["total_ai_credits"] == pytest.approx(25.0)


def test_ai_credits_summary_headline_null_when_no_meta(billing_db: None) -> None:
    """Without headline meta, fields are None (frontend falls back to row totals)."""
    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-02")

    assert out["headline_ai_credits"] is None
    assert out["headline_ai_credit_cost_usd"] is None
    assert out["headline_fetched_at"] is None


@pytest.mark.asyncio
async def test_ingest_ai_credit_headline_stores_meta() -> None:
    """_ingest_ai_credit_headline persists aggregate totals in DB meta."""
    from unittest.mock import AsyncMock

    from app.snapshot import _ingest_ai_credit_headline

    db.init_db()

    fake_gh = AsyncMock()
    fake_gh.org_ai_credit_usage.return_value = {
        "timePeriod": {"year": 2026, "month": 6},
        "usageItems": [
            {
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "model": "gpt-4o",
                "grossQuantity": 500000.0,
                "grossAmount": 5000.0,
                "netQuantity": 500000.0,
                "netAmount": 750.0,
            },
            {
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "model": "claude-sonnet-4",
                "grossQuantity": 306917.98,
                "grossAmount": 3069.18,
                "netQuantity": 306917.98,
                "netAmount": 484.98,
            },
        ],
    }

    summary = await _ingest_ai_credit_headline(fake_gh)

    assert summary["total_qty"] == pytest.approx(806917.98)
    assert summary["total_net_usd"] == pytest.approx(1234.98)
    assert summary["total_gross_usd"] == pytest.approx(8069.18)
    assert summary["items"] == 2

    # Verify meta was stored.
    assert float(db.get_meta("ai_credit_headline_qty")) == pytest.approx(806917.98)
    assert float(db.get_meta("ai_credit_headline_net_usd")) == pytest.approx(1234.98)
    assert db.get_meta("ai_credit_headline_period") == "2026-06"
    assert db.get_meta("ai_credit_headline_at") is not None
