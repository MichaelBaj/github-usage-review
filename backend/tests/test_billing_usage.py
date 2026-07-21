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
    assert "billing csv" in out["tokens_note"].lower()


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


def test_ai_credits_summary_reports_monthly_applied_credits_and_discount() -> None:
    """Monthly org-level AICredits map to credits-applied + included-discount fields."""
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-07-01",
                "login": "",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "unit_type": "AICredits",
                "quantity": 1000,
                "gross_amount_usd": 10.0,
                "net_amount_usd": 1.5,
            },
            {
                "date": "2026-07-02",
                "login": "",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "unit_type": "AICredits",
                "quantity": 500,
                "gross_amount_usd": 5.0,
                "net_amount_usd": 0.0,
            },
            {
                "date": "2026-06-30",
                "login": "",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "unit_type": "AICredits",
                "quantity": 999,
                "gross_amount_usd": 9.99,
                "net_amount_usd": 0.0,
            },
        ]
    )

    # Act
    out = analytics.ai_credits_summary(start="2026-07-01", end="2026-07-07")

    # Assert
    assert out["credits_applied_month_label"] == "Jul 2026"
    assert out["credits_applied_month"] == pytest.approx(1500.0)
    assert out["credits_applied_discount_usd_month"] == pytest.approx(13.5)


def test_ai_credits_summary_excludes_org_level_applied_aicredits_from_consumed_totals() -> None:
    """Org-level unit_type=AICredits rows are allowance/discount, not consumed credits."""
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-07-01",
                "login": "",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "unit_type": "AICredits",
                "quantity": 1000,
                "gross_amount_usd": 10.0,
                "net_amount_usd": 2.0,
            },
            {
                "date": "2026-07-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 120,
                "gross_amount_usd": 1.2,
                "net_amount_usd": 1.2,
                "model": "Claude Sonnet 4.6",
            },
        ]
    )

    out = analytics.ai_credits_summary(start="2026-07-01", end="2026-07-01")

    assert out["total_ai_credits"] == pytest.approx(120.0)
    assert out["top_users"][0]["login"] == "alice"
    assert out["credits_applied_month"] == pytest.approx(1000.0)
    assert out["credits_applied_discount_usd_month"] == pytest.approx(8.0)


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


def test_balanced_users_ranking_prioritizes_perfect_balance_and_volume() -> None:
    """Balanced users are sorted by combined score of closeness to the 45-55% plateau and volume."""
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        [
            # User 1: total = 10, perfectly 50/50
            # Within plateau => distance = 0 => balance_factor = 1.0 => score = log10(10) * 1.0 = 1.00
            {
                "date": "2026-06-01",
                "login": "user_low_vol_perfect",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 5,
                "net_amount_usd": 0.20,
                "model": "Claude Opus 4.6",
            },
            {
                "date": "2026-06-01",
                "login": "user_low_vol_perfect",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 5,
                "net_amount_usd": 0.20,
                "model": "Claude Sonnet 4.6",
            },
            # User 2: total = 10000, 55/45 balance (perfect mix sample)
            # Within plateau => distance = 0 => balance_factor = 1.0 => score = log10(10000) * 1.0 = 4.00
            {
                "date": "2026-06-01",
                "login": "user_high_vol_balanced_plateau",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 5500,
                "net_amount_usd": 220.00,
                "model": "Claude Opus 4.6",
            },
            {
                "date": "2026-06-01",
                "login": "user_high_vol_balanced_plateau",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 4500,
                "net_amount_usd": 180.00,
                "model": "Claude Sonnet 4.6",
            },
            # User 3: total = 10000, 40/60 balance
            # Outside plateau => high_pct = 40.0 => distance = 5.0 => balance_factor = 1 - 5/45 = 8/9 => score = 4.00 * (8/9)^2 = 3.16
            {
                "date": "2026-06-01",
                "login": "user_high_vol_less_balanced",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 4000,
                "net_amount_usd": 160.00,
                "model": "Claude Opus 4.6",
            },
            {
                "date": "2026-06-01",
                "login": "user_high_vol_less_balanced",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 6000,
                "net_amount_usd": 240.00,
                "model": "Claude Sonnet 4.6",
            },
        ]
    )

    # Act
    out = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-01")
    ranked = [u["login"] for u in out["balanced_users"]]

    # Assert
    # Expected scores:
    # user_high_vol_balanced_plateau: log10(10000) * 1.0 = 4.00
    # user_high_vol_less_balanced: log10(10000) * (8/9)^2 = 3.16
    # user_low_vol_perfect: log10(10) * 1.0 = 1.00
    assert ranked == ["user_high_vol_balanced_plateau", "user_high_vol_less_balanced", "user_low_vol_perfect"]


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


