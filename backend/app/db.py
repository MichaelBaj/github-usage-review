"""SQLite storage for daily Copilot metric snapshots.

Snapshots are idempotent per (date, scope) — re-running the snapshot job
for the same day overwrites prior rows so a delayed run never duplicates.
"""
from __future__ import annotations

import contextlib
import gzip
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_org_metrics (
    date TEXT PRIMARY KEY,
    total_active_users INTEGER,
    total_engaged_users INTEGER,
    raw_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_team_metrics (
    date TEXT NOT NULL,
    team_slug TEXT NOT NULL,
    total_active_users INTEGER,
    total_engaged_users INTEGER,
    raw_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, team_slug)
);

CREATE TABLE IF NOT EXISTS daily_language_metrics (
    date TEXT NOT NULL,
    language TEXT NOT NULL,
    editor TEXT NOT NULL,
    suggestions INTEGER DEFAULT 0,
    acceptances INTEGER DEFAULT 0,
    lines_suggested INTEGER DEFAULT 0,
    lines_accepted INTEGER DEFAULT 0,
    engaged_users INTEGER DEFAULT 0,
    PRIMARY KEY (date, language, editor)
);

CREATE TABLE IF NOT EXISTS daily_editor_metrics (
    date TEXT NOT NULL,
    editor TEXT NOT NULL,
    suggestions INTEGER DEFAULT 0,
    acceptances INTEGER DEFAULT 0,
    lines_suggested INTEGER DEFAULT 0,
    lines_accepted INTEGER DEFAULT 0,
    chat_total_chats INTEGER DEFAULT 0,
    chat_insertion_events INTEGER DEFAULT 0,
    chat_copy_events INTEGER DEFAULT 0,
    engaged_users INTEGER DEFAULT 0,
    PRIMARY KEY (date, editor)
);

