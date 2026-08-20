"""FastAPI application exposing the Copilot usage dashboard API."""
from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import analytics, db
from .config import settings
from .config import VERSION
from .github_client import GitHubClient, SnapshotPreflightError
from .importer import ImportValidationError, import_usage_file
from .snapshot import assert_snapshot_permissions, run_snapshot
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("copilot-usage")


scheduler = AsyncIOScheduler(timezone="UTC")


_background_tasks: set[asyncio.Task[None]] = set()
IMPORT_UPLOAD = File(...)
USAGE_REPORT_TYPES = {"detailed", "summarized", "premium_request", "ai_credit"}
REFRESH_ALL_REPORT_TYPES: tuple[str, ...] = ("ai_credit", "detailed")
REFRESH_ALL_POLL_SECONDS = 10
REFRESH_ALL_TIMEOUT_SECONDS = 20 * 60

_refresh_all_lock = asyncio.Lock()
_refresh_all_jobs: dict[str, dict[str, Any]] = {}
_refresh_all_latest_job_id: str | None = None
_refresh_all_tasks: dict[str, asyncio.Task[None]] = {}
_refresh_all_job_tokens: dict[str, str] = {}

def _require_github_token_for_feature(feature_name: str) -> str:
    token = settings.github_token
    if token:
        return token
    raise HTTPException(
        status_code=400,
        detail=f"{feature_name} requires GitHub auth. Configure GITHUB_TOKEN.",
    )


