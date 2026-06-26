"""Derived analytics: KPIs, trends, leaderboard, stale seats, ROI, projections.

Pure read-only functions over the SQLite snapshots. All numeric outputs
are bounded and rounded for direct presentation to the frontend.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls
from typing import Any

from . import db
from .config import BILLING_MIN_DATE, settings

# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def _today() -> date_cls:
    """Return today's UTC date."""
    return datetime.now(UTC).date()


def _parse_date(value: str | None) -> date_cls | None:
    """Parse a YYYY-MM-DD string into a ``date``; return ``None`` on failure."""
    if not value:
        return None
    try:
        return date_cls.fromisoformat(value[:10])
    except ValueError:
        return None


def _window(
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
    default_days: int = 30,
) -> tuple[str, str, int]:
    """Resolve a flexible window spec into ``(start_iso, end_iso, day_count)``.

    Precedence: explicit ``start``/``end`` beats ``days``. ``end`` defaults to
    today (UTC); ``start`` derives from ``end - days``.

    Args:
        days: Number of days back from ``end`` (inclusive of today).
        start: ISO date string ``YYYY-MM-DD`` for window start (inclusive).
        end: ISO date string ``YYYY-MM-DD`` for window end (inclusive).
        default_days: Window size used when no params supplied.

    Returns:
        Tuple ``(start_iso, end_iso, day_count)`` where ``day_count`` is
        the inclusive number of days in the window.
    """
    end_d = _parse_date(end) or _today()
    if start:
        start_d = _parse_date(start) or (end_d - timedelta(days=default_days - 1))
    else:
        n = days if days is not None else default_days
        n = max(1, n)
        start_d = end_d - timedelta(days=n - 1)
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    day_count = (end_d - start_d).days + 1
    return start_d.isoformat(), end_d.isoformat(), day_count


# ---------------------------------------------------------------------------
# Existing helpers (kept)
# ---------------------------------------------------------------------------


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string into an aware datetime, returning ``None`` on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sum_day(raw: dict[str, Any]) -> dict[str, int]:
    """Sum suggestions/acceptances across editors and languages for one day.

    Handles both the legacy ``copilot_ide_code_completions`` nesting and the
    new report format (identified by the ``_report`` key).
    """
    if raw.get("_report"):
        # New report format — flat top-level counters.
        return {
            "suggestions": raw.get("code_generation_activity_count") or 0,
            "acceptances": raw.get("code_acceptance_activity_count") or 0,
            "lines_suggested": raw.get("loc_suggested_to_add_sum") or 0,
            "lines_accepted": raw.get("loc_added_sum") or 0,
        }
    # Legacy format — traverse nested editor/model/language trees.
    suggestions = acceptances = lines_suggested = lines_accepted = 0
    code = raw.get("copilot_ide_code_completions") or {}
    for editor in code.get("editors", []) or []:
        for model in editor.get("models", []) or []:
            for lang in model.get("languages", []) or []:
                suggestions += lang.get("total_code_suggestions", 0) or 0
                acceptances += lang.get("total_code_acceptances", 0) or 0
                lines_suggested += lang.get("total_code_lines_suggested", 0) or 0
                lines_accepted += lang.get("total_code_lines_accepted", 0) or 0
    return {
        "suggestions": suggestions,
        "acceptances": acceptances,
        "lines_suggested": lines_suggested,
        "lines_accepted": lines_accepted,
    }