CREATE TABLE IF NOT EXISTS seats (
    login TEXT PRIMARY KEY,
    team TEXT,
    assigning_team TEXT,
    created_at TEXT,
    updated_at TEXT,
    last_activity_at TEXT,
    last_activity_editor TEXT,
    pending_cancellation_date TEXT,
    plan_type TEXT,
    raw_json TEXT NOT NULL,
    snapshot_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_model_metrics (
    date TEXT NOT NULL,
    scope TEXT NOT NULL,               -- 'org' or 'team'
    team_slug TEXT NOT NULL DEFAULT '',
    editor TEXT NOT NULL,
    model TEXT NOT NULL,
    is_chat INTEGER NOT NULL,          -- 0 = code completion, 1 = chat
    suggestions INTEGER DEFAULT 0,
    acceptances INTEGER DEFAULT 0,
    lines_suggested INTEGER DEFAULT 0,
    lines_accepted INTEGER DEFAULT 0,
    chats INTEGER DEFAULT 0,
    chat_insertions INTEGER DEFAULT 0,
    chat_copies INTEGER DEFAULT 0,
    engaged_users INTEGER DEFAULT 0,
    PRIMARY KEY (date, scope, team_slug, editor, model, is_chat)
);

CREATE INDEX IF NOT EXISTS idx_model_metrics_scope_team_date
    ON daily_model_metrics(scope, team_slug, date);

CREATE TABLE IF NOT EXISTS daily_team_language_metrics (
    date TEXT NOT NULL,
    team_slug TEXT NOT NULL,
    language TEXT NOT NULL,
    editor TEXT NOT NULL,
    suggestions INTEGER DEFAULT 0,
    acceptances INTEGER DEFAULT 0,
    lines_suggested INTEGER DEFAULT 0,
    lines_accepted INTEGER DEFAULT 0,
    engaged_users INTEGER DEFAULT 0,
    PRIMARY KEY (date, team_slug, language, editor)
);

CREATE INDEX IF NOT EXISTS idx_team_lang_team_date
    ON daily_team_language_metrics(team_slug, date);

CREATE TABLE IF NOT EXISTS repos (
    name TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    archived INTEGER DEFAULT 0,
    fork INTEGER DEFAULT 0,
    default_branch TEXT,
    updated_at TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pull_requests (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    author TEXT,
    state TEXT,                        -- 'open', 'closed', 'merged'
    created_at TEXT,
    merged_at TEXT,
    closed_at TEXT,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    changed_files INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    review_comments INTEGER DEFAULT 0,
    commits INTEGER DEFAULT 0,
    title TEXT,
    base_ref TEXT,
    head_ref TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (repo, number)
);

CREATE INDEX IF NOT EXISTS idx_pr_author_created ON pull_requests(author, created_at);
CREATE INDEX IF NOT EXISTS idx_pr_author_merged ON pull_requests(author, merged_at);
CREATE INDEX IF NOT EXISTS idx_pr_created ON pull_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_pr_merged ON pull_requests(merged_at);

CREATE TABLE IF NOT EXISTS team_members (
    team_slug TEXT NOT NULL,
    login TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (team_slug, login)
);

CREATE INDEX IF NOT EXISTS idx_team_members_login ON team_members(login);
"""

# ``billing_usage`` is created and migrated separately (see ``_migrate_billing_usage``)
# because its primary key gained ``model`` and ``workflow_path`` to keep
# CSV AI-credit / workflow rows distinct, which requires a table rebuild on
# pre-existing databases.


def _billing_table_ddl(table: str) -> str:
    """Return the ``CREATE TABLE`` DDL for the billing-usage table.

    Args:
        table: Target table name (``billing_usage`` or a temp rebuild name).

    Returns:
        A single ``CREATE TABLE`` statement.
    """
    return f"""
    CREATE TABLE {table} (
        date TEXT NOT NULL,                       -- usage day (YYYY-MM-DD, UTC)
        login TEXT NOT NULL DEFAULT '',           -- empty = org-level / no per-user attribution
        product TEXT NOT NULL,
        sku TEXT NOT NULL,
        unit_type TEXT,
        quantity REAL NOT NULL,
        gross_amount_usd REAL DEFAULT 0,
        discount_amount_usd REAL DEFAULT 0,
        net_amount_usd REAL DEFAULT 0,
        repository_name TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',           -- model for AI-credit CSV rows; '' otherwise
        workflow_path TEXT NOT NULL DEFAULT '',   -- workflow for general usage CSV; '' otherwise
        cost_center_name TEXT DEFAULT '',
        organization TEXT DEFAULT '',
        applied_cost_per_quantity REAL DEFAULT 0,
        total_monthly_quota TEXT DEFAULT '',
        aic_quantity REAL DEFAULT 0,
        aic_gross_amount REAL DEFAULT 0,
        source TEXT DEFAULT '',                   -- import provenance (e.g. csv_ai_usage_report)
        PRIMARY KEY (date, login, sku, repository_name, model, workflow_path)
    );
    """


_BILLING_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_billing_login_date ON billing_usage(login, date);
CREATE INDEX IF NOT EXISTS idx_billing_sku_date ON billing_usage(sku, date);
"""

# Columns preserved when rebuilding an old (pre-model) billing_usage table.
_BILLING_LEGACY_COLUMNS = (
    "date, login, product, sku, unit_type, quantity, "
    "gross_amount_usd, discount_amount_usd, net_amount_usd, repository_name"
)

def _utcnow_iso() -> str:
    """Return a timezone-aware UTC ISO-8601 timestamp."""
    return datetime.now(UTC).isoformat()


def _ensure_parent(path: str) -> None:
    """Create the parent directory of ``path`` if missing."""
    parent = Path(path).parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with Row factory; commits on success."""
    _ensure_parent(settings.db_path)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_billing_usage(conn: sqlite3.Connection) -> None:
    """Create or upgrade ``billing_usage`` to the model-aware schema.

    The primary key gained ``model`` and ``workflow_path`` so CSV AI-credit
    and per-workflow rows stay distinct. SQLite cannot alter a primary key in
    place, so an existing pre-model table is rebuilt while preserving its rows.

    Args:
        conn: An open SQLite connection (used within ``init_db``).
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(billing_usage)")}
    if not cols:
        conn.execute(_billing_table_ddl("billing_usage"))
        conn.executescript(_BILLING_INDEX_DDL)
        return
    if "model" in cols:
        return
    conn.execute(_billing_table_ddl("billing_usage_new"))
    conn.execute(
        f"INSERT INTO billing_usage_new ({_BILLING_LEGACY_COLUMNS}) "
        f"SELECT {_BILLING_LEGACY_COLUMNS} FROM billing_usage"
    )
    conn.execute("DROP TABLE billing_usage")
    conn.execute("ALTER TABLE billing_usage_new RENAME TO billing_usage")
    conn.executescript(_BILLING_INDEX_DDL)


def init_db() -> None:
    """Create all tables if they do not yet exist."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate_billing_usage(conn)


def set_meta(key: str, value: str) -> None:
    """Upsert a meta key/value pair."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_meta(key: str) -> str | None:
    """Return the meta value for ``key`` or ``None`` if absent."""
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def upsert_org_day(
    date: str,
    total_active: int | None,
    total_engaged: int | None,
    raw: dict[str, Any],
) -> None:
    """Upsert the org-level daily metrics row for ``date``."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_org_metrics(date, total_active_users, total_engaged_users, raw_json, fetched_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_active_users=excluded.total_active_users,
                total_engaged_users=excluded.total_engaged_users,
                raw_json=excluded.raw_json,
                fetched_at=excluded.fetched_at
            """,
            (date, total_active, total_engaged, json.dumps(raw), _utcnow_iso()),
        )


def upsert_team_day(
    date: str,
    team_slug: str,
    total_active: int | None,
    total_engaged: int | None,
    raw: dict[str, Any],
) -> None:
    """Upsert per-team daily metrics for ``(date, team_slug)``."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_team_metrics(date, team_slug, total_active_users, total_engaged_users, raw_json, fetched_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, team_slug) DO UPDATE SET
                total_active_users=excluded.total_active_users,
                total_engaged_users=excluded.total_engaged_users,
                raw_json=excluded.raw_json,
                fetched_at=excluded.fetched_at
            """,
            (date, team_slug, total_active, total_engaged, json.dumps(raw), _utcnow_iso()),
        )


