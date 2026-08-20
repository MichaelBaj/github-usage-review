"""Validates that Copilot Usage Insight and Code Generation Insight files
set the correct, independent meta timestamps after import."""
from __future__ import annotations

import json

from app import db
from app.importer import import_usage_file


def _per_user_record(day: str = "2026-08-18", login: str = "plessard128") -> dict:
    """Code Generation Insight: per-user record from users-1-day endpoint."""
    return {
        "report_start_day": "2026-07-23",
        "report_end_day": "2026-08-19",
        "day": day,
        "organization_id": "94717918",
        "enterprise_id": "7342",
        "user_id": 99365722,
        "user_login": login,
        "user_initiated_interaction_count": 0,
        "code_generation_activity_count": 5,
        "code_acceptance_activity_count": 2,
        "totals_by_ide": [{"ide": "vscode", "code_generation_activity_count": 5, "code_acceptance_activity_count": 2}],
        "totals_by_feature": [{"feature": "code_completion", "code_generation_activity_count": 5, "code_acceptance_activity_count": 2, "loc_suggested_to_add_sum": 10, "loc_added_sum": 4}],
        "totals_by_language_feature": [{"language": "python", "feature": "code_completion", "code_generation_activity_count": 5, "code_acceptance_activity_count": 2, "loc_suggested_to_add_sum": 10, "loc_added_sum": 4}],
        "totals_by_language_model": [],
        "totals_by_model_feature": [{"model": "gpt-4o", "feature": "code_completion", "code_generation_activity_count": 5, "code_acceptance_activity_count": 2}],
        "used_agent": False,
        "used_chat": False,
        "loc_suggested_to_add_sum": 10,
        "loc_deleted_sum": 0,
        "used_cli": False,
        "used_copilot_coding_agent": True,
        "used_copilot_cloud_agent": True,
        "used_copilot_code_review_active": False,
        "used_copilot_code_review_passive": True,
        "ai_adoption_phase": {"phase_number": 3, "phase": "Phase 3", "version": "v1"},
        "ai_credits_used": 57.864515,
        "used_copilot_app": False,
    }


def _aggregated_1day_record(day: str = "2026-08-18") -> dict:
    """Copilot Usage Insight: aggregated org/enterprise 1-day record."""
    return {
        "day": day,
        "enterprise_id": "7342",
        "daily_active_users": 150,
        "monthly_active_users": 500,
        "weekly_active_users": 200,
        "code_generation_activity_count": 2000,
        "code_acceptance_activity_count": 800,
        "loc_suggested_to_add_sum": 5000,
        "loc_added_sum": 2000,
        "loc_deleted_sum": 100,
        "user_initiated_interaction_count": 1500,
        "totals_by_ide": [{"ide": "vscode", "code_generation_activity_count": 2000, "code_acceptance_activity_count": 800, "loc_suggested_to_add_sum": 5000, "loc_added_sum": 2000}],
        "totals_by_feature": [{"feature": "code_completion", "code_generation_activity_count": 2000, "code_acceptance_activity_count": 800, "loc_suggested_to_add_sum": 5000, "loc_added_sum": 2000, "user_initiated_interaction_count": 0}],
        "totals_by_language_feature": [{"language": "python", "feature": "code_completion", "code_generation_activity_count": 2000, "code_acceptance_activity_count": 800, "loc_suggested_to_add_sum": 5000, "loc_added_sum": 2000}],
        "totals_by_model_feature": [{"model": "gpt-4o", "feature": "code_completion", "code_generation_activity_count": 2000, "code_acceptance_activity_count": 800, "loc_suggested_to_add_sum": 5000, "loc_added_sum": 2000}],
        "totals_by_ai_adoption_phase": [],
        "pull_requests": {"total_created": 50, "total_merged": 40},
    }


class TestCodeGenerationInsightTimestamp:
    """Per-user NDJSON (Code Generation Insight) sets github_export_ndjson timestamp."""

    def test_sets_github_export_ndjson_load_at(self) -> None:
        db.init_db()
        content = json.dumps(_per_user_record()).encode()

        result = import_usage_file("c000.ndjson", content)

        assert result["source_type"] == "github_export_ndjson"
        assert db.get_meta("last_github_export_ndjson_load_at") is not None

    def test_does_not_set_copilot_usage_insight_timestamp(self) -> None:
        db.init_db()
        content = json.dumps(_per_user_record()).encode()

        import_usage_file("c000.ndjson", content)

        assert db.get_meta("last_copilot_usage_insight_ndjson_load_at") is None


