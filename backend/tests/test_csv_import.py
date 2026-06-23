"""Tests for CSV billing-report import (AI usage + general usage schemas)."""
from __future__ import annotations

import pytest

from app import analytics, db
from app.importer import ImportValidationError, import_usage_file

AI_USAGE_CSV = (
    "Date,Username,Product,SKU,Unit Type,Quantity,Model,Total Monthly Quota,"
    "Gross Amount,Discount Amount,Net Amount,Repository\n"
    "2026-06-01,Alice,Copilot,copilot_ai_credit,request,12,GPT-4.1,Unlimited,0.48,0,0.48,\n"
    "2026-06-01,alice,Copilot,copilot_ai_credit,request,8,Claude 3.5 Sonnet,Unlimited,0.32,0,0.32,\n"
    "2026-06-01,bob,Copilot,copilot_ai_credit,request,5,GPT-4.1,Unlimited,0.20,0,0.20,\n"
)

USAGE_CSV = (
    "Date,Username,Product,SKU,Unit Type,Quantity,Workflow Path,"
    "Gross Amount,Discount Amount,Net Amount,Repository\n"
    "2026-06-01,alice,Copilot,Copilot Premium Request,request,10,,0.40,0,0.40,\n"
    "2026-06-01,,Actions,Actions Linux,minute,100,.github/workflows/ci.yml,0.80,0,0.80,acme/app\n"
    "2026-06-01,,Git LFS,Storage,gigabyte-hour,5,,0.05,0,0.05,acme/app\n"
)


def _import(csv_text: str, filename: str) -> dict:
    """Initialize the DB and import a CSV payload by filename."""
    db.init_db()
    return import_usage_file(filename, csv_text.encode("utf-8"))


def test_ai_usage_csv_imports_and_keeps_models_distinct() -> None:
    """AI usage rows import under csv_ai_usage_report without collapsing models."""
    # Act
    summary = _import(AI_USAGE_CSV, "AIUsageReport_2026-06.csv")

    # Assert
    assert summary["source_type"] == "csv_ai_usage_report"
    assert summary["rows_imported"] == 3
    assert summary["skipped_rows"] == 0
    with db.connect() as conn:
        alice_models = conn.execute(
            "SELECT model, quantity FROM billing_usage "
            "WHERE login = 'alice' ORDER BY model"
        ).fetchall()
    # alice has two distinct models on the same date/sku — both preserved.
    assert {r["model"] for r in alice_models} == {"Claude 3.5 Sonnet", "GPT-4.1"}


def test_ai_usage_csv_surfaces_in_premium_summary_and_by_model() -> None:
    """AI-credit rows count as billable Copilot usage and group by model column."""
    # Arrange
    _import(AI_USAGE_CSV, "AIUsageReport.csv")

    # Act
    summary = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-01")
    per_user = analytics.ai_credits_for_user(
        "alice", start="2026-06-01", end="2026-06-01"
    )

    # Assert
    assert summary["available"] is True
    assert summary["total_ai_credits"] == pytest.approx(25.0)  # 12 + 8 + 5
    by_model = {row["model"]: row["ai_credits"] for row in per_user["by_model"]}
    assert by_model["GPT-4.1"] == pytest.approx(12.0)
    assert by_model["Claude 3.5 Sonnet"] == pytest.approx(8.0)


def test_general_usage_csv_excludes_non_copilot_from_copilot_rollups() -> None:
    """General usage rows store all products but only Copilot surfaces in rollups."""
    # Act
    summary = _import(USAGE_CSV, "usageReport_2026-06.csv")
    premium = analytics.ai_credits_summary(start="2026-06-01", end="2026-06-01")

    # Assert
    assert summary["source_type"] == "csv_usage_report"
    assert summary["rows_imported"] == 3
    with db.connect() as conn:
        products = {r["product"] for r in conn.execute("SELECT product FROM billing_usage")}
    assert products == {"Copilot", "Actions", "Git LFS"}
    # Only the Copilot billable row counts toward AI-credit totals.
    assert premium["total_ai_credits"] == pytest.approx(10.0)


def test_csv_header_order_and_aliases_are_tolerated() -> None:
    """Header order and Title Case spelling do not affect parsing."""
    # Arrange
    reordered = (
        "Quantity,SKU,Date,Model,Total Monthly Quota,Username,Net Amount\n"
        "7,copilot_ai_credit,2026-06-02,GPT-4.1,Unlimited,carol,0.28\n"
    )

    # Act
    summary = _import(reordered, "AIUsageReport.csv")

    # Assert
    assert summary["rows_imported"] == 1
    with db.connect() as conn:
        row = conn.execute("SELECT login, model, quantity FROM billing_usage").fetchone()
    assert row["login"] == "carol"
    assert row["model"] == "GPT-4.1"
    assert row["quantity"] == pytest.approx(7.0)