def replace_language_rows(date: str, rows: Iterable[dict[str, Any]]) -> None:
    """Replace all language-breakdown rows for ``date``."""
    with connect() as conn:
        conn.execute("DELETE FROM daily_language_metrics WHERE date = ?", (date,))
        conn.executemany(
            """
            INSERT INTO daily_language_metrics(date, language, editor, suggestions, acceptances,
                lines_suggested, lines_accepted, engaged_users)
            VALUES(:date, :language, :editor, :suggestions, :acceptances,
                :lines_suggested, :lines_accepted, :engaged_users)
            """,
            [{"date": date, **r} for r in rows],
        )


def replace_editor_rows(date: str, rows: Iterable[dict[str, Any]]) -> None:
    """Replace all editor-breakdown rows for ``date``."""
    with connect() as conn:
        conn.execute("DELETE FROM daily_editor_metrics WHERE date = ?", (date,))
        conn.executemany(
            """
            INSERT INTO daily_editor_metrics(date, editor, suggestions, acceptances,
                lines_suggested, lines_accepted, chat_total_chats, chat_insertion_events,
                chat_copy_events, engaged_users)
            VALUES(:date, :editor, :suggestions, :acceptances,
                :lines_suggested, :lines_accepted, :chat_total_chats, :chat_insertion_events,
                :chat_copy_events, :engaged_users)
            """,
            [{"date": date, **r} for r in rows],
        )


def get_seat_logins() -> set[str]:
    """Return the set of all logins currently in the seats table."""
    with connect() as conn:
        rows = conn.execute("SELECT login FROM seats").fetchall()
    return {r[0] for r in rows if r[0]}


def replace_seats(seats: list[dict[str, Any]]) -> None:
    """Replace the entire seats table with ``seats``."""
    snapshot_at = _utcnow_iso()
    with connect() as conn:
        conn.execute("DELETE FROM seats")
        conn.executemany(
            """
            INSERT INTO seats(login, team, assigning_team, created_at, updated_at,
                last_activity_at, last_activity_editor, pending_cancellation_date,
                plan_type, raw_json, snapshot_at)
            VALUES(:login, :team, :assigning_team, :created_at, :updated_at,
                :last_activity_at, :last_activity_editor, :pending_cancellation_date,
                :plan_type, :raw_json, :snapshot_at)
            """,
            [{**s, "snapshot_at": snapshot_at} for s in seats],
        )


def replace_model_rows(
    date: str,
    scope: str,
    team_slug: str,
    rows: Iterable[dict[str, Any]],
) -> None:
    """Replace all model-breakdown rows for ``(date, scope, team_slug)``."""
    with connect() as conn:
        conn.execute(
            "DELETE FROM daily_model_metrics WHERE date = ? AND scope = ? AND team_slug = ?",
            (date, scope, team_slug),
        )
        conn.executemany(
            """
            INSERT INTO daily_model_metrics(date, scope, team_slug, editor, model, is_chat,
                suggestions, acceptances, lines_suggested, lines_accepted,
                chats, chat_insertions, chat_copies, engaged_users)
            VALUES(:date, :scope, :team_slug, :editor, :model, :is_chat,
                :suggestions, :acceptances, :lines_suggested, :lines_accepted,
                :chats, :chat_insertions, :chat_copies, :engaged_users)
            """,
            [
                {"date": date, "scope": scope, "team_slug": team_slug, **r}
                for r in rows
            ],
        )


