"""Tests for the POST /api/snapshot/run endpoint preflight behavior."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_snapshot_run_fails_fast_on_preflight_error(monkeypatch) -> None:
    """Preflight permission failures return a clear 403 and skip snapshot ingestion."""
    monkeypatch.setattr("app.config.settings.github_token", "test-token")

    async def _run_snapshot() -> dict[str, str]:
        raise RuntimeError("run_snapshot should not be called when preflight fails")

    async def _failing_preflight() -> None:
        from app.github_client import SnapshotPreflightError

        raise SnapshotPreflightError(
            "Snapshot preflight failed due to GitHub token/org permission issues:\n"
            "- Copilot seats access failed (403) at GET /orgs/example/copilot/billing/seats. "
            "Action: use a token authorized for org admin-level Copilot access."
        )

    monkeypatch.setattr("app.main.assert_snapshot_permissions", _failing_preflight)
    monkeypatch.setattr("app.main.run_snapshot", _run_snapshot)

    with TestClient(app) as client:
        response = client.post("/api/snapshot/run")

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "Snapshot preflight failed" in detail
    assert "Copilot seats access failed (403)" in detail
    assert "Action:" in detail


def test_snapshot_run_executes_when_preflight_passes(monkeypatch) -> None:
    """Successful preflight allows the snapshot run to proceed."""
    monkeypatch.setattr("app.config.settings.github_token", "test-token")

    called: dict[str, bool] = {"run": False}

    async def _ok_preflight() -> None:
        return None

    async def _run_snapshot() -> dict[str, str]:
        called["run"] = True
        return {"status": "ok"}

    monkeypatch.setattr("app.main.assert_snapshot_permissions", _ok_preflight)
    monkeypatch.setattr("app.main.run_snapshot", _run_snapshot)

    with TestClient(app) as client:
        response = client.post("/api/snapshot/run")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert called["run"] is True
