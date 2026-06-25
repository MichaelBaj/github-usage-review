"""Tests for new analytics: model breakdown, cost, PR correlation, user/team detail."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import analytics, db
from app.config import BILLING_MIN_DATE
from app.snapshot import _flatten_languages, _flatten_models, _normalize_seat


def _day(date: str) -> dict:
    """Build a metrics day with two code models and one chat model."""
    return {
        "date": date,
        "total_active_users": 4,
        "total_engaged_users": 3,
        "copilot_ide_code_completions": {
            "editors": [
                {
                    "name": "vscode",
                    "total_engaged_users": 3,
                    "models": [
                        {
                            "name": "gpt-4o-copilot",
                            "total_engaged_users": 3,
                            "languages": [
                                {
                                    "name": "python",
                                    "total_code_suggestions": 80,
                                    "total_code_acceptances": 30,
                                    "total_code_lines_suggested": 160,
                                    "total_code_lines_accepted": 60,
                                }
                            ],
                        },
                        {
                            "name": "claude-3-5-sonnet",
                            "total_engaged_users": 1,
                            "languages": [
                                {
                                    "name": "go",
                                    "total_code_suggestions": 20,
                                    "total_code_acceptances": 12,
                                    "total_code_lines_suggested": 40,
                                    "total_code_lines_accepted": 24,
                                }
                            ],
                        },
                    ],
                }
            ]
        },
        "copilot_ide_chat": {
            "editors": [
                {
                    "name": "vscode",
                    "models": [
                        {
                            "name": "gpt-4o",
                            "total_chats": 18,
                            "total_chat_insertion_events": 5,
                            "total_chat_copy_events": 7,
                        }
                    ],
                }
            ]
        },
    }


@pytest.fixture
def db_with_models() -> None:
    """Populate org + team metrics, models, seats, team members, and PRs."""
    db.init_db()
    today = datetime.now(UTC).date()
    for offset in range(5):
        d = (today - timedelta(days=offset)).isoformat()
        day = _day(d)
        db.upsert_org_day(d, day["total_active_users"], day["total_engaged_users"], day)
        db.replace_language_rows(d, _flatten_languages(day))
        db.replace_model_rows(d, "org", "", _flatten_models(day))
        # also store team-scoped copy under team "alpha"
        db.upsert_team_day(d, "alpha", day["total_active_users"], day["total_engaged_users"], day)
        db.replace_team_language_rows(d, "alpha", _flatten_languages(day))
        db.replace_model_rows(d, "team", "alpha", _flatten_models(day))

    seats = [
        _normalize_seat(
            {
                "assignee": {"login": "alice"},
                "assigning_team": {"slug": "alpha", "name": "Alpha"},
                "created_at": (datetime.now(UTC) - timedelta(days=60)).isoformat(),
                "last_activity_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "last_activity_editor": "vscode",
            }
        ),
        _normalize_seat(
            {
                "assignee": {"login": "bob"},
                "assigning_team": {"slug": "alpha", "name": "Alpha"},
                "created_at": (datetime.now(UTC) - timedelta(days=120)).isoformat(),
                "last_activity_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
                "last_activity_editor": "vscode",
            }
        ),
        _normalize_seat(
            {
                "assignee": {"login": "carol"},
                "assigning_team": {"slug": "beta", "name": "Beta"},
                "created_at": (datetime.now(UTC) - timedelta(days=200)).isoformat(),
                "last_activity_at": None,
            }
        ),
    ]
    db.replace_seats(seats)
    db.replace_team_members("alpha", ["alice", "bob"])
    db.replace_team_members("beta", ["carol", "dave"])

    # PRs: alice has seat (AI), dave does not.
    now = datetime.now(UTC)
    prs = [
        {
            "repo": "platform",
            "number": 1,
            "author": "alice",
            "state": "merged",
            "created_at": (now - timedelta(days=3, hours=4)).isoformat(),
            "merged_at": (now - timedelta(days=3)).isoformat(),
            "closed_at": (now - timedelta(days=3)).isoformat(),
            "additions": 120,
            "deletions": 30,
            "changed_files": 6,
            "comments": 1,
            "review_comments": 4,
            "commits": 3,
            "title": "feat: thing",
            "base_ref": "main",
            "head_ref": "alice/thing",
        },
        {
            "repo": "platform",
            "number": 2,
            "author": "bob",
            "state": "merged",
            "created_at": (now - timedelta(days=5, hours=12)).isoformat(),
            "merged_at": (now - timedelta(days=5)).isoformat(),
            "closed_at": (now - timedelta(days=5)).isoformat(),
            "additions": 200,
            "deletions": 50,
            "changed_files": 8,
            "comments": 0,
            "review_comments": 6,
            "commits": 5,
            "title": "feat: other",
            "base_ref": "main",
            "head_ref": "bob/other",
        },
        {
            "repo": "core",
            "number": 7,
            "author": "dave",
            "state": "merged",
            "created_at": (now - timedelta(days=4, hours=20)).isoformat(),
            "merged_at": (now - timedelta(days=4)).isoformat(),
            "closed_at": (now - timedelta(days=4)).isoformat(),
            "additions": 50,
            "deletions": 60,
            "changed_files": 3,
            "comments": 2,
            "review_comments": 2,
            "commits": 2,
            "title": "fix: thing",
            "base_ref": "main",
            "head_ref": "dave/fix",
        },
    ]
    db.upsert_pull_requests(prs)

    # Consumption billing: uniform $1/day Copilot spend for the last 90 days,
    # so consumption-based cost scales linearly with the window length.
    db.replace_billing_usage(
        [
            {
                "date": (today - timedelta(days=offset)).isoformat(),
                "login": "alice",
                "product": "Copilot",
                "sku": "Copilot Premium Request",
                "unit_type": "request",
                "quantity": 1,
                "gross_amount_usd": 1.0,
                "discount_amount_usd": 0.0,
                "net_amount_usd": 1.0,
                "repository_name": "",
            }
            for offset in range(90)
        ]
    )


def test_model_breakdown_splits_code_and_chat(db_with_models: None) -> None:
    """Models endpoint returns code + chat rows separately for the org scope."""
    # Act
    out = analytics.model_breakdown(days=7)

    # Assert — billing-only/unspecified models must not appear in model tables.
    assert {r["model"] for r in out["code"]} == {"gpt-4o-copilot", "claude-sonnet-3.5"}
    assert {r["model"] for r in out["chat"]} == {"gpt-4o"}
    # acceptance_rate must be computed and bounded.
    for r in out["code"]:
        assert 0.0 <= r["acceptance_rate"] <= 1.0


def test_ai_credits_summary_excludes_pre_billing_min_date(db_with_models: None) -> None:
    """Org AI-credit totals ignore rows older than BILLING_MIN_DATE."""
    cutoff = datetime.fromisoformat(BILLING_MIN_DATE).date()
    db.replace_billing_usage(
        [
            {
                "date": (cutoff - timedelta(days=1)).isoformat(),
                "login": "alice",
                "product": "Copilot",
                "sku": "Copilot Premium Request - gpt-4o-copilot",
                "unit_type": "request",
                "quantity": 999,
                "gross_amount_usd": 99.9,
                "discount_amount_usd": 0.0,
                "net_amount_usd": 99.9,
                "repository_name": "",
            },
            {
                "date": cutoff.isoformat(),
                "login": "alice",
                "product": "Copilot",
                "sku": "Copilot Premium Request - gpt-4o-copilot",
                "unit_type": "request",
                "quantity": 7,
                "gross_amount_usd": 0.7,
                "discount_amount_usd": 0.0,
                "net_amount_usd": 0.7,
                "repository_name": "",
            },
        ]
    )

    out = analytics.ai_credits_summary(
        start=(cutoff - timedelta(days=1)).isoformat(),
        end=cutoff.isoformat(),
    )

    assert out["total_ai_credits"] == 7.0


def test_model_breakdown_filters_to_team(db_with_models: None) -> None:
    """Passing ``team`` scopes the breakdown to that team's rows."""
    # Act
    out = analytics.model_breakdown(days=7, team="alpha")

    # Assert
    assert out["scope"] == "team"
    assert out["team"] == "alpha"
    assert any(r["model"] == "gpt-4o-copilot" for r in out["code"])


