"""Import local Copilot usage export files into the existing metrics store."""
from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import db
from .config import BILLING_MIN_DATE
from .schemas import (
    ApiDay,
    CsvAiUsageRow,
    CsvUsageRow,
    ExportRow,
    ValidationErrorDetail,
    collect_validation_errors,
    generate_remediation_prompt,
)
from .snapshot import _flatten_editors, _flatten_languages, _flatten_models

SUPPORTED_IMPORT_SUFFIXES = {".json", ".jsonl", ".ndjson", ".csv"}
MAX_WARNINGS = 25
MAX_VALIDATION_ERRORS = 50

# CSV billing reports route only into billing_usage; they never synthesize
# activity telemetry (suggestions, acceptances, active/engaged users).
_CSV_BILLING_REQUIRED = {"date", "sku", "quantity"}


class ImportValidationError(ValueError):
    """Raised when an uploaded import file cannot be parsed or contains no rows."""


@dataclass
class ExportDay:
    """Aggregated per-day state from per-user GitHub export rows."""

    date: str
    raw_rows: list[dict[str, Any]] = field(default_factory=list)
    active_users: set[str] = field(default_factory=set)
    engaged_users: set[str] = field(default_factory=set)
    language_rows: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    editor_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_rows: dict[tuple[str, str, int], dict[str, Any]] = field(default_factory=dict)


