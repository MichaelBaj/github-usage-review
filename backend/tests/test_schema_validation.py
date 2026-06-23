"""Tests for Pydantic import schemas and remediation prompt generation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    ApiDay,
    CsvAiUsageRow,
    CsvUsageRow,
    ExportRow,
    ValidationErrorDetail,
    collect_validation_errors,
    generate_remediation_prompt,
)


# ---------------------------------------------------------------------------
# ExportRow
# ---------------------------------------------------------------------------


class TestExportRow:
    """Validation of GitHub per-user export row schema."""

    def test_valid_row_with_user_login(self) -> None:
        """Minimal valid export row with user_login passes."""
        row = ExportRow.model_validate({
            "day": "2026-06-04",
            "user_login": "alice",
        })

        assert row.day == "2026-06-04"
        assert row.user_login == "alice"

    def test_valid_row_with_user_id_only(self) -> None:
        """Export row with user_id but no user_login passes."""
        row = ExportRow.model_validate({
            "day": "2026-06-04",
            "user_id": 12345,
        })

        assert row.user_id == 12345

    def test_missing_user_identity_rejected(self) -> None:
        """Export row without user_login or user_id fails validation."""
        with pytest.raises(ValidationError, match="user_login.*user_id"):
            ExportRow.model_validate({"day": "2026-06-04"})

    def test_invalid_date_format_rejected(self) -> None:
        """Export row with non-date day field fails validation."""
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            ExportRow.model_validate({
                "day": "not-a-date",
                "user_login": "alice",
            })

    def test_extra_fields_tolerated(self) -> None:
        """Extra fields from GitHub don't break validation."""
        row = ExportRow.model_validate({
            "day": "2026-06-04",
            "user_login": "alice",
            "report_start_day": "2026-05-20",
            "enterprise_id": "7342",
        })

        assert row.day == "2026-06-04"

    def test_full_row_with_nested_totals(self) -> None:
        """Full export row with all totals_by_* arrays passes."""
        row = ExportRow.model_validate({
            "day": "2026-06-04",
            "user_login": "alice",
            "user_id": 123,
            "totals_by_ide": [{"ide": "vscode", "code_generation_activity_count": 5}],
            "totals_by_feature": [{"feature": "code_completion"}],
            "totals_by_language_feature": [{"language": "python", "feature": "code_completion"}],
            "totals_by_model_feature": [{"model": "gpt-4o", "feature": "code_completion"}],
        })

        assert len(row.totals_by_ide) == 1
        assert row.totals_by_ide[0].ide == "vscode"

    def test_date_truncated_to_10_chars(self) -> None:
        """Date with trailing content is truncated to YYYY-MM-DD."""
        row = ExportRow.model_validate({
            "day": "2026-06-04T00:00:00Z",
            "user_login": "alice",
        })

        assert row.day == "2026-06-04"


# ---------------------------------------------------------------------------
# ApiDay
# ---------------------------------------------------------------------------


class TestApiDay:
    """Validation of Copilot Metrics API day record schema."""

    def test_valid_day_with_completions(self) -> None:
        """API day with copilot_ide_code_completions passes."""
        day = ApiDay.model_validate({
            "date": "2026-06-01",
            "total_active_users": 3,
            "copilot_ide_code_completions": {"editors": []},
        })

        assert day.date == "2026-06-01"
        assert day.total_active_users == 3

    def test_valid_day_with_chat_only(self) -> None:
        """API day with only copilot_ide_chat passes."""
        day = ApiDay.model_validate({
            "date": "2026-06-01",
            "copilot_ide_chat": {"editors": []},
        })

        assert day.copilot_ide_chat is not None

    def test_missing_both_sections_rejected(self) -> None:
        """API day without completions or chat fails."""
        with pytest.raises(ValidationError, match="copilot_ide_code_completions.*copilot_ide_chat"):
            ApiDay.model_validate({"date": "2026-06-01"})

    def test_invalid_date_rejected(self) -> None:
        """API day with bad date format fails."""
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            ApiDay.model_validate({
                "date": "June 1st",
                "copilot_ide_code_completions": {"editors": []},
            })

    def test_extra_fields_tolerated(self) -> None:
        """Extra fields don't break API day validation."""
        day = ApiDay.model_validate({
            "date": "2026-06-01",
            "copilot_ide_code_completions": {"editors": []},
            "copilot_dotcom_pull_requests": {"total": 5},
        })

        assert day.date == "2026-06-01"

    def test_nested_editor_model_language(self) -> None:
        """Full nested structure validates correctly."""
        day = ApiDay.model_validate({
            "date": "2026-06-01",
            "copilot_ide_code_completions": {
                "editors": [{
                    "name": "vscode",
                    "total_engaged_users": 2,
                    "models": [{
                        "name": "gpt-4o",
                        "languages": [{
                            "name": "python",
                            "total_code_suggestions": 10,
                            "total_code_acceptances": 4,
                        }],
                    }],
                }],
            },
        })

        assert day.copilot_ide_code_completions is not None
        editors = day.copilot_ide_code_completions.editors
        assert editors[0].name == "vscode"
        assert editors[0].models[0].languages[0].total_code_suggestions == 10


# ---------------------------------------------------------------------------
# CsvAiUsageRow
# ---------------------------------------------------------------------------