def test_model_breakdown_includes_ai_credits(db_with_models: None) -> None:
    """model_breakdown attaches ai_credits from billing_usage per model."""
    today = datetime.now(UTC).date()
    # Seed billing rows with model-specific SKUs matching fixture models.
    db.replace_billing_usage(
        [
            {
                "date": (today - timedelta(days=1)).isoformat(),
                "login": "alice",
                "product": "Copilot",
                "sku": "Copilot Premium Request - gpt-4o-copilot",
                "unit_type": "request",
                "quantity": 42,
                "gross_amount_usd": 4.2,
                "discount_amount_usd": 0.0,
                "net_amount_usd": 4.2,
                "repository_name": "",
            },
            {
                "date": (today - timedelta(days=1)).isoformat(),
                "login": "bob",
                "product": "Copilot",
                "sku": "Copilot Premium Request - gpt-4o",
                "unit_type": "request",
                "quantity": 10,
                "gross_amount_usd": 1.0,
                "discount_amount_usd": 0.0,
                "net_amount_usd": 1.0,
                "repository_name": "",
            },
        ]
    )

    out = analytics.model_breakdown(days=7)

    code_gpt4o = next(r for r in out["code"] if r["model"] == "gpt-4o-copilot")
    assert code_gpt4o["ai_credits"] == 42

    chat_gpt4o = next(r for r in out["chat"] if r["model"] == "gpt-4o")
    assert chat_gpt4o["ai_credits"] == 10

    # Model with no billing data should have 0 credits.
    code_claude = next(r for r in out["code"] if r["model"] == "claude-sonnet-3.5")
    assert code_claude["ai_credits"] == 0.0


