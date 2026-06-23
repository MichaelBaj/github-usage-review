"""Tests for the snapshot flattener functions (pure, no I/O)."""
from __future__ import annotations

from app.snapshot import _flatten_editors, _flatten_languages, _normalize_seat


def _sample_day() -> dict:
    """Return a minimal Copilot metrics day record covering both code and chat."""
    return {
        "date": "2026-06-01",
        "total_active_users": 12,
        "total_engaged_users": 10,
        "copilot_ide_code_completions": {
            "editors": [
                {
                    "name": "vscode",
                    "total_engaged_users": 8,
                    "models": [
                        {
                            "languages": [
                                {
                                    "name": "python",
                                    "total_code_suggestions": 100,
                                    "total_code_acceptances": 40,
                                    "total_code_lines_suggested": 200,
                                    "total_code_lines_accepted": 75,
                                    "total_engaged_users": 6,
                                },
                                {
                                    "name": "typescript",
                                    "total_code_suggestions": 50,
                                    "total_code_acceptances": 20,
                                    "total_code_lines_suggested": 80,
                                    "total_code_lines_accepted": 30,
                                    "total_engaged_users": 3,
                                },
                            ]
                        }
                    ],
                }
            ]
        },
        "copilot_ide_chat": {
            "editors": [
                {
                    "name": "vscode",
                    "models": [
                        {
                            "total_chats": 25,
                            "total_chat_insertion_events": 5,
                            "total_chat_copy_events": 7,
                        }
                    ],
                }
            ]
        },
    }


def test_flatten_languages_returns_one_row_per_language_editor_pair() -> None:
    """Each (language, editor) pair becomes one row with summed metrics."""
    # Arrange
    day = _sample_day()

    # Act
    rows = _flatten_languages(day)

    # Assert
    assert len(rows) == 2
    by_lang = {r["language"]: r for r in rows}
    assert by_lang["python"]["acceptances"] == 40
    assert by_lang["typescript"]["lines_accepted"] == 30
    assert all(r["editor"] == "vscode" for r in rows)


def test_flatten_languages_collapses_duplicate_models() -> None:
    """Rows for the same language across multiple models are summed."""
    # Arrange
    day = _sample_day()
    day["copilot_ide_code_completions"]["editors"][0]["models"].append(
        {
            "languages": [
                {
                    "name": "python",
                    "total_code_suggestions": 10,
                    "total_code_acceptances": 5,
                    "total_code_lines_suggested": 20,
                    "total_code_lines_accepted": 8,
                    "total_engaged_users": 1,
                }
            ]
        }
    )

    # Act
    rows = _flatten_languages(day)

    # Assert
    py_row = next(r for r in rows if r["language"] == "python")
    assert py_row["suggestions"] == 110
    assert py_row["acceptances"] == 45


def test_flatten_languages_handles_empty_day() -> None:
    """A day with no completions returns an empty list, not an error."""
    # Arrange
    empty: dict = {"date": "2026-06-01"}

    # Act
    rows = _flatten_languages(empty)

    # Assert
    assert rows == []


def test_flatten_editors_combines_code_and_chat() -> None:
    """Editor rows include both code-completion totals and chat events."""
    # Arrange
    day = _sample_day()

    # Act
    rows = _flatten_editors(day)

    # Assert
    assert len(rows) == 1
    row = rows[0]
    assert row["editor"] == "vscode"
    assert row["suggestions"] == 150
    assert row["acceptances"] == 60
    assert row["chat_total_chats"] == 25
    assert row["chat_copy_events"] == 7
    assert row["engaged_users"] == 8


def test_normalize_seat_extracts_assignee_login() -> None:
    """A seat record is flattened into the storage shape with login present."""
    # Arrange
    seat = {
        "assignee": {"login": "alice"},
        "assigning_team": {"slug": "platform", "name": "Platform"},
        "created_at": "2026-01-01T00:00:00Z",
        "last_activity_at": "2026-05-30T12:00:00Z",
        "last_activity_editor": "vscode",
    }

    # Act
    normalized = _normalize_seat(seat)

    # Assert
    assert normalized["login"] == "alice"
    assert normalized["team"] == "platform"
    assert normalized["assigning_team"] == "Platform"
    assert normalized["last_activity_editor"] == "vscode"
    assert "raw_json" in normalized
