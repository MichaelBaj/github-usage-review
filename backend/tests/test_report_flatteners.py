"""Tests for report-format (2026-03-10 API) flattener functions."""
from __future__ import annotations

from app.snapshot import (
    _report_flatten_editors,
    _report_flatten_features,
    _report_flatten_languages,
    _report_flatten_models,
    _report_day_to_raw_json,
)
from app.analytics import _sum_day


def _report_day() -> dict:
    """Minimal report-format day record for testing."""
    return {
        "day": "2026-06-15",
        "daily_active_users": 20,
        "code_generation_activity_count": 500,
        "code_acceptance_activity_count": 200,
        "loc_suggested_to_add_sum": 1000,
        "loc_added_sum": 400,
        "loc_deleted_sum": 50,
        "totals_by_language_feature": [
            {
                "language": "python",
                "feature": "code_completion",
                "code_generation_activity_count": 300,
                "code_acceptance_activity_count": 120,
                "loc_suggested_to_add_sum": 600,
                "loc_added_sum": 240,
            },
            {
                "language": "python",
                "feature": "agent_mode",
                "code_generation_activity_count": 50,
                "code_acceptance_activity_count": 20,
                "loc_suggested_to_add_sum": 100,
                "loc_added_sum": 40,
            },
            {
                "language": "typescript",
                "feature": "code_completion",
                "code_generation_activity_count": 150,
                "code_acceptance_activity_count": 60,
                "loc_suggested_to_add_sum": 300,
                "loc_added_sum": 120,
            },
        ],
        "totals_by_ide": [
            {
                "ide": "vscode",
                "code_generation_activity_count": 400,
                "code_acceptance_activity_count": 160,
                "loc_suggested_to_add_sum": 800,
                "loc_added_sum": 320,
            },
            {
                "ide": "jetbrains",
                "code_generation_activity_count": 100,
                "code_acceptance_activity_count": 40,
                "loc_suggested_to_add_sum": 200,
                "loc_added_sum": 80,
            },
        ],
        "totals_by_model_feature": [
            {
                "model": "gpt-4o",
                "feature": "code_completion",
                "code_generation_activity_count": 350,
                "code_acceptance_activity_count": 140,
                "loc_suggested_to_add_sum": 700,
                "loc_added_sum": 280,
            },
            {
                "model": "gpt-4o",
                "feature": "agent_mode",
                "user_initiated_interaction_count": 30,
                "loc_suggested_to_add_sum": 100,
                "loc_added_sum": 40,
            },
            {
                "model": "claude-sonnet-4",
                "feature": "agent_mode",
                "user_initiated_interaction_count": 20,
                "loc_suggested_to_add_sum": 60,
                "loc_added_sum": 20,
            },
        ],
        "totals_by_feature": [
            {
                "feature": "code_completion",
                "user_initiated_interaction_count": 0,
                "code_generation_activity_count": 450,
                "code_acceptance_activity_count": 180,
                "loc_suggested_to_add_sum": 900,
                "loc_added_sum": 360,
                "loc_deleted_sum": 10,
            },
            {
                "feature": "agent_mode",
                "user_initiated_interaction_count": 50,
                "code_generation_activity_count": 50,
                "code_acceptance_activity_count": 20,
                "loc_suggested_to_add_sum": 100,
                "loc_added_sum": 40,
                "loc_deleted_sum": 40,
            },
        ],
    }


# -- Languages ---------------------------------------------------------------


def test_report_flatten_languages_aggregates_across_features() -> None:
    """Python rows from two features should be summed into one row."""
    rows = _report_flatten_languages(_report_day())
    by_lang = {r["language"]: r for r in rows}
    assert by_lang["python"]["suggestions"] == 350  # 300 + 50
    assert by_lang["python"]["acceptances"] == 140  # 120 + 20
    assert by_lang["python"]["lines_accepted"] == 280  # 240 + 40
    assert by_lang["typescript"]["suggestions"] == 150
    assert all(r["editor"] == "all" for r in rows)


def test_report_flatten_languages_empty() -> None:
    rows = _report_flatten_languages({"day": "2026-01-01"})
    assert rows == []


# -- Editors ------------------------------------------------------------------


def test_report_flatten_editors_maps_ides() -> None:
    rows = _report_flatten_editors(_report_day())
    by_ed = {r["editor"]: r for r in rows}
    assert len(rows) == 2
    assert by_ed["vscode"]["suggestions"] == 400
    assert by_ed["jetbrains"]["acceptances"] == 40
    assert by_ed["vscode"]["chat_total_chats"] == 0  # not available in new API


def test_report_flatten_editors_empty() -> None:
    rows = _report_flatten_editors({"day": "2026-01-01"})
    assert rows == []


# -- Models -------------------------------------------------------------------


def test_report_flatten_models_splits_code_vs_chat() -> None:
    rows = _report_flatten_models(_report_day())
    by_key = {(r["model"], r["is_chat"]): r for r in rows}
    # gpt-4o code_completion → is_chat=0
    assert by_key[("gpt-4o", 0)]["suggestions"] == 350
    # gpt-4o agent_mode → is_chat=1
    assert by_key[("gpt-4o", 1)]["chats"] == 30
    # claude-sonnet-4 agent_mode → is_chat=1
    assert by_key[("claude-sonnet-4", 1)]["chats"] == 20
    assert all(r["editor"] == "all" for r in rows)


def test_report_flatten_models_empty() -> None:
    rows = _report_flatten_models({"day": "2026-01-01"})
    assert rows == []


# -- Features -----------------------------------------------------------------


def test_report_flatten_features_maps_all_fields() -> None:
    rows = _report_flatten_features(_report_day())
    by_feat = {r["feature"]: r for r in rows}
    assert len(rows) == 2
    assert by_feat["code_completion"]["code_generations"] == 450
    assert by_feat["agent_mode"]["interactions"] == 50
    assert by_feat["agent_mode"]["loc_deleted"] == 40


def test_report_flatten_features_empty() -> None:
    rows = _report_flatten_features({"day": "2026-01-01"})
    assert rows == []


# -- Raw JSON marker ----------------------------------------------------------


def test_report_day_to_raw_json_sets_marker() -> None:
    raw = _report_day_to_raw_json(_report_day())
    assert raw["_report"] is True
    assert raw["day"] == "2026-06-15"


# -- Dual-format _sum_day -----------------------------------------------------


def test_sum_day_report_format() -> None:
    raw = _report_day_to_raw_json(_report_day())
    sums = _sum_day(raw)
    assert sums["suggestions"] == 500
    assert sums["acceptances"] == 200
    assert sums["lines_suggested"] == 1000
    assert sums["lines_accepted"] == 400


def test_sum_day_legacy_format() -> None:
    """Legacy format still works unchanged."""
    legacy = {
        "copilot_ide_code_completions": {
            "editors": [
                {
                    "name": "vscode",
                    "models": [
                        {
                            "languages": [
                                {
                                    "name": "python",
                                    "total_code_suggestions": 100,
                                    "total_code_acceptances": 40,
                                    "total_code_lines_suggested": 200,
                                    "total_code_lines_accepted": 75,
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    }
    sums = _sum_day(legacy)
    assert sums["suggestions"] == 100
    assert sums["acceptances"] == 40