class TestCopilotUsageInsightTimestamp:
    """Aggregated NDJSON (Copilot Usage Insight) sets copilot_usage_insight_ndjson timestamp."""

    def test_aggregated_1day_sets_copilot_usage_insight_load_at(self) -> None:
        db.init_db()
        content = json.dumps(_aggregated_1day_record()).encode()

        result = import_usage_file("c000.ndjson", content)

        assert result["source_type"] == "copilot_usage_insight_ndjson"
        assert db.get_meta("last_copilot_usage_insight_ndjson_load_at") is not None

    def test_aggregated_1day_does_not_set_code_gen_timestamp(self) -> None:
        db.init_db()
        content = json.dumps(_aggregated_1day_record()).encode()

        import_usage_file("c000.ndjson", content)

        assert db.get_meta("last_github_export_ndjson_load_at") is None

    def test_28day_wrapped_sets_copilot_usage_insight_load_at(self) -> None:
        db.init_db()
        wrapped = {
            "enterprise_id": "7342",
            "report_start_day": "2026-07-22",
            "report_end_day": "2026-08-18",
            "day_totals": [_aggregated_1day_record()],
        }
        content = json.dumps(wrapped).encode()

        result = import_usage_file("c000.ndjson", content)

        assert result["source_type"] == "copilot_usage_insight_ndjson"
        assert db.get_meta("last_copilot_usage_insight_ndjson_load_at") is not None


class TestTimestampsAreIndependent:
    """Importing one file type must not clobber the other's timestamp."""

    def test_code_gen_then_usage_insight(self) -> None:
        db.init_db()
        # Import Code Generation Insight first
        import_usage_file("code-gen.ndjson", json.dumps(_per_user_record()).encode())
        code_gen_ts = db.get_meta("last_github_export_ndjson_load_at")
        assert code_gen_ts is not None

        # Import Copilot Usage Insight second
        import_usage_file("usage-insight.ndjson", json.dumps(_aggregated_1day_record("2026-08-17")).encode())
        usage_ts = db.get_meta("last_copilot_usage_insight_ndjson_load_at")
        assert usage_ts is not None

        # Code gen timestamp should be unchanged
        assert db.get_meta("last_github_export_ndjson_load_at") == code_gen_ts

    def test_usage_insight_then_code_gen(self) -> None:
        db.init_db()
        # Import Copilot Usage Insight first
        import_usage_file("usage-insight.ndjson", json.dumps(_aggregated_1day_record()).encode())
        usage_ts = db.get_meta("last_copilot_usage_insight_ndjson_load_at")
        assert usage_ts is not None

        # Import Code Generation Insight second
        import_usage_file("code-gen.ndjson", json.dumps(_per_user_record("2026-08-17")).encode())
        code_gen_ts = db.get_meta("last_github_export_ndjson_load_at")
        assert code_gen_ts is not None

        # Usage insight timestamp should be unchanged
        assert db.get_meta("last_copilot_usage_insight_ndjson_load_at") == usage_ts


class TestSourceHintOverride:
    """source_hint parameter overrides the auto-detected source_type for timestamp."""

    def test_per_user_with_copilot_usage_insight_hint(self) -> None:
        """Per-user NDJSON imported with copilot_usage_insight_ndjson hint sets that timestamp."""
        db.init_db()
        content = json.dumps(_per_user_record()).encode()

        result = import_usage_file("c000.ndjson", content, source_hint="copilot_usage_insight_ndjson")

        assert result["source_type"] == "copilot_usage_insight_ndjson"
        assert db.get_meta("last_copilot_usage_insight_ndjson_load_at") is not None
        assert db.get_meta("last_github_export_ndjson_load_at") is None

    def test_per_user_with_github_export_hint(self) -> None:
        """Per-user NDJSON imported with github_export_ndjson hint sets that timestamp."""
        db.init_db()
        content = json.dumps(_per_user_record()).encode()

        result = import_usage_file("c000.ndjson", content, source_hint="github_export_ndjson")

        assert result["source_type"] == "github_export_ndjson"
        assert db.get_meta("last_github_export_ndjson_load_at") is not None
        assert db.get_meta("last_copilot_usage_insight_ndjson_load_at") is None

    def test_invalid_source_hint_ignored(self) -> None:
        """Invalid source_hint values are ignored; auto-detection used."""
        db.init_db()
        content = json.dumps(_per_user_record()).encode()

        result = import_usage_file("c000.ndjson", content, source_hint="bogus_type")

        assert result["source_type"] == "github_export_ndjson"
        assert db.get_meta("last_github_export_ndjson_load_at") is not None