def import_usage_file(filename: str, content: bytes) -> dict[str, Any]:
    """Import a supported local Copilot usage export file.

    Args:
        filename: Original uploaded filename; suffix determines line-oriented parsing.
        content: Uploaded file bytes already bounded by the API layer.

    Returns:
        Import summary suitable for the API response.

    Raises:
        ImportValidationError: If the file type or content is invalid.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMPORT_SUFFIXES:
        raise ImportValidationError("unsupported file type; upload .json, .jsonl, .ndjson, or .csv")

    if suffix == ".csv":
        summary = _import_csv(content, filename)
        data_load_source = summary["source_type"]
    else:
        if suffix == ".json":
            records, warnings, skipped = _parse_json(content)
        else:
            records, warnings, skipped = _parse_json_lines(content)

        if not records:
            raise ImportValidationError("import file contained no valid records")

        rows_read = len(records) + skipped
        if _is_api_day(records[0]):
            summary = _import_api_days(records, rows_read, skipped, warnings, filename)
        elif _is_export_row(records[0]):
            summary = _import_export_rows(
                records, rows_read, skipped, warnings, source_suffix=suffix, filename=filename,
            )
        else:
            raise ImportValidationError("unrecognized Copilot usage export shape")
        data_load_source = "json_import"

    imported_at = datetime.now(UTC).isoformat()
    summary["imported_at"] = imported_at
    db.set_meta("last_import_at", imported_at)
    db.set_meta("last_data_load_at", imported_at)
    db.set_meta("last_data_load_source", data_load_source)
    return summary


def _parse_json(content: bytes) -> tuple[list[dict[str, Any]], list[str], int]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportValidationError(f"invalid JSON file: {exc}") from exc
    if not isinstance(payload, list):
        raise ImportValidationError("JSON import must be an array of day records or export rows")
    records = [row for row in payload if isinstance(row, dict)]
    skipped = len(payload) - len(records)
    warnings = [f"skipped {skipped} non-object JSON array entries"] if skipped else []
    return records, warnings, skipped


def _parse_json_lines(content: bytes) -> tuple[list[dict[str, Any]], list[str], int]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ImportValidationError(f"invalid UTF-8 file: {exc}") from exc
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    skipped = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            skipped += 1
            _add_warning(warnings, f"line {line_number}: invalid JSON skipped ({exc.msg})")
            continue
        if not isinstance(row, dict):
            skipped += 1
            _add_warning(warnings, f"line {line_number}: non-object row skipped")
            continue
        records.append(row)
    return records, warnings, skipped


# --- CSV billing-report import ------------------------------------------------
#
# Two GitHub billing CSV schemas are supported. Both route exclusively into the
# billing_usage table; no activity telemetry (suggestions, acceptances,
# active/engaged users) is ever synthesized from billing rows.
#   * csv_ai_usage_report — per-user/date/model Copilot AI-credit billing rows
#     (identified by a ``model`` column).
#   * csv_usage_report — general GitHub billing rows across products (Actions,
#     storage, Copilot, …), identified by ``workflow_path``/``product``.

# Canonical CSV field -> accepted header aliases (after header normalization).
_CSV_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "usage_date", "day"),
    "username": ("username", "user", "user_login", "handle", "login"),
    "product": ("product",),
    "sku": ("sku",),
    "unit_type": ("unit_type", "units", "unit"),
    "quantity": ("quantity", "quantity_used"),
    "gross_amount": ("gross_amount", "gross_amount_usd", "gross"),
    "discount_amount": ("discount_amount", "discount_amount_usd", "discount"),
    "net_amount": ("net_amount", "net_amount_usd", "net", "amount"),
    "repository": ("repository", "repository_name", "repository_slug", "repo"),
    "model": ("model",),
    "workflow_path": ("workflow_path", "workflow"),
    "cost_center_name": ("cost_center_name", "cost_center"),
    "organization": ("organization", "org", "owner"),
    "applied_cost_per_quantity": ("applied_cost_per_quantity", "price_per_unit", "cost_per_quantity"),
    "total_monthly_quota": ("total_monthly_quota", "monthly_quota"),
    "aic_quantity": ("aic_quantity",),
    "aic_gross_amount": ("aic_gross_amount",),
}


def _norm_header(header: str) -> str:
    """Normalize a CSV header to a lowercase, underscore-delimited key.

    Strips parenthetical units (e.g. ``"Price Per Unit ($)"`` -> ``price_per_unit``)
    so Title Case headers with spaces map onto canonical field names.
    """
    text = re.sub(r"\(.*?\)", " ", (header or "").strip().lower())
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _parse_csv_rows(content: bytes) -> tuple[set[str], list[dict[str, str]]]:
    """Parse CSV bytes into normalized header set + per-row dicts.

    Uses :class:`csv.DictReader` (not naive splitting) and decodes with
    ``utf-8-sig`` so a leading UTF-8 BOM is stripped transparently.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportValidationError(f"invalid UTF-8 CSV file: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportValidationError("CSV file has no header row")
    field_map = {name: _norm_header(name) for name in reader.fieldnames}
    headers = {value for value in field_map.values() if value}
    rows: list[dict[str, str]] = []
    for raw in reader:
        norm: dict[str, str] = {}
        for original, value in raw.items():
            key = field_map.get(original, "")
            if key:
                norm[key] = (value or "").strip()
        rows.append(norm)
    return headers, rows


def _detect_csv_report(headers: set[str]) -> str | None:
    """Classify a CSV by its header columns, or ``None`` if unrecognized."""
    if not headers >= _CSV_BILLING_REQUIRED:
        return None
    if "model" in headers:
        return "csv_ai_usage_report"
    if "workflow_path" in headers or "product" in headers:
        return "csv_usage_report"
    return None


def _csv_pick(row: dict[str, str], field_name: str) -> str:
    """Return the first non-empty aliased value for ``field_name``."""
    for alias in _CSV_FIELD_ALIASES[field_name]:
        value = row.get(alias)
        if value:
            return value
    return ""


def _csv_float(value: str, warnings: list[str], label: str) -> float:
    """Parse a CSV money/quantity cell, defaulting blanks/invalids to 0.0."""
    if not value:
        return 0.0
    try:
        return float(value.replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        _add_warning(warnings, f"{label}: non-numeric value '{value}' treated as 0")
        return 0.0


def _import_csv(content: bytes, filename: str = "") -> dict[str, Any]:
    """Import a GitHub billing CSV report into the billing-usage store."""
    headers, raw_rows = _parse_csv_rows(content)
    source_type = _detect_csv_report(headers)
    if source_type is None:
        raise ImportValidationError(
            "unrecognized CSV billing report; require columns "
            f"{sorted(_CSV_BILLING_REQUIRED)} plus 'model' (AI usage report) "
            "or 'workflow_path'/'product' (usage report); "
            f"found columns: {sorted(headers)}"
        )

    schema_cls = CsvAiUsageRow if source_type == "csv_ai_usage_report" else CsvUsageRow
    warnings: list[str] = []
    validation_errors: list[ValidationErrorDetail] = []
    skipped = 0
    billing_rows: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows, start=2):  # row 1 is the header line
        date = str(_csv_pick(row, "date"))[:10]
        if not date:
            skipped += 1
            _add_warning(warnings, f"row {index}: missing date skipped")
            continue
        if date < BILLING_MIN_DATE:
            skipped += 1
            _add_warning(warnings, f"row {index}: date {date} before {BILLING_MIN_DATE} skipped")
            continue

        built = {
            "date": date,
            "login": _csv_pick(row, "username").lower(),
            "product": _csv_pick(row, "product") or "Unknown",
            "sku": _csv_pick(row, "sku") or "Unknown",
            "unit_type": _csv_pick(row, "unit_type"),
            "quantity": _csv_float(_csv_pick(row, "quantity"), warnings, f"row {index} quantity"),
            "gross_amount_usd": _csv_float(
                _csv_pick(row, "gross_amount"), warnings, f"row {index} gross_amount"
            ),
            "discount_amount_usd": _csv_float(
                _csv_pick(row, "discount_amount"), warnings, f"row {index} discount_amount"
            ),
            "net_amount_usd": _csv_float(
                _csv_pick(row, "net_amount"), warnings, f"row {index} net_amount"
            ),
            "repository_name": _csv_pick(row, "repository"),
            "model": _csv_pick(row, "model"),
            "workflow_path": _csv_pick(row, "workflow_path"),
            "cost_center_name": _csv_pick(row, "cost_center_name"),
            "organization": _csv_pick(row, "organization"),
            "applied_cost_per_quantity": _csv_float(
                _csv_pick(row, "applied_cost_per_quantity"),
                warnings,
                f"row {index} applied_cost_per_quantity",
            ),
            "total_monthly_quota": _csv_pick(row, "total_monthly_quota"),
            "aic_quantity": _csv_float(
                _csv_pick(row, "aic_quantity"), warnings, f"row {index} aic_quantity"
            ),
            "aic_gross_amount": _csv_float(
                _csv_pick(row, "aic_gross_amount"), warnings, f"row {index} aic_gross_amount"
            ),
            "source": source_type,
        }

        # Schema validation — reject row on failure
        try:
            schema_cls.model_validate({
                "date": built["date"],
                "sku": built["sku"],
                "quantity": built["quantity"],
                "model": built.get("model", ""),
                "product": built["product"],
                "username": built["login"],
                "unit_type": built["unit_type"],
                "gross_amount_usd": built["gross_amount_usd"],
                "discount_amount_usd": built["discount_amount_usd"],
                "net_amount_usd": built["net_amount_usd"],
                "repository_name": built["repository_name"],
                "total_monthly_quota": built.get("total_monthly_quota", ""),
                "workflow_path": built.get("workflow_path", ""),
            })
        except ValidationError as exc:
            skipped += 1
            errs = collect_validation_errors(exc.errors(), index)
            _add_validation_errors(validation_errors, errs)
            _add_warning(warnings, f"row {index}: schema validation failed — {exc.errors()[0]['msg']}")
            continue

        billing_rows.append(built)

    if not billing_rows:
        prompt = generate_remediation_prompt(validation_errors, source_type, filename)
        raise ImportValidationError(
            "CSV file contained no rows with a valid date"
            + (f"\n\n{prompt}" if prompt else "")
        )

    dates = sorted({r["date"] for r in billing_rows})
    overwritten = _existing_billing_dates(dates)
    db.upsert_billing_usage(billing_rows)
    return _summary(
        source_type, len(raw_rows), len(billing_rows), skipped, warnings, dates, overwritten,
        validation_errors=validation_errors, filename=filename,
    )


def _existing_billing_dates(dates: list[str]) -> list[dict[str, str]]:
    """Return ``{date, scope}`` markers for dates already present in billing."""
    if not dates:
        return []
    placeholders = ",".join("?" for _ in dates)
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT date FROM billing_usage WHERE date IN ({placeholders})",
            dates,
        ).fetchall()
    return [{"date": row["date"], "scope": "billing"} for row in rows]