def test_chat_vs_inline_includes_share(db_with_models: None) -> None:
    """Chat-vs-inline returns share + totals for both modes."""
    # Act
    out = analytics.chat_vs_inline(days=7)

    # Assert
    assert out["code_suggestions"] > 0
    assert out["chat_total"] > 0
    assert 0.0 < out["chat_interaction_share"] < 1.0


def test_cost_for_window_reflects_consumption(db_with_models: None) -> None:
    """Window cost equals summed Copilot consumption; longer windows cost more."""
    # Act
    short = analytics.cost_for_window(days=30)
    long_ = analytics.cost_for_window(days=60)

    # Assert
    today = datetime.now(UTC).date()
    cutoff = datetime.fromisoformat(BILLING_MIN_DATE).date()

    short_start = today - timedelta(days=29)
    long_start = today - timedelta(days=59)
    short_billed_days = max(0, (today - max(short_start, cutoff)).days + 1)
    long_billed_days = max(0, (today - max(long_start, cutoff)).days + 1)

    assert short["window_cost_usd"] == pytest.approx(float(short_billed_days), rel=0.01)
    assert long_["window_cost_usd"] == pytest.approx(float(long_billed_days), rel=0.01)
    assert "seats_in_window" not in short
    assert "seat_cost_usd" not in short


def test_pr_correlation_splits_ai_vs_non(db_with_models: None) -> None:
    """PRs by seat-holders bucket into ai_authored; non-seat into non_ai_authored."""
    # Act
    out = analytics.pr_correlation(days=30)

    # Assert
    assert out["ai_authored"]["pr_count"] == 2  # alice + bob
    assert out["non_ai_authored"]["pr_count"] == 1  # dave
    assert out["total_prs"] == 3
    assert 0.0 < out["ai_authored_share"] <= 1.0
    assert out["ai_authored"]["avg_cycle_time_hours"] is not None


