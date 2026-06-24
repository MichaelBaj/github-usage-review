"""Tests for local Copilot usage file imports."""
from __future__ import annotations

import json

import pytest

from app import analytics, db
from app.importer import ImportValidationError, import_usage_file


def _api_day(date: str = "2026-06-01", suggestions: int = 10) -> dict:
    """Build a minimal Copilot Metrics API-shaped day."""
    return {
        "date": date,
        "total_active_users": 3,
        "total_engaged_users": 2,
        "copilot_ide_code_completions": {
            "editors": [
                {
                    "name": "vscode",
                    "total_engaged_users": 2,
                    "models": [
                        {
                            "name": "gpt-4o",
                            "total_engaged_users": 2,
                            "languages": [
                                {
                                    "name": "python",
                                    "total_code_suggestions": suggestions,
                                    "total_code_acceptances": 4,
                                    "total_code_lines_suggested": 20,
                                    "total_code_lines_accepted": 8,
                                    "total_engaged_users": 2,
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    }


def _export_row(
    login: str,
    day: str = "2026-06-02",
    generation: int = 5,
    acceptance: int = 2,
) -> dict:
    """Build a minimal GitHub per-user-per-day export row."""
    return {
        "day": day,
        "user_id": hash(login) % 10000,
        "user_login": login,
        "user_initiated_interaction_count": 3,
        "code_generation_activity_count": generation,
        "code_acceptance_activity_count": acceptance,
        "used_chat": True,
        "totals_by_ide": [
            {
                "ide": "vscode",
                "user_initiated_interaction_count": 3,
                "code_generation_activity_count": generation,
                "code_acceptance_activity_count": acceptance,
            }
        ],
        "totals_by_feature": [
            {
                "feature": "code_completion",
                "code_generation_activity_count": generation,
                "code_acceptance_activity_count": acceptance,
                "loc_suggested_to_add_sum": generation * 2,
                "loc_added_sum": acceptance * 2,
            },
            {
                "feature": "chat_panel_agent_mode",
                "user_initiated_interaction_count": 3,
                "code_generation_activity_count": 1,
                "code_acceptance_activity_count": 0,
            },
        ],
        "totals_by_language_feature": [
            {
                "language": "python",
                "feature": "code_completion",
                "code_generation_activity_count": generation,
                "code_acceptance_activity_count": acceptance,
                "loc_suggested_to_add_sum": generation * 2,
                "loc_added_sum": acceptance * 2,
            }
        ],
        "totals_by_model_feature": [
            {
                "model": "gpt-4o-copilot",
                "feature": "code_completion",
                "code_generation_activity_count": generation,
                "code_acceptance_activity_count": acceptance,
                "loc_suggested_to_add_sum": generation * 2,
                "loc_added_sum": acceptance * 2,
            },
            {
                "model": "claude-opus-4.7",
                "feature": "copilot_cli",
                "user_initiated_interaction_count": 3,
            },
        ],
    }


def test_import_usage_file_api_array_imports_metrics_day() -> None:
    """API-shaped JSON arrays reuse snapshot normalization."""
    # Arrange
    db.init_db()
    content = json.dumps([_api_day()]).encode()

    # Act
    result = import_usage_file("metrics.json", content)

    # Assert
    assert result["source_type"] == "api_json"
    assert result["rows_imported"] == 1
    trend = analytics.trends(start="2026-06-01", end="2026-06-01")
    assert trend[0]["suggestions"] == 10
    assert trend[0]["acceptances"] == 4


def test_import_usage_file_ndjson_aggregates_users_and_breakdowns() -> None:
    """NDJSON export rows aggregate to org daily metrics and model rows."""
    # Arrange
    db.init_db()
    content = "\n".join(json.dumps(row) for row in [_export_row("alice"), _export_row("bob")]).encode()

    # Act
    result = import_usage_file("export.ndjson", content)

    # Assert
    assert result["source_type"] == "github_export_ndjson"
    assert result["rows_imported"] == 2
    trend = analytics.trends(start="2026-06-02", end="2026-06-02")
    assert trend[0]["active_users"] == 2
    assert trend[0]["engaged_users"] == 2
    assert trend[0]["lines_suggested"] == 20
    models = analytics.model_breakdown(start="2026-06-02", end="2026-06-02")
    assert models["code"][0]["suggestions"] == 10
    assert models["chat"][0]["chats"] == 6


def test_import_usage_file_reimport_overwrites_existing_date() -> None:
    """Re-importing the same date replaces rows instead of duplicating them."""
    # Arrange
    db.init_db()
    first = json.dumps([_api_day(suggestions=10)]).encode()
    second = json.dumps([_api_day(suggestions=25)]).encode()

    # Act
    import_usage_file("metrics.json", first)
    result = import_usage_file("metrics.json", second)

    # Assert
    assert result["overwritten"] == [{"date": "2026-06-01", "scope": "org"}]
    trend = analytics.trends(start="2026-06-01", end="2026-06-01")
    assert len(trend) == 1
    assert trend[0]["suggestions"] == 25


def test_import_usage_file_malformed_ndjson_lines_warn_and_continue() -> None:
    """Malformed NDJSON lines are skipped while valid rows import."""
    # Arrange
    db.init_db()
    content = f"not-json\n{json.dumps(_export_row('alice'))}\n[]\n".encode()

    # Act
    result = import_usage_file("export.jsonl", content)

    # Assert
    assert result["rows_imported"] == 1
    assert result["skipped_rows"] == 2
    assert len(result["warnings"]) == 2


def test_import_usage_file_sparse_export_leaves_absent_sources_empty() -> None:
    """Sparse imports do not fabricate team, seat, billing, or PR data."""
    # Arrange
    db.init_db()
    content = json.dumps([_export_row("alice")]).encode()

    # Act
    import_usage_file("export.json", content)

    # Assert
    assert analytics.teams_leaderboard(start="2026-06-02", end="2026-06-02") == []
    assert analytics.users_list(start="2026-06-02", end="2026-06-02") == []
    assert analytics.ai_credits_summary(start="2026-06-02", end="2026-06-02")["available"] is False


def test_import_usage_file_completely_invalid_file_fails() -> None:
    """A file with no valid records raises a clear validation error."""
    # Arrange
    db.init_db()

    # Act / Assert
    with pytest.raises(ImportValidationError, match="no valid records"):
        import_usage_file("export.ndjson", b"not-json\n")


def _real_shape_row(
    login: str,
    day: str = "2026-06-04",
) -> dict:
    """Build an export row matching the real GitHub export structure.

    Covers multiple features (code_completion, chat_panel_agent_mode,
    copilot_cli, agent_edit), per-IDE totals, and per-model breakdowns so
    the importer's feature-kind mapping is exercised end to end.
    """
    return {
        "report_start_day": "2026-05-20",
        "report_end_day": "2026-06-16",
        "day": day,
        "organization_id": "94717918",
        "enterprise_id": "7342",
        "user_id": 156003204,
        "user_login": login,
        "user_initiated_interaction_count": 25,
        "code_generation_activity_count": 20,
        "code_acceptance_activity_count": 3,
        "used_agent": True,
        "used_chat": True,
        "loc_suggested_to_add_sum": 23,
        "loc_added_sum": 9,
        "totals_by_ide": [
            {
                "ide": "vscode",
                "user_initiated_interaction_count": 18,
                "code_generation_activity_count": 20,
                "code_acceptance_activity_count": 3,
                "loc_suggested_to_add_sum": 23,
                "loc_added_sum": 9,
            }
        ],
        "totals_by_feature": [
            {
                "feature": "chat_panel_agent_mode",
                "user_initiated_interaction_count": 18,
                "code_generation_activity_count": 3,
                "code_acceptance_activity_count": 1,
                "loc_suggested_to_add_sum": 7,
                "loc_added_sum": 3,
            },
            {
                "feature": "code_completion",
                "user_initiated_interaction_count": 0,
                "code_generation_activity_count": 16,
                "code_acceptance_activity_count": 2,
                "loc_suggested_to_add_sum": 16,
                "loc_added_sum": 2,
            },
            {
                "feature": "copilot_cli",
                "user_initiated_interaction_count": 7,
                "code_generation_activity_count": 0,
                "code_acceptance_activity_count": 0,
            },
            {
                "feature": "agent_edit",
                "user_initiated_interaction_count": 0,
                "code_generation_activity_count": 1,
                "code_acceptance_activity_count": 0,
                "loc_added_sum": 4,
            },
        ],
        "totals_by_language_feature": [
            {
                "language": "shellscript",
                "feature": "code_completion",
                "code_generation_activity_count": 15,
                "code_acceptance_activity_count": 2,
                "loc_suggested_to_add_sum": 15,
                "loc_added_sum": 2,
            },
            {
                "language": "bash",
                "feature": "chat_panel_agent_mode",
                "code_generation_activity_count": 3,
                "code_acceptance_activity_count": 1,
                "loc_suggested_to_add_sum": 7,
                "loc_added_sum": 3,
            },
        ],
        "totals_by_model_feature": [
            {
                "model": "claude-opus-4.6",
                "feature": "chat_panel_agent_mode",
                "user_initiated_interaction_count": 18,
                "code_generation_activity_count": 3,
                "code_acceptance_activity_count": 1,
                "loc_suggested_to_add_sum": 7,
                "loc_added_sum": 3,
            },
            {
                "model": "gpt-5.2",
                "feature": "copilot_cli",
                "user_initiated_interaction_count": 7,
            },
            {
                "model": "gpt-4o-copilot",
                "feature": "code_completion",
                "code_generation_activity_count": 16,
                "code_acceptance_activity_count": 2,
                "loc_suggested_to_add_sum": 16,
                "loc_added_sum": 2,
            },
        ],
    }


def test_import_usage_file_real_shape_maps_features_and_loc() -> None:
    """A real-shape export row maps code/chat features and LOC fields correctly."""
    # Arrange
    db.init_db()
    content = json.dumps([_real_shape_row("aakshat")]).encode()

    # Act
    result = import_usage_file("export.json", content)

    # Assert
    assert result["source_type"] == "github_export_json"
    assert result["rows_imported"] == 1
    trend = analytics.trends(start="2026-06-04", end="2026-06-04")
    assert trend[0]["lines_suggested"] == 15  # only code_completion language rows
    assert trend[0]["lines_accepted"] == 2
    models = analytics.model_breakdown(start="2026-06-04", end="2026-06-04")
    code_models = {m["model"] for m in models["code"]}
    chat_models = {m["model"] for m in models["chat"]}
    assert "gpt-4o-copilot" in code_models
    assert {"claude-opus-4.6", "gpt-5.2"} <= chat_models


def test_import_usage_file_real_shape_aggregates_multiple_days() -> None:
    """Rows across multiple days create one org row per distinct day."""
    # Arrange
    db.init_db()
    rows = [
        _real_shape_row("aakshat", day="2026-06-04"),
        _real_shape_row("madhu", day="2026-06-04"),
        _real_shape_row("syan", day="2026-06-05"),
    ]
    content = "\n".join(json.dumps(row) for row in rows).encode()

    # Act
    result = import_usage_file("export.ndjson", content)

    # Assert
    assert result["rows_imported"] == 3
    assert result["date_range"] == {"start": "2026-06-04", "end": "2026-06-05"}
    trend = analytics.trends(start="2026-06-04", end="2026-06-05")
    by_date = {row["date"]: row for row in trend}
    assert by_date["2026-06-04"]["active_users"] == 2
    assert by_date["2026-06-05"]["active_users"] == 1


def test_import_export_without_totals_by_model_feature_populates_model_metrics() -> None:
    """Export rows with totals_by_feature but no totals_by_model_feature still populate daily_model_metrics."""
    # Arrange
    db.init_db()
    row = _export_row("alice", generation=8, acceptance=3)
    del row["totals_by_model_feature"]
    content = json.dumps(row).encode()

    # Act
    result = import_usage_file("export.ndjson", content)

    # Assert
    assert result["rows_imported"] == 1
    models = analytics.model_breakdown(start="2026-06-02", end="2026-06-02")
    code_sug = sum(r["suggestions"] for r in models["code"])
    code_acc = sum(r["acceptances"] for r in models["code"])
    assert code_sug == 8, f"expected 8 code suggestions, got {code_sug}"
    assert code_acc == 3, f"expected 3 code acceptances, got {code_acc}"
    # Chat interactions from totals_by_feature fallback
    chat_total = sum(r["chats"] for r in models["chat"])


def test_import_export_populates_chat_insertions_from_acceptance_count() -> None:
    """Export chat features map code_acceptance_activity_count → chat_insertions."""
    # Arrange
    db.init_db()
    row = _export_row("alice", generation=5, acceptance=2)
    # Add acceptance count to the chat feature entry
    row["totals_by_feature"][1]["code_acceptance_activity_count"] = 4
    row["totals_by_model_feature"].append({
        "model": "claude-opus-4.7",
        "feature": "chat_panel_agent_mode",
        "user_initiated_interaction_count": 5,
        "code_acceptance_activity_count": 4,
    })
    content = json.dumps(row).encode()

    # Act
    import_usage_file("export.ndjson", content)

    # Assert
    models = analytics.model_breakdown(start="2026-06-02", end="2026-06-02")
    chat_insertions = sum(r["chat_insertions"] for r in models["chat"])
    assert chat_insertions == 4, f"expected 4 chat_insertions, got {chat_insertions}"


def test_api_day_invalid_date_reports_validation_error() -> None:
    """API day with non-date string fails with schema validation."""
    # Arrange
    db.init_db()
    bad_day = {
        "date": "not-a-date",
        "total_active_users": 3,
        "copilot_ide_code_completions": {"editors": []},
    }
    content = json.dumps([bad_day]).encode()

    # Act + Assert
    with pytest.raises(ImportValidationError, match="Validation Errors"):
        import_usage_file("metrics.json", content)


def test_export_row_invalid_date_reports_validation_error() -> None:
    """Export row with non-date day field fails with schema validation error and remediation prompt."""
    # Arrange
    db.init_db()
    bad_row = {"day": "not-a-date", "user_login": "alice", "user_id": 1}
    content = json.dumps(bad_row).encode()

    # Act + Assert — all rows invalid → ImportValidationError with remediation prompt
    with pytest.raises(ImportValidationError, match="Validation Errors"):
        import_usage_file("export.ndjson", content)

def test_import_export_filters_active_users_to_org_seats() -> None:
    """Enterprise-wide exports count only users present in the seats table."""
    # Arrange
    db.init_db()
    # Seed seats — only alice is in the org
    db.replace_seats([
        {
            "login": "alice",
            "team": "core",
            "assigning_team": "core",
            "created_at": "2026-05-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
            "last_activity_at": "2026-06-02T00:00:00Z",
            "last_activity_editor": "vscode",
            "pending_cancellation_date": None,
            "plan_type": "business",
            "raw_json": "{}",
        }
    ])
    # Import with 3 users — only alice should count as active/engaged
    rows = [
        _export_row("alice"),
        _export_row("bob"),
        _export_row("charlie"),
    ]
    content = json.dumps(rows).encode()

    # Act
    result = import_usage_file("export.json", content)

    # Assert — all 3 rows imported but active/engaged filtered to 1
    assert result["rows_imported"] == 3
    assert any("filtered" in w for w in result["warnings"])
    trend = analytics.trends(start="2026-06-02", end="2026-06-02")
    assert trend[0]["active_users"] == 1
    assert trend[0]["engaged_users"] == 1


def test_import_export_no_seats_skips_filtering() -> None:
    """When seats table is empty, all users count (no filtering)."""
    # Arrange
    db.init_db()
    rows = [_export_row("alice"), _export_row("bob")]
    content = json.dumps(rows).encode()

    # Act
    result = import_usage_file("export.json", content)

    # Assert — no filtering applied
    assert not any("filtered" in w for w in result.get("warnings", []))
    trend = analytics.trends(start="2026-06-02", end="2026-06-02")
    assert trend[0]["active_users"] == 2