def _import_api_days(
    records: list[dict[str, Any]],
    rows_read: int,
    skipped: int,
    warnings: list[str],
    filename: str = "",
) -> dict[str, Any]:
    days: list[dict[str, Any]] = []
    validation_errors: list[ValidationErrorDetail] = []
    for idx, record in enumerate(records, start=1):
        if not _is_api_day(record):
            skipped += 1
            continue
        try:
            ApiDay.model_validate(record)
        except ValidationError as exc:
            skipped += 1
            errs = collect_validation_errors(exc.errors(), idx)
            _add_validation_errors(validation_errors, errs)
            _add_warning(warnings, f"record {idx}: schema validation failed — {exc.errors()[0]['msg']}")
            continue
        days.append(record)

    if len(days) != len(records) - skipped:
        _add_warning(warnings, "skipped records that were not Copilot Metrics API day records")
    if not days:
        prompt = generate_remediation_prompt(validation_errors, "api_json", filename)
        raise ImportValidationError(
            "JSON file contained no valid Copilot Metrics API day records"
            + (f"\n\n{prompt}" if prompt else "")
        )

    dates = sorted({str(day["date"])[:10] for day in days})
    overwritten = _existing_org_scopes(dates)
    for day in days:
        date = str(day["date"])[:10]
        db.upsert_org_day(
            date,
            _as_int(day.get("total_active_users")),
            _as_int(day.get("total_engaged_users")),
            day,
        )
        db.replace_language_rows(date, _flatten_languages(day))
        db.replace_editor_rows(date, _flatten_editors(day))
        db.replace_model_rows(date, "org", "", _flatten_models(day))

    return _summary(
        "api_json", rows_read, len(days), skipped, warnings, dates, overwritten,
        validation_errors=validation_errors, filename=filename,
    )


