"""FastAPI application exposing the Copilot usage dashboard API."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import analytics, db
from .config import settings
from .importer import ImportValidationError, import_usage_file
from .snapshot import run_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("copilot-usage")


scheduler = AsyncIOScheduler(timezone="UTC")


_background_tasks: set[asyncio.Task[None]] = set()
IMPORT_UPLOAD = File(...)


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
    }


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
    return await run_snapshot()


@app.post("/api/data/import-file")
async def import_file(file: UploadFile = IMPORT_UPLOAD) -> dict[str, Any]:
    """Import a local JSON/JSONL/NDJSON Copilot usage export upload."""
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
        return import_usage_file(filename, b"".join(chunks))
    except ImportValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.get("/api/data/export")
def export_database() -> Response:
    """Export the entire database as a single gzip-compressed SQLite file."""
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
    file: UploadFile = IMPORT_UPLOAD,
    mode: str = Query("merge", pattern="^(replace|merge)$"),
) -> dict[str, Any]:
    """Import a full-database export, replacing or merging into the live DB."""
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
    db.set_meta("last_data_load_at", datetime.now(UTC).isoformat())
    db.set_meta("last_data_load_source", f"db-export ({mode})")
    tables = result["tables"]
    return {
        "source_type": "db_export",
        "mode": result["mode"],
        "tables_imported": len(tables),
        "rows_total": sum(tables.values()),
        "tables": tables,
    }