class TestCsvAiUsageRow:
    """Validation of AI usage billing CSV row schema."""

    def test_valid_row(self) -> None:
        """Fully populated AI usage row passes."""
        row = CsvAiUsageRow.model_validate({
            "date": "2026-06-01",
            "sku": "copilot_ai_credit",
            "quantity": 12.0,
            "model": "GPT-4.1",
            "username": "alice",
        })

        assert row.date == "2026-06-01"
        assert row.model == "GPT-4.1"

    def test_empty_sku_rejected(self) -> None:
        """Empty SKU fails validation."""
        with pytest.raises(ValidationError, match="sku"):
            CsvAiUsageRow.model_validate({
                "date": "2026-06-01",
                "sku": "",
                "model": "GPT-4.1",
            })

    def test_empty_model_rejected(self) -> None:
        """Empty model fails for AI usage report rows."""
        with pytest.raises(ValidationError, match="model"):
            CsvAiUsageRow.model_validate({
                "date": "2026-06-01",
                "sku": "copilot_ai_credit",
                "model": "",
            })

    def test_invalid_date_rejected(self) -> None:
        """Non-date string fails validation."""
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            CsvAiUsageRow.model_validate({
                "date": "yesterday",
                "sku": "copilot_ai_credit",
                "model": "GPT-4.1",
            })

    def test_defaults_for_optional_fields(self) -> None:
        """Optional fields default to empty/zero."""
        row = CsvAiUsageRow.model_validate({
            "date": "2026-06-01",
            "sku": "copilot_ai_credit",
            "model": "GPT-4.1",
        })

        assert row.username == ""
        assert row.gross_amount_usd == 0.0
        assert row.repository_name == ""


# ---------------------------------------------------------------------------
# CsvUsageRow
# ---------------------------------------------------------------------------


class TestCsvUsageRow:
    """Validation of general usage billing CSV row schema."""

    def test_valid_row(self) -> None:
        """General usage row with sku passes."""
        row = CsvUsageRow.model_validate({
            "date": "2026-06-01",
            "sku": "Actions Linux",
            "quantity": 100.0,
            "product": "Actions",
        })

        assert row.sku == "Actions Linux"

    def test_empty_sku_rejected(self) -> None:
        """Empty SKU fails validation."""
        with pytest.raises(ValidationError, match="sku"):
            CsvUsageRow.model_validate({
                "date": "2026-06-01",
                "sku": "  ",
                "product": "Actions",
            })

    def test_no_model_field_needed(self) -> None:
        """General usage rows don't require model."""
        row = CsvUsageRow.model_validate({
            "date": "2026-06-01",
            "sku": "Copilot Premium Request",
        })

        assert row.workflow_path == ""


# ---------------------------------------------------------------------------
# collect_validation_errors
# ---------------------------------------------------------------------------


class TestCollectValidationErrors:
    """Converting Pydantic errors into structured details."""

    def test_converts_pydantic_errors(self) -> None:
        """Pydantic error list maps to ValidationErrorDetail entries."""
        try:
            ExportRow.model_validate({"day": "bad-date", "user_login": "x"})
        except ValidationError as exc:
            details = collect_validation_errors(exc.errors(), row_number=5)

        assert len(details) >= 1
        assert details[0].row == 5
        assert details[0].field != ""

    def test_truncates_long_values(self) -> None:
        """Input values longer than 200 chars are truncated."""
        fake_errors = [{"loc": ("field",), "msg": "bad", "input": "x" * 300}]

        details = collect_validation_errors(fake_errors, row_number=1)

        assert len(details[0].value) <= 200


# ---------------------------------------------------------------------------
# generate_remediation_prompt
# ---------------------------------------------------------------------------


class TestRemediationPrompt:
    """Remediation prompt generation from validation errors."""

    def test_empty_errors_returns_empty_string(self) -> None:
        """No errors → empty prompt."""
        result = generate_remediation_prompt([], "csv_ai_usage_report", "test.csv")

        assert result == ""

    def test_prompt_contains_filename_and_format(self) -> None:
        """Prompt includes filename and detected format."""
        errors = [
            ValidationErrorDetail(row=2, field="sku", message="sku must not be empty", value=""),
        ]

        prompt = generate_remediation_prompt(errors, "csv_ai_usage_report", "billing.csv")

        assert "billing.csv" in prompt
        assert "csv_ai_usage_report" in prompt

    def test_prompt_contains_error_table(self) -> None:
        """Prompt has markdown table with row and field info."""
        errors = [
            ValidationErrorDetail(row=3, field="date", message="expected YYYY-MM-DD", value="bad"),
            ValidationErrorDetail(row=5, field="model", message="model must not be empty", value=""),
        ]

        prompt = generate_remediation_prompt(errors, "csv_ai_usage_report", "data.csv")

        assert "| Row |" in prompt
        assert "| 3 |" in prompt
        assert "| 5 |" in prompt

    def test_prompt_contains_fix_instructions(self) -> None:
        """Prompt includes actionable fix instructions."""
        errors = [
            ValidationErrorDetail(row=2, field="sku", message="required", value=""),
        ]

        prompt = generate_remediation_prompt(errors, "csv_usage_report", "report.csv")

        assert "Fix each row" in prompt
        assert "re-upload" in prompt.lower()

    def test_prompt_schema_hint_for_ndjson(self) -> None:
        """NDJSON format gets appropriate schema hint."""
        errors = [
            ValidationErrorDetail(row=1, field="day", message="bad date", value="x"),
        ]

        prompt = generate_remediation_prompt(errors, "github_export_ndjson", "export.ndjson")

        assert "NDJSON" in prompt
        assert "user_login" in prompt

    def test_prompt_schema_hint_for_api_json(self) -> None:
        """API JSON format gets appropriate schema hint."""
        errors = [
            ValidationErrorDetail(row=1, field="date", message="bad", value="x"),
        ]

        prompt = generate_remediation_prompt(errors, "api_json", "metrics.json")

        assert "copilot_ide_code_completions" in prompt