def _import_export_rows(
    records: list[dict[str, Any]],
    rows_read: int,
    skipped: int,
    warnings: list[str],
    source_suffix: str,
    filename: str = "",
) -> dict[str, Any]:
    by_day: dict[str, ExportDay] = {}
    imported_rows = 0
    validation_errors: list[ValidationErrorDetail] = []
    for idx, record in enumerate(records, start=1):
        if not _is_export_row(record):
            skipped += 1
            _add_warning(warnings, "skipped row without day/user export fields")
            continue
        try:
            ExportRow.model_validate(record)
        except ValidationError as exc:
            skipped += 1
            errs = collect_validation_errors(exc.errors(), idx)
            _add_validation_errors(validation_errors, errs)
            _add_warning(warnings, f"row {idx}: schema validation failed — {exc.errors()[0]['msg']}")
            continue
        date = str(record["day"])[:10]
        day = by_day.setdefault(date, ExportDay(date=date))
        _accumulate_export_row(day, record)
        imported_rows += 1

    if not by_day:
        source_type = "github_export_json" if source_suffix == ".json" else "github_export_ndjson"
        prompt = generate_remediation_prompt(validation_errors, source_type, filename)
        raise ImportValidationError(
            "file contained no valid GitHub per-user export rows"
            + (f"\n\n{prompt}" if prompt else "")
        )

    dates = sorted(by_day)
    overwritten = _existing_org_scopes(dates)
    for date in dates:
        day = by_day[date]
        raw = _export_day_raw(day)
        db.upsert_org_day(date, len(day.active_users), len(day.engaged_users), raw)
        db.replace_language_rows(date, day.language_rows.values())
        db.replace_editor_rows(date, day.editor_rows.values())
        db.replace_model_rows(date, "org", "", day.model_rows.values())

    source_type = "github_export_json" if source_suffix == ".json" else "github_export_ndjson"
    return _summary(
        source_type, rows_read, imported_rows, skipped, warnings, dates, overwritten,
        validation_errors=validation_errors, filename=filename,
    )


def _accumulate_export_row(day: ExportDay, row: dict[str, Any]) -> None:
    day.raw_rows.append(row)
    user_key = str(row.get("user_login") or row.get("user_id") or "unknown")
    if _has_any_usage(row):
        day.active_users.add(user_key)
    if _has_engagement(row):
        day.engaged_users.add(user_key)

    editors = _row_editors(row)
    for entry in row.get("totals_by_language_feature") or []:
        if _feature_kind(entry.get("feature")) != "code":
            continue
        editor = editors[0]
        key = (str(entry.get("language") or "unknown"), editor)
        bucket = day.language_rows.setdefault(key, _new_language_row(key[0], editor))
        _add_code_metrics(bucket, entry)
        if _has_counter(entry, ("code_generation_activity_count", "code_acceptance_activity_count")):
            bucket["engaged_users"] += 1

    _accumulate_editor_rows(day, row, editors)
    _accumulate_model_rows(day, row, editors[0])