def test_csv_utf8_bom_is_stripped() -> None:
    """A leading UTF-8 BOM does not corrupt the first header."""
    # Arrange
    payload = ("\ufeff" + AI_USAGE_CSV).encode("utf-8")

    # Act
    db.init_db()
    summary = import_usage_file("AIUsageReport.csv", payload)

    # Assert
    assert summary["source_type"] == "csv_ai_usage_report"
    assert summary["rows_imported"] == 3


def test_csv_blank_and_invalid_numeric_cells_default_to_zero() -> None:
    """Blank/invalid numeric cells import as 0 with a warning, not a failure."""
    # Arrange
    bad = (
        "Date,Username,Product,SKU,Model,Total Monthly Quota,Quantity,Net Amount\n"
        "2026-06-01,alice,Copilot,copilot_ai_credit,GPT-4.1,Unlimited,,oops\n"
    )

    # Act
    summary = _import(bad, "AIUsageReport.csv")

    # Assert
    assert summary["rows_imported"] == 1
    assert summary["warnings"]  # at least one numeric-coercion warning
    with db.connect() as conn:
        row = conn.execute("SELECT quantity, net_amount_usd FROM billing_usage").fetchone()
    assert row["quantity"] == pytest.approx(0.0)
    assert row["net_amount_usd"] == pytest.approx(0.0)


def test_csv_unknown_schema_is_rejected() -> None:
    """A CSV without billing columns raises a validation error (4xx upstream)."""
    # Arrange
    unknown = "day,user\n2026-06-02,alice\n"

    # Act + Assert
    db.init_db()
    with pytest.raises(ImportValidationError):
        import_usage_file("mystery.csv", unknown.encode("utf-8"))


def test_csv_reimport_is_idempotent() -> None:
    """Re-importing the same CSV updates rows in place without duplication."""
    # Arrange
    _import(AI_USAGE_CSV, "AIUsageReport.csv")

    # Act
    import_usage_file("AIUsageReport.csv", AI_USAGE_CSV.encode("utf-8"))

    # Assert
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM billing_usage").fetchone()["n"]
    assert count == 3  # unchanged after a second import


def test_csv_reimport_reports_overwritten_dates() -> None:
    """A second import flags the existing date under the billing scope."""
    # Arrange
    _import(AI_USAGE_CSV, "AIUsageReport.csv")

    # Act
    summary = import_usage_file("AIUsageReport.csv", AI_USAGE_CSV.encode("utf-8"))

    # Assert
    assert {o["scope"] for o in summary["overwritten"]} == {"billing"}
    assert {o["date"] for o in summary["overwritten"]} == {"2026-06-01"}


def test_csv_ai_usage_missing_model_produces_validation_errors() -> None:
    """AI usage CSV with empty model column skips rows with validation errors."""
    # Arrange — model column present but empty on one row
    csv_text = (
        "Date,Username,Product,SKU,Unit Type,Quantity,Model,Gross Amount\n"
        "2026-06-01,alice,Copilot,copilot_ai_credit,request,12,GPT-4.1,0.48\n"
        "2026-06-01,bob,Copilot,copilot_ai_credit,request,5,,0.20\n"
    )

    # Act
    summary = _import(csv_text, "AIUsageReport.csv")

    # Assert
    assert summary["rows_imported"] == 1
    assert summary["skipped_rows"] == 1
    assert summary["validation_errors"]
    assert summary["validation_errors"][0]["field"] == "model"
    assert "remediation_prompt" in summary
    assert "AIUsageReport.csv" in summary["remediation_prompt"]


def test_csv_all_rows_invalid_raises_with_remediation_prompt() -> None:
    """CSV where all rows fail schema validation raises error with prompt."""
    # Arrange — all rows have empty SKU (after header detection uses Unknown fallback)
    csv_text = (
        "Date,SKU,Quantity,Model\n"
        "not-a-date,,5,GPT-4.1\n"
    )

    # Act + Assert
    db.init_db()
    with pytest.raises(ImportValidationError, match="Validation Errors"):
        import_usage_file("bad.csv", csv_text.encode("utf-8"))