def test_ai_credits_for_user_keeps_non_model_rows_without_same_user_model_match() -> None:
    """User credits should not drop when another user has model-attributed rows."""
    # Arrange
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-06-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 7,
                "net_amount_usd": 0.28,
                "model": "",
            },
            {
                "date": "2026-06-01",
                "login": "bob",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 11,
                "net_amount_usd": 0.44,
                "model": "GPT-5.4",
            },
        ]
    )

    # Act
    out = analytics.ai_credits_for_user("alice", start="2026-06-01", end="2026-06-01")

    # Assert
    assert out["ai_credits"] == pytest.approx(7.0)


def test_ai_credits_for_team_keeps_non_model_rows_without_member_model_match() -> None:
    """Team credits should include member rows even if model rows exist for other users."""
    # Arrange
    db.init_db()
    db.replace_team_members("alpha", ["alice"])
    db.replace_billing_usage(
        [
            {
                "date": "2026-06-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 9,
                "net_amount_usd": 0.36,
                "model": "",
            },
            {
                "date": "2026-06-01",
                "login": "bob",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 14,
                "net_amount_usd": 0.56,
                "model": "Claude Opus 4.6",
            },
        ]
    )

    # Act
    out = analytics.ai_credits_for_team("alpha", start="2026-06-01", end="2026-06-01")

    # Assert
    assert out["ai_credits"] == pytest.approx(9.0)
    assert out["members"] == 1


# ---------------------------------------------------------------------------
# Headline AI-credit aggregate (ai_credit/usage endpoint)
# ---------------------------------------------------------------------------


def test_ai_credits_summary_includes_headline_from_meta(billing_db: None) -> None:
    """When headline meta keys are set, ai_credits_summary exposes them."""
    db.set_meta("ai_credit_headline_qty", "806917.98")
    db.set_meta("ai_credit_headline_net_usd", "1234.98")
    db.set_meta("ai_credit_headline_gross_usd", "8069.18")
    db.set_meta("ai_credit_headline_period", "2026-06")
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


# ---------------------------------------------------------------------------
# daily_org_ai_credits — projection chart data
# ---------------------------------------------------------------------------

def _seed_two_months(cur_date: str, prev_date: str) -> None:
    """Seed billing_usage with one row per day for two calendar months."""
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": cur_date,
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 10,
                "net_amount_usd": 0.40,
                "model": "claude-sonnet",
            },
            {
                "date": prev_date,
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 7,
                "net_amount_usd": 0.28,
                "model": "claude-sonnet",
            },
        ]
    )


def test_daily_org_ai_credits_returns_correct_month_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Month labels match the calendar months relative to the mocked today."""
    from datetime import date as date_cls
    monkeypatch.setattr(analytics, "_today", lambda: date_cls(2026, 7, 7))
    _seed_two_months("2026-07-03", "2026-06-15")

    out = analytics.daily_org_ai_credits()

    assert out["current_month_label"] == "Jul 2026"
    assert out["previous_month_label"] == "Jun 2026"


def test_daily_org_ai_credits_cumulative_running_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cumulative series increases monotonically and matches raw daily totals."""
    from datetime import date as date_cls
    monkeypatch.setattr(analytics, "_today", lambda: date_cls(2026, 7, 7))
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-07-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 5,
                "net_amount_usd": 0.20,
                "model": "claude-sonnet",
            },
            {
                "date": "2026-07-03",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 10,
                "net_amount_usd": 0.40,
                "model": "claude-sonnet",
            },
        ]
    )

    out = analytics.daily_org_ai_credits()
    cur = out["current_month"]

    # Must have entries up to day 3 (the last day with data)
    assert len(cur) == 3
    assert cur[0] == {"day": 1, "cumulative": pytest.approx(5.0)}
    assert cur[1] == {"day": 2, "cumulative": pytest.approx(5.0)}   # no data → unchanged
    assert cur[2] == {"day": 3, "cumulative": pytest.approx(15.0)}

    # Each step must be non-decreasing
    for i in range(1, len(cur)):
        assert cur[i]["cumulative"] >= cur[i - 1]["cumulative"]