def trends(
    days: int = 90,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Return per-day org metrics over the window, oldest first."""
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=90)
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT date, total_active_users, total_engaged_users, raw_json "
            "FROM daily_org_metrics WHERE date BETWEEN ? AND ? ORDER BY date ASC",
            (start_iso, end_iso),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        sums = _sum_day(json.loads(row["raw_json"]))
        acc_rate = (sums["acceptances"] / sums["suggestions"]) if sums["suggestions"] else 0.0
        out.append(
            {
                "date": row["date"],
                "active_users": row["total_active_users"] or 0,
                "engaged_users": row["total_engaged_users"] or 0,
                "suggestions": sums["suggestions"],
                "acceptances": sums["acceptances"],
                "lines_suggested": sums["lines_suggested"],
                "lines_accepted": sums["lines_accepted"],
                "acceptance_rate": round(acc_rate, 4),
            }
        )
    return out


def _seat_summary() -> dict[str, Any]:
    """Compute aggregate seat status from the seats table."""
    now = datetime.now(UTC)
    stale_cut = now - timedelta(days=settings.stale_seat_days)
    active_cut = now - timedelta(days=7)
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT login, last_activity_at, last_activity_editor, assigning_team FROM seats"
        ).fetchall()
    total = len(rows)
    active_7d = 0
    active_30d = 0
    never_used = 0
    stale: list[dict[str, Any]] = []
    for row in rows:
        last_activity = _parse_iso(row["last_activity_at"])
        if last_activity is None:
            never_used += 1
            stale.append(
                {
                    "login": row["login"],
                    "team": row["assigning_team"],
                    "last_activity_at": None,
                    "editor": None,
                    "days_inactive": None,
                }
            )
            continue
        if last_activity >= active_cut:
            active_7d += 1
        if last_activity >= stale_cut:
            active_30d += 1
        else:
            stale.append(
                {
                    "login": row["login"],
                    "team": row["assigning_team"],
                    "last_activity_at": row["last_activity_at"],
                    "editor": row["last_activity_editor"],
                    "days_inactive": (now - last_activity).days,
                }
            )
    stale.sort(key=lambda item: (item["days_inactive"] is None, -(item["days_inactive"] or 0)))
    return {
        "total_seats": total,
        "active_7d": active_7d,
        "active_30d": active_30d,
        "stale_count": len(stale),
        "never_used": never_used,
        "stale_seats": stale,
    }


def kpis(
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return the headline KPIs over a configurable window (default 30 days)."""
    start_iso, end_iso, window_days = _window(days=days, start=start, end=end, default_days=30)
    trend = trends(start=start_iso, end=end_iso)
    seats = _seat_summary()
    last7 = trend[-7:] if len(trend) >= 7 else trend
    suggestions = sum(d["suggestions"] for d in trend)
    acceptances = sum(d["acceptances"] for d in trend)
    lines_accepted = sum(d["lines_accepted"] for d in trend)
    acc_rate = (acceptances / suggestions) if suggestions else 0.0
    hours_saved = (acceptances * settings.minutes_saved_per_acceptance) / 60.0
    # Cost is now consumption-based (GitHub bills Copilot per actual usage),
    # not a fixed per-seat price. The monthly figure is a 30-day run-rate
    # extrapolated from the window's actual consumption.
    window_cost = _consumption_cost_usd(start_iso, end_iso)
    monthly_cost = round(window_cost * (30.0 / window_days), 2) if window_days else 0.0
    adoption = (seats["active_30d"] / seats["total_seats"]) if seats["total_seats"] else 0.0
    avg_dau_7d = (sum(d["active_users"] for d in last7) / len(last7)) if last7 else 0
    return {
        "window_start": start_iso,
        "window_end": end_iso,
        "window_days": window_days,
        "total_seats": seats["total_seats"],
        "active_users_7d": seats["active_7d"],
        "active_users_30d": seats["active_30d"],
        "never_used_seats": seats["never_used"],
        "stale_seats": seats["stale_count"],
        "adoption_rate_30d": round(adoption, 4),
        "avg_dau_7d": round(avg_dau_7d, 1),
        "acceptance_rate_30d": round(acc_rate, 4),
        "acceptances_30d": acceptances,
        "suggestions_30d": suggestions,
        "lines_accepted_window": lines_accepted,
        "hours_saved_30d": round(hours_saved, 1),
        "monthly_cost_usd": round(monthly_cost, 2),
        "window_cost_usd": window_cost,
        "last_snapshot_at": db.get_meta("last_snapshot_at"),
        "last_data_load_at": db.get_meta("last_data_load_at"),
        "last_data_load_source": db.get_meta("last_data_load_source"),
    }


def stale_seats() -> list[dict[str, Any]]:
    """Return the list of stale seats (inactive longer than configured threshold)."""
    return _seat_summary()["stale_seats"]


def _team_member_rollup(
    members: list[str],
    start_iso: str,
    end_iso: str,
) -> dict[str, Any]:
    """Aggregate per-user signals for a set of team members over a window.

    Per-team Copilot insight is derived by joining org-wide *per-user* data
    (``seats`` activity, ``pull_requests`` authorship, ``billing_usage``
    consumption) to team membership, because the GitHub team Copilot-metrics
    endpoint is unavailable for enterprise-managed orgs. This is the basis for
    building the Teams dashboard from user data rather than team-scoped metrics.

    Args:
        members: Team member logins (from ``team_members``).
        start_iso: Inclusive window start (``YYYY-MM-DD``).
        end_iso: Inclusive window end (``YYYY-MM-DD``).

    Returns:
        ``{"members": [per-member rows], "summary": {team aggregates}}``.
    """
    now = datetime.now(UTC)
    stale_cut = now - timedelta(days=settings.stale_seat_days)
    start_dt = f"{start_iso}T00:00:00+00:00"
    end_dt = f"{end_iso}T23:59:59+00:00"
    member_set = {m for m in members if m}
    lower_map = {m.lower(): m for m in member_set}

    seat_by_login: dict[str, dict[str, Any]] = {}
    pr_by_login: dict[str, dict[str, int]] = {}
    premium_by_login: dict[str, float] = {}
    cost_by_login: dict[str, float] = {}

    if member_set:
        placeholders = ",".join("?" for _ in member_set)
        lower_placeholders = ",".join("?" for _ in lower_map)
        ordered_members = sorted(member_set)
        ordered_lower = sorted(lower_map)
        with db.connect() as conn:
            for row in conn.execute(
                f"SELECT login, last_activity_at, last_activity_editor "
                f"FROM seats WHERE login IN ({placeholders})",
                ordered_members,
            ).fetchall():
                seat_by_login[row["login"]] = dict(row)
            for row in conn.execute(
                f"SELECT author, COUNT(*) AS prs, "
                f"SUM(CASE WHEN merged_at IS NOT NULL THEN 1 ELSE 0 END) AS merged, "
                f"SUM(additions) AS adds, SUM(deletions) AS dels "
                f"FROM pull_requests "
                f"WHERE author IN ({placeholders}) "
                f"AND ((created_at BETWEEN ? AND ?) OR (merged_at BETWEEN ? AND ?)) "
                f"GROUP BY author",
                (*ordered_members, start_dt, end_dt, start_dt, end_dt),
            ).fetchall():
                pr_by_login[row["author"]] = {
                    "prs": row["prs"] or 0,
                    "merged_prs": row["merged"] or 0,
                    "additions": row["adds"] or 0,
                    "deletions": row["dels"] or 0,
                }
            for row in conn.execute(
                f"SELECT login, SUM(quantity) AS qty FROM billing_usage "
                f"WHERE date BETWEEN ? AND ? AND lower(product) LIKE '%copilot%' "
                f"{_BILLING_MIN_DATE_SQL} "
                f"AND {_COPILOT_BILLABLE_SKU_SQL} "
                f"{_billing_dedup_sql(conn, start_iso, end_iso)} "
                f"AND lower(login) IN ({lower_placeholders}) GROUP BY login",
                (start_iso, end_iso, *ordered_lower),
            ).fetchall():
                canonical = lower_map.get((row["login"] or "").lower(), row["login"])
                premium_by_login[canonical] = float(row["qty"] or 0)
            for row in conn.execute(
                f"SELECT login, SUM(net_amount_usd) AS net FROM billing_usage "
                f"WHERE date BETWEEN ? AND ? AND lower(product) LIKE '%copilot%' "
                f"{_BILLING_MIN_DATE_SQL} "
                f"AND {_COPILOT_BILLABLE_SKU_SQL} "
                f"{_billing_dedup_sql(conn, start_iso, end_iso)} "
                f"AND lower(login) IN ({lower_placeholders}) GROUP BY login",
                (start_iso, end_iso, *ordered_lower),
            ).fetchall():
                canonical = lower_map.get((row["login"] or "").lower(), row["login"])
                cost_by_login[canonical] = round(float(row["net"] or 0), 2)

    rows_out: list[dict[str, Any]] = []
    active_members = stale_members = never_used_members = 0
    total_premium = total_cost = 0.0
    total_prs = total_merged = total_net_lines = 0
    for login in sorted(member_set):
        seat = seat_by_login.get(login)
        last_activity = _parse_iso(seat["last_activity_at"]) if seat else None
        if seat is None:
            status = "no_seat"
        elif last_activity is None:
            status = "never_used"
            never_used_members += 1
        elif last_activity >= stale_cut:
            status = "active"
            active_members += 1
        else:
            status = "stale"
            stale_members += 1
        pr = pr_by_login.get(login, {"prs": 0, "merged_prs": 0, "additions": 0, "deletions": 0})
        net_lines = pr["additions"] - pr["deletions"]
        premium = premium_by_login.get(login, 0.0)
        cost = cost_by_login.get(login, 0.0)
        total_premium += premium
        total_cost += cost
        total_prs += pr["prs"]
        total_merged += pr["merged_prs"]
        total_net_lines += net_lines
        rows_out.append(
            {
                "login": login,
                "has_seat": seat is not None,
                "status": status,
                "last_activity_at": seat["last_activity_at"] if seat else None,
                "last_activity_editor": seat["last_activity_editor"] if seat else None,
                "prs": pr["prs"],
                "merged_prs": pr["merged_prs"],
                "net_lines": net_lines,
                "ai_credits": round(premium, 2),
                "cost_usd": cost,
            }
        )
    rows_out.sort(key=lambda r: (r["ai_credits"], r["prs"]), reverse=True)

    members_total = len(member_set)
    members_with_seats = sum(1 for r in rows_out if r["has_seat"])
    adoption_rate = (active_members / members_with_seats) if members_with_seats else 0.0
    return {
        "members": rows_out,
        "summary": {
            "members_total": members_total,
            "members_with_seats": members_with_seats,
            "active_members": active_members,
            "stale_members": stale_members,
            "never_used_members": never_used_members,
            "adoption_rate": round(adoption_rate, 4),
            "ai_credits": round(total_premium, 2),
            "window_cost_usd": round(total_cost, 2),
            "prs": total_prs,
            "merged_prs": total_merged,
            "net_lines": total_net_lines,
        },
    }


def teams_leaderboard(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Return per-team aggregated usage over a window.

    The GitHub team Copilot-metrics endpoint is unavailable for
    enterprise-managed orgs, so team rows are built by aggregating per-user
    data (seat activity, PR authorship, billing consumption) over the team's
    membership. Any team-scoped metrics that *are* present are merged in for
    backward compatibility, but membership is the authoritative team source.
    """
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    with db.connect() as conn:
        membership_rows = conn.execute(
            "SELECT team_slug, login FROM team_members"
        ).fetchall()
        metric_rows = conn.execute(
            "SELECT date, team_slug, total_active_users, raw_json "
            "FROM daily_team_metrics WHERE date BETWEEN ? AND ?",
            (start_iso, end_iso),
        ).fetchall()

    members_by_team: dict[str, list[str]] = defaultdict(list)
    for row in membership_rows:
        if row["team_slug"] and row["login"]:
            members_by_team[row["team_slug"]].append(row["login"])

    # Team-scoped metrics (usually empty for enterprise-managed orgs).
    metrics_by_team: dict[str, dict[str, Any]] = {}
    metric_day_counts: dict[str, int] = {}
    for row in metric_rows:
        slug = row["team_slug"]
        sums = _sum_day(json.loads(row["raw_json"]))
        agg = metrics_by_team.setdefault(
            slug,
            {"suggestions": 0, "acceptances": 0, "lines_accepted": 0,
             "lines_suggested": 0, "active_users_sum": 0, "peak_active_users": 0},
        )
        agg["suggestions"] += sums["suggestions"]
        agg["acceptances"] += sums["acceptances"]
        agg["lines_accepted"] += sums["lines_accepted"]
        agg["lines_suggested"] += sums["lines_suggested"]
        agg["active_users_sum"] += row["total_active_users"] or 0
        agg["peak_active_users"] = max(agg["peak_active_users"], row["total_active_users"] or 0)
        metric_day_counts[slug] = metric_day_counts.get(slug, 0) + 1

    slugs = sorted(set(members_by_team) | set(metrics_by_team))
    out: list[dict[str, Any]] = []
    for slug in slugs:
        rollup = _team_member_rollup(members_by_team.get(slug, []), start_iso, end_iso)
        summary = rollup["summary"]
        metric = metrics_by_team.get(slug)
        if metric:
            days_n = metric_day_counts.get(slug, 1) or 1
            suggestions = metric["suggestions"]
            acceptances = metric["acceptances"]
            lines_accepted = metric["lines_accepted"]
            lines_suggested = metric["lines_suggested"]
            avg_active_users = round(metric["active_users_sum"] / days_n, 1)
            peak_active_users = metric["peak_active_users"]
            acceptance_rate = round((acceptances / suggestions) if suggestions else 0.0, 4)
        else:
            suggestions = acceptances = lines_accepted = lines_suggested = 0
            avg_active_users = peak_active_users = 0
            acceptance_rate = 0.0
        out.append(
            {
                "team": slug,
                # User-derived (primary source for enterprise-managed orgs).
                "members_total": summary["members_total"],
                "members_with_seats": summary["members_with_seats"],
                "active_members": summary["active_members"],
                "stale_members": summary["stale_members"],
                "never_used_members": summary["never_used_members"],
                "adoption_rate": summary["adoption_rate"],
                "ai_credits": summary["ai_credits"],
                "window_cost_usd": summary["window_cost_usd"],
                "prs": summary["prs"],
                "merged_prs": summary["merged_prs"],
                "net_lines": summary["net_lines"],
                # Team-scoped metrics (kept for backward compatibility).
                "suggestions": suggestions,
                "acceptances": acceptances,
                "lines_accepted": lines_accepted,
                "lines_suggested": lines_suggested,
                "active_users_sum": metric["active_users_sum"] if metric else 0,
                "peak_active_users": peak_active_users,
                "avg_active_users": avg_active_users,
                "acceptance_rate": acceptance_rate,
            }
        )
    out.sort(key=lambda item: (item["active_members"], item["members_total"]), reverse=True)
    return out


def breakdowns(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return aggregated language + editor + model breakdowns over a window."""
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    with db.connect() as conn:
        lang_rows = conn.execute(
            "SELECT language, SUM(acceptances) AS acc, SUM(suggestions) AS sug, "
            "SUM(lines_accepted) AS la "
            "FROM daily_language_metrics WHERE date BETWEEN ? AND ? GROUP BY language ORDER BY acc DESC",
            (start_iso, end_iso),
        ).fetchall()
        editor_rows = conn.execute(
            "SELECT editor, SUM(acceptances) AS acc, SUM(suggestions) AS sug, "
            "SUM(chat_total_chats) AS chats "
            "FROM daily_editor_metrics WHERE date BETWEEN ? AND ? GROUP BY editor ORDER BY acc DESC",
            (start_iso, end_iso),
        ).fetchall()
        model_rows = conn.execute(
            "SELECT model, SUM(acceptances) AS acc, SUM(suggestions) AS sug, "
            "SUM(chats) AS chats "
            "FROM daily_model_metrics WHERE date BETWEEN ? AND ? AND scope = 'org' "
            "GROUP BY model ORDER BY (SUM(suggestions) + SUM(chats)) DESC",
            (start_iso, end_iso),
        ).fetchall()
    return {
        "languages": [dict(r) for r in lang_rows],
        "editors": [dict(r) for r in editor_rows],
        "models": [
            dict(r) for r in model_rows
            if _normalize_model_name(r["model"]) not in ("unspecified", "unknown")
        ],
    }


def feature_breakdown(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return per-feature usage breakdown over a window.

    Features include ``code_completion``, ``chat_panel_agent_mode``,
    ``copilot_cli``, ``agent_edit``, etc.
    """
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT feature, "
            "SUM(interactions) AS interactions, "
            "SUM(code_generations) AS code_generations, "
            "SUM(code_acceptances) AS code_acceptances, "
            "SUM(loc_suggested) AS loc_suggested, "
            "SUM(loc_accepted) AS loc_accepted, "
            "SUM(loc_deleted) AS loc_deleted "
            "FROM daily_feature_metrics WHERE date BETWEEN ? AND ? "
            "GROUP BY feature ORDER BY SUM(interactions) + SUM(code_generations) DESC",
            (start_iso, end_iso),
        ).fetchall()
    return {
        "window_start": start_iso,
        "window_end": end_iso,
        "features": [dict(r) for r in rows],
    }


def roi(
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return cost/savings/ROI summary for a window."""
    kpi = kpis(days=days, start=start, end=end)
    annual_cost = kpi["monthly_cost_usd"] * 12
    annual_hours_saved = kpi["hours_saved_30d"] * 12
    return {
        "window_start": kpi["window_start"],
        "window_end": kpi["window_end"],
        "window_days": kpi["window_days"],
        "minutes_saved_per_acceptance": settings.minutes_saved_per_acceptance,
        "monthly_cost_usd": kpi["monthly_cost_usd"],
        "window_cost_usd": kpi["window_cost_usd"],
        "annual_cost_usd": round(annual_cost, 2),
        "hours_saved_window": kpi["hours_saved_30d"],
        "annual_hours_saved_est": round(annual_hours_saved, 1),
    }


def _linreg(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Return ``(slope, intercept)`` for a simple linear regression."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den else 0.0
    intercept = mean_y - slope * mean_x
    return slope, intercept


def projections() -> dict[str, Any]:
    """Project active-user trajectory 90 days forward and right-size seats."""
    trend = trends(days=90)
    if not trend:
        return {"available": False, "reason": "no data yet"}
    xs = [float(i) for i in range(len(trend))]
    ys = [float(d["active_users"]) for d in trend]
    slope, intercept = _linreg(xs, ys)
    horizon = len(trend) + 90
    projected_active = max(0.0, slope * horizon + intercept)
    seats = _seat_summary()
    target_adoption = 0.80
    recommended_seats = (
        round(projected_active / target_adoption) if projected_active else seats["total_seats"]
    )
    return {
        "available": True,
        "history_days": len(trend),
        "current_active": ys[-1],
        "projected_active_90d": round(projected_active, 1),
        "trend_slope_per_day": round(slope, 3),
        "current_seats": seats["total_seats"],
        "recommended_seats_for_80pct_adoption": recommended_seats,
        "potential_seat_reduction": max(0, seats["total_seats"] - recommended_seats),
    }


# ---------------------------------------------------------------------------
# New analytics — models, chat/inline split, distribution, cohorts, PR data
# ---------------------------------------------------------------------------


def model_breakdown(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Aggregate model usage for a window.

    Args:
        days: Window size in days (default 30).
        start: Override window start (inclusive, YYYY-MM-DD).
        end: Override window end (inclusive, YYYY-MM-DD).
        team: Optional team slug; ``None`` rolls up the whole org.

    Returns:
        Dict with ``window_*`` info and rows split into ``code`` and
        ``chat`` arrays per (editor, model).
    """
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    scope = "team" if team else "org"
    team_slug = team or ""
    with db.connect() as conn:
        if team:
            # Team scope: use daily_model_metrics which has complete per-model breakdown.
            rows = conn.execute(
                "SELECT editor, model, is_chat, "
                "SUM(suggestions) AS suggestions, SUM(acceptances) AS acceptances, "
                "SUM(lines_suggested) AS lines_suggested, SUM(lines_accepted) AS lines_accepted, "
                "SUM(chats) AS chats, SUM(chat_insertions) AS chat_insertions, "
                "SUM(chat_copies) AS chat_copies, MAX(engaged_users) AS engaged_users "
                "FROM daily_model_metrics "
                "WHERE date BETWEEN ? AND ? AND scope = ? AND team_slug = ? "
                "GROUP BY editor, model, is_chat",
                (start_iso, end_iso, scope, team_slug),
            ).fetchall()
        else:
            # Org scope: for code, use raw_json (same source as kpis/trends).
            # For chat, use daily_model_metrics (has individual model breakdown).
            # This ensures model_breakdown totals match KPI totals.
            day_rows = conn.execute(
                "SELECT raw_json FROM daily_org_metrics "
                "WHERE date BETWEEN ? AND ? ORDER BY date ASC",
                (start_iso, end_iso),
            ).fetchall()
            
            # Aggregate code from raw_json into per-editor rows.
            code_by_editor: dict[str, dict[str, Any]] = {}
            for dr in day_rows:
                raw = json.loads(dr["raw_json"])
                if raw.get("_report"):
                    # New report format: use totals_by_ide directly.
                    for ide_obj in raw.get("totals_by_ide") or []:
                        editor = ide_obj.get("ide") or "unknown"
                        if editor not in code_by_editor:
                            code_by_editor[editor] = {
                                "editor": editor,
                                "model": "Code",
                                "is_chat": 0,
                                "suggestions": 0,
                                "acceptances": 0,
                                "lines_suggested": 0,
                                "lines_accepted": 0,
                                "chats": 0,
                                "chat_insertions": 0,
                                "chat_copies": 0,
                                "engaged_users": 0,
                            }
                        bucket = code_by_editor[editor]
                        bucket["suggestions"] += ide_obj.get("code_generation_activity_count") or 0
                        bucket["acceptances"] += ide_obj.get("code_acceptance_activity_count") or 0
                        bucket["lines_suggested"] += ide_obj.get("loc_suggested_to_add_sum") or 0
                        bucket["lines_accepted"] += ide_obj.get("loc_added_sum") or 0
                else:
                    # Legacy format: traverse nested editors/models/languages.
                    code = raw.get("copilot_ide_code_completions") or {}
                    for editor_obj in code.get("editors", []) or []:
                        editor = editor_obj.get("name", "unknown")
                        if editor not in code_by_editor:
                            code_by_editor[editor] = {
                                "editor": editor,
                                "model": "Code",
                                "is_chat": 0,
                                "suggestions": 0,
                                "acceptances": 0,
                                "lines_suggested": 0,
                                "lines_accepted": 0,
                                "chats": 0,
                                "chat_insertions": 0,
                                "chat_copies": 0,
                                "engaged_users": 0,
                            }
                        bucket = code_by_editor[editor]
                        for model_obj in editor_obj.get("models", []) or []:
                            bucket["engaged_users"] = max(
                                bucket["engaged_users"],
                                model_obj.get("total_engaged_users", 0) or 0,
                            )
                            for lang in model_obj.get("languages", []) or []:
                                bucket["suggestions"] += (
                                    lang.get("total_code_suggestions", 0) or 0
                                )
                                bucket["acceptances"] += (
                                    lang.get("total_code_acceptances", 0) or 0
                                )
                                bucket["lines_suggested"] += (
                                    lang.get("total_code_lines_suggested", 0) or 0
                                )
                                bucket["lines_accepted"] += (
                                    lang.get("total_code_lines_accepted", 0) or 0
                                )

            # Get chat from daily_model_metrics.
            chat_rows = conn.execute(
                "SELECT editor, model, "
                "SUM(chats) AS chats, SUM(chat_insertions) AS chat_insertions, "
                "SUM(chat_copies) AS chat_copies, MAX(engaged_users) AS engaged_users "
                "FROM daily_model_metrics "
                "WHERE date BETWEEN ? AND ? AND scope = ? AND is_chat = 1 "
                "GROUP BY editor, model",
                (start_iso, end_iso, scope),
            ).fetchall()
            
            # Combine code (per-editor) and chat (per-model) rows.
            rows = list(code_by_editor.values()) + [
                {
                    "editor": r["editor"],
                    "model": r["model"],
                    "is_chat": 1,
                    "suggestions": 0,
                    "acceptances": 0,
                    "lines_suggested": 0,
                    "lines_accepted": 0,
                    "chats": r["chats"],
                    "chat_insertions": r["chat_insertions"],
                    "chat_copies": r["chat_copies"],
                    "engaged_users": r["engaged_users"],
                }
                for r in chat_rows
            ]
        try:
            dedup = _billing_dedup_sql(conn, start_iso, end_iso)
            billing_rows = conn.execute(
                "SELECT sku, model, SUM(quantity) AS qty "
                "FROM billing_usage WHERE date BETWEEN ? AND ? "
                f"{_BILLING_MIN_DATE_SQL} "
                "AND lower(product) LIKE '%copilot%' "
                f"AND {_COPILOT_BILLABLE_SKU_SQL} "
                f"{dedup} "
                "GROUP BY sku, model",
                (start_iso, end_iso),
            ).fetchall()
        except Exception:
            billing_rows = []

    # Build model→ai_credits lookup from billing data (normalized).
    # This map can include "unspecified", but model tables below will not.
    credits_by_model: dict[str, float] = {}
    for br in billing_rows:
        model_name = _normalize_model_name(br["model"] or _model_from_sku(br["sku"]))
        credits_by_model[model_name] = (
            credits_by_model.get(model_name, 0.0) + float(br["qty"] or 0)
        )

    code: list[dict[str, Any]] = []
    chat: list[dict[str, Any]] = []
    for r in rows:
        sug = r["suggestions"] or 0
        acc = r["acceptances"] or 0
        normalized = _normalize_model_name(r["model"])
        if normalized in ("unspecified", "unknown"):
            # Product requirement: model-level tables must not show
            # unspecified/unknown — these lack actionable detail.
            continue
        entry = {
            "editor": r["editor"],
            "model": normalized,
            "suggestions": sug,
            "acceptances": acc,
            "lines_suggested": r["lines_suggested"] or 0,
            "lines_accepted": r["lines_accepted"] or 0,
            "chats": r["chats"] or 0,
            "chat_insertions": r["chat_insertions"] or 0,
            "chat_copies": r["chat_copies"] or 0,
            "engaged_users": r["engaged_users"] or 0,
            "acceptance_rate": round((acc / sug) if sug else 0.0, 4),
            "ai_credits": credits_by_model.get(normalized, 0.0),
        }
        if r["is_chat"]:
            chat.append(entry)
        else:
            code.append(entry)

    # Add billing-only models (e.g. "Code Review model", "Auto: ..."
    # variants) that have no metrics counterpart.
    # Skip "unspecified"/"unknown".
    metrics_models = {e["model"] for e in code + chat}
    for model_name, credits in credits_by_model.items():
        if model_name in metrics_models:
            continue
        if model_name in ("unspecified", "unknown"):
            continue
        chat.append({
            "editor": "",
            "model": model_name,
            "suggestions": 0,
            "acceptances": 0,
            "lines_suggested": 0,
            "lines_accepted": 0,
            "chats": 0,
            "chat_insertions": 0,
            "chat_copies": 0,
            "engaged_users": 0,
            "acceptance_rate": 0.0,
            "ai_credits": credits,
        })

    code.sort(key=lambda x: x["acceptances"], reverse=True)
    chat.sort(key=lambda x: x["chats"], reverse=True)

    # When team-scope Copilot metrics are unavailable (common: GitHub
    # returns 404 for team metrics), fall back to billing-derived model
    # data aggregated from team members.
    if team and not code and not chat:
        with db.connect() as conn:
            member_rows = conn.execute(
                "SELECT login FROM team_members WHERE team_slug = ?", (team,)
            ).fetchall()
            members = [r["login"] for r in member_rows if r["login"]]
            if members:
                ph = ",".join("?" for _ in members)
                try:
                    billing_team = conn.execute(
                        f"SELECT model, sku, SUM(quantity) AS qty, "
                        f"SUM(net_amount_usd) AS net "
                        f"FROM billing_usage WHERE date BETWEEN ? AND ? "
                        f"{_BILLING_MIN_DATE_SQL} "
                        f"AND lower(product) LIKE '%copilot%' "
                        f"AND {_COPILOT_BILLABLE_SKU_SQL} "
                        f"AND lower(login) IN ({ph}) "
                        f"AND model != '' "
                        f"GROUP BY model ORDER BY qty DESC",
                        (start_iso, end_iso, *[m.lower() for m in members]),
                    ).fetchall()
                except Exception:
                    billing_team = []
                for br in billing_team:
                    model_name = _normalize_model_name(br["model"] or _model_from_sku(br["sku"]))
                    if model_name == "unspecified":
                        continue
                    code.append({
                        "editor": "",
                        "model": model_name,
                        "suggestions": 0,
                        "acceptances": 0,
                        "lines_suggested": 0,
                        "lines_accepted": 0,
                        "chats": 0,
                        "chat_insertions": 0,
                        "chat_copies": 0,
                        "engaged_users": 0,
                        "acceptance_rate": 0.0,
                        "ai_credits": float(br["qty"] or 0),
                    })

    # Build per-editor code completion summary for org scope.
    code_editors: list[dict[str, Any]] = []
    if not team:
        for r in code:
            code_editors.append({
                "editor": r["editor"],
                "suggestions": r["suggestions"],
                "acceptances": r["acceptances"],
                "acceptance_rate": r["acceptance_rate"],
                "lines_suggested": r["lines_suggested"],
                "lines_accepted": r["lines_accepted"],
            })
        code_editors.sort(key=lambda x: x["acceptances"], reverse=True)

    return {
        "window_start": start_iso,
        "window_end": end_iso,
        "scope": scope,
        "team": team,
        "code": code,
        "chat": chat,
        "code_editors": code_editors,
    }


def chat_vs_inline(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Compare code-completion vs chat usage for a window."""
    data = model_breakdown(days=days, start=start, end=end, team=team)
    code_acc = sum(r["acceptances"] for r in data["code"])
    code_sug = sum(r["suggestions"] for r in data["code"])
    code_lines = sum(r["lines_accepted"] for r in data["code"])
    chat_total = sum(r["chats"] for r in data["chat"])
    chat_ins = sum(r["chat_insertions"] for r in data["chat"])
    chat_copies = sum(r["chat_copies"] for r in data["chat"])
    chat_share = (
        chat_total / (chat_total + code_sug) if (chat_total + code_sug) else 0.0
    )
    return {
        "window_start": data["window_start"],
        "window_end": data["window_end"],
        "scope": data["scope"],
        "team": team,
        "code_suggestions": code_sug,
        "code_acceptances": code_acc,
        "code_lines_accepted": code_lines,
        "code_acceptance_rate": round((code_acc / code_sug) if code_sug else 0.0, 4),
        "chat_total": chat_total,
        "chat_insertions": chat_ins,
        "chat_copies": chat_copies,
        "chat_interaction_share": round(chat_share, 4),
    }


def _consumption_cost_usd(
    start_iso: str,
    end_iso: str,
    logins: set[str] | None = None,
) -> float:
    """Sum actual Copilot consumption charges over a window.

    GitHub bills Copilot on consumption (enhanced billing usage), so dollar
    cost is the sum of ``net_amount_usd`` across Copilot billing rows in the
    window — not a fixed per-seat price.

    Args:
        start_iso: Inclusive window start (``YYYY-MM-DD``).
        end_iso: Inclusive window end (``YYYY-MM-DD``).
        logins: Optional set of seat logins to attribute cost to; when omitted,
            all org-level Copilot consumption is summed (including rows with no
            per-user attribution).

    Returns:
        Total net consumption cost in USD, rounded to cents.
    """
    query = (
        "SELECT SUM(net_amount_usd) AS net FROM billing_usage "
        "WHERE date BETWEEN ? AND ? "
        f"{_BILLING_MIN_DATE_SQL} "
        "AND lower(product) LIKE '%copilot%'"
    )
    params: list[Any] = [start_iso, end_iso]
    if logins is not None:
        if not logins:
            return 0.0
        placeholders = ",".join("?" for _ in logins)
        query += f" AND lower(login) IN ({placeholders})"
        params.extend(sorted(login.lower() for login in logins))
    with db.connect() as conn:
        dedup = _billing_dedup_sql(conn, start_iso, end_iso)
        query += f" {dedup}"
        row = conn.execute(query, params).fetchone()
    return round(float(row["net"] or 0.0), 2) if row else 0.0


def cost_for_window(
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Compute actual Copilot consumption cost for a window.

    GitHub bills Copilot on consumption, so the window cost is the summed
    ``net_amount_usd`` of Copilot billing rows in the window. The monthly
    figure extrapolates that to a 30-day run-rate.
    """
    start_iso, end_iso, window_days = _window(days=days, start=start, end=end, default_days=30)
    window_cost = _consumption_cost_usd(start_iso, end_iso)
    monthly = round(window_cost * (30.0 / window_days), 2) if window_days else 0.0
    return {
        "window_start": start_iso,
        "window_end": end_iso,
        "window_days": window_days,
        "monthly_cost_usd": monthly,
        "window_cost_usd": window_cost,
    }


def cohort_ramp() -> dict[str, Any]:
    """Compute seat-onboarding ramp: days from seat assignment to first activity.

    Uses ``seats.created_at`` and ``seats.last_activity_at`` as the only
    signals available without per-user metrics. ``time_to_first_use_days``
    is approximated as days between assignment and last activity for
    seats that became active within 30 days of assignment; older active
    seats are still counted but lumped into "long-tail".
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT login, created_at, last_activity_at FROM seats"
        ).fetchall()
    buckets = {"<=7d": 0, "8-14d": 0, "15-30d": 0, ">30d": 0, "never": 0}
    samples: list[int] = []
    for r in rows:
        created = _parse_iso(r["created_at"])
        last_active = _parse_iso(r["last_activity_at"])
        if not last_active:
            buckets["never"] += 1
            continue
        if not created:
            continue
        delta_days = max(0, (last_active - created).days)
        samples.append(delta_days)
        if delta_days <= 7:
            buckets["<=7d"] += 1
        elif delta_days <= 14:
            buckets["8-14d"] += 1
        elif delta_days <= 30:
            buckets["15-30d"] += 1
        else:
            buckets[">30d"] += 1
    samples.sort()
    median = samples[len(samples) // 2] if samples else None
    return {
        "buckets": buckets,
        "median_days_to_first_use": median,
        "sample_size": len(samples),
        "never_used": buckets["never"],
    }


# ---------------------------------------------------------------------------
# PR correlation analytics — quality / outcome signals
# ---------------------------------------------------------------------------


def _pr_window_clause() -> str:
    """SQL clause: PRs whose ``created_at`` overlaps the window."""
    return "(created_at BETWEEN ? AND ?) OR (merged_at BETWEEN ? AND ?)"


def _seat_logins() -> set[str]:
    """Return the set of logins that currently hold a Copilot seat."""
    with db.connect() as conn:
        rows = conn.execute("SELECT login FROM seats").fetchall()
    return {r["login"] for r in rows if r["login"]}


def _active_seat_logins(within_days: int = 30) -> set[str]:
    """Return logins active within the given recency window."""
    cutoff = (datetime.now(UTC) - timedelta(days=within_days)).isoformat()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT login FROM seats WHERE last_activity_at >= ?", (cutoff,)
        ).fetchall()
    return {r["login"] for r in rows if r["login"]}


def _hours(seconds: float) -> float:
    """Convert seconds to hours, rounded to 1 decimal."""
    return round(seconds / 3600.0, 1)


def pr_correlation(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """PR outcome metrics, split by whether the author has a Copilot seat.

    Heuristic for "AI-touched": author currently holds a Copilot seat.
    This is the best signal available without per-line attribution.
    """
    start_iso, end_iso, window_days = _window(days=days, start=start, end=end, default_days=30)
    start_dt = f"{start_iso}T00:00:00+00:00"
    end_dt = f"{end_iso}T23:59:59+00:00"
    seat_set = _seat_logins()
    member_filter: set[str] | None = None
    if team:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT login FROM team_members WHERE team_slug = ?", (team,)
            ).fetchall()
        member_filter = {r["login"] for r in rows if r["login"]}

    with db.connect() as conn:
        prs = conn.execute(
            "SELECT repo, number, author, state, created_at, merged_at, closed_at, "
            "additions, deletions, changed_files, commits, review_comments "
            "FROM pull_requests "
            "WHERE (created_at BETWEEN ? AND ?) OR (merged_at BETWEEN ? AND ?)",
            (start_dt, end_dt, start_dt, end_dt),
        ).fetchall()

    def _bucket() -> dict[str, Any]:
        return {
            "pr_count": 0,
            "merged_count": 0,
            "additions": 0,
            "deletions": 0,
            "changed_files": 0,
            "commits": 0,
            "review_comments": 0,
            "cycle_time_hours_sum": 0.0,
            "cycle_time_n": 0,
        }

    ai = _bucket()
    non_ai = _bucket()

    for pr in prs:
        author = pr["author"]
        if member_filter is not None and author not in member_filter:
            continue
        bucket = ai if author in seat_set else non_ai
        bucket["pr_count"] += 1
        bucket["additions"] += pr["additions"] or 0
        bucket["deletions"] += pr["deletions"] or 0
        bucket["changed_files"] += pr["changed_files"] or 0
        bucket["commits"] += pr["commits"] or 0
        bucket["review_comments"] += pr["review_comments"] or 0
        if pr["merged_at"]:
            bucket["merged_count"] += 1
            created = _parse_iso(pr["created_at"])
            merged = _parse_iso(pr["merged_at"])
            if created and merged and merged >= created:
                bucket["cycle_time_hours_sum"] += (merged - created).total_seconds() / 3600.0
                bucket["cycle_time_n"] += 1

    def _finalize(b: dict[str, Any]) -> dict[str, Any]:
        avg_cycle = (
            b["cycle_time_hours_sum"] / b["cycle_time_n"] if b["cycle_time_n"] else None
        )
        merge_rate = (b["merged_count"] / b["pr_count"]) if b["pr_count"] else 0.0
        return {
            "pr_count": b["pr_count"],
            "merged_count": b["merged_count"],
            "merge_rate": round(merge_rate, 4),
            "additions": b["additions"],
            "deletions": b["deletions"],
            "net_lines": b["additions"] - b["deletions"],
            "changed_files": b["changed_files"],
            "commits": b["commits"],
            "review_comments": b["review_comments"],
            "avg_cycle_time_hours": round(avg_cycle, 1) if avg_cycle is not None else None,
            "avg_pr_size_lines": round(
                (b["additions"] + b["deletions"]) / b["pr_count"], 1
            )
            if b["pr_count"]
            else None,
            "avg_review_comments_per_pr": round(
                b["review_comments"] / b["pr_count"], 2
            )
            if b["pr_count"]
            else None,
        }

    ai_final = _finalize(ai)
    non_ai_final = _finalize(non_ai)
    total_prs = ai_final["pr_count"] + non_ai_final["pr_count"]
    ai_share = (ai_final["pr_count"] / total_prs) if total_prs else 0.0

    cycle_delta = None
    if (
        ai_final["avg_cycle_time_hours"] is not None
        and non_ai_final["avg_cycle_time_hours"] is not None
    ):
        cycle_delta = round(
            ai_final["avg_cycle_time_hours"] - non_ai_final["avg_cycle_time_hours"], 1
        )

    return {
        "window_start": start_iso,
        "window_end": end_iso,
        "window_days": window_days,
        "team": team,
        "total_prs": total_prs,
        "ai_authored_share": round(ai_share, 4),
        "ai_authored": ai_final,
        "non_ai_authored": non_ai_final,
        "ai_minus_non_ai_cycle_hours": cycle_delta,
    }


def power_user_concentration(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Distribution of PR activity across users.

    Returns top-10% share, Gini-ish concentration, and a per-user
    bucket count. PR-derived because per-user Copilot acceptance data
    is not exposed by the API.
    """
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    start_dt = f"{start_iso}T00:00:00+00:00"
    end_dt = f"{end_iso}T23:59:59+00:00"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT author, COUNT(*) AS prs, SUM(additions) AS adds, SUM(deletions) AS dels "
            "FROM pull_requests "
            "WHERE (created_at BETWEEN ? AND ?) OR (merged_at BETWEEN ? AND ?) "
            "GROUP BY author",
            (start_dt, end_dt, start_dt, end_dt),
        ).fetchall()
        seat_logins = _seat_logins()
        member_filter: set[str] | None = None
        if team:
            mrows = conn.execute(
                "SELECT login FROM team_members WHERE team_slug = ?", (team,)
            ).fetchall()
            member_filter = {r["login"] for r in mrows if r["login"]}

    users: list[dict[str, Any]] = []
    for r in rows:
        author = r["author"]
        if not author:
            continue
        if member_filter is not None and author not in member_filter:
            continue
        users.append(
            {
                "login": author,
                "prs": r["prs"] or 0,
                "additions": r["adds"] or 0,
                "deletions": r["dels"] or 0,
                "has_seat": author in seat_logins,
            }
        )
    users.sort(key=lambda u: u["prs"], reverse=True)
    total_prs = sum(u["prs"] for u in users)
    n = len(users)
    top10_n = max(1, n // 10) if n else 0
    top10_prs = sum(u["prs"] for u in users[:top10_n])
    top10_share = (top10_prs / total_prs) if total_prs else 0.0
    median_prs = users[n // 2]["prs"] if n else 0

    return {
        "window_start": start_iso,
        "window_end": end_iso,
        "team": team,
        "active_authors": n,
        "total_prs": total_prs,
        "top_10pct_share": round(top10_share, 4),
        "median_prs_per_user": median_prs,
        "top_users": users[:10],
    }


# ---------------------------------------------------------------------------
# Per-team and per-user detail views
# ---------------------------------------------------------------------------


def teams_list() -> list[dict[str, Any]]:
    """List every team slug we have any data for (metrics or membership)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT team_slug FROM daily_team_metrics "
            "UNION SELECT team_slug FROM team_members ORDER BY team_slug"
        ).fetchall()
    return [{"team": r["team_slug"]} for r in rows if r["team_slug"]]


def team_detail(
    team_slug: str,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Detail view for one team: metrics + members + PR correlation + cost share."""
    start_iso, end_iso, window_days = _window(days=days, start=start, end=end, default_days=30)
    with db.connect() as conn:
        member_rows = conn.execute(
            "SELECT login FROM team_members WHERE team_slug = ?", (team_slug,)
        ).fetchall()
        team_day_rows = conn.execute(
            "SELECT date, total_active_users, total_engaged_users, raw_json "
            "FROM daily_team_metrics WHERE team_slug = ? AND date BETWEEN ? AND ? "
            "ORDER BY date ASC",
            (team_slug, start_iso, end_iso),
        ).fetchall()
        lang_rows = conn.execute(
            "SELECT language, SUM(acceptances) AS acc, SUM(suggestions) AS sug, "
            "SUM(lines_accepted) AS la, SUM(lines_suggested) AS ls "
            "FROM daily_team_language_metrics "
            "WHERE team_slug = ? AND date BETWEEN ? AND ? "
            "GROUP BY language ORDER BY acc DESC",
            (team_slug, start_iso, end_iso),
        ).fetchall()

    daily: list[dict[str, Any]] = []
    sug = acc = la = ls = 0
    for row in team_day_rows:
        sums = _sum_day(json.loads(row["raw_json"]))
        sug += sums["suggestions"]
        acc += sums["acceptances"]
        la += sums["lines_accepted"]
        ls += sums["lines_suggested"]
        daily.append(
            {
                "date": row["date"],
                "active_users": row["total_active_users"] or 0,
                "engaged_users": row["total_engaged_users"] or 0,
                "suggestions": sums["suggestions"],
                "acceptances": sums["acceptances"],
                "lines_accepted": sums["lines_accepted"],
                "acceptance_rate": round(
                    (sums["acceptances"] / sums["suggestions"]) if sums["suggestions"] else 0.0, 4
                ),
            }
        )

    member_logins = [r["login"] for r in member_rows]
    # Build the team view by aggregating per-user data (seat activity, PRs,
    # billing) over the membership — the GitHub team-metrics endpoint is
    # unavailable for enterprise-managed orgs, so this is the primary source.
    rollup = _team_member_rollup(member_logins, start_iso, end_iso)
    activity = rollup["summary"]
    members_with_seats = activity["members_with_seats"]
    # Team cost is the actual Copilot consumption attributed to its members
    # over the window; the monthly figure is a 30-day run-rate.
    window_cost = activity["window_cost_usd"]
    monthly_team_cost = round(window_cost * (30.0 / window_days), 2) if window_days else 0.0

    # Per-day team activity derived from member PR authorship (user data),
    # since per-team Copilot daily metrics are unavailable.
    activity_daily = _team_activity_daily(member_logins, start_iso, end_iso)

    return {
        "team": team_slug,
        "window_start": start_iso,
        "window_end": end_iso,
        "window_days": window_days,
        "data_source": "user_aggregation",
        "members_total": len(member_logins),
        "members_with_seats": members_with_seats,
        "monthly_cost_usd": round(monthly_team_cost, 2),
        "window_cost_usd": window_cost,
        "activity": activity,
        "member_activity": rollup["members"],
        "activity_daily": activity_daily,
        "totals": {
            "suggestions": sug,
            "acceptances": acc,
            "lines_suggested": ls,
            "lines_accepted": la,
            "acceptance_rate": round((acc / sug) if sug else 0.0, 4),
            "hours_saved": round((acc * settings.minutes_saved_per_acceptance) / 60.0, 1),
        },
        "daily": daily,
        "languages": [dict(r) for r in lang_rows],
        "models": model_breakdown(start=start_iso, end=end_iso, team=team_slug),
        "chat_vs_inline": chat_vs_inline(start=start_iso, end=end_iso, team=team_slug),
        "pr_correlation": pr_correlation(start=start_iso, end=end_iso, team=team_slug),
        "ai_credits": ai_credits_for_team(team_slug, start=start_iso, end=end_iso),
        "members": member_logins,
    }


def _team_activity_daily(
    members: list[str],
    start_iso: str,
    end_iso: str,
) -> list[dict[str, Any]]:
    """Per-day PR activity for a team's members over the window (user-derived)."""
    member_set = {m for m in members if m}
    if not member_set:
        return []
    start_dt = f"{start_iso}T00:00:00+00:00"
    end_dt = f"{end_iso}T23:59:59+00:00"
    placeholders = ",".join("?" for _ in member_set)
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT author, created_at, merged_at, additions, deletions "
            f"FROM pull_requests WHERE author IN ({placeholders}) "
            f"AND ((created_at BETWEEN ? AND ?) OR (merged_at BETWEEN ? AND ?))",
            (*sorted(member_set), start_dt, end_dt, start_dt, end_dt),
        ).fetchall()
    daily: dict[str, dict[str, int]] = defaultdict(
        lambda: {"prs": 0, "merged_prs": 0, "net_lines": 0}
    )
    for r in rows:
        bucket_date = (r["merged_at"] or r["created_at"] or "")[:10]
        if not bucket_date:
            continue
        bucket = daily[bucket_date]
        bucket["prs"] += 1
        if r["merged_at"]:
            bucket["merged_prs"] += 1
        bucket["net_lines"] += (r["additions"] or 0) - (r["deletions"] or 0)
    return [{"date": d, **vals} for d, vals in sorted(daily.items())]


def users_list(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """List all seat-holders + PR activity rollup for the window.

    Note: per-user Copilot metrics (model, LOC suggested/accepted,
    language, interaction count) are not exposed by the GitHub API.
    We surface seat lifecycle + PR activity per user as the best
    available per-user signal.
    """
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    start_dt = f"{start_iso}T00:00:00+00:00"
    end_dt = f"{end_iso}T23:59:59+00:00"
    with db.connect() as conn:
        seat_rows = conn.execute(
            "SELECT login, assigning_team, created_at, last_activity_at, last_activity_editor "
            "FROM seats"
        ).fetchall()
        pr_rows = conn.execute(
            "SELECT lower(author) AS author, COUNT(*) AS prs, SUM(additions) AS adds, SUM(deletions) AS dels, "
            "SUM(CASE WHEN merged_at IS NOT NULL THEN 1 ELSE 0 END) AS merged "
            "FROM pull_requests "
            "WHERE (created_at BETWEEN ? AND ?) OR (merged_at BETWEEN ? AND ?) "
            "GROUP BY lower(author)",
            (start_dt, end_dt, start_dt, end_dt),
        ).fetchall()
        credit_rows = conn.execute(
            "SELECT lower(login) AS login, SUM(quantity) AS qty "
            "FROM billing_usage WHERE date BETWEEN ? AND ? "
            f"{_BILLING_MIN_DATE_SQL} "
            "AND lower(product) LIKE '%copilot%' "
            f"AND {_COPILOT_BILLABLE_SKU_SQL} "
            f"{_billing_dedup_sql(conn, start_iso, end_iso)} "
            "AND login != '' "
            "GROUP BY lower(login)",
            (start_iso, end_iso),
        ).fetchall()
    credits_by_login: dict[str, float] = {
        r["login"]: round(float(r["qty"] or 0), 2) for r in credit_rows
    }
    pr_by_login: dict[str, dict[str, Any]] = {
        r["author"]: {
            "prs": r["prs"] or 0,
            "merged": r["merged"] or 0,
            "additions": r["adds"] or 0,
            "deletions": r["dels"] or 0,
        }
        for r in pr_rows
        if r["author"]
    }

    now = datetime.now(UTC)
    stale_cut = now - timedelta(days=settings.stale_seat_days)
    out: list[dict[str, Any]] = []
    for row in seat_rows:
        last_active = _parse_iso(row["last_activity_at"])
        if last_active is None:
            status = "never_used"
            days_inactive = None
        elif last_active >= stale_cut:
            status = "active"
            days_inactive = (now - last_active).days
        else:
            status = "stale"
            days_inactive = (now - last_active).days
        login_lower = (row["login"] or "").lower()
        pr_data = pr_by_login.get(login_lower, {"prs": 0, "merged": 0, "additions": 0, "deletions": 0})
        out.append(
            {
                "login": row["login"],
                "team": row["assigning_team"],
                "created_at": row["created_at"],
                "last_activity_at": row["last_activity_at"],
                "last_activity_editor": row["last_activity_editor"],
                "status": status,
                "days_inactive": days_inactive,
                "prs": pr_data["prs"],
                "merged_prs": pr_data["merged"],
                "additions": pr_data["additions"],
                "deletions": pr_data["deletions"],
                "net_lines": pr_data["additions"] - pr_data["deletions"],
                "ai_credits": credits_by_login.get(login_lower, 0.0),
            }
        )
    out.sort(key=lambda u: u["prs"], reverse=True)
    return out


def user_detail(
    login: str,
    days: int = 90,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Detail view for one user: seat info + per-day PR activity."""
    start_iso, end_iso, window_days = _window(days=days, start=start, end=end, default_days=90)
    start_dt = f"{start_iso}T00:00:00+00:00"
    end_dt = f"{end_iso}T23:59:59+00:00"
    with db.connect() as conn:
        seat = conn.execute(
            "SELECT login, assigning_team, created_at, updated_at, last_activity_at, "
            "last_activity_editor, pending_cancellation_date, plan_type "
            "FROM seats WHERE login = ?",
            (login,),
        ).fetchone()
        prs = conn.execute(
            "SELECT repo, number, state, created_at, merged_at, additions, deletions, "
            "changed_files, review_comments, title "
            "FROM pull_requests "
            "WHERE author = ? AND ((created_at BETWEEN ? AND ?) OR (merged_at BETWEEN ? AND ?)) "
            "ORDER BY COALESCE(merged_at, created_at) DESC",
            (login, start_dt, end_dt, start_dt, end_dt),
        ).fetchall()
        teams = conn.execute(
            "SELECT team_slug FROM team_members WHERE login = ?", (login,)
        ).fetchall()

    daily: dict[str, dict[str, int]] = defaultdict(
        lambda: {"prs": 0, "merged": 0, "additions": 0, "deletions": 0}
    )
    pr_rows: list[dict[str, Any]] = []
    additions_total = 0
    deletions_total = 0
    cycle_hours: list[float] = []
    for r in prs:
        bucket_date = (r["merged_at"] or r["created_at"] or "")[:10]
        bucket = daily[bucket_date]
        bucket["prs"] += 1
        if r["merged_at"]:
            bucket["merged"] += 1
            created = _parse_iso(r["created_at"])
            merged = _parse_iso(r["merged_at"])
            if created and merged:
                cycle_hours.append((merged - created).total_seconds() / 3600.0)
        bucket["additions"] += r["additions"] or 0
        bucket["deletions"] += r["deletions"] or 0
        additions_total += r["additions"] or 0
        deletions_total += r["deletions"] or 0
        pr_rows.append(dict(r))

    avg_cycle = round(sum(cycle_hours) / len(cycle_hours), 1) if cycle_hours else None
    # Per-user cost is this user's actual Copilot consumption over the window.
    cost_share = _consumption_cost_usd(start_iso, end_iso, logins={login})
    premium = ai_credits_for_user(login, start=start_iso, end=end_iso)

    return {
        "login": login,
        "window_start": start_iso,
        "window_end": end_iso,
        "window_days": window_days,
        "has_seat": seat is not None,
        "seat": dict(seat) if seat else None,
        "teams": [t["team_slug"] for t in teams],
        "totals": {
            "prs": len(pr_rows),
            "merged": sum(1 for p in pr_rows if p.get("merged_at")),
            "additions": additions_total,
            "deletions": deletions_total,
            "net_lines": additions_total - deletions_total,
            "avg_cycle_time_hours": avg_cycle,
            "window_cost_usd": cost_share,
            "ai_credits": premium["ai_credits"],
            "ai_credit_cost_usd": premium["ai_credit_cost_usd"],
        },
        "daily": [
            {"date": d, **vals}
            for d, vals in sorted(daily.items())
        ],
        "recent_prs": pr_rows[:50],
        "pr_ingest_enabled": settings.pr_ingest_enabled,
        "ai_credits": premium,
        "per_user_copilot_metrics_available": False,
        "per_user_copilot_note": (
            "GitHub does not expose per-user Copilot acceptance/model/language "
            "metrics. Only seat-level activity timestamp + editor and "
            "billing-derived AI-credit counts are available."
        ),
        "tokens_available": False,
        "tokens_note": TOKENS_NOTE,
    }


def quality_summary(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """One-shot rollup for the Quality tab."""
    return {
        "chat_vs_inline": chat_vs_inline(days=days, start=start, end=end),
        "model_breakdown": model_breakdown(days=days, start=start, end=end),
        "power_users": power_user_concentration(days=days, start=start, end=end),
        "cohort_ramp": cohort_ramp(),
        "pr_correlation": pr_correlation(days=days, start=start, end=end),
        "ai_credits": ai_credits_summary(days=days, start=start, end=end),
    }


# ---------------------------------------------------------------------------
# Billing usage — AI credits + tokens (token data NOT exposed by GitHub)
# ---------------------------------------------------------------------------


TOKENS_NOTE = (
    "GitHub does not expose per-user or per-org token counts for Copilot. "
    "Only AI-credit counts (and other billed SKUs) are available via "
    "the enhanced billing API."
)


def _is_legacy_premium_request_sku(sku: str | None) -> bool:
    """Return True if the SKU represents a legacy Copilot premium request."""
    if not sku:
        return False
    s = sku.lower()
    return "premium" in s and "request" in s


# SQL predicate matching billable Copilot usage SKUs: legacy premium requests
# plus AI-credit SKUs (e.g. ``copilot_ai_credit``) surfaced by CSV billing
# reports. Kept in one place so every rollup query stays consistent.
_COPILOT_BILLABLE_SKU_SQL = (
    "((lower(sku) LIKE '%premium%' AND lower(sku) LIKE '%request%') "
    "OR lower(sku) LIKE '%ai_credit%' OR lower(sku) LIKE '%ai credit%')"
)

# Query-time guard so rows imported before billing launch never leak into
# rollups, even if legacy data still exists in the DB.
_BILLING_MIN_DATE_SQL = f"AND date >= '{BILLING_MIN_DATE}'"


def _billing_dedup_sql(
    conn: Any, start_iso: str, end_iso: str,
) -> str:
    """Return a SQL fragment that prevents double-counting billing rows.

    When both the AI-usage CSV (per-user/per-model detail) and the general
    usage CSV (monthly aggregates) have been imported, their rows overlap.
    This helper returns a conditional filter:

    * **AI-credit SKUs** — keep only model-attributed rows (``model != ''``).
    * **Non-AI-credit SKUs** (licenses) — keep only login-attributed rows
      (``login != ''``), excluding the general-CSV monthly aggregate.

    Returns ``""`` when only non-detailed data exists (general CSV only).
    """
    has = conn.execute(
        "SELECT 1 FROM billing_usage WHERE date BETWEEN ? AND ? "
        f"{_BILLING_MIN_DATE_SQL} "
        "AND lower(product) LIKE '%copilot%' "
        f"AND {_COPILOT_BILLABLE_SKU_SQL} "
        "AND model != '' LIMIT 1",
        (start_iso, end_iso),
    ).fetchone()
    if has:
        return (
            f"AND (({_COPILOT_BILLABLE_SKU_SQL} AND model != '') "
            f"OR (NOT ({_COPILOT_BILLABLE_SKU_SQL}) AND login != ''))"
        )
    return ""


def _is_copilot_billable_sku(sku: str | None) -> bool:
    """Return True for billable Copilot SKUs (legacy premium requests + AI credits)."""
    if not sku:
        return False
    s = sku.lower()
    if "premium" in s and "request" in s:
        return True
    return "ai_credit" in s or "ai credit" in s


def _normalize_billing_label(value: str | None) -> str:
    """Normalize free-form billing labels for stable grouping."""
    if not value:
        return ""
    s = value.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _canonical_billable_sku(sku: str | None) -> str:
    """Map billable Copilot SKU variants to canonical names."""
    s = _normalize_billing_label(sku)
    if "premium" in s and "request" in s:
        return "copilot_premium_request"
    if "ai_credit" in s:
        return "copilot_ai_credit"
    return s or "unknown"


def _canonical_copilot_product(product: str | None) -> str:
    """Map Copilot product label variants to one canonical value."""
    s = _normalize_billing_label(product)
    if "copilot" in s:
        return "copilot"
    return s or "unknown"


def _model_from_sku(sku: str | None) -> str:
    """Extract a model name from a billing SKU.

    GitHub's enhanced-billing SKUs for legacy premium requests follow the
    shape ``"Copilot Premium Request - <model>"``. Anything past the last
    ``-`` is treated as the model name; unparseable or model-less SKUs
    become ``"unspecified"``.
    """
    if not sku:
        return "unspecified"
    parts = [p.strip() for p in sku.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return parts[-1]
    # Fall back: dash without spaces (e.g. "Copilot Premium Request-GPT-4o")
    if "-" in sku:
        tail = sku.rsplit("-", 1)[-1].strip()
        if tail and tail.lower() not in {"request", "premium"}:
            return tail
    return "unspecified"


# Regex: claude-{...}-{variant} where variant is a known Claude model tier.
_CLAUDE_REORDER_RE = re.compile(r"^claude-(.+?)-(sonnet|opus|haiku)(.*)$")
# Trailing version hyphens: -3-5 → -3.5 at end of string.
_TRAILING_VERSION_RE = re.compile(r"-(\d+)-(\d+)$")
_GPT_HIGH_RE = re.compile(r"(^|-)gpt-5\.(4|5)($|-)")
_GPT_LOW_RE = re.compile(r"(^|-)gpt-5\.(2|3)($|-)")

# Display strings returned with ``ai_credits_summary`` to keep frontend labels
# aligned with backend model-tier rules.
HIGH_TIER_LABELS = ["Opus", "GPT-5.4/5.5", "Gemini Pro"]
LOW_TIER_LABELS = ["Haiku", "Flash", "Auto:*", "Sonnet", "GPT-5.2/5.3", "Code Review"]


def _normalize_model_name(name: str) -> str:
    """Normalize a model name to a canonical lowercase-hyphenated form.

    Handles the inconsistency between GitHub data sources:
    - Metrics API: ``"claude-3.5-sonnet"`` (version before variant)
    - Billing CSV: ``"Claude Sonnet 3.5"`` (Title Case, variant before version)
    - SKU-derived: ``"Claude Sonnet 3.5"`` (from ``_model_from_sku``)

    Canonical output: ``"claude-sonnet-3.5"``, ``"gpt-4o"``, ``"o3-mini"``.
    """
    if not name:
        return "unknown"
    # Lowercase, strip, replace spaces/underscores with hyphens.
    s = name.strip().lower().replace(" ", "-").replace("_", "-")
    # Collapse multiple hyphens.
    s = re.sub(r"-{2,}", "-", s)
    # Reorder claude-{version}-{variant} → claude-{variant}-{version}.
    # Only triggers when a known variant (sonnet/opus/haiku) appears AFTER
    # the version segment (e.g., "claude-3.5-sonnet" → "claude-sonnet-3.5").
    m = _CLAUDE_REORDER_RE.match(s)
    if m:
        s = f"claude-{m.group(2)}-{m.group(1)}{m.group(3)}"
    # Normalize trailing version hyphens: "claude-sonnet-3-5" → "claude-sonnet-3.5"
    s = _TRAILING_VERSION_RE.sub(r"-\1.\2", s)
    return s


def _model_tier(name: str) -> str | None:
    """Classify model into ``high`` / ``low`` tiers for balanced-user analysis.

    High-tier takes precedence over the generic ``Auto:*`` low-tier rule so
    labels such as ``Auto: GPT-5.4`` still count as high-tier usage.
    """
    normalized = _normalize_model_name(name)
    if "opus" in normalized:
        return "high"
    if _GPT_HIGH_RE.search(normalized):
        return "high"
    if "gemini" in normalized and "pro" in normalized:
        return "high"

    if "haiku" in normalized:
        return "low"
    if "flash" in normalized:
        return "low"
    if "sonnet" in normalized:
        return "low"
    if "code-review" in normalized:
        return "low"
    if _GPT_LOW_RE.search(normalized):
        return "low"
    if normalized.startswith("auto:") or normalized.startswith("auto-"):
        return "low"
    return None


def ai_credits_summary(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Aggregate Copilot AI-credit usage at the org level.

    Returns totals, per-SKU breakdown, and top users for the window.
    Surfaces the token-availability note alongside the data.
    """
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    with db.connect() as conn:
        dedup = _billing_dedup_sql(conn, start_iso, end_iso)
        sku_rows = conn.execute(
            "SELECT sku, product, SUM(quantity) AS qty, "
            "SUM(gross_amount_usd) AS gross, SUM(net_amount_usd) AS net "
            "FROM billing_usage WHERE date BETWEEN ? AND ? "
            f"{_BILLING_MIN_DATE_SQL} "
            "AND lower(product) LIKE '%copilot%' "
            f"AND {_COPILOT_BILLABLE_SKU_SQL} "
            f"{dedup} "
            "GROUP BY sku, product",
            (start_iso, end_iso),
        ).fetchall()
        per_user_rows = conn.execute(
            "SELECT login, SUM(quantity) AS qty, "
            "SUM(gross_amount_usd) AS gross, SUM(net_amount_usd) AS net "
            "FROM billing_usage WHERE date BETWEEN ? AND ? "
            f"{_BILLING_MIN_DATE_SQL} "
            "AND lower(product) LIKE '%copilot%' "
            f"AND {_COPILOT_BILLABLE_SKU_SQL} "
            f"{dedup} "
            "AND login != '' "
            "GROUP BY login ORDER BY qty DESC LIMIT 25",
            (start_iso, end_iso),
        ).fetchall()
        per_model_user_rows = conn.execute(
            "SELECT model, sku, login, SUM(quantity) AS qty "
            "FROM billing_usage WHERE date BETWEEN ? AND ? "
            f"{_BILLING_MIN_DATE_SQL} "
            "AND lower(product) LIKE '%copilot%' "
            f"AND {_COPILOT_BILLABLE_SKU_SQL} "
            f"{dedup} "
            "AND login != '' "
            "GROUP BY model, sku, login",
            (start_iso, end_iso),
        ).fetchall()
        totals_row = conn.execute(
            "SELECT SUM(quantity) AS qty, SUM(net_amount_usd) AS net "
            "FROM billing_usage WHERE date BETWEEN ? AND ? "
            f"{_BILLING_MIN_DATE_SQL} "
            "AND lower(product) LIKE '%copilot%' "
            f"AND {_COPILOT_BILLABLE_SKU_SQL} "
            f"{dedup}",
            (start_iso, end_iso),
        ).fetchone()
        has_any_row = conn.execute(
            "SELECT COUNT(*) AS n FROM billing_usage "
            "WHERE date >= ? AND lower(product) LIKE '%copilot%'",
            (BILLING_MIN_DATE,)
        ).fetchone()

    sku_totals: dict[tuple[str, str], dict[str, float]] = {}
    for r in sku_rows:
        sku_key = _canonical_billable_sku(r["sku"])
        product_key = _canonical_copilot_product(r["product"])
        bucket = sku_totals.setdefault(
            (sku_key, product_key),
            {"quantity": 0.0, "gross_amount_usd": 0.0, "net_amount_usd": 0.0},
        )
        bucket["quantity"] += float(r["qty"] or 0)
        bucket["gross_amount_usd"] += float(r["gross"] or 0)
        bucket["net_amount_usd"] += float(r["net"] or 0)

    skus = [
        {
            "sku": sku,
            "product": product,
            "quantity": vals["quantity"],
            "gross_amount_usd": round(vals["gross_amount_usd"], 2),
            "net_amount_usd": round(vals["net_amount_usd"], 2),
        }
        for (sku, product), vals in sorted(
            sku_totals.items(),
            key=lambda item: item[1]["quantity"],
            reverse=True,
        )
    ]
    top_users = [
        {
            "login": r["login"],
            "ai_credits": float(r["qty"] or 0),
            "gross_amount_usd": round(float(r["gross"] or 0), 2),
            "net_amount_usd": round(float(r["net"] or 0), 2),
        }
        for r in per_user_rows
    ]

    # Build model -> top users from billing usage. Grouping key is normalized
    # so variants across data sources roll up together; display label preserves
    # human-friendly model strings from billing rows when available.
    model_totals: dict[str, float] = defaultdict(float)
    model_user_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    model_display: dict[str, str] = {}
    user_totals: dict[str, float] = defaultdict(float)
    user_high_totals: dict[str, float] = defaultdict(float)
    user_low_totals: dict[str, float] = defaultdict(float)
    user_models: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in per_model_user_rows:
        raw_model = (row["model"] or _model_from_sku(row["sku"]) or "").strip()
        model_key = _normalize_model_name(raw_model)
        if model_key in {"unspecified", "unknown"}:
            continue
        qty = float(row["qty"] or 0)
        if qty <= 0:
            continue
        model_totals[model_key] += qty
        login = (row["login"] or "").strip()
        if login:
            model_user_totals[model_key][login] += qty
            user_totals[login] += qty
            tier = _model_tier(raw_model)
            if tier == "high":
                user_high_totals[login] += qty
            elif tier == "low":
                user_low_totals[login] += qty
            if tier:
                per_user_model = user_models[login].setdefault(
                    model_key,
                    {"model": raw_model or model_key, "quantity": 0.0, "tier": tier},
                )
                per_user_model["quantity"] += qty
        if model_key not in model_display and raw_model and raw_model.lower() != "unspecified":
            model_display[model_key] = raw_model

    top_users_per_model: list[dict[str, Any]] = []
    for model_key, total in sorted(model_totals.items(), key=lambda kv: kv[1], reverse=True):
        per_user = sorted(
            model_user_totals[model_key].items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:5]
        if total <= 0:
            continue
        top_users_per_model.append(
            {
                "model": model_display.get(model_key, model_key),
                "total_ai_credits": round(total, 2),
                "top_users": [
                    {
                        "login": login,
                        "ai_credits": round(qty, 2),
                        "percentage": round((qty / total) * 100.0, 2),
                    }
                    for login, qty in per_user
                ],
            }
        )

    balanced_threshold = 20.0
    balanced_users: list[dict[str, Any]] = []
    for login, total in user_totals.items():
        if total <= 0:
            continue
        high_pct = (user_high_totals.get(login, 0.0) / total) * 100.0
        low_pct = (user_low_totals.get(login, 0.0) / total) * 100.0
        if high_pct < balanced_threshold or low_pct < balanced_threshold:
            continue

        model_rows = sorted(
            user_models.get(login, {}).values(),
            key=lambda row: row["quantity"],
            reverse=True,
        )
        balanced_users.append(
            {
                "login": login,
                "total_ai_credits": round(total, 2),
                "high_pct": round(high_pct, 2),
                "low_pct": round(low_pct, 2),
                "models": [
                    {
                        "model": row["model"],
                        "quantity": round(row["quantity"], 2),
                        "pct": round((row["quantity"] / total) * 100.0, 2),
                        "tier": row["tier"],
                    }
                    for row in model_rows
                ],
            }
        )
    balanced_users.sort(key=lambda row: row["total_ai_credits"], reverse=True)

    # Headline totals from the ai_credit/usage aggregate endpoint (fresher
    # than per-day row sums).  Only include when the stored period covers the
    # query window's month.
    headline_qty: float | None = None
    headline_net: float | None = None
    headline_gross: float | None = None
    raw_qty = db.get_meta("ai_credit_headline_qty")
    if raw_qty is not None:
        headline_qty = float(raw_qty)
        raw_net = db.get_meta("ai_credit_headline_net_usd")
        headline_net = float(raw_net) if raw_net else None
        raw_gross = db.get_meta("ai_credit_headline_gross_usd")
        headline_gross = float(raw_gross) if raw_gross else None

    return {
        "window_start": start_iso,
        "window_end": end_iso,
        "available": (has_any_row["n"] or 0) > 0,
        "total_ai_credits": float(totals_row["qty"] or 0) if totals_row else 0.0,
        "total_ai_credit_cost_usd": round(
            float(totals_row["net"] or 0) if totals_row else 0.0, 2
        ),
        "headline_ai_credits": headline_qty,
        "headline_ai_credit_cost_usd": round(headline_net, 2) if headline_net is not None else None,
        "headline_ai_credit_gross_usd": round(headline_gross, 2) if headline_gross is not None else None,
        "headline_fetched_at": db.get_meta("ai_credit_headline_at"),
        "skus": skus,
        "top_users": top_users,
        "top_users_per_model": top_users_per_model,
        "balanced_user_threshold_pct": balanced_threshold,
        "balanced_user_high_tiers": HIGH_TIER_LABELS,
        "balanced_user_low_tiers": LOW_TIER_LABELS,
        "balanced_users": balanced_users,
        "tokens_available": False,
        "tokens_note": TOKENS_NOTE,
    }


def ai_credits_for_user(
    login: str,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Per-user AI-credit usage over a window."""
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    with db.connect() as conn:
        try:
            dedup = _billing_dedup_sql(conn, start_iso, end_iso)
            rows = conn.execute(
                "SELECT date, sku, model, SUM(quantity) AS qty, SUM(net_amount_usd) AS net "
                "FROM billing_usage WHERE date BETWEEN ? AND ? "
                f"{_BILLING_MIN_DATE_SQL} "
                "AND lower(login) = lower(?) "
                "AND lower(product) LIKE '%copilot%' "
                f"{dedup} "
                "GROUP BY date, sku, model ORDER BY date ASC, sku ASC",
                (start_iso, end_iso, login),
            ).fetchall()
        except Exception:
            rows = []
    total_qty = 0.0
    total_net = 0.0
    by_sku: dict[str, dict[str, float]] = {}
    by_model: dict[str, dict[str, float]] = {}
    daily: dict[str, float] = {}
    for r in rows:
        qty = float(r["qty"] or 0)
        net = float(r["net"] or 0)
        if _is_copilot_billable_sku(r["sku"]):
            total_qty += qty
            total_net += net
            daily[r["date"]] = daily.get(r["date"], 0.0) + qty
            # Prefer the stored model column (AI-credit CSV rows); fall back to
            # parsing the model out of legacy premium-request SKU strings.
            model = r["model"] or _model_from_sku(r["sku"])
            if model != "unspecified":
                mbucket = by_model.setdefault(
                    model, {"quantity": 0.0, "net_amount_usd": 0.0}
                )
                mbucket["quantity"] += qty
                mbucket["net_amount_usd"] += net
        bucket = by_sku.setdefault(r["sku"], {"quantity": 0.0, "net_amount_usd": 0.0})
        bucket["quantity"] += qty
        bucket["net_amount_usd"] += net
    return {
        "login": login,
        "window_start": start_iso,
        "window_end": end_iso,
        "ai_credits": round(total_qty, 2),
        "ai_credit_cost_usd": round(total_net, 2),
        "by_sku": [
            {"sku": s, "quantity": round(v["quantity"], 2), "net_amount_usd": round(v["net_amount_usd"], 2)}
            for s, v in sorted(by_sku.items(), key=lambda kv: -kv[1]["quantity"])
        ],
        "by_model": [
            {
                "model": m,
                "ai_credits": round(v["quantity"], 2),
                "net_amount_usd": round(v["net_amount_usd"], 2),
                "share": round(v["quantity"] / total_qty, 4) if total_qty > 0 else 0.0,
            }
            for m, v in sorted(by_model.items(), key=lambda kv: -kv[1]["quantity"])
        ],
        "daily_ai_credits": [
            {"date": d, "ai_credits": round(q, 2)}
            for d, q in sorted(daily.items())
        ],
        "tokens_available": False,
        "tokens_note": TOKENS_NOTE,
    }


def ai_credits_for_team(
    team_slug: str,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Aggregate AI-credit usage for a team by summing its members."""
    start_iso, end_iso, _ = _window(days=days, start=start, end=end, default_days=30)
    with db.connect() as conn:
        member_rows = conn.execute(
            "SELECT login FROM team_members WHERE team_slug = ?", (team_slug,)
        ).fetchall()
        members = [r["login"] for r in member_rows if r["login"]]
        if not members:
            return {
                "team": team_slug,
                "window_start": start_iso,
                "window_end": end_iso,
                "ai_credits": 0.0,
                "ai_credit_cost_usd": 0.0,
                "top_users": [],
                "members": 0,
                "tokens_available": False,
                "tokens_note": TOKENS_NOTE,
            }
        placeholders = ",".join("?" for _ in members)
        rows = conn.execute(
            f"SELECT login, SUM(quantity) AS qty, SUM(net_amount_usd) AS net "
            f"FROM billing_usage WHERE date BETWEEN ? AND ? "
            f"{_BILLING_MIN_DATE_SQL} "
            f"AND lower(product) LIKE '%copilot%' "
            f"AND {_COPILOT_BILLABLE_SKU_SQL} "
            f"{_billing_dedup_sql(conn, start_iso, end_iso)} "
            f"AND lower(login) IN ({placeholders}) "
            f"GROUP BY login ORDER BY qty DESC",
            (start_iso, end_iso, *[m.lower() for m in members]),
        ).fetchall()
    top_users = [
        {
            "login": r["login"],
            "ai_credits": float(r["qty"] or 0),
            "net_amount_usd": round(float(r["net"] or 0), 2),
        }
        for r in rows
    ]
    total_qty = sum(u["ai_credits"] for u in top_users)
    total_net = sum(u["net_amount_usd"] for u in top_users)
    return {
        "team": team_slug,
        "window_start": start_iso,
        "window_end": end_iso,
        "members": len(members),
        "ai_credits": round(total_qty, 2),
        "ai_credit_cost_usd": round(total_net, 2),
        "top_users": top_users,
        "tokens_available": False,
        "tokens_note": TOKENS_NOTE,
    }
