#!/usr/bin/env python3
"""Reset the Copilot usage database to a clean slate.

Deletes all data while preserving schema and configuration. Use this when:
- Mistrusting accumulated data after schema changes
- Restarting fresh from API snapshots
- Reimporting from .csv or .ndjson files
- Resetting for clean test data seeding

Schema tables are preserved so the app can re-populate via:
- Daily snapshot job (normal operation)
- /api/data/import-file endpoint (CSV, JSON, NDJSON)
- /api/snapshot/run endpoint (force immediate snapshot)
- scripts.seed_test_data (synthetic test data)

The meta table is cleared (losing last snapshot time, etc).
"""
import sqlite3
import sys
from argparse import ArgumentParser
from pathlib import Path

# Add parent to path so we can import app.config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import settings


def _resolve_db_path(configured_db_path: str) -> Path:
    """Resolve database path with local-development fallbacks.

    If ``configured_db_path`` does not exist and points to the container default
    (``/data/copilot.db``), fall back to common local paths.
    """
    configured = Path(configured_db_path)
    if configured.exists():
        return configured

    # Common local-dev locations when config still points at container path.
    candidates = [
        Path(__file__).resolve().parents[1] / "data" / "copilot.db",  # backend/data/copilot.db
        Path(__file__).resolve().parents[2] / "data" / "copilot.db",  # repo-root data/copilot.db
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return configured


def reset_data(db_path_override: str | None = None) -> None:
    """Delete all data rows while preserving schema."""
    configured_db_path = db_path_override or settings.db_path
    db_path = _resolve_db_path(configured_db_path)
    print(f"Resetting database: {db_path}")

    if not db_path.exists():
        print("  ✓ Database does not exist; nothing to reset.")
        print("    Hint: pass --db-path PATH or set DB_PATH env var.")
        return

    conn = sqlite3.connect(db_path)
    try:
        # Preserve schema; delete all rows.
        target_tables = [
            "daily_org_metrics",
            "daily_team_metrics",
            "daily_language_metrics",
            "daily_editor_metrics",
            "daily_model_metrics",
            "daily_team_language_metrics",
            "seats",
            "repos",
            "pull_requests",
            "team_members",
            "billing_usage",
            "meta",
        ]

        existing_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        for table in target_tables:
            if table not in existing_tables:
                continue
            conn.execute(f"DELETE FROM {table}")
            print(f"  ✓ Cleared {table}")

        conn.commit()
        print(f"\n✓ Reset complete. Database ready for fresh imports or snapshots.")
    finally:
        conn.close()


def _parse_args() -> str | None:
    """Parse CLI arguments and return optional DB path override."""
    parser = ArgumentParser(description="Clear Copilot usage DB data (preserve schema).")
    parser.add_argument(
        "--db-path",
        help="Explicit SQLite database path to clear (overrides DB_PATH/settings).",
    )
    args = parser.parse_args()
    return args.db_path


if __name__ == "__main__":
    reset_data(db_path_override=_parse_args())