def _require_admin_token(
    request: Request,
    x_admin_token: str | None = None,
) -> None:
    """Validate admin token from header or query param. Raises 401/403."""
    if not settings.admin_token:
        raise HTTPException(status_code=403, detail="Admin access is disabled (no ADMIN_TOKEN configured).")
    provided = x_admin_token or request.query_params.get("token") or ""
    if not provided:
        raise HTTPException(status_code=401, detail="Admin token required.")
    if not hmac.compare_digest(provided, settings.admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


class UsageReportCreateRequest(BaseModel):
    report_type: str = Field(pattern=r"^(detailed|summarized|premium_request|ai_credit)$")
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    send_email: bool = False


class RefreshAllStartRequest(BaseModel):
    report_types: list[str] = Field(default_factory=lambda: list(REFRESH_ALL_REPORT_TYPES))
    send_email: bool = False


class RefreshAllRetryRequest(BaseModel):
    job_id: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _find_running_refresh_all_job() -> dict[str, Any] | None:
    for job in _refresh_all_jobs.values():
        if job.get("status") == "running":
            return job
    return None


def _append_refresh_step(job: dict[str, Any], key: str, label: str) -> None:
    steps = job.setdefault("steps", [])
    steps.append(
        {
            "key": key,
            "label": label,
            "status": "pending",
            "message": "pending",
            "updated_at": _now_iso(),
            "meta": {},
        }
    )


def _update_refresh_step(
    job: dict[str, Any],
    key: str,
    *,
    status: str,
    message: str,
    meta: dict[str, Any] | None = None,
) -> None:
    for step in job.get("steps", []):
        if step.get("key") == key:
            step["status"] = status
            step["message"] = message
            step["updated_at"] = _now_iso()
            if meta is not None:
                step["meta"] = meta
            return


def _create_refresh_all_job(*, report_types: list[str], send_email: bool) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    job: dict[str, Any] = {
        "id": job_id,
        "status": "pending",
        "started_at": None,
        "finished_at": None,
        "report_types": report_types,
        "send_email": send_email,
        "created_at": _now_iso(),
        "errors": [],
        "steps": [],
    }
    _append_refresh_step(job, "snapshot", "Snapshot APIs")
    for report_type in report_types:
        _append_refresh_step(job, f"{report_type}-create", f"{report_type}: create report")
        _append_refresh_step(job, f"{report_type}-poll", f"{report_type}: wait for completion")
        _append_refresh_step(job, f"{report_type}-import", f"{report_type}: import CSV")

    _refresh_all_jobs[job_id] = job
    global _refresh_all_latest_job_id
    _refresh_all_latest_job_id = job_id
    task = asyncio.create_task(_run_refresh_all_job(job_id))
    _refresh_all_tasks[job_id] = task
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(lambda _t, jid=job_id: _refresh_all_tasks.pop(jid, None))
    task.add_done_callback(lambda _t, jid=job_id: _refresh_all_job_tokens.pop(jid, None))
    return job


def _mark_running_steps_canceled(job: dict[str, Any]) -> None:
    for step in job.get("steps", []):
        if step.get("status") in {"pending", "running"}:
            step["status"] = "failed"
            step["message"] = "canceled"
            step["updated_at"] = _now_iso()


async def _wait_for_usage_report_completion(
    gh: GitHubClient,
    report_id: str,
    job: dict[str, Any],
    step_key: str,
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + REFRESH_ALL_TIMEOUT_SECONDS
    while True:
        report = await gh.get_usage_report_export(report_id)
        status = str(report.get("status") or "").lower()
        _update_refresh_step(
            job,
            step_key,
            status="running",
            message=f"report status: {status or 'unknown'}",
            meta={"report_id": report_id, "status": status},
        )
        if status == "completed":
            return report
        if status == "failed":
            raise RuntimeError(f"usage report {report_id} failed")
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(f"usage report {report_id} timed out")
        await asyncio.sleep(REFRESH_ALL_POLL_SECONDS)


async def _download_and_import_usage_report(
    gh: GitHubClient,
    report_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    job = await gh.get_usage_report_export(report_id)
    status = str(job.get("status") or "").lower()
    if status != "completed":
        raise HTTPException(status_code=409, detail=f"report status is {status or 'unknown'}")
    urls = job.get("download_urls") or []
    if not isinstance(urls, list) or not urls:
        raise HTTPException(status_code=404, detail="report has no download URL")
    csv_text = await gh.download_usage_report(str(urls[0]))
    report_type = str(job.get("report_type") or "usage")
    start_date = str(job.get("start_date") or "")
    end_date = str(job.get("end_date") or "")
    filename = f"{report_type}_{start_date}_{end_date}.csv".replace(" ", "_")
    try:
        imported = import_usage_file(filename, csv_text.encode("utf-8"))
    except ImportValidationError as exc:
        raise HTTPException(status_code=400, detail=f"usage report import failed: {exc}") from exc
    return job, imported


def _ensure_iso_date(label: str, value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{label} must be YYYY-MM-DD") from exc
    return value


def _raise_github_http_error(exc: httpx.HTTPStatusError, context: str) -> None:
    code = exc.response.status_code
    detail = f"{context} failed ({code})"
    try:
        payload = exc.response.json()
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, str) and message.strip():
            detail = f"{detail}: {message}"
    except Exception:
        pass
    if "usage report" in context and code in (403, 404):
        configured_enterprise = settings.github_enterprise.strip()
        configured_slug_display = configured_enterprise if configured_enterprise else "(empty)"
        detail = (
            f"{detail}. Enterprise usage-reports API requires: "
            "(1) Enterprise Cloud usage-reports feature enabled, "
            "(2) caller is enterprise owner or enterprise billing manager, "
            "(3) PAT has enterprise billing scope (classic: manage_billing:enterprise; "
            "manage_billing:copilot + read:enterprise are also commonly required for related Copilot endpoints). "
            f"Configured enterprise slug: '{configured_slug_display}'."
        )
    raise HTTPException(status_code=code, detail=detail) from exc


def _is_usage_report_api_access_error(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    if exc.response.status_code not in (403, 404):
        return False
    request = exc.request
    if request is None:
        return False
    return "/settings/billing/reports" in request.url.path


def _usage_report_api_access_message() -> str:
    configured_enterprise = settings.github_enterprise.strip()
    configured_slug_display = configured_enterprise if configured_enterprise else "(empty)"
    return (
        "enterprise usage-reports API unavailable "
        f"for configured enterprise '{configured_slug_display}'. "
        "This endpoint is typically restricted to enterprise owners/billing managers "
        "and tenants with usage-report export enabled."
    )


def _format_refresh_report_error(exc: Exception) -> str:
    if _is_usage_report_api_access_error(exc):
        return _usage_report_api_access_message()
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        try:
            payload = exc.response.json()
            message = payload.get("message") if isinstance(payload, dict) else None
            if isinstance(message, str) and message.strip():
                return f"GitHub API error {code}: {message.strip()}"
        except Exception:
            pass
        return f"GitHub API error {code}"
    return str(exc)


def _find_reusable_usage_report(
    exports: list[dict[str, Any]],
    *,
    report_type: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any] | None:
    matches = [
        row
        for row in exports
        if str(row.get("report_type") or "") == report_type
        and str(row.get("start_date") or "") == start_date
        and str(row.get("end_date") or "") == end_date
        and str(row.get("status") or "").lower() in {"pending", "in_progress", "processing", "completed"}
    ]
    if not matches:
        return None
    matches.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return matches[0]


async def _scheduled_snapshot() -> None:
    """Run a snapshot, logging any error rather than raising."""
    try:
        summary = await run_snapshot()
        log.info("scheduled snapshot complete: %s", summary)
    except Exception:
        log.exception("scheduled snapshot failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the DB, schedule snapshots, and clean up on shutdown."""
    del app
    db.init_db()
    if settings.seed_mode:
        log.warning("SEED_MODE enabled; snapshots disabled to preserve synthetic data")
    elif not settings.github_token:
        log.warning("GITHUB_TOKEN not set; snapshots disabled")
    elif not settings.snapshot_time_utc:
        log.info("SNAPSHOT_TIME_UTC not set; scheduled snapshots disabled")
    else:
        hour_str, minute_str = settings.snapshot_time_utc.split(":")
        scheduler.add_job(
            _scheduled_snapshot,
            CronTrigger(hour=int(hour_str), minute=int(minute_str)),
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Copilot Usage Review", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness + basic info endpoint."""
    return {
        "ok": True,
        "org": settings.github_org,
        "last_snapshot_at": db.get_meta("last_snapshot_at"),
        "last_data_load_at": db.get_meta("last_data_load_at"),
        "last_data_load_source": db.get_meta("last_data_load_source"),
        "last_api_load_at": db.get_meta("last_api_load_at"),
        "last_csv_load_at": db.get_meta("last_csv_load_at"),
        "last_csv_load_source": db.get_meta("last_csv_load_source"),
        "last_json_load_at": db.get_meta("last_json_load_at"),
        "last_json_load_source": db.get_meta("last_json_load_source"),
        "last_api_json_load_at": db.get_meta("last_api_json_load_at"),
        "last_github_export_ndjson_load_at": db.get_meta("last_github_export_ndjson_load_at"),
        "last_copilot_usage_insight_ndjson_load_at": db.get_meta("last_copilot_usage_insight_ndjson_load_at"),
        "last_csv_usage_report_load_at": db.get_meta("last_csv_usage_report_load_at"),
        "last_csv_ai_usage_report_load_at": db.get_meta("last_csv_ai_usage_report_load_at"),
        "last_db_export_load_at": db.get_meta("last_db_export_load_at"),
        "last_db_export_load_source": db.get_meta("last_db_export_load_source"),
        "version": VERSION,
    }


@app.get("/api/auth/validate-admin")
def validate_admin(token: str = Query("")) -> dict[str, bool]:
    """Validate an admin token without side effects."""
    if not settings.admin_token:
        raise HTTPException(status_code=403, detail="Admin access is disabled.")
    if not token or not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token.")
    return {"valid": True}


@app.get("/api/kpis")
def get_kpis(
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return headline dashboard KPIs for a window (default last 30 days)."""
    return analytics.kpis(days=days, start=start, end=end)


@app.get("/api/trends")
def get_trends(
    days: int = 90,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Return daily org metrics for the window."""
    return analytics.trends(days=days, start=start, end=end)


@app.get("/api/teams")
def get_teams(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Return per-team aggregated metrics for the window."""
    return analytics.teams_leaderboard(days=days, start=start, end=end)


@app.get("/api/teams/list")
def get_team_list() -> list[dict[str, Any]]:
    """Return all team slugs we have data for."""
    return analytics.teams_list()


@app.get("/api/teams/{team_slug}")
def get_team_detail(
    team_slug: str,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return full detail for one team (metrics + PR rollup + cost)."""
    return analytics.team_detail(team_slug, days=days, start=start, end=end)


@app.get("/api/seats/stale")
def get_stale_seats() -> list[dict[str, Any]]:
    """Return seats inactive longer than the configured threshold."""
    return analytics.stale_seats()


@app.get("/api/users")
def get_users(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Return seat-holders with PR activity rollup for the window."""
    return analytics.users_list(days=days, start=start, end=end)


@app.get("/api/users/{login}")
def get_user_detail(
    login: str,
    days: int = 90,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return detail view for one user (seat + PR activity)."""
    return analytics.user_detail(login, days=days, start=start, end=end)


@app.get("/api/breakdowns")
def get_breakdowns(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return language + editor breakdowns for the window."""
    return analytics.breakdowns(days=days, start=start, end=end)


@app.get("/api/models")
def get_models(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Return per-model usage breakdown for the window."""
    return analytics.model_breakdown(days=days, start=start, end=end, team=team)


@app.get("/api/chat-vs-inline")
def get_chat_vs_inline(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Return code-completion vs chat usage split."""
    return analytics.chat_vs_inline(days=days, start=start, end=end, team=team)


@app.get("/api/features")
def get_features(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return per-feature usage breakdown (agent mode, completions, CLI, etc.)."""
    return analytics.feature_breakdown(days=days, start=start, end=end)


@app.get("/api/cost")
def get_cost(
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return prorated seat cost for the window."""
    return analytics.cost_for_window(days=days, start=start, end=end)


@app.get("/api/cohorts")
def get_cohorts() -> dict[str, Any]:
    """Return seat-onboarding ramp distribution."""
    return analytics.cohort_ramp()


@app.get("/api/distribution")
def get_distribution(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Return power-user concentration metrics for the window."""
    return analytics.power_user_concentration(days=days, start=start, end=end, team=team)


@app.get("/api/pr-correlation")
def get_pr_correlation(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Return PR outcome metrics split by AI-seat ownership."""
    return analytics.pr_correlation(days=days, start=start, end=end, team=team)


@app.get("/api/quality")
def get_quality(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return the rollup payload for the Quality tab."""
    return analytics.quality_summary(days=days, start=start, end=end)


@app.get("/api/ai-credits")
def get_ai_credits(
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return org-level Copilot AI-credit usage from billing data."""
    return analytics.ai_credits_summary(days=days, start=start, end=end)


@app.get("/api/ai-credits/users/{login}")
def get_ai_credits_user(
    login: str,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return per-user Copilot AI-credit usage."""
    return analytics.ai_credits_for_user(login, days=days, start=start, end=end)


@app.get("/api/ai-credits/teams/{team_slug}")
def get_ai_credits_team(
    team_slug: str,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return per-team Copilot AI-credit usage."""
    return analytics.ai_credits_for_team(team_slug, days=days, start=start, end=end)


@app.get("/api/ai-credits/projection")
async def get_ai_credits_projection() -> dict[str, Any]:
    """Return daily cumulative AI-credit usage for the current and previous calendar months.

    Used by the Summary page projection chart to visualise month-over-month
    consumption trends and aid budget forecasting. Includes budget quota when
    available (from GitHub Budgets API or MONTHLY_AI_BUDGET_USD env fallback).
    """
    result = analytics.daily_org_ai_credits()

    # If no quota resolved from billing data / env, try the Budgets API live.
    if result.get("monthly_quota_credits") is None and settings.github_token:
        try:
            from .github_client import GitHubClient

            client = GitHubClient()
            budgets = await client.org_budgets()
            # Find the AI-credits budget scoped to org or multi_user_customer.
            for b in budgets:
                sku = (b.get("budget_product_sku") or "").lower()
                scope = (b.get("budget_scope") or "").lower()
                if sku in ("ai_credits", "premium_requests") and scope in (
                    "organization",
                    "multi_user_customer",
                    "enterprise",
                ):
                    budget_amount = float(b.get("budget_amount") or 0)
                    if budget_amount > 0:
                        budget_credits = budget_amount / 0.01
                        included = result.get("included_credits") or 0
                        result["budget_usd"] = budget_amount
                        result["monthly_quota_credits"] = round(
                            budget_credits + included, 2
                        )
                    break
        except Exception:
            log.debug("Budgets API unavailable; quota line will be absent", exc_info=True)

    return result


@app.get("/api/roi")
def get_roi(
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Return cost/savings ROI summary for the window."""
    return analytics.roi(days=days, start=start, end=end)


@app.get("/api/projections")
def get_projections() -> dict[str, Any]:
    """Return projected active users and right-sized seat recommendation."""
    return analytics.projections()


@app.post("/api/snapshot/run")
async def trigger_snapshot() -> dict[str, Any]:
    """Trigger an immediate snapshot. Requires ``GITHUB_TOKEN``."""
    if settings.seed_mode:
        raise HTTPException(
            status_code=409,
            detail="SEED_MODE is enabled; refusing to run a snapshot over synthetic data",
        )
    if not settings.github_token:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured")
    try:
        await assert_snapshot_permissions()
    except SnapshotPreflightError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return await run_snapshot()


@app.post("/api/data/import-file")
async def import_file(
    request: Request,
    file: UploadFile = IMPORT_UPLOAD,
    source_hint: str | None = Form(None),
    x_admin_token: str | None = Header(None),
) -> dict[str, Any]:
    """Import a local JSON/JSONL/NDJSON Copilot usage export upload."""
    _require_admin_token(request, x_admin_token)
    filename = file.filename or ""
    max_bytes = max(1, settings.import_max_upload_mb) * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"import file exceeds {settings.import_max_upload_mb} MiB limit",
            )
        chunks.append(chunk)
    try:
        return import_usage_file(filename, b"".join(chunks), source_hint=source_hint)
    except ImportValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.get("/api/data/export")
def export_database(
    request: Request,
    x_admin_token: str | None = Header(None),
) -> Response:
    """Export the entire database as a single gzip-compressed SQLite file."""
    _require_admin_token(request, x_admin_token)
    payload = db.export_database_gzip()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"copilot-usage-export-{stamp}.db.gz"
    return Response(
        content=payload,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/data/import-db")
async def import_database(
    request: Request,
    file: UploadFile = IMPORT_UPLOAD,
    mode: str = Query("merge", pattern="^(replace|merge)$"),
    x_admin_token: str | None = Header(None),
) -> dict[str, Any]:
    """Import a full-database export, replacing or merging into the live DB."""
    _require_admin_token(request, x_admin_token)
    max_bytes = max(1, settings.import_max_upload_mb) * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"import file exceeds {settings.import_max_upload_mb} MiB limit",
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    if not db.is_database_export(content):
        raise HTTPException(
            status_code=400,
            detail="uploaded file is not a database export",
        )
    try:
        result = db.import_database(content, mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    imported_at = datetime.now(UTC).isoformat()
    db.set_meta("last_data_load_at", imported_at)
    db.set_meta("last_data_load_source", f"db-export ({mode})")
    db.set_meta("last_db_export_load_at", imported_at)
    db.set_meta("last_db_export_load_source", f"db-export ({mode})")
    tables = result["tables"]
    return {
        "source_type": "db_export",
        "mode": result["mode"],
        "tables_imported": len(tables),
        "rows_total": sum(tables.values()),
        "tables": tables,
    }


@app.get("/api/usage-reports")
async def list_usage_reports(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """List enterprise usage-report export jobs."""
    auth_token = _require_github_token_for_feature("list usage reports")
    try:
        async with GitHubClient(token=auth_token) as gh:
            rows = await gh.list_usage_report_exports()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        _raise_github_http_error(exc, "list usage reports")
    rows = sorted(rows, key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return {
        "enterprise": settings.github_enterprise,
        "exports": rows[:limit],
    }


@app.post("/api/usage-reports")
async def create_usage_report(req: UsageReportCreateRequest) -> dict[str, Any]:
    """Create an async enterprise usage-report export job."""
    auth_token = _require_github_token_for_feature("create usage report")
    if req.report_type not in USAGE_REPORT_TYPES:
        raise HTTPException(status_code=400, detail="unsupported report_type")
    start_date = _ensure_iso_date("start_date", req.start_date)
    end_date = _ensure_iso_date("end_date", req.end_date)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
    try:
        async with GitHubClient(token=auth_token) as gh:
            job = await gh.create_usage_report_export(
                report_type=req.report_type,
                start_date=start_date,
                end_date=end_date,
                send_email=req.send_email,
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        _raise_github_http_error(exc, "create usage report")
    return job


@app.get("/api/usage-reports/{report_id}")
async def get_usage_report(report_id: str) -> dict[str, Any]:
    """Get one usage-report export job."""
    auth_token = _require_github_token_for_feature("get usage report")
    if not report_id:
        raise HTTPException(status_code=400, detail="report_id is required")
    try:
        async with GitHubClient(token=auth_token) as gh:
            job = await gh.get_usage_report_export(report_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        _raise_github_http_error(exc, "get usage report")
    return job


@app.get("/api/usage-reports/{report_id}/download")
async def download_usage_report(report_id: str) -> Response:
    """Download CSV content for a completed usage-report export job."""
    auth_token = _require_github_token_for_feature("download usage report")
    if not report_id:
        raise HTTPException(status_code=400, detail="report_id is required")
    try:
        async with GitHubClient(token=auth_token) as gh:
            job = await gh.get_usage_report_export(report_id)
            status = str(job.get("status") or "").lower()
            if status != "completed":
                raise HTTPException(status_code=409, detail=f"report status is {status or 'unknown'}")
            urls = job.get("download_urls") or []
            if not isinstance(urls, list) or not urls:
                raise HTTPException(status_code=404, detail="report has no download URL")
            text = await gh.download_usage_report(str(urls[0]))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        _raise_github_http_error(exc, "download usage report")

    report_type = str(job.get("report_type") or "usage")
    start_date = str(job.get("start_date") or "")
    end_date = str(job.get("end_date") or "")
    filename = f"{report_type}_{start_date}_{end_date}.csv".replace(" ", "_")
    return Response(
        content=text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/usage-reports/{report_id}/import")
async def import_usage_report(report_id: str) -> dict[str, Any]:
    """Download a completed usage report and import it into billing data."""
    auth_token = _require_github_token_for_feature("import usage report")
    if not report_id:
        raise HTTPException(status_code=400, detail="report_id is required")
    try:
        async with GitHubClient(token=auth_token) as gh:
            job, imported = await _download_and_import_usage_report(gh, report_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        _raise_github_http_error(exc, "import usage report")
    status = str(job.get("status") or "").lower()
    report_type = str(job.get("report_type") or "usage")
    start_date = str(job.get("start_date") or "")
    end_date = str(job.get("end_date") or "")

    return {
        "report_id": report_id,
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
        "import": imported,
    }


async def _run_refresh_all_job(job_id: str) -> None:
    async with _refresh_all_lock:
        job = _refresh_all_jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["started_at"] = _now_iso()
    errors: list[str] = []
    canceled = False

    try:
        _update_refresh_step(job, "snapshot", status="running", message="snapshot in progress")
        await assert_snapshot_permissions()
        snapshot_summary = await run_snapshot()
        _update_refresh_step(
            job,
            "snapshot",
            status="completed",
            message="snapshot complete",
            meta={"summary": snapshot_summary},
        )
    except asyncio.CancelledError:
        canceled = True
        _mark_running_steps_canceled(job)
        job["status"] = "canceled"
        job["finished_at"] = _now_iso()
        job["errors"] = ["refresh-all canceled by user"]
        raise
    except Exception as exc:
        _update_refresh_step(
            job,
            "snapshot",
            status="failed",
            message=f"snapshot failed: {exc}",
        )
        job["status"] = "failed"
        job["finished_at"] = _now_iso()
        job["errors"] = [str(exc)]
        return

    try:
        auth_token = _refresh_all_job_tokens.get(job_id)
        async with GitHubClient(token=auth_token) as gh:
            report_types: list[str] = job.get("report_types") or []
            now = datetime.now(UTC)
            start_date = f"{now.year}-{now.month:02d}-01"
            end_date = f"{now.year}-{now.month:02d}-{now.day:02d}"
            exports: list[dict[str, Any]] = []

            try:
                exports = await gh.list_usage_report_exports()
            except Exception as exc:
                if not _is_usage_report_api_access_error(exc):
                    raise
                access_msg = _usage_report_api_access_message()
                errors.append(access_msg)
                for report_type in report_types:
                    create_key = f"{report_type}-create"
                    poll_key = f"{report_type}-poll"
                    import_key = f"{report_type}-import"
                    _update_refresh_step(job, create_key, status="failed", message=access_msg)
                    _update_refresh_step(
                        job,
                        poll_key,
                        status="failed",
                        message="skipped: report API unavailable",
                    )
                    _update_refresh_step(
                        job,
                        import_key,
                        status="failed",
                        message="skipped: report API unavailable",
                    )
                return

            for report_type in report_types:
                create_key = f"{report_type}-create"
                poll_key = f"{report_type}-poll"
                import_key = f"{report_type}-import"
                try:
                    _update_refresh_step(
                        job,
                        create_key,
                        status="running",
                        message=f"checking existing {report_type} report",
                    )
                    report = _find_reusable_usage_report(
                        exports,
                        report_type=report_type,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    if report is None:
                        _update_refresh_step(
                            job,
                            create_key,
                            status="running",
                            message=f"creating {report_type} report",
                        )
                        report = await gh.create_usage_report_export(
                            report_type=report_type,
                            start_date=start_date,
                            end_date=end_date,
                            send_email=bool(job.get("send_email")),
                        )
                        exports.append(report)
                        create_message = f"created {report_type} report"
                    else:
                        create_message = f"reused {report_type} report"

                    report_id = str(report.get("id") or "")
                    report_status = str(report.get("status") or "").lower()
                    _update_refresh_step(
                        job,
                        create_key,
                        status="completed",
                        message=create_message,
                        meta={"report_id": report_id},
                    )
                    if report_status == "completed":
                        _update_refresh_step(
                            job,
                            poll_key,
                            status="completed",
                            message="report already completed",
                            meta={"report_id": report_id, "status": report_status},
                        )
                    else:
                        _update_refresh_step(
                            job,
                            poll_key,
                            status="running",
                            message="waiting for completion",
                            meta={"report_id": report_id},
                        )
                        completed = await _wait_for_usage_report_completion(gh, report_id, job, poll_key)
                        _update_refresh_step(
                            job,
                            poll_key,
                            status="completed",
                            message="report completed",
                            meta={"report_id": report_id, "status": completed.get("status")},
                        )
                    _update_refresh_step(
                        job,
                        import_key,
                        status="running",
                        message="importing report",
                        meta={"report_id": report_id},
                    )
                    _job, imported = await _download_and_import_usage_report(gh, report_id)
                    _update_refresh_step(
                        job,
                        import_key,
                        status="completed",
                        message="report imported",
                        meta={
                            "report_id": report_id,
                            "rows_imported": imported.get("rows_imported"),
                            "source_type": imported.get("source_type"),
                        },
                    )
                except Exception as exc:
                    msg = _format_refresh_report_error(exc)
                    errors.append(f"{report_type}: {msg}")
                    _update_refresh_step(
                        job,
                        import_key,
                        status="failed",
                        message=f"{report_type} flow failed: {msg}",
                    )
    except asyncio.CancelledError:
        canceled = True
        _mark_running_steps_canceled(job)
        job["status"] = "canceled"
        job["finished_at"] = _now_iso()
        job["errors"] = ["refresh-all canceled by user"]
        raise
    finally:
        job["finished_at"] = _now_iso()
        if not canceled and errors:
            job["status"] = "completed_with_errors"
            job["errors"] = errors
        elif not canceled:
            job["status"] = "completed"
            job["errors"] = []


@app.post("/api/refresh-all/start")
async def start_refresh_all(req: RefreshAllStartRequest) -> dict[str, Any]:
    """Start background "refresh all data" job with per-source progress."""
    if settings.seed_mode:
        raise HTTPException(status_code=409, detail="SEED_MODE is enabled; refresh-all is disabled")
    _require_github_token_for_feature("refresh-all")
    report_types = [rt for rt in req.report_types if rt in USAGE_REPORT_TYPES]
    if not report_types:
        report_types = list(REFRESH_ALL_REPORT_TYPES)

    async with _refresh_all_lock:
        running = _find_running_refresh_all_job()
        if running:
            return {"started": False, "job": running}
        job = _create_refresh_all_job(report_types=report_types, send_email=req.send_email)
        job["auth_mode"] = "pat"
        _refresh_all_job_tokens[str(job.get("id"))] = settings.github_token

    return {"started": True, "job": job}


@app.get("/api/refresh-all/status")
async def refresh_all_status_latest() -> dict[str, Any]:
    """Return latest refresh-all job status (running or most recent)."""
    running = _find_running_refresh_all_job()
    if running:
        return running
    if _refresh_all_latest_job_id and _refresh_all_latest_job_id in _refresh_all_jobs:
        return _refresh_all_jobs[_refresh_all_latest_job_id]
    raise HTTPException(status_code=404, detail="no refresh-all job found")


@app.get("/api/refresh-all/status/{job_id}")
async def refresh_all_status(job_id: str) -> dict[str, Any]:
    """Return status for a specific refresh-all job."""
    job = _refresh_all_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="refresh-all job not found")
    return job


@app.post("/api/refresh-all/cancel")
async def cancel_refresh_all(job_id: str | None = Query(default=None)) -> dict[str, Any]:
    """Cancel currently running refresh-all job (or a specific running job)."""
    async with _refresh_all_lock:
        running = _find_running_refresh_all_job()
        if not running:
            raise HTTPException(status_code=409, detail="no running refresh-all job")
        target = running
        if job_id:
            job = _refresh_all_jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="refresh-all job not found")
            if job.get("status") != "running":
                raise HTTPException(status_code=409, detail="refresh-all job is not running")
            target = job
        target_id = str(target.get("id") or "")
        task = _refresh_all_tasks.get(target_id)
        if not task:
            raise HTTPException(status_code=409, detail="running task handle not found")
        task.cancel()
    return {"canceled": True, "job_id": target_id}


@app.post("/api/refresh-all/retry")
async def retry_refresh_all(req: RefreshAllRetryRequest) -> dict[str, Any]:
    """Retry refresh-all based on most recent failed/canceled/error job settings."""
    async with _refresh_all_lock:
        running = _find_running_refresh_all_job()
        if running:
            return {"started": False, "job": running}

        source_job: dict[str, Any] | None = None
        if req.job_id:
            source_job = _refresh_all_jobs.get(req.job_id)
            if not source_job:
                raise HTTPException(status_code=404, detail="source refresh-all job not found")
        elif _refresh_all_latest_job_id and _refresh_all_latest_job_id in _refresh_all_jobs:
            source_job = _refresh_all_jobs[_refresh_all_latest_job_id]

        if not source_job:
            raise HTTPException(status_code=404, detail="no refresh-all job found to retry")

        status = str(source_job.get("status") or "")
        if status not in {"failed", "completed_with_errors", "canceled", "completed"}:
            raise HTTPException(status_code=409, detail=f"job status '{status}' cannot be retried")

        source_types = source_job.get("report_types") or []
        report_types = [rt for rt in source_types if rt in USAGE_REPORT_TYPES]
        if not report_types:
            report_types = list(REFRESH_ALL_REPORT_TYPES)
        send_email = bool(source_job.get("send_email"))
        job = _create_refresh_all_job(report_types=report_types, send_email=send_email)
        job["auth_mode"] = "pat"
        _refresh_all_job_tokens[str(job.get("id"))] = settings.github_token

    return {"started": True, "job": job}