def _accumulate_editor_rows(day: ExportDay, row: dict[str, Any], editors: list[str]) -> None:
    code_totals = _sum_feature_rows(row.get("totals_by_feature") or [], kind="code")
    chat_totals = _sum_feature_rows(row.get("totals_by_feature") or [], kind="chat")
    for editor in editors:
        bucket = day.editor_rows.setdefault(editor, _new_editor_row(editor))
        if len(editors) == 1:
            _add_code_metrics(bucket, code_totals)
            bucket["chat_total_chats"] += _interaction_count(chat_totals)
            bucket["chat_insertion_events"] += _as_int(chat_totals.get("code_acceptance_activity_count"))
        for ide in row.get("totals_by_ide") or []:
            if str(ide.get("ide") or "unknown") == editor:
                bucket["engaged_users"] += 1 if _has_counter(ide, ("code_generation_activity_count", "code_acceptance_activity_count")) else 0


def _accumulate_model_rows(day: ExportDay, row: dict[str, Any], editor: str) -> None:
    model_features = row.get("totals_by_model_feature") or []
    if model_features:
        entries = model_features
    else:
        # Fall back to totals_by_feature (no per-model split) so that
        # code suggestions / acceptances still populate daily_model_metrics.
        entries = [
            {**entry, "model": "unknown"}
            for entry in (row.get("totals_by_feature") or [])
        ]
    for entry in entries:
        kind = _feature_kind(entry.get("feature"))
        if kind == "other":
            continue
        model = str(entry.get("model") or "unknown")
        key = (editor, model, 1 if kind == "chat" else 0)
        bucket = day.model_rows.setdefault(key, _new_model_row(editor, model, key[2]))
        if kind == "code":
            _add_code_metrics(bucket, entry)
        else:
            bucket["chats"] += _interaction_count(entry)
            bucket["chat_insertions"] += _as_int(entry.get("code_acceptance_activity_count"))
        if _has_counter(entry, ("code_generation_activity_count", "code_acceptance_activity_count", "user_initiated_interaction_count")):
            bucket["engaged_users"] += 1


def _export_day_raw(day: ExportDay) -> dict[str, Any]:
    languages = [
        {
            "editor": row["editor"],
            "name": row["language"],
            "total_code_suggestions": row["suggestions"],
            "total_code_acceptances": row["acceptances"],
            "total_code_lines_suggested": row["lines_suggested"],
            "total_code_lines_accepted": row["lines_accepted"],
            "total_engaged_users": row["engaged_users"],
        }
        for row in day.language_rows.values()
    ]
    editor_models = _raw_code_editors(day.editor_rows, languages)
    chat_editors = _raw_chat_editors(day.editor_rows)
    return {
        "date": day.date,
        "total_active_users": len(day.active_users),
        "total_engaged_users": len(day.engaged_users),
        "source": "github_copilot_usage_export",
        "raw_rows": day.raw_rows,
        "copilot_ide_code_completions": {"editors": editor_models},
        "copilot_ide_chat": {"editors": chat_editors},
    }


def _raw_code_editors(
    editor_rows: dict[str, dict[str, Any]],
    languages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_editor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lang in languages:
        by_editor[str(lang.pop("editor", "unknown"))].append(lang)
    return [
        {
            "name": editor,
            "total_engaged_users": editor_rows.get(editor, {}).get("engaged_users", 0),
            "models": [{"name": "github_export", "languages": rows}],
        }
        for editor, rows in by_editor.items()
    ]


def _raw_chat_editors(editor_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": editor,
            "models": [
                {
                    "name": "github_export",
                    "total_engaged_users": row["engaged_users"],
                    "total_chats": row["chat_total_chats"],
                    "total_chat_insertion_events": row["chat_insertion_events"],
                    "total_chat_copy_events": row["chat_copy_events"],
                }
            ],
        }
        for editor, row in editor_rows.items()
        if row["chat_total_chats"]
    ]


def _summary(
    source_type: str,
    rows_read: int,
    rows_imported: int,
    skipped_rows: int,
    warnings: list[str],
    dates: list[str],
    overwritten: list[dict[str, str]],
    *,
    validation_errors: list[ValidationErrorDetail] | None = None,
    filename: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_type": source_type,
        "rows_read": rows_read,
        "rows_imported": rows_imported,
        "skipped_rows": skipped_rows,
        "warnings": warnings,
        "date_range": {"start": dates[0], "end": dates[-1]} if dates else None,
        "overwritten": overwritten,
    }
    if validation_errors:
        result["validation_errors"] = [
            err.model_dump() for err in validation_errors[:MAX_VALIDATION_ERRORS]
        ]
        result["remediation_prompt"] = generate_remediation_prompt(
            validation_errors, source_type, filename,
        )
    return result