def replace_team_language_rows(
    date: str,
    team_slug: str,
    rows: Iterable[dict[str, Any]],
) -> None:
    """Replace all team-language-breakdown rows for ``(date, team_slug)``."""
    with connect() as conn:
        conn.execute(
            "DELETE FROM daily_team_language_metrics WHERE date = ? AND team_slug = ?",
            (date, team_slug),
        )
        conn.executemany(
            """
            INSERT INTO daily_team_language_metrics(date, team_slug, language, editor,
                suggestions, acceptances, lines_suggested, lines_accepted, engaged_users)
            VALUES(:date, :team_slug, :language, :editor,
                :suggestions, :acceptances, :lines_suggested, :lines_accepted, :engaged_users)
            """,
            [{"date": date, "team_slug": team_slug, **r} for r in rows],
        )


def replace_repos(repos: list[dict[str, Any]]) -> None:
    """Replace the repos table with the latest org repo inventory."""
    fetched_at = _utcnow_iso()
    with connect() as conn:
        conn.execute("DELETE FROM repos")
        conn.executemany(
            """
            INSERT INTO repos(name, full_name, archived, fork, default_branch, updated_at, fetched_at)
            VALUES(:name, :full_name, :archived, :fork, :default_branch, :updated_at, :fetched_at)
            """,
            [{**r, "fetched_at": fetched_at} for r in repos],
        )


def get_repo_last_fetched(repo_name: str) -> tuple[str | None, str | None]:
    """Return ``(updated_at, fetched_at)`` for a repo, or ``(None, None)``."""
    with connect() as conn:
        row = conn.execute(
            "SELECT updated_at, fetched_at FROM repos WHERE name = ?", (repo_name,)
        ).fetchone()
        if row:
            return row["updated_at"], row["fetched_at"]
    return None, None


def existing_pr_numbers(repo_name: str) -> set[int]:
    """Return set of PR numbers already stored for ``repo_name`` with detail data."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT number FROM pull_requests WHERE repo = ? AND (additions > 0 OR deletions > 0 OR changed_files > 0)",
            (repo_name,),
        ).fetchall()
    return {r["number"] for r in rows}


def upsert_pull_requests(prs: list[dict[str, Any]]) -> None:
    """Upsert pull request rows (idempotent on ``(repo, number)``).

    On conflict, detail fields (additions, deletions, changed_files, commits)
    are only overwritten when the incoming value is non-zero — this prevents
    list-level rows (which lack detail data) from clobbering previously stored
    detail.
    """
    if not prs:
        return
    fetched_at = _utcnow_iso()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO pull_requests(repo, number, author, state, created_at, merged_at,
                closed_at, additions, deletions, changed_files, comments, review_comments,
                commits, title, base_ref, head_ref, fetched_at)
            VALUES(:repo, :number, :author, :state, :created_at, :merged_at,
                :closed_at, :additions, :deletions, :changed_files, :comments, :review_comments,
                :commits, :title, :base_ref, :head_ref, :fetched_at)
            ON CONFLICT(repo, number) DO UPDATE SET
                author=excluded.author,
                state=excluded.state,
                created_at=excluded.created_at,
                merged_at=excluded.merged_at,
                closed_at=excluded.closed_at,
                additions=CASE WHEN excluded.additions > 0 THEN excluded.additions ELSE pull_requests.additions END,
                deletions=CASE WHEN excluded.deletions > 0 THEN excluded.deletions ELSE pull_requests.deletions END,
                changed_files=CASE WHEN excluded.changed_files > 0 THEN excluded.changed_files ELSE pull_requests.changed_files END,
                comments=excluded.comments,
                review_comments=excluded.review_comments,
                commits=CASE WHEN excluded.commits > 0 THEN excluded.commits ELSE pull_requests.commits END,
                title=excluded.title,
                base_ref=excluded.base_ref,
                head_ref=excluded.head_ref,
                fetched_at=excluded.fetched_at
            """,
            [{**p, "fetched_at": fetched_at} for p in prs],
        )


