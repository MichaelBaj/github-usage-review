"""Tests for the POST /api/data/import-file upload endpoint."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


def _export_row(login: str, day: str = "2026-06-02") -> dict:
    """Build a minimal GitHub per-user-per-day export row."""
    return {
        "day": day,
        "user_id": 123,
        "user_login": login,
        "user_initiated_interaction_count": 3,
        "code_generation_activity_count": 5,
        "code_acceptance_activity_count": 2,
        "totals_by_ide": [{"ide": "vscode", "code_generation_activity_count": 5}],
        "totals_by_feature": [
            {
                "feature": "code_completion",
                "code_generation_activity_count": 5,
                "code_acceptance_activity_count": 2,
                "loc_suggested_to_add_sum": 10,
                "loc_added_sum": 4,
            }
        ],
        "totals_by_language_feature": [
            {
                "language": "python",
                "feature": "code_completion",
                "code_generation_activity_count": 5,
                "code_acceptance_activity_count": 2,
                "loc_suggested_to_add_sum": 10,
                "loc_added_sum": 4,
            }
        ],
        "totals_by_model_feature": [
            {
                "model": "gpt-4o-copilot",
                "feature": "code_completion",
                "code_generation_activity_count": 5,
                "code_acceptance_activity_count": 2,
            }
        ],
    }


def test_import_endpoint_accepts_ndjson_upload() -> None:
    """A valid NDJSON upload returns 200 with an import summary."""
    # Arrange
    content = "\n".join(json.dumps(_export_row(name)) for name in ("alice", "bob")).encode()

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/api/data/import-file",
            files={"file": ("export.ndjson", content, "application/x-ndjson")},
        )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["source_type"] == "github_export_ndjson"
    assert body["rows_imported"] == 2
    assert body["date_range"] == {"start": "2026-06-02", "end": "2026-06-02"}


def test_import_endpoint_rejects_unsupported_extension() -> None:
    """An unsupported file extension returns 400."""
    # Arrange
    content = b"day,user\n2026-06-02,alice\n"

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/api/data/import-file",
            files={"file": ("export.txt", content, "text/plain")},
        )

    # Assert
    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"]


def test_import_endpoint_accepts_csv_billing_report() -> None:
    """A CSV billing report imports via the endpoint with a csv source type."""
    # Arrange
    content = (
        b"Date,Username,Product,SKU,Model,Total Monthly Quota,Quantity,Net Amount\n"
        b"2026-06-01,alice,Copilot,copilot_ai_credit,GPT-4.1,Unlimited,12,0.48\n"
    )

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/api/data/import-file",
            files={"file": ("AIUsageReport.csv", content, "text/csv")},
        )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["source_type"] == "csv_ai_usage_report"
    assert body["rows_imported"] == 1


def test_import_endpoint_rejects_invalid_file() -> None:
    """A file with no valid records returns 400."""
    # Arrange
    content = b"not-json\nstill-not-json\n"

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/api/data/import-file",
            files={"file": ("export.ndjson", content, "application/x-ndjson")},
        )

    # Assert
    assert response.status_code == 400
    assert response.json()["detail"]


def test_import_endpoint_enforces_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """An upload above the configured size cap returns 413."""
    # Arrange
    monkeypatch.setattr(config.settings, "import_max_upload_mb", 1)
    oversized = b"x" * (2 * 1024 * 1024)

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/api/data/import-file",
            files={"file": ("export.ndjson", oversized, "application/x-ndjson")},
        )

    # Assert
    assert response.status_code == 413
    assert "1 MiB" in response.json()["detail"]


def test_import_endpoint_accepts_file_near_real_export_size() -> None:
    """A multi-megabyte NDJSON upload (like the GitHub export) imports under the default cap."""
    # Arrange — ~3 MB of valid rows, well under the 25 MiB default cap
    rows = [json.dumps(_export_row(f"user{i}", day="2026-06-03")) for i in range(8000)]
    content = "\n".join(rows).encode()
    assert len(content) > 2 * 1024 * 1024

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/api/data/import-file",
            files={"file": ("part-00001.ndjson", content, "application/x-ndjson")},
        )

    # Assert
    assert response.status_code == 200
    assert response.json()["rows_imported"] == 8000


def test_import_endpoint_ndjson_with_bad_rows_returns_validation_errors() -> None:
    """NDJSON with some schema-invalid rows imports valid ones and reports errors."""
    # Arrange — one valid row + one row with bad date
    good = json.dumps(_export_row("alice"))
    bad = json.dumps({"day": "not-a-date", "user_login": "bob"})
    content = f"{good}\n{bad}".encode()

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/api/data/import-file",
            files={"file": ("export.ndjson", content, "application/x-ndjson")},
        )

    # Assert — partial import succeeds with validation details
    assert response.status_code == 200
    body = response.json()
    assert body["rows_imported"] == 1
    assert body["skipped_rows"] >= 1
    assert "validation_errors" in body
    assert "remediation_prompt" in body
    assert "export.ndjson" in body["remediation_prompt"]
