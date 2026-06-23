"""Pydantic v2 schemas for import file validation.

Each user-facing import format has a corresponding model. Validation errors
produce structured ``ValidationErrorDetail`` entries with row context and a
generated remediation prompt that any coding agent can consume to fix the
source file.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

MAX_VALIDATION_ERRORS = 50


def _check_date_prefix(value: str) -> str:
    """Validate that *value* starts with a ``YYYY-MM-DD`` date prefix."""
    if not _DATE_RE.match(value):
        raise ValueError(f"expected YYYY-MM-DD date, got '{value}'")
    return value[:10]


# ---------------------------------------------------------------------------
# Nested models for JSON/NDJSON sub-structures
# ---------------------------------------------------------------------------


class IdeTotal(BaseModel):
    """Per-IDE activity totals inside an export row."""

    model_config = ConfigDict(extra="allow")

    ide: str = "unknown"
    code_generation_activity_count: int = 0
    code_acceptance_activity_count: int = 0
    loc_suggested_to_add_sum: int = 0
    loc_added_sum: int = 0


class FeatureTotal(BaseModel):
    """Per-feature activity totals inside an export row."""

    model_config = ConfigDict(extra="allow")

    feature: str
    code_generation_activity_count: int = 0
    code_acceptance_activity_count: int = 0
    loc_suggested_to_add_sum: int = 0
    loc_added_sum: int = 0


class LanguageFeatureTotal(BaseModel):
    """Per-language+feature totals inside an export row."""

    model_config = ConfigDict(extra="allow")

    language: str
    feature: str
    code_generation_activity_count: int = 0
    code_acceptance_activity_count: int = 0
    loc_suggested_to_add_sum: int = 0
    loc_added_sum: int = 0


class ModelFeatureTotal(BaseModel):
    """Per-model+feature totals inside an export row."""

    model_config = ConfigDict(extra="allow")

    model: str
    feature: str
    code_generation_activity_count: int = 0
    code_acceptance_activity_count: int = 0


class LanguageBlock(BaseModel):
    """Per-language stats inside a Copilot Metrics API model block."""

    model_config = ConfigDict(extra="allow")

    name: str
    total_code_suggestions: int = 0
    total_code_acceptances: int = 0
    total_code_lines_suggested: int = 0
    total_code_lines_accepted: int = 0
    total_engaged_users: int = 0


class ModelBlock(BaseModel):
    """Per-model stats inside a Copilot Metrics API editor block."""

    model_config = ConfigDict(extra="allow")

    name: str
    total_engaged_users: int = 0
    languages: list[LanguageBlock] = []


class ChatModelBlock(BaseModel):
    """Per-model chat stats inside a Copilot Metrics API chat editor block."""

    model_config = ConfigDict(extra="allow")

    name: str
    total_engaged_users: int = 0
    total_chats: int = 0
    total_chat_insertion_events: int = 0
    total_chat_copy_events: int = 0


class EditorBlock(BaseModel):
    """Per-editor block inside ``copilot_ide_code_completions``."""

    model_config = ConfigDict(extra="allow")

    name: str
    total_engaged_users: int = 0
    models: list[ModelBlock] = []


class ChatEditorBlock(BaseModel):
    """Per-editor block inside ``copilot_ide_chat``."""

    model_config = ConfigDict(extra="allow")

    name: str
    models: list[ChatModelBlock] = []


class CodeCompletions(BaseModel):
    """Top-level ``copilot_ide_code_completions`` wrapper."""

    model_config = ConfigDict(extra="allow")

    editors: list[EditorBlock] = []


class IdeChat(BaseModel):
    """Top-level ``copilot_ide_chat`` wrapper."""

    model_config = ConfigDict(extra="allow")

    editors: list[ChatEditorBlock] = []


# ---------------------------------------------------------------------------
# Top-level import schemas
# ---------------------------------------------------------------------------


class ExportRow(BaseModel):
    """GitHub per-user Copilot usage export row (NDJSON/JSON)."""

    model_config = ConfigDict(extra="allow")

    day: str
    user_login: str | None = None
    user_id: int | str | None = None

    totals_by_ide: list[IdeTotal] = []
    totals_by_feature: list[FeatureTotal] = []
    totals_by_language_feature: list[LanguageFeatureTotal] = []
    totals_by_model_feature: list[ModelFeatureTotal] = []

    @field_validator("day")
    @classmethod
    def _validate_day(cls, value: str) -> str:
        return _check_date_prefix(value)

    @model_validator(mode="after")
    def _require_user_identity(self) -> ExportRow:
        if self.user_login is None and self.user_id is None:
            raise ValueError("export row must have 'user_login' or 'user_id'")
        return self


class ApiDay(BaseModel):
    """Copilot Metrics API day record (JSON array element)."""

    model_config = ConfigDict(extra="allow")

    date: str
    total_active_users: int = 0
    total_engaged_users: int = 0
    copilot_ide_code_completions: CodeCompletions | None = None
    copilot_ide_chat: IdeChat | None = None

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        return _check_date_prefix(value)

    @model_validator(mode="after")
    def _require_at_least_one_section(self) -> ApiDay:
        if self.copilot_ide_code_completions is None and self.copilot_ide_chat is None:
            raise ValueError("API day must have 'copilot_ide_code_completions' or 'copilot_ide_chat'")
        return self


class CsvAiUsageRow(BaseModel):
    """Normalized row from a GitHub AI-usage billing CSV (has ``model`` column)."""

    model_config = ConfigDict(extra="allow")

    date: str
    sku: str
    quantity: float = 0.0
    model: str
    username: str = ""
    product: str = ""
    unit_type: str = ""
    gross_amount_usd: float = 0.0
    discount_amount_usd: float = 0.0
    net_amount_usd: float = 0.0
    repository_name: str = ""
    total_monthly_quota: str = ""

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        return _check_date_prefix(value)

    @field_validator("sku")
    @classmethod
    def _require_sku(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sku must not be empty")
        return value

    @field_validator("model")
    @classmethod
    def _require_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be empty for AI usage report")
        return value


class CsvUsageRow(BaseModel):
    """Normalized row from a GitHub general usage billing CSV."""

    model_config = ConfigDict(extra="allow")

    date: str
    sku: str
    quantity: float = 0.0
    product: str = ""
    username: str = ""
    unit_type: str = ""
    gross_amount_usd: float = 0.0
    discount_amount_usd: float = 0.0
    net_amount_usd: float = 0.0
    repository_name: str = ""
    workflow_path: str = ""

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        return _check_date_prefix(value)

    @field_validator("sku")
    @classmethod
    def _require_sku(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sku must not be empty")
        return value


# ---------------------------------------------------------------------------
# Structured validation error + remediation prompt
# ---------------------------------------------------------------------------


class ValidationErrorDetail(BaseModel):
    """One field-level validation failure with context for remediation."""

    row: int
    field: str
    message: str
    value: str = ""


def collect_validation_errors(
    errors: list[dict[str, Any]],
    row_number: int,
) -> list[ValidationErrorDetail]:
    """Convert a Pydantic ``ValidationError.errors()`` list into flat details."""
    out: list[ValidationErrorDetail] = []
    for err in errors:
        loc = err.get("loc", ())
        field_name = ".".join(str(part) for part in loc) if loc else "unknown"
        value = err.get("input", "")
        out.append(
            ValidationErrorDetail(
                row=row_number,
                field=field_name,
                message=err.get("msg", "validation error"),
                value=str(value)[:200],
            )
        )
    return out


def generate_remediation_prompt(
    errors: list[ValidationErrorDetail],
    source_type: str,
    filename: str,
) -> str:
    """Build a markdown prompt an agent can use to fix the import file.

    Args:
        errors: Structured validation errors collected during import.
        source_type: Detected import format (e.g. ``csv_ai_usage_report``).
        filename: Original uploaded filename.

    Returns:
        Markdown string with context, error details, and fix instructions.
    """
    if not errors:
        return ""

    schema_hints = _schema_hint(source_type)
    error_lines = _format_error_lines(errors)

    return (
        f"## Import Validation Errors — `{filename}`\n\n"
        f"**Detected format:** `{source_type}`\n\n"
        f"### Expected Schema\n\n{schema_hints}\n\n"
        f"### Errors Found ({len(errors)} total)\n\n{error_lines}\n\n"
        "### Instructions\n\n"
        "Fix each row in the source file so it conforms to the expected schema above.\n"
        "- Ensure date fields use `YYYY-MM-DD` format.\n"
        "- Ensure required fields (`sku`, `date`) are never empty.\n"
        "- For AI usage CSVs, every row must have a non-empty `model` column.\n"
        "- For export NDJSON, every row must have `day` plus `user_login` or `user_id`.\n"
        "- For API day JSON, every record must have `date` plus "
        "`copilot_ide_code_completions` or `copilot_ide_chat`.\n"
        "- Numeric fields (`quantity`, `gross_amount`, etc.) must be valid numbers.\n\n"
        "After fixing, re-upload the file.\n"
    )


def _schema_hint(source_type: str) -> str:
    """Return a concise schema description for the given import type."""
    hints: dict[str, str] = {
        "csv_ai_usage_report": (
            "CSV columns: `Date`, `Username`, `Product`, `SKU` (required), "
            "`Unit Type`, `Quantity`, `Model` (required), `Total Monthly Quota`, "
            "`Gross Amount`, `Discount Amount`, `Net Amount`, `Repository`"
        ),
        "csv_usage_report": (
            "CSV columns: `Date`, `Username`, `Product` (required), `SKU` (required), "
            "`Unit Type`, `Quantity`, `Workflow Path`, "
            "`Gross Amount`, `Discount Amount`, `Net Amount`, `Repository`"
        ),
        "api_json": (
            "JSON array of day records. Each record: "
            '`{"date": "YYYY-MM-DD", "total_active_users": N, '
            '"copilot_ide_code_completions": {...}, "copilot_ide_chat": {...}}`'
        ),
        "github_export_json": (
            "JSON array of per-user export rows. Each row: "
            '`{"day": "YYYY-MM-DD", "user_login": "...", "user_id": N, '
            '"totals_by_ide": [...], "totals_by_feature": [...]}`'
        ),
        "github_export_ndjson": (
            "NDJSON (one JSON object per line). Each row: "
            '`{"day": "YYYY-MM-DD", "user_login": "...", "user_id": N, '
            '"totals_by_ide": [...], "totals_by_feature": [...]}`'
        ),
    }
    return hints.get(source_type, f"Unknown format: `{source_type}`")


def _format_error_lines(errors: list[ValidationErrorDetail]) -> str:
    """Format validation errors as a markdown table."""
    lines = ["| Row | Field | Error | Value |", "|-----|-------|-------|-------|"]
    for err in errors[:MAX_VALIDATION_ERRORS]:
        safe_val = err.value.replace("|", "\\|")[:60]
        safe_msg = err.message.replace("|", "\\|")
        lines.append(f"| {err.row} | `{err.field}` | {safe_msg} | `{safe_val}` |")
    if len(errors) > MAX_VALIDATION_ERRORS:
        lines.append(f"\n*… and {len(errors) - MAX_VALIDATION_ERRORS} more errors not shown.*")
    return "\n".join(lines)