def replace_team_members(team_slug: str, logins: list[str]) -> None:
    """Replace the members list for ``team_slug``."""
    fetched_at = _utcnow_iso()
    with connect() as conn:
        conn.execute("DELETE FROM team_members WHERE team_slug = ?", (team_slug,))
        conn.executemany(
            "INSERT INTO team_members(team_slug, login, fetched_at) VALUES(?, ?, ?)",
            [(team_slug, login, fetched_at) for login in logins],
        )


def _as_float(value: Any) -> float:
    """Coerce ``value`` to float, returning 0.0 for blank/invalid input."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_billing_row(row: dict[str, Any]) -> dict[str, Any]:
    """Fill a billing row with all schema columns, defaulting new fields.

    Keeps legacy callers (API snapshot, seed) working unchanged: rows without
    the CSV-specific keys get ``model``/``workflow_path`` of ``''`` so their
    effective key matches the original ``(date, login, sku, repository_name)``.
    """
    return {
        "date": row.get("date") or "",
        "login": row.get("login") or "",
        "product": row.get("product") or "Unknown",
        "sku": row.get("sku") or "Unknown",
        "unit_type": row.get("unit_type") or "",
        "quantity": _as_float(row.get("quantity")),
        "gross_amount_usd": _as_float(row.get("gross_amount_usd")),
        "discount_amount_usd": _as_float(row.get("discount_amount_usd")),
        "net_amount_usd": _as_float(row.get("net_amount_usd")),
        "repository_name": row.get("repository_name") or "",
        "model": row.get("model") or "",
        "workflow_path": row.get("workflow_path") or "",
        "cost_center_name": row.get("cost_center_name") or "",
        "organization": row.get("organization") or "",
        "applied_cost_per_quantity": _as_float(row.get("applied_cost_per_quantity")),
        "total_monthly_quota": row.get("total_monthly_quota") or "",
        "aic_quantity": _as_float(row.get("aic_quantity")),
        "aic_gross_amount": _as_float(row.get("aic_gross_amount")),
        "source": row.get("source") or "",
    }


_BILLING_INSERT_SQL = """
    INSERT INTO billing_usage(date, login, product, sku, unit_type, quantity,
        gross_amount_usd, discount_amount_usd, net_amount_usd, repository_name,
        model, workflow_path, cost_center_name, organization,
        applied_cost_per_quantity, total_monthly_quota, aic_quantity,
        aic_gross_amount, source)
    VALUES(:date, :login, :product, :sku, :unit_type, :quantity,
        :gross_amount_usd, :discount_amount_usd, :net_amount_usd, :repository_name,
        :model, :workflow_path, :cost_center_name, :organization,
        :applied_cost_per_quantity, :total_monthly_quota, :aic_quantity,
        :aic_gross_amount, :source)
    ON CONFLICT(date, login, sku, repository_name, model, workflow_path) DO UPDATE SET
        quantity=excluded.quantity,
        gross_amount_usd=excluded.gross_amount_usd,
        discount_amount_usd=excluded.discount_amount_usd,
        net_amount_usd=excluded.net_amount_usd,
        product=excluded.product,
        unit_type=excluded.unit_type,
        cost_center_name=excluded.cost_center_name,
        organization=excluded.organization,
        applied_cost_per_quantity=excluded.applied_cost_per_quantity,
        total_monthly_quota=excluded.total_monthly_quota,
        aic_quantity=excluded.aic_quantity,
        aic_gross_amount=excluded.aic_gross_amount,
        source=excluded.source
