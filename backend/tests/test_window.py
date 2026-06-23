"""Tests for the window-resolution helper used by all time-range analytics."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.analytics import _window


def test_window_defaults_to_30_days_ending_today() -> None:
    """When no params are supplied, the window spans the default size ending today."""
    # Act
    start, end, n = _window()

    # Assert
    today = datetime.now(UTC).date().isoformat()
    assert end == today
    assert n == 30


def test_window_uses_explicit_days() -> None:
    """``days=7`` produces a 7-day window ending today."""
    # Act
    start, end, n = _window(days=7)

    # Assert
    assert n == 7
    assert (datetime.fromisoformat(end).date() - datetime.fromisoformat(start).date()).days == 6


def test_window_uses_explicit_start_and_end() -> None:
    """Explicit dates override ``days`` and define inclusive bounds."""
    # Act
    start, end, n = _window(days=999, start="2026-01-01", end="2026-01-10")

    # Assert
    assert start == "2026-01-01"
    assert end == "2026-01-10"
    assert n == 10


def test_window_swaps_reversed_bounds() -> None:
    """A reversed range is normalized so ``start <= end``."""
    # Act
    start, end, _ = _window(start="2026-02-01", end="2026-01-01")

    # Assert
    assert start == "2026-01-01"
    assert end == "2026-02-01"


def test_window_invalid_dates_fall_back_to_today() -> None:
    """A bad ISO string falls back to today's date for ``end``."""
    # Act
    _, end, _ = _window(end="not-a-date")

    # Assert
    assert end == datetime.now(UTC).date().isoformat()