def _existing_org_scopes(dates: list[str]) -> list[dict[str, str]]:
    if not dates:
        return []
    placeholders = ",".join("?" for _ in dates)
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT date FROM daily_org_metrics WHERE date IN ({placeholders})",
            dates,
        ).fetchall()
    return [{"date": row["date"], "scope": "org"} for row in rows]


def _is_api_day(record: dict[str, Any]) -> bool:
    return isinstance(record.get("date"), str) and (
        "copilot_ide_code_completions" in record or "copilot_ide_chat" in record
    )


def _is_export_row(record: dict[str, Any]) -> bool:
    return isinstance(record.get("day"), str) and (
        "user_login" in record or "user_id" in record
    )


def _row_editors(row: dict[str, Any]) -> list[str]:
    editors = [str(item.get("ide") or "unknown") for item in row.get("totals_by_ide") or []]
    return editors or ["unknown"]


def _feature_kind(feature: Any) -> str:
    value = str(feature or "").lower()
    if value == "code_completion":
        return "code"
    if "chat" in value or "agent" in value or "cli" in value:
        return "chat"
    return "other"


def _has_any_usage(row: dict[str, Any]) -> bool:
    usage_keys = (
        "user_initiated_interaction_count",
        "code_generation_activity_count",
        "code_acceptance_activity_count",
        "loc_suggested_to_add_sum",
        "loc_added_sum",
    )
    flag_keys = tuple(key for key in row if key.startswith("used_"))
    return _has_counter(row, usage_keys) or any(bool(row.get(key)) for key in flag_keys)


def _has_engagement(row: dict[str, Any]) -> bool:
    return _has_counter(row, ("code_generation_activity_count", "code_acceptance_activity_count"))


def _has_counter(row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_as_int(row.get(key)) > 0 for key in keys)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _interaction_count(row: dict[str, Any]) -> int:
    return _as_int(row.get("user_initiated_interaction_count")) or _as_int(
        row.get("code_generation_activity_count")
    )


def _sum_feature_rows(rows: list[dict[str, Any]], kind: str) -> dict[str, int]:
    totals = {
        "code_generation_activity_count": 0,
        "code_acceptance_activity_count": 0,
        "loc_suggested_to_add_sum": 0,
        "loc_added_sum": 0,
        "user_initiated_interaction_count": 0,
    }
    for row in rows:
        if _feature_kind(row.get("feature")) != kind:
            continue
        for key in totals:
            totals[key] += _as_int(row.get(key))
    return totals


def _add_code_metrics(bucket: dict[str, Any], source: dict[str, Any]) -> None:
    bucket["suggestions"] += _as_int(source.get("code_generation_activity_count"))
    bucket["acceptances"] += _as_int(source.get("code_acceptance_activity_count"))
    bucket["lines_suggested"] += _as_int(source.get("loc_suggested_to_add_sum"))
    bucket["lines_accepted"] += _as_int(source.get("loc_added_sum"))


def _new_language_row(language: str, editor: str) -> dict[str, Any]:
    return {
        "language": language,
        "editor": editor,
        "suggestions": 0,
        "acceptances": 0,
        "lines_suggested": 0,
        "lines_accepted": 0,
        "engaged_users": 0,
    }


def _new_editor_row(editor: str) -> dict[str, Any]:
    return {
        "editor": editor,
        "suggestions": 0,
        "acceptances": 0,
        "lines_suggested": 0,
        "lines_accepted": 0,
        "chat_total_chats": 0,
        "chat_insertion_events": 0,
        "chat_copy_events": 0,
        "engaged_users": 0,
    }


def _new_model_row(editor: str, model: str, is_chat: int) -> dict[str, Any]:
    return {
        "editor": editor,
        "model": model,
        "is_chat": is_chat,
        "suggestions": 0,
        "acceptances": 0,
        "lines_suggested": 0,
        "lines_accepted": 0,
        "chats": 0,
        "chat_insertions": 0,
        "chat_copies": 0,
        "engaged_users": 0,
    }


def _add_warning(warnings: list[str], message: str) -> None:
    if len(warnings) < MAX_WARNINGS:
        warnings.append(message)


def _add_validation_errors(
    target: list[ValidationErrorDetail],
    new_errors: list[ValidationErrorDetail],
) -> None:
    """Append validation errors up to the cap."""
    remaining = MAX_VALIDATION_ERRORS - len(target)
    if remaining > 0:
        target.extend(new_errors[:remaining])