def test_pr_correlation_filters_to_team_members(db_with_models: None) -> None:
    """Team filter limits PRs to that team's members."""
    # Act
    out = analytics.pr_correlation(days=30, team="alpha")

    # Assert
    assert out["ai_authored"]["pr_count"] == 2  # alice + bob (both alpha)
    assert out["non_ai_authored"]["pr_count"] == 0


def test_power_user_concentration_returns_top_users(db_with_models: None) -> None:
    """Distribution returns ranked authors + top-10% share."""
    # Act
    out = analytics.power_user_concentration(days=30)

    # Assert
    assert out["active_authors"] == 3
    assert len(out["top_users"]) == 3
    assert out["top_10pct_share"] > 0.0


def test_cohort_ramp_buckets_seats(db_with_models: None) -> None:
    """Cohort ramp counts seats into time-to-first-use buckets including never-used."""
    # Act
    out = analytics.cohort_ramp()

    # Assert
    assert out["never_used"] == 1  # carol
    assert sum(out["buckets"].values()) == 3


def test_team_detail_aggregates_metrics_and_pr(db_with_models: None) -> None:
    """Team detail includes daily series, totals, models, PR correlation, and cost."""
    # Act
    out = analytics.team_detail("alpha", days=7)

    # Assert
    assert out["team"] == "alpha"
    assert out["members_with_seats"] == 2  # alice + bob
    assert out["totals"]["acceptances"] > 0
    assert out["models"]["scope"] == "team"
    assert out["pr_correlation"]["ai_authored"]["pr_count"] == 2


def test_users_list_includes_pr_activity(db_with_models: None) -> None:
    """User list joins seat info with PR activity rollup."""
    # Act
    out = analytics.users_list(days=30)

    # Assert
    logins = {u["login"]: u for u in out}
    assert logins["alice"]["prs"] == 1
    assert logins["bob"]["status"] == "active"
    assert logins["carol"]["status"] == "never_used"


def test_users_list_includes_ai_credits(db_with_models: None) -> None:
    """User list includes per-user AI credit totals from billing_usage."""
    # Act
    out = analytics.users_list(days=30)

    # Assert — alice has 1 credit/day × 30 days in fixture
    logins = {u["login"]: u for u in out}
    assert logins["alice"]["ai_credits"] > 0
    assert logins["bob"]["ai_credits"] == 0.0
    assert logins["carol"]["ai_credits"] == 0.0


def test_user_detail_returns_seat_and_prs(db_with_models: None) -> None:
    """User detail returns seat + per-day PR aggregates + transparency note."""
    # Act
    out = analytics.user_detail("alice", days=30)

    # Assert
    assert out["has_seat"] is True
    assert out["totals"]["prs"] == 1
    assert out["totals"]["additions"] == 120
    assert out["per_user_copilot_metrics_available"] is False
    assert "alpha" in out["teams"]


def test_kpis_include_window_cost(db_with_models: None) -> None:
    """KPIs now expose ``window_cost_usd`` aligned to the requested window."""
    # Act
    short = analytics.kpis(days=7)
    long_ = analytics.kpis(days=60)

    # Assert
    assert short["window_days"] == 7
    assert short["window_cost_usd"] < long_["window_cost_usd"]


def test_kpis_accepts_explicit_start_end(db_with_models: None) -> None:
    """An explicit date range overrides ``days`` and is reflected in the response."""
    # Act
    out = analytics.kpis(start="2026-01-01", end="2026-01-10")

    # Assert
    assert out["window_start"] == "2026-01-01"
    assert out["window_end"] == "2026-01-10"
    assert out["window_days"] == 10
