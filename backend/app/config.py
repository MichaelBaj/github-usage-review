"""Application configuration loaded from environment.

Defaults are safe for local development. Production deployments must set
``GITHUB_TOKEN`` and override ``CORS_ALLOW_ORIGINS`` to a constrained
allowlist.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Billing data before this date is rejected during import.
BILLING_MIN_DATE = "2026-06-01"


class Settings(BaseSettings):
    """Runtime configuration for the Copilot usage review service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_token: str = ""
    github_org: str = "Juniper-SSN"
    github_enterprise: str = Field(
        default="juniper-net",
        description=(
            "Enterprise slug used as a fallback for endpoints that 404 at the "
            "org scope (org metrics, billing usage). Set to empty string to disable."
        ),
    )
    seat_cost_usd: float = 39.0
    minutes_saved_per_acceptance: float = Field(
        default=0.5,
        description="Tunable benchmark: minutes saved per accepted suggestion.",
    )
    stale_seat_days: int = 30
    db_path: str = "/data/copilot.db"
    snapshot_time_utc: str = Field(
        default="",
        description=(
            "HH:MM in UTC for the daily cron snapshot. "
            "Leave empty to disable scheduled snapshots."
        ),
    )
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        description="CORS allowlist for frontend; comma-separated in env.",
    )

    # --- PR correlation ingestion ---
    pr_ingest_enabled: bool = Field(
        default=False,
        description=(
            "If true, the snapshot also ingests org pull-request activity for "
            "ROI/quality correlation. Disabled by default to minimise GitHub "
            "API usage; the core Copilot usage dashboard works without it."
        ),
    )
    pr_lookback_days: int = Field(
        default=30,
        description="How many days back to fetch PR activity on each snapshot run.",
    )
    pr_max_repos: int = Field(
        default=50,
        description="Cap on number of org repos walked per snapshot to bound API/rate-limit cost.",
    )
    pr_concurrency: int = Field(
        default=4,
        description="Concurrent in-flight PR detail requests per snapshot run (unused when pr_fetch_detail is false).",
    )
    pr_fetch_detail: bool = Field(
        default=False,
        description=(
            "When true, fetch individual PR detail (additions/deletions/changed_files) "
            "via one API call per PR. When false (default), only list-level metadata "
            "is stored — dramatically reducing API calls."
        ),
    )
    pr_include_forks: bool = Field(default=False)
    pr_include_archived: bool = Field(default=False)

    # --- Seed / preview mode ---
    seed_mode: bool = Field(
        default=False,
        description=(
            "When true, disables the boot snapshot, the daily cron, and the "
            "POST /api/snapshot/run endpoint so synthetic data from "
            "scripts/seed_test_data.py is preserved."
        ),
    )
    import_max_upload_mb: int = Field(
        default=25,
        description="Maximum local JSON/JSONL/NDJSON import upload size in MiB.",
    )


settings = Settings()
