"""Tests for analytics functions backed by a temp SQLite database."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app import analytics, db
from app.config import BILLING_MIN_DATE
from app.snapshot import _flatten_editors, _flatten_languages, _normalize_seat


def _build_day(date: str, suggestions: int, acceptances: int, active_users: int) -> dict:
    """Build a synthetic Copilot metrics day record."""
    return {
        "date": date,
        "total_active_users": active_users,
        "total_engaged_users": active_users,
        "copilot_ide_code_completions": {
            "editors": [
                {
                    "name": "vscode",
                    "total_engaged_users": active_users,
                    "models": [
                        {
                            "languages": [
                                {
                                    "name": "python",
                                    "total_code_suggestions": suggestions,
                                    "total_code_acceptances": acceptances,
                                    "total_code_lines_suggested": suggestions * 2,
                                    "total_code_lines_accepted": acceptances * 2,
                                    "total_engaged_users": active_users,
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    }


@pytest.fixture
def populated_db() -> None:
    """Populate the DB with 10 days of synthetic data and 3 seats."""
    db.init_db()
    today = datetime.now(UTC).date()
    for offset in range(10):
        date_str = (today - timedelta(days=offset)).isoformat()
        day = _build_day(date_str, suggestions=100 + offset, acceptances=40 + offset, active_users=5)
        db.upsert_org_day(date_str, day["total_active_users"], day["total_engaged_users"], day)
        db.replace_language_rows(date_str, _flatten_languages(day))
        db.replace_editor_rows(date_str, _flatten_editors(day))

    seats = [
        # Recently active
        _normalize_seat(
            {
                "assignee": {"login": "alice"},
                "assigning_team": {"slug": "platform", "name": "Platform"},
                "last_activity_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "last_activity_editor": "vscode",
            }
        ),
        # Stale
        _normalize_seat(
            {
                "assignee": {"login": "bob"},
                "assigning_team": {"slug": "platform", "name": "Platform"},
                "last_activity_at": (datetime.now(UTC) - timedelta(days=60)).isoformat(),
                "last_activity_editor": "vscode",
            }
        ),
        # Never used
        _normalize_seat(
            {
                "assignee": {"login": "carol"},
                "assigning_team": {"slug": "core", "name": "Core"},
                "last_activity_at": None,
            }
        ),
    ]
    db.replace_seats(seats)

    # Consumption billing: uniform $2/day Copilot spend for the last 30 days
    # so cost analytics reflect actual usage charges rather than seat price.
    db.replace_billing_usage(
        [
            {
                "date": (today - timedelta(days=offset)).isoformat(),
                "login": "alice",
                "product": "Copilot",
                "sku": "Copilot Premium Request",
                "unit_type": "request",
                "quantity": 2,
                "gross_amount_usd": 2.0,
                "discount_amount_usd": 0.0,
                "net_amount_usd": 2.0,
                "repository_name": "",
            }
            for offset in range(30)
        ]
    )


def test_trends_returns_rows_in_ascending_date_order(populated_db: None) -> None:
    """Trends should be oldest-first to support time-series charting."""
    # Act
    result = analytics.trends(days=30)

    # Assert
    assert len(result) == 10
    dates = [r["date"] for r in result]
    assert dates == sorted(dates)


def test_trends_computes_acceptance_rate(populated_db: None) -> None:
    """Acceptance rate equals acceptances / suggestions per day."""
    # Act
    result = analytics.trends(days=30)

    # Assert
    first = result[0]
    expected = round(first["acceptances"] / first["suggestions"], 4)
    assert first["acceptance_rate"] == expected


def test_kpis_reflect_seat_status_breakdown(populated_db: None) -> None:
    """KPIs should correctly count total, active-30d, never-used and stale seats."""
    # Act
    result = analytics.kpis()

    # Assert
    assert result["total_seats"] == 3
    assert result["active_users_30d"] == 1  # alice only
    assert result["never_used_seats"] == 1  # carol
    assert result["stale_seats"] == 2  # bob + carol


def test_kpis_compute_cost_and_hours_saved(populated_db: None) -> None:
    """Cost reflects actual consumption charges; hours saved scales with acceptances."""
    # Act
    result = analytics.kpis()

    # Assert
    today = datetime.now(UTC).date()
    cutoff = datetime.fromisoformat(BILLING_MIN_DATE).date()
    start = today - timedelta(days=29)
    billed_days = max(0, (today - max(start, cutoff)).days + 1)
    expected = float(billed_days * 2)
    assert result["window_cost_usd"] == pytest.approx(expected, rel=0.01)
    assert result["monthly_cost_usd"] == pytest.approx(expected, rel=0.01)
    assert result["hours_saved_30d"] > 0
    assert "cost_per_active_user_usd" not in result
    assert "wasted_spend_usd" not in result
    assert "seat_cost_usd" not in result


def test_stale_seats_includes_never_used(populated_db: None) -> None:
    """The stale list must contain seats with null last_activity_at."""
    # Act
    result = analytics.stale_seats()

    # Assert
    logins = {row["login"] for row in result}
    assert "bob" in logins
    assert "carol" in logins
    assert "alice" not in logins


def test_breakdowns_groups_by_language(populated_db: None) -> None:
    """Language breakdown aggregates acceptances across days."""
    # Act
    result = analytics.breakdowns(days=30)

    # Assert
    langs = {row["language"]: row for row in result["languages"]}
    assert "python" in langs
    assert langs["python"]["acc"] > 0


def test_linreg_returns_zero_slope_for_constant_series() -> None:
    """A flat series should produce a slope near zero."""
    # Act
    slope, intercept = analytics._linreg([0.0, 1.0, 2.0, 3.0], [5.0, 5.0, 5.0, 5.0])

    # Assert
    assert slope == pytest.approx(0.0)
    assert intercept == pytest.approx(5.0)


def test_projections_recommend_seats_for_target_adoption(populated_db: None) -> None:
    """Projection includes a right-sized seat recommendation."""
    # Act
    result = analytics.projections()

    # Assert
    assert result["available"] is True
    assert result["history_days"] == 10
    assert result["recommended_seats_for_80pct_adoption"] >= 0


def test_projections_unavailable_when_no_data() -> None:
    """With no snapshots, projections should signal unavailability."""
    # Arrange
    db.init_db()

    # Act
    result = analytics.projections()

    # Assert
    assert result["available"] is False


def test_db_upsert_is_idempotent(populated_db: None) -> None:
    """Re-inserting the same date does not create duplicates."""
    # Arrange
    today = datetime.now(UTC).date().isoformat()
    day = _build_day(today, suggestions=999, acceptances=500, active_users=99)

    # Act
    db.upsert_org_day(today, day["total_active_users"], day["total_engaged_users"], day)

    # Assert
    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM daily_org_metrics WHERE date = ?",
            (today,),
        ).fetchone()["n"]
        latest = conn.execute(
            "SELECT raw_json FROM daily_org_metrics WHERE date = ?",
            (today,),
        ).fetchone()
    assert count == 1
    assert json.loads(latest["raw_json"])["total_active_users"] == 99
