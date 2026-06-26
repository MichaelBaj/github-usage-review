"""Pull Copilot metrics + seats from GitHub and persist into SQLite.

The Copilot metrics API returns up to the last 28 days as an array of
day records. We upsert every day we receive so re-runs are idempotent
and the local store grows beyond 28 days over time toward the 90-day
exec view.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from . import db
from .config import BILLING_MIN_DATE, settings
from .github_client import GitHubClient

log = logging.getLogger(__name__)


async def assert_snapshot_permissions() -> None:
    """Validate token/org access before running expensive snapshot ingestion."""
    async with GitHubClient() as gh:
        await gh.assert_snapshot_permissions(include_pr_checks=settings.pr_ingest_enabled)


def _flatten_languages(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract per-(language, editor) aggregates from a metrics day record."""
    rows: list[dict[str, Any]] = []
    code = day.get("copilot_ide_code_completions") or {}
    for editor in code.get("editors", []) or []:
        editor_name = editor.get("name", "unknown")
        for model in editor.get("models", []) or []:
            for lang in model.get("languages", []) or []:
                rows.append(
                    {
                        "language": lang.get("name", "unknown"),
                        "editor": editor_name,
                        "suggestions": lang.get("total_code_suggestions", 0) or 0,
                        "acceptances": lang.get("total_code_acceptances", 0) or 0,
                        "lines_suggested": lang.get("total_code_lines_suggested", 0) or 0,
                        "lines_accepted": lang.get("total_code_lines_accepted", 0) or 0,
                        "engaged_users": lang.get("total_engaged_users", 0) or 0,
                    }
                )
    collapsed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["language"], row["editor"])
        if key not in collapsed:
            collapsed[key] = row
            continue
        cur = collapsed[key]
        for field in ("suggestions", "acceptances", "lines_suggested", "lines_accepted", "engaged_users"):
            cur[field] += row[field]
    return list(collapsed.values())


def _flatten_editors(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate per-editor totals including chat events."""
    code = day.get("copilot_ide_code_completions") or {}
    chat = day.get("copilot_ide_chat") or {}

    editor_rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "suggestions": 0,
            "acceptances": 0,
            "lines_suggested": 0,
            "lines_accepted": 0,
            "chat_total_chats": 0,
            "chat_insertion_events": 0,
            "chat_copy_events": 0,
            "engaged_users": 0,
        }
    )

    for editor in code.get("editors", []) or []:
        name = editor.get("name", "unknown")
        row = editor_rows[name]
        row["engaged_users"] = max(row["engaged_users"], editor.get("total_engaged_users", 0) or 0)
        for model in editor.get("models", []) or []:
            for lang in model.get("languages", []) or []:
                row["suggestions"] += lang.get("total_code_suggestions", 0) or 0
                row["acceptances"] += lang.get("total_code_acceptances", 0) or 0
                row["lines_suggested"] += lang.get("total_code_lines_suggested", 0) or 0
                row["lines_accepted"] += lang.get("total_code_lines_accepted", 0) or 0

    for editor in chat.get("editors", []) or []:
        name = editor.get("name", "unknown")
        row = editor_rows[name]
        for model in editor.get("models", []) or []:
            row["chat_total_chats"] += model.get("total_chats", 0) or 0
            row["chat_insertion_events"] += model.get("total_chat_insertion_events", 0) or 0
            row["chat_copy_events"] += model.get("total_chat_copy_events", 0) or 0

    return [{"editor": name, **values} for name, values in editor_rows.items()]


def _flatten_models(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a metrics day into per-(editor, model, is_chat) rows.

    Combines code-completion and chat trees so a single table can drive
    "model usage" charts for code AND chat.
    """
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}

    def _bucket(editor: str, model: str, is_chat: int) -> dict[str, Any]:
        key = (editor, model, is_chat)
        if key not in rows:
            rows[key] = {
                "editor": editor,
                "model": model,
                "is_chat": is_chat,
                "suggestions": 0,
                "acceptances": 0,
                "lines_suggested": 0,
                "lines_accepted": 0,
                "chats": 0,
                "chat_insertions": 0,
                "chat_copies": 0,
                "engaged_users": 0,
            }
        return rows[key]

    code = day.get("copilot_ide_code_completions") or {}
    for editor in code.get("editors", []) or []:
        editor_name = editor.get("name", "unknown")
        for model in editor.get("models", []) or []:
            model_name = model.get("name") or "default"
            bucket = _bucket(editor_name, model_name, 0)
            bucket["engaged_users"] = max(
                bucket["engaged_users"], model.get("total_engaged_users", 0) or 0
            )
            for lang in model.get("languages", []) or []:
                bucket["suggestions"] += lang.get("total_code_suggestions", 0) or 0
                bucket["acceptances"] += lang.get("total_code_acceptances", 0) or 0
                bucket["lines_suggested"] += lang.get("total_code_lines_suggested", 0) or 0
                bucket["lines_accepted"] += lang.get("total_code_lines_accepted", 0) or 0

    chat = day.get("copilot_ide_chat") or {}
    for editor in chat.get("editors", []) or []:
        editor_name = editor.get("name", "unknown")
        for model in editor.get("models", []) or []:
            model_name = model.get("name") or "default"
            bucket = _bucket(editor_name, model_name, 1)
            bucket["engaged_users"] = max(
                bucket["engaged_users"], model.get("total_engaged_users", 0) or 0
            )
            bucket["chats"] += model.get("total_chats", 0) or 0
            bucket["chat_insertions"] += model.get("total_chat_insertion_events", 0) or 0
            bucket["chat_copies"] += model.get("total_chat_copy_events", 0) or 0

    return list(rows.values())