def test_daily_org_ai_credits_empty_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no billing data both series are empty; labels are still set."""
    from datetime import date as date_cls
    monkeypatch.setattr(analytics, "_today", lambda: date_cls(2026, 7, 7))
    db.init_db()

    out = analytics.daily_org_ai_credits()

    assert out["current_month"] == []
    assert out["previous_month"] == []
    assert out["current_month_label"] == "Jul 2026"
    assert out["previous_month_label"] == "Jun 2026"


def test_daily_org_ai_credits_excludes_non_billable_skus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-billable SKUs (e.g. enterprise seats) are excluded from credit totals."""
    from datetime import date as date_cls
    monkeypatch.setattr(analytics, "_today", lambda: date_cls(2026, 7, 7))
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-07-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 20,
                "net_amount_usd": 0.80,
                "model": "claude-sonnet",
            },
            {
                "date": "2026-07-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_enterprise",       # non-billable seat SKU
                "quantity": 900,
                "net_amount_usd": 9.00,
                "model": "",
            },
        ]
    )

    out = analytics.daily_org_ai_credits()

    assert len(out["current_month"]) == 1
    assert out["current_month"][0]["cumulative"] == pytest.approx(20.0)


def test_daily_org_ai_credits_excludes_org_level_applied_aicredits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Projection excludes org-level AICredits when per-user rows exist for same date."""
    from datetime import date as date_cls

    monkeypatch.setattr(analytics, "_today", lambda: date_cls(2026, 7, 7))
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-07-01",
                "login": "",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "unit_type": "AICredits",
                "quantity": 1000,
                "gross_amount_usd": 10.0,
                "net_amount_usd": 0.0,
            },
            {
                "date": "2026-07-01",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 12,
                "net_amount_usd": 0.48,
                "model": "claude-sonnet",
            },
            {
                "date": "2026-07-02",
                "login": "alice",
                "product": "Copilot",
                "sku": "copilot_ai_credit",
                "quantity": 8,
                "net_amount_usd": 0.32,
                "model": "claude-sonnet",
            },
        ]
    )

    out = analytics.daily_org_ai_credits()
    cur = out["current_month"]

    # Jul 1: org-level excluded because per-user row exists; Jul 2: user row kept
    assert cur[0] == {"day": 1, "cumulative": pytest.approx(12.0)}
    assert cur[1] == {"day": 2, "cumulative": pytest.approx(20.0)}


def test_daily_org_ai_credits_keeps_org_aicredits_when_no_per_user_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Projection keeps org-level AICredits rows when no per-user data exists for that date."""
    from datetime import date as date_cls

    monkeypatch.setattr(analytics, "_today", lambda: date_cls(2026, 7, 7))
    db.init_db()
    db.replace_billing_usage(
        [
            {
                "date": "2026-07-01",
                "login": "",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "unit_type": "AICredits",
                "quantity": 500,
                "gross_amount_usd": 5.0,
                "net_amount_usd": 0.0,
            },
            {
                "date": "2026-07-02",
                "login": "",
                "product": "Copilot",
                "sku": "Copilot AI Credits",
                "unit_type": "AICredits",
                "quantity": 300,
                "gross_amount_usd": 3.0,
                "net_amount_usd": 0.0,
            },
        ]
    )

    out = analytics.daily_org_ai_credits()
    cur = out["current_month"]

    # No per-user rows → org-level AICredits kept as best available signal
    assert cur[0] == {"day": 1, "cumulative": pytest.approx(500.0)}
    assert cur[1] == {"day": 2, "cumulative": pytest.approx(800.0)}
