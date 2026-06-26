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


def test_ingest_pr_activity_does_not_skip_repos_on_first_run() -> None:
    """Repos must not be skipped on the first PR ingestion run.

    Regression: replace_repos was called BEFORE the PR-fetching loop,
    causing get_repo_last_fetched to return the just-stored pushed_at.
    The skip-unchanged check then considered every repo already scanned.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app import db
    from app.snapshot import _ingest_pr_activity

    db.init_db()

    fake_repos = [
        {"name": "repo-a", "full_name": "org/repo-a", "pushed_at": "2026-06-25T10:00:00Z",
         "archived": False, "fork": False, "default_branch": "main"},
    ]
    fake_pr = {
        "number": 42, "state": "open", "title": "test PR",
        "user": {"login": "alice"},
        "created_at": "2026-06-24T12:00:00Z", "merged_at": None, "closed_at": None,
        "comments": 0, "review_comments": 0,
        "base": {"ref": "main"}, "head": {"ref": "feat"},
    }

    gh = MagicMock()
    gh.list_org_repos = AsyncMock(return_value=fake_repos)
    gh.get_pull_request = AsyncMock(return_value={
        "additions": 10, "deletions": 3, "changed_files": 2, "commits": 1,
        "comments": 0, "review_comments": 0,
    })

    async def _fake_pulls(repo, state="all", since_iso=None):
        yield fake_pr

    gh.list_repo_pulls = _fake_pulls

    since = "2026-06-01T00:00:00+00:00"
    summary = asyncio.run(
        _ingest_pr_activity(gh, since)
    )

    assert summary["repos_scanned"] >= 1, f"Expected repos scanned >= 1, got {summary}"
    assert summary["prs_upserted"] >= 1, f"Expected PRs upserted >= 1, got {summary}"

    with db.connect() as conn:
        pr_count = conn.execute("SELECT count(*) FROM pull_requests").fetchone()[0]
    assert pr_count >= 1, "PR should be stored in DB"
