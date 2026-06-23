"""Shared pytest fixtures."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point ``settings.db_path`` at a per-test SQLite file.

    Yields:
        Path to the temporary SQLite file.
    """
    from app import config

    db_file = tmp_path / "test.db"
    monkeypatch.setattr(config.settings, "db_path", str(db_file))
    yield db_file
