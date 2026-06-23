"""Tests for the model-breakdown flattener (pure, no I/O)."""
from __future__ import annotations

from app.snapshot import _flatten_models


def _day_with_two_models_and_chat() -> dict:
    """Build a metrics day spanning two code models and a chat model."""
    return {
        "date": "2026-06-01",
        "copilot_ide_code_completions": {
            "editors": [
                {
                    "name": "vscode",
                    "models": [
                        {
                            "name": "gpt-4o-copilot",
                            "total_engaged_users": 5,
                            "languages": [
                                {
                                    "name": "python",
                                    "total_code_suggestions": 100,
                                    "total_code_acceptances": 40,
                                    "total_code_lines_suggested": 200,
                                    "total_code_lines_accepted": 75,
                                },
                                {
                                    "name": "go",
                                    "total_code_suggestions": 50,
                                    "total_code_acceptances": 20,
                                    "total_code_lines_suggested": 80,
                                    "total_code_lines_accepted": 30,
                                },
                            ],
                        },
                        {
                            "name": "claude-3-5-sonnet",
                            "total_engaged_users": 2,
                            "languages": [
                                {
                                    "name": "rust",
                                    "total_code_suggestions": 10,
                                    "total_code_acceptances": 6,
                                    "total_code_lines_suggested": 22,
                                    "total_code_lines_accepted": 14,
                                }
                            ],
                        },
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
                            "name": "gpt-4o",
                            "total_engaged_users": 4,
                            "total_chats": 25,
                            "total_chat_insertion_events": 6,
                            "total_chat_copy_events": 9,
                        }
                    ],
                }
            ]
        },
    }


def test_flatten_models_separates_code_and_chat_rows() -> None:
    """One row per (editor, model, is_chat); chat and code never collapse."""
    # Arrange
    day = _day_with_two_models_and_chat()

    # Act
    rows = _flatten_models(day)

    # Assert
    code_rows = [r for r in rows if r["is_chat"] == 0]
    chat_rows = [r for r in rows if r["is_chat"] == 1]
    assert len(code_rows) == 2
    assert len(chat_rows) == 1
    assert {r["model"] for r in code_rows} == {"gpt-4o-copilot", "claude-3-5-sonnet"}
    assert chat_rows[0]["model"] == "gpt-4o"


def test_flatten_models_sums_languages_per_model() -> None:
    """Per-model code aggregates sum across all languages."""
    # Arrange
    day = _day_with_two_models_and_chat()

    # Act
    rows = _flatten_models(day)

    # Assert
    gpt = next(r for r in rows if r["model"] == "gpt-4o-copilot" and r["is_chat"] == 0)
    assert gpt["suggestions"] == 150  # 100 + 50
    assert gpt["acceptances"] == 60  # 40 + 20
    assert gpt["lines_accepted"] == 105  # 75 + 30


def test_flatten_models_captures_chat_events() -> None:
    """Chat rows surface chat counters and zero out code counters."""
    # Arrange
    day = _day_with_two_models_and_chat()

    # Act
    rows = _flatten_models(day)

    # Assert
    chat = next(r for r in rows if r["is_chat"] == 1)
    assert chat["chats"] == 25
    assert chat["chat_insertions"] == 6
    assert chat["chat_copies"] == 9
    assert chat["suggestions"] == 0
    assert chat["acceptances"] == 0


def test_flatten_models_handles_empty_day() -> None:
    """An empty payload yields an empty list."""
    # Act
    rows = _flatten_models({})

    # Assert
    assert rows == []


def test_flatten_models_defaults_model_name_when_missing() -> None:
    """Models without a ``name`` field default to ``'default'`` so they bucket cleanly."""
    # Arrange
    day = {
        "copilot_ide_code_completions": {
            "editors": [
                {
                    "name": "vscode",
                    "models": [
                        {
                            "languages": [
                                {
                                    "name": "python",
                                    "total_code_suggestions": 5,
                                    "total_code_acceptances": 2,
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    }

    # Act
    rows = _flatten_models(day)

    # Assert
    assert len(rows) == 1
    assert rows[0]["model"] == "default"
    assert rows[0]["suggestions"] == 5
