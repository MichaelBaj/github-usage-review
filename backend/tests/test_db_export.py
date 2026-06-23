"""Tests for full-database export and import (replace / merge)."""
from __future__ import annotations

import gzip

import pytest

from app import db


def _seed_billing(login: str, quantity: int) -> None:
    """Insert one billing-usage row for ``login`` with the given quantity."""
    db.upsert_billing_usage(
        [
            {
                "date": "2026-06-01",
                "login": login,
                "sku": "Copilot Premium Request",
                "product": "Copilot",
                "unit_type": "request",
                "quantity": quantity,
                "gross_amount": 0.0,
                "discount_amount": 0.0,
                "net_amount": 0.0,
            }
        ]
    )


def _billing_quantity(login: str) -> int | None:
    """Return the stored quantity for ``login`` or None if absent."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT quantity FROM billing_usage WHERE login = ?", (login,)
        ).fetchone()
    return None if row is None else row["quantity"]


def test_export_produces_gzipped_sqlite() -> None:
    db.init_db()
    _seed_billing("alice", 3)

    payload = db.export_database_gzip()

    assert payload[:2] == db.GZIP_MAGIC
    raw = gzip.decompress(payload)
    assert raw[: len(db.SQLITE_MAGIC)] == db.SQLITE_MAGIC
    assert db.is_database_export(payload)
    assert db.is_database_export(raw)


def test_import_replace_overwrites_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    db.init_db()
    _seed_billing("alice", 3)
    export = db.export_database_gzip()

    # Mutate the live DB after the export was taken.
    _seed_billing("alice", 99)
    _seed_billing("bob", 7)

    result = db.import_database(export, "replace")

    assert result["mode"] == "replace"
    assert _billing_quantity("alice") == 3
    # replace wipes the table, so the post-export row is gone.
    assert _billing_quantity("bob") is None


def test_import_merge_upserts(monkeypatch: pytest.MonkeyPatch) -> None:
    db.init_db()
    _seed_billing("alice", 3)
    export = db.export_database_gzip()

    _seed_billing("alice", 99)
    _seed_billing("bob", 7)

    result = db.import_database(export, "merge")

    assert result["mode"] == "merge"
    # alice's key is overwritten by the export's value.
    assert _billing_quantity("alice") == 3
    # bob was not in the export but merge keeps existing rows.
    assert _billing_quantity("bob") == 7


def test_import_accepts_raw_sqlite_bytes() -> None:
    db.init_db()
    _seed_billing("alice", 5)
    raw = gzip.decompress(db.export_database_gzip())

    _seed_billing("alice", 1)
    db.import_database(raw, "replace")

    assert _billing_quantity("alice") == 5


def test_import_rejects_invalid_mode() -> None:
    db.init_db()
    with pytest.raises(ValueError, match="invalid import mode"):
        db.import_database(db.export_database_gzip(), "overwrite")


def test_import_rejects_non_sqlite_content() -> None:
    db.init_db()
    with pytest.raises(ValueError, match="not a valid SQLite"):
        db.import_database(b"not a database at all", "merge")


def test_is_database_export_rejects_plain_text() -> None:
    assert not db.is_database_export(b"date,sku,quantity\n2026-06-01,x,1\n")
    assert not db.is_database_export(gzip.compress(b"hello world"))