"""


def replace_billing_usage(rows: list[dict[str, Any]]) -> None:
    """Replace all billing-usage rows in a single transaction.

    Billing usage is full-snapshot per fetch — the API returns the same
    window each time, so replacing is safe and avoids duplicate keys.
    """
    with connect() as conn:
        conn.execute("DELETE FROM billing_usage")
        if not rows:
            return
        conn.executemany(_BILLING_INSERT_SQL, [_normalize_billing_row(r) for r in rows])


def upsert_billing_usage(rows: list[dict[str, Any]]) -> None:
    """Insert or update billing rows without clearing the table.

    Used by partial imports (e.g. CSV billing reports) so that re-importing a
    file is idempotent and does not erase billing rows from other dates or
    sources. Conflicts on the full primary key update the row in place.
    """
    if not rows:
        return
    with connect() as conn:
        conn.executemany(_BILLING_INSERT_SQL, [_normalize_billing_row(r) for r in rows])


# ---------------------------------------------------------------------------
# Full-database export / import (single-file backup of the whole SQLite store)
# ---------------------------------------------------------------------------

SQLITE_MAGIC = b"SQLite format 3\x00"
GZIP_MAGIC = b"\x1f\x8b"
DB_EXPORT_MODES = ("replace", "merge")


def export_database_gzip() -> bytes:
    """Return the entire database as gzip-compressed bytes.

    Uses SQLite's online backup API so a consistent snapshot is produced even
    while the application is reading from the live database.
    """
    _ensure_parent(settings.db_path)
    src = sqlite3.connect(settings.db_path)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    try:
        dst = sqlite3.connect(tmp_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
        raw = Path(tmp_path).read_bytes()
    finally:
        src.close()
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
    return gzip.compress(raw, compresslevel=6)


def is_database_export(content: bytes) -> bool:
    """Return True if ``content`` looks like a (optionally gzipped) DB export."""
    if content[:2] == GZIP_MAGIC:
        try:
            head = gzip.decompress(content[: 1 << 20])
        except (OSError, EOFError):
            # Truncated gzip stream still starts with our DB once fully decoded;
            # fall back to magic-only detection on the compressed wrapper.
            return True
        return head[: len(SQLITE_MAGIC)] == SQLITE_MAGIC
    return content[: len(SQLITE_MAGIC)] == SQLITE_MAGIC


def import_database(content: bytes, mode: str) -> dict[str, Any]:
    """Import a full-database export, replacing or merging into the live DB.

    Args:
        content: Raw upload bytes — a SQLite file, optionally gzip-compressed.
        mode: ``"replace"`` wipes each shared table before copying;
            ``"merge"`` upserts rows (``INSERT OR REPLACE``) keyed by primary key.

    Returns:
        Summary with the mode and post-import row count per table.

    Raises:
        ValueError: If ``mode`` is invalid or ``content`` is not a SQLite export.
    """
    if mode not in DB_EXPORT_MODES:
        raise ValueError(f"invalid import mode '{mode}'; expected one of {DB_EXPORT_MODES}")
    raw = gzip.decompress(content) if content[:2] == GZIP_MAGIC else content
    if raw[: len(SQLITE_MAGIC)] != SQLITE_MAGIC:
        raise ValueError("uploaded file is not a valid SQLite database export")

    # Ensure the live DB exists with the current schema before importing into it.
    init_db()

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.write(tmp_fd, raw)
    os.close(tmp_fd)
    try:
        _validate_sqlite_file(tmp_path)
        return _copy_database(tmp_path, mode)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)


def _validate_sqlite_file(path: str) -> None:
    """Open ``path`` read-only to confirm it is a usable SQLite database."""
    probe = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        probe.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"uploaded database could not be opened: {exc}") from exc
    finally:
        probe.close()


def _copy_database(src_path: str, mode: str) -> dict[str, Any]:
    """Copy shared tables from ``src_path`` into the live DB under one transaction."""
    _ensure_parent(settings.db_path)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    tables: dict[str, int] = {}
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("ATTACH DATABASE ? AS src", (src_path,))
        src_tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM src.sqlite_master WHERE type='table'")
        }
        dest_tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM main.sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        conn.execute("BEGIN")
        for table in dest_tables:
            if table not in src_tables:
                continue
            dest_cols = [r["name"] for r in conn.execute(f'PRAGMA main.table_info("{table}")')]
            src_cols = {r["name"] for r in conn.execute(f'PRAGMA src.table_info("{table}")')}
            shared = [c for c in dest_cols if c in src_cols]
            if not shared:
                continue
            col_list = ",".join(f'"{c}"' for c in shared)
            if mode == "replace":
                conn.execute(f'DELETE FROM main."{table}"')
            verb = "INSERT OR REPLACE INTO" if mode == "merge" else "INSERT INTO"
            conn.execute(
                f'{verb} main."{table}"({col_list}) SELECT {col_list} FROM src."{table}"'
            )
            tables[table] = conn.execute(
                f'SELECT COUNT(*) AS n FROM main."{table}"'
            ).fetchone()["n"]
        conn.execute("COMMIT")
        conn.execute("DETACH DATABASE src")
    except Exception:
        conn.rollback()
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("DETACH DATABASE src")
        raise
    finally:
        conn.close()
    return {"mode": mode, "tables": tables}