# ---------------------------------------------------------------------------
# Report-format flatteners (2026-03-10 API)
# ---------------------------------------------------------------------------


def _report_flatten_languages(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract per-language aggregates from a report-format day record.

    The new API provides ``totals_by_language_feature`` (language × feature).
    We aggregate across features to produce per-language totals compatible
    with the ``daily_language_metrics`` schema.  The editor dimension is no
    longer available, so we store ``"all"`` as the editor.
    """
    lang_agg: dict[str, dict[str, int]] = {}
    for item in day.get("totals_by_language_feature") or []:
        lang = item.get("language") or "unknown"
        row = lang_agg.setdefault(lang, {
            "suggestions": 0,
            "acceptances": 0,
            "lines_suggested": 0,
            "lines_accepted": 0,
            "engaged_users": 0,
        })
        row["suggestions"] += item.get("code_generation_activity_count") or 0
        row["acceptances"] += item.get("code_acceptance_activity_count") or 0
        row["lines_suggested"] += item.get("loc_suggested_to_add_sum") or 0
        row["lines_accepted"] += item.get("loc_added_sum") or 0
    return [{"language": lang, "editor": "all", **vals} for lang, vals in lang_agg.items()]


def _report_flatten_editors(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract per-editor aggregates from a report-format day.

    Maps ``totals_by_ide`` into the ``daily_editor_metrics`` schema.
    Chat-specific columns (``chat_total_chats``, etc.) are no longer
    available in the new API and default to 0.
    """
    rows: list[dict[str, Any]] = []
    for item in day.get("totals_by_ide") or []:
        rows.append({
            "editor": item.get("ide") or "unknown",
            "suggestions": item.get("code_generation_activity_count") or 0,
            "acceptances": item.get("code_acceptance_activity_count") or 0,
            "lines_suggested": item.get("loc_suggested_to_add_sum") or 0,
            "lines_accepted": item.get("loc_added_sum") or 0,
            "chat_total_chats": 0,
            "chat_insertion_events": 0,
            "chat_copy_events": 0,
            "engaged_users": 0,
        })
    return rows


def _report_flatten_models(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract per-model aggregates from a report-format day.

    The new API provides ``totals_by_model_feature`` (model × feature).
    We map feature names to ``is_chat``: code_completion → 0, everything
    else → 1.  Editor dimension is stored as ``"all"``.
    """
    _CODE_FEATURES = {"code_completion"}
    model_agg: dict[tuple[str, int], dict[str, Any]] = {}
    for item in day.get("totals_by_model_feature") or []:
        model_name = item.get("model") or "unknown"
        feature = item.get("feature") or ""
        is_chat = 0 if feature in _CODE_FEATURES else 1
        key = (model_name, is_chat)
        row = model_agg.setdefault(key, {
            "editor": "all",
            "model": model_name,
            "is_chat": is_chat,
            "suggestions": 0,
            "acceptances": 0,
            "lines_suggested": 0,
            "lines_accepted": 0,
            "chats": 0,
            "chat_insertions": 0,
            "chat_copies": 0,
            "engaged_users": 0,
        })
        if is_chat:
            row["chats"] += item.get("user_initiated_interaction_count") or 0
        else:
            row["suggestions"] += item.get("code_generation_activity_count") or 0
            row["acceptances"] += item.get("code_acceptance_activity_count") or 0
        row["lines_suggested"] += item.get("loc_suggested_to_add_sum") or 0
        row["lines_accepted"] += item.get("loc_added_sum") or 0
    return list(model_agg.values())


def _report_flatten_features(day: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract per-feature aggregates from a report-format day.

    Maps ``totals_by_feature`` into the ``daily_feature_metrics`` schema.
    """
    rows: list[dict[str, Any]] = []
    for item in day.get("totals_by_feature") or []:
        rows.append({
            "feature": item.get("feature") or "unknown",
            "interactions": item.get("user_initiated_interaction_count") or 0,
            "code_generations": item.get("code_generation_activity_count") or 0,
            "code_acceptances": item.get("code_acceptance_activity_count") or 0,
            "loc_suggested": item.get("loc_suggested_to_add_sum") or 0,
            "loc_accepted": item.get("loc_added_sum") or 0,
            "loc_deleted": item.get("loc_deleted_sum") or 0,
        })
    return rows


def _report_day_to_raw_json(day: dict[str, Any]) -> dict[str, Any]:
    """Build a ``raw_json`` blob from a report-format day record.

    Stores the day record directly.  The ``_report`` key signals to
    analytics that this uses the report format rather than the legacy
    ``copilot_ide_code_completions`` nesting.
    """
    return {"_report": True, **day}


def _normalize_repo(repo: dict[str, Any]) -> dict[str, Any]:
    """Project a GitHub repo record into our storage row.

    Uses ``pushed_at`` (preferred) or ``updated_at`` so that the stored
    ``updated_at`` column reflects when the repo last received commits —
    enabling the skip-unchanged-repos optimization during PR ingestion.
    """
    return {
        "name": repo.get("name") or "",
        "full_name": repo.get("full_name") or "",
        "archived": 1 if repo.get("archived") else 0,
        "fork": 1 if repo.get("fork") else 0,
        "default_branch": repo.get("default_branch"),
        "updated_at": repo.get("pushed_at") or repo.get("updated_at"),
    }


def _normalize_pr_list_item(repo: str, pr: dict[str, Any]) -> dict[str, Any]:
    """Project the PR list payload into storage shape (no addition/deletion yet)."""
    user = pr.get("user") or {}
    base = pr.get("base") or {}
    head = pr.get("head") or {}
    state = pr.get("state") or "open"
    if pr.get("merged_at"):
        state = "merged"
    return {
        "repo": repo,
        "number": pr.get("number") or 0,
        "author": user.get("login"),
        "state": state,
        "created_at": pr.get("created_at"),
        "merged_at": pr.get("merged_at"),
        "closed_at": pr.get("closed_at"),
        "additions": 0,
        "deletions": 0,
        "changed_files": 0,
        "comments": pr.get("comments") or 0,
        "review_comments": pr.get("review_comments") or 0,
        "commits": 0,
        "title": pr.get("title"),
        "base_ref": base.get("ref"),
        "head_ref": head.get("ref"),
    }


def _merge_pr_detail(base_row: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    """Layer detail-endpoint fields (additions/deletions/etc.) onto a list-row."""
    return {
        **base_row,
        "additions": detail.get("additions") or 0,
        "deletions": detail.get("deletions") or 0,
        "changed_files": detail.get("changed_files") or 0,
        "commits": detail.get("commits") or 0,
        "comments": detail.get("comments") or base_row.get("comments") or 0,
        "review_comments": detail.get("review_comments") or base_row.get("review_comments") or 0,
    }


async def _ingest_pr_activity(gh: GitHubClient, since_iso: str) -> dict[str, Any]:
    """Fetch repos + PRs (created on/after ``since_iso``) across the org.

    Returns a summary dict with repo/PR counts. PRs are upserted into
    ``pull_requests``; repos into ``repos``.

    Optimizations to minimise API calls:
    * Repos whose ``pushed_at`` is unchanged since last snapshot are skipped
      entirely (no list-pulls request).
    * By default (``pr_fetch_detail=False``) only list-level PR metadata is
      stored — **no per-PR detail API call**. Set ``PR_FETCH_DETAIL=true``
      to fetch additions/deletions/changed_files at the cost of one extra
      API call per new PR.
    * When detail fetching is on, PRs already stored with non-zero detail
      data skip the individual detail call.
    """
    summary: dict[str, Any] = {
        "repos_scanned": 0,
        "prs_upserted": 0,
        "repos_skipped_unchanged": 0,
        "pr_details_skipped": 0,
        "pr_detail_fetch": settings.pr_fetch_detail,
    }
    try:
        raw_repos = await gh.list_org_repos()
    except httpx.HTTPStatusError as exc:
        log.warning("list_org_repos failed (%s); PR ingestion skipped", exc.response.status_code)
        summary["repos_error"] = str(exc.response.status_code)
        return summary

    filtered: list[dict[str, Any]] = []
    for r in raw_repos:
        if not settings.pr_include_forks and r.get("fork"):
            continue
        if not settings.pr_include_archived and r.get("archived"):
            continue
        filtered.append(r)
    filtered.sort(key=lambda r: r.get("pushed_at") or r.get("updated_at") or "", reverse=True)
    filtered = filtered[: settings.pr_max_repos]
    summary["repos_total"] = len(raw_repos)

    semaphore = asyncio.Semaphore(max(1, settings.pr_concurrency))

    async def _enrich(repo_name: str, row: dict[str, Any]) -> dict[str, Any] | None:
        async with semaphore:
            try:
                detail = await gh.get_pull_request(repo_name, row["number"])
            except httpx.HTTPStatusError as exc:
                log.info("PR detail skip %s#%s: %s", repo_name, row["number"], exc.response.status_code)
                return row
            return _merge_pr_detail(row, detail)

    total_prs = 0
    repos_skipped = 0
    details_skipped = 0
    for repo in filtered:
        repo_name = repo.get("name") or ""
        if not repo_name:
            continue

        # Skip repos with no pushes since last scan.
        pushed_at = repo.get("pushed_at") or repo.get("updated_at") or ""
        prev_updated, _prev_fetched = db.get_repo_last_fetched(repo_name)
        if prev_updated and pushed_at and pushed_at <= prev_updated:
            repos_skipped += 1
            continue

        list_rows: list[dict[str, Any]] = []
        try:
            async for pr in gh.list_repo_pulls(repo_name, state="all", since_iso=since_iso):
                list_rows.append(_normalize_pr_list_item(repo_name, pr))
        except httpx.HTTPStatusError as exc:
            log.info("list_repo_pulls skip %s: %s", repo_name, exc.response.status_code)
            continue
        if not list_rows:
            continue

        if settings.pr_fetch_detail:
            # Optional: fetch individual PR detail for additions/deletions.
            known_prs = db.existing_pr_numbers(repo_name)
            need_detail: list[dict[str, Any]] = []
            already_list: list[dict[str, Any]] = []
            for row in list_rows:
                if row["number"] in known_prs:
                    already_list.append(row)
                    details_skipped += 1
                else:
                    need_detail.append(row)
            if need_detail:
                detailed = await asyncio.gather(
                    *(_enrich(repo_name, row) for row in need_detail),
                    return_exceptions=False,
                )
                to_upsert = [r for r in detailed if r is not None] + already_list
            else:
                to_upsert = already_list
        else:
            # Default: store list-level metadata only — zero extra API calls.
            to_upsert = list_rows

        if to_upsert:
            db.upsert_pull_requests(to_upsert)
            total_prs += len(to_upsert)

    summary["repos_scanned"] = len(filtered) - repos_skipped
    summary["repos_skipped_unchanged"] = repos_skipped
    summary["prs_upserted"] = total_prs
    summary["pr_details_skipped"] = details_skipped
    # Store repos AFTER the PR-fetching loop so the skip-unchanged
    # optimization can compare against the PREVIOUS snapshot's timestamps,
    # not the just-written ones from this run.
    db.replace_repos([_normalize_repo(r) for r in filtered])
    return summary


def _flatten_billing_usage(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Project enhanced-billing ``usageItems`` into storage rows.

    The endpoint shape (paraphrased):

    .. code-block:: json

        {"usageItems": [
            {"date": "2026-06-01", "product": "Copilot",
             "sku": "Copilot Premium Request",
             "unitType": "request", "quantity": 12,
             "grossAmount": 0.48, "discountAmount": 0,
             "netAmount": 0.48,
             "username": "alice", "repositoryName": ""}
        ]}

    Missing fields default safely so the storage row is always complete.
    """
    items = payload.get("usageItems") or []
    out: list[dict[str, Any]] = []
    for it in items:
        raw_date = it.get("date") or it.get("usageAt") or ""
        date = raw_date[:10] if isinstance(raw_date, str) else ""
        if not date:
            continue
        if date < BILLING_MIN_DATE:
            continue
        out.append(
            {
                "date": date,
                "login": (it.get("username") or "").lower(),
                "product": it.get("product") or "Unknown",
                "sku": it.get("sku") or "Unknown",
                "unit_type": it.get("unitType") or "",
                "quantity": float(it.get("quantity") or 0),
                "gross_amount_usd": float(it.get("grossAmount") or 0),
                "discount_amount_usd": float(it.get("discountAmount") or 0),
                "net_amount_usd": float(it.get("netAmount") or 0),
                "repository_name": it.get("repositoryName") or "",
            }
        )
    return out


async def _ingest_billing_usage(gh: GitHubClient) -> dict[str, Any]:
    """Fetch enhanced billing usage; persist Copilot-related rows.

    Falls back from org → enterprise scope on 404. Non-fatal on 403/404
    (older tiers / disabled plans).
    """
    summary: dict[str, Any] = {"rows": 0}
    try:
        payload = await gh.org_billing_usage()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 and gh.enterprise:
            try:
                payload = await gh.enterprise_billing_usage()
            except httpx.HTTPStatusError as exc2:
                log.warning("enterprise billing usage failed (%s)", exc2.response.status_code)
                summary["error"] = str(exc2.response.status_code)
                return summary
        else:
            log.warning(
                "org billing usage failed (%s); enhanced billing API may be "
                "unavailable on this org tier. AI-credit metrics will "
                "not populate.",
                exc.response.status_code,
            )
            summary["error"] = str(exc.response.status_code)
            return summary

    rows = _flatten_billing_usage(payload)
    db.upsert_billing_usage(rows)
    summary["rows"] = len(rows)
    summary["copilot_rows"] = sum(1 for r in rows if "copilot" in (r["product"] or "").lower())
    return summary


async def _ingest_ai_credit_headline(gh: GitHubClient) -> dict[str, Any]:
    """Fetch aggregated AI-credit totals and persist as DB metadata.

    Uses the ``ai_credit/usage`` endpoint which returns pre-aggregated
    ``grossQuantity`` / ``netAmount`` per SKU — typically fresher than
    the per-day general usage endpoint. The headline total is stored in
    ``meta`` so analytics can prefer it over the sum of per-day rows.

    Non-fatal: returns summary with error key on failure.
    """
    summary: dict[str, Any] = {}
    try:
        payload = await gh.org_ai_credit_usage()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 and gh.enterprise:
            try:
                payload = await gh.enterprise_ai_credit_usage()
            except httpx.HTTPStatusError as exc2:
                log.warning("enterprise ai_credit/usage failed (%s)", exc2.response.status_code)
                summary["error"] = str(exc2.response.status_code)
                return summary
        elif exc.response.status_code in (403, 404):
            log.info("ai_credit/usage unavailable (%s); headline totals won't populate.", exc.response.status_code)
            summary["error"] = str(exc.response.status_code)
            return summary
        else:
            raise

    items = payload.get("usageItems") or []
    total_qty = sum(float(it.get("grossQuantity") or it.get("netQuantity") or 0) for it in items)
    total_net = sum(float(it.get("netAmount") or 0) for it in items)
    total_gross = sum(float(it.get("grossAmount") or 0) for it in items)

    # Persist headline totals as meta — analytics prefers these over row sums.
    ts = datetime.now(UTC).isoformat()
    db.set_meta("ai_credit_headline_qty", str(total_qty))
    db.set_meta("ai_credit_headline_net_usd", str(total_net))
    db.set_meta("ai_credit_headline_gross_usd", str(total_gross))
    db.set_meta("ai_credit_headline_at", ts)

    # Store the time period for freshness checks.
    tp = payload.get("timePeriod") or {}
    period_label = f"{tp.get('year', '')}-{tp.get('month', ''):02d}" if tp.get("year") else ""
    if period_label:
        db.set_meta("ai_credit_headline_period", period_label)

    summary["total_qty"] = total_qty
    summary["total_net_usd"] = round(total_net, 2)
    summary["total_gross_usd"] = round(total_gross, 2)
    summary["items"] = len(items)
    return summary


def _normalize_seat(seat: dict[str, Any]) -> dict[str, Any]:
    """Flatten a seat record into the storage shape."""
    assignee = seat.get("assignee") or {}
    assigning_team = seat.get("assigning_team") or {}
    return {
        "login": assignee.get("login", "unknown"),
        "team": assigning_team.get("slug"),
        "assigning_team": assigning_team.get("name"),
        "created_at": seat.get("created_at"),
        "updated_at": seat.get("updated_at"),
        "last_activity_at": seat.get("last_activity_at"),
        "last_activity_editor": seat.get("last_activity_editor"),
        "pending_cancellation_date": seat.get("pending_cancellation_date"),
        "plan_type": seat.get("plan_type"),
        "raw_json": json.dumps(seat),
    }


async def run_snapshot() -> dict[str, Any]:
    """Pull all metrics + seats from GitHub and persist them.

    Uses the 2026-03-10 report-download API for Copilot metrics.
    Falls back to the legacy ``/copilot/metrics`` endpoint when the
    report API is unavailable (404).

    Returns:
        Summary dict with counts and start/end timestamps.
    """
    db.init_db()
    summary: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat()}

    async with GitHubClient() as gh:
        # --- Org metrics via report-download API ---
        report_days: list[dict[str, Any]] = []
        try:
            report = await gh.org_metrics_report()
            report_days = report.get("day_totals") or []
            summary["metrics_api"] = "report"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning(
                    "org metrics report 404 for %s; report API may not be "
                    "enabled. Continuing with seats only.",
                    gh.org,
                )
                summary["org_metrics_error"] = "404"
            else:
                raise

        for day in report_days:
            date = day.get("day")
            if not date:
                continue
            raw = _report_day_to_raw_json(day)
            db.upsert_org_day(
                date,
                day.get("daily_active_users"),
                None,  # total_engaged_users not in report format
                raw,
            )
            db.replace_language_rows(date, _report_flatten_languages(day))
            db.replace_editor_rows(date, _report_flatten_editors(day))
            db.replace_model_rows(date, "org", "", _report_flatten_models(day))
            db.replace_feature_rows(date, _report_flatten_features(day))
        summary["org_days"] = len(report_days)

        # --- Per-user and user-teams reports for team derivation ---
        # Fetch the most recent day's user-teams report to refresh team
        # membership, and ingest per-user data for engaged-user computation.
        if report_days:
            latest_day = max(d.get("day", "") for d in report_days)
            if latest_day:
                try:
                    user_team_rows = await gh.user_teams_report(latest_day)
                    # Derive team membership from user-teams report.
                    teams_from_report: dict[str, list[str]] = defaultdict(list)
                    for ut in user_team_rows:
                        slug = ut.get("slug")
                        login = ut.get("user_login")
                        if slug and login:
                            teams_from_report[slug].append(login)
                    for slug, members in teams_from_report.items():
                        db.replace_team_members(slug, members)
                    summary["user_teams_rows"] = len(user_team_rows)
                    summary["teams_from_report"] = len(teams_from_report)
                except httpx.HTTPStatusError as exc:
                    log.info("user-teams report skipped: %s", exc.response.status_code)
                    summary["user_teams_error"] = str(exc.response.status_code)

        # --- Also fetch teams list for any additional membership data ---
        teams: list[dict[str, Any]] = []
        try:
            teams = await gh.list_teams()
        except httpx.HTTPStatusError as exc:
            log.warning(
                "list_teams failed (%s); skipping team member sync. "
                "Token likely lacks read:org scope or SSO authorization.",
                exc.response.status_code,
            )
            summary["teams_error"] = str(exc.response.status_code)

        for team in teams:
            slug = team.get("slug")
            if not slug:
                continue
            try:
                members = await gh.list_team_members(slug)
                db.replace_team_members(slug, [m.get("login") for m in members if m.get("login")])
            except httpx.HTTPStatusError as exc:
                log.info("list_team_members skip %s: %s", slug, exc.response.status_code)
        summary["teams_total"] = len(teams)

        try:
            seats_raw = await gh.list_seats()
            db.replace_seats([_normalize_seat(s) for s in seats_raw])
            summary["seats"] = len(seats_raw)
        except httpx.HTTPStatusError as exc:
            log.warning("list_seats failed (%s); seats not refreshed.", exc.response.status_code)
            summary["seats_error"] = str(exc.response.status_code)
            summary["seats"] = 0

        if settings.pr_ingest_enabled:
            since_dt = datetime.now(UTC) - timedelta(days=settings.pr_lookback_days)
            since_iso = since_dt.isoformat()
            try:
                summary["pr_ingest"] = await _ingest_pr_activity(gh, since_iso)
            except Exception:
                log.exception("PR ingestion failed")
                summary["pr_ingest_error"] = "exception"
        else:
            summary["pr_ingest"] = {"enabled": False}

        try:
            summary["billing_usage"] = await _ingest_billing_usage(gh)
        except Exception:
            log.exception("billing usage ingestion failed")
            summary["billing_usage_error"] = "exception"

        try:
            summary["ai_credit_headline"] = await _ingest_ai_credit_headline(gh)
        except Exception:
            log.exception("ai_credit headline ingestion failed")
            summary["ai_credit_headline_error"] = "exception"

    summary["finished_at"] = datetime.now(UTC).isoformat()
    db.set_meta("last_snapshot_at", summary["finished_at"])
    db.set_meta("last_data_load_at", summary["finished_at"])
    db.set_meta("last_data_load_source", "api")
    return summary
