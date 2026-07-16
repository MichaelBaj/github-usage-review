"""Integration tests for refresh-all endpoint orchestration flows."""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def reset_refresh_all_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset in-memory refresh-all state before each test."""
    import app.main as main

    main._refresh_all_jobs.clear()
    main._refresh_all_tasks.clear()
    main._background_tasks.clear()
    main._refresh_all_latest_job_id = None
    monkeypatch.setattr("app.config.settings.github_token", "test-token")
    monkeypatch.setattr("app.main.REFRESH_ALL_REPORT_TYPES", ())


def _wait_for_status(client: TestClient, job_id: str, expected: set[str]) -> dict[str, object]:
    """Poll job status until it matches one of the expected values."""
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        response = client.get(f"/api/refresh-all/status/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in expected:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"refresh-all job {job_id} did not reach expected status: {sorted(expected)}")


def test_refresh_all_cancel_endpoint_marks_job_canceled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Canceling a running refresh-all job marks it canceled and returns terminal status."""

    async def _ok_preflight() -> None:
        return None

    async def _slow_snapshot() -> dict[str, str]:
        await asyncio.sleep(2)
        return {"status": "ok"}

    monkeypatch.setattr("app.main.assert_snapshot_permissions", _ok_preflight)
    monkeypatch.setattr("app.main.run_snapshot", _slow_snapshot)

    with TestClient(app) as client:
        start_response = client.post("/api/refresh-all/start", json={"report_types": []})
        assert start_response.status_code == 200
        start_payload = start_response.json()
        assert start_payload["started"] is True
        job_id = start_payload["job"]["id"]

        _wait_for_status(client, job_id, {"running"})
        cancel_response = client.post(f"/api/refresh-all/cancel?job_id={job_id}")
        assert cancel_response.status_code == 200
        assert cancel_response.json() == {"canceled": True, "job_id": job_id}

        terminal = _wait_for_status(client, job_id, {"canceled"})
        assert terminal["errors"] == ["refresh-all canceled by user"]


def test_refresh_all_retry_endpoint_restarts_from_prior_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry endpoint starts a new refresh-all job from prior job settings."""

    async def _ok_preflight() -> None:
        return None

    async def _fast_snapshot() -> dict[str, str]:
        return {"status": "ok"}

    monkeypatch.setattr("app.main.assert_snapshot_permissions", _ok_preflight)
    monkeypatch.setattr("app.main.run_snapshot", _fast_snapshot)

    with TestClient(app) as client:
        start_response = client.post(
            "/api/refresh-all/start",
            json={"report_types": [], "send_email": True},
        )
        assert start_response.status_code == 200
        first_job = start_response.json()["job"]
        first_job_id = first_job["id"]
        assert first_job["send_email"] is True
        assert first_job["report_types"] == []

        _wait_for_status(client, first_job_id, {"completed"})

        retry_response = client.post("/api/refresh-all/retry", json={"job_id": first_job_id})
        assert retry_response.status_code == 200
        retry_payload = retry_response.json()
        assert retry_payload["started"] is True

        retried_job = retry_payload["job"]
        retried_job_id = retried_job["id"]
        assert retried_job_id != first_job_id
        assert retried_job["send_email"] is True
        assert retried_job["report_types"] == []

        terminal = _wait_for_status(client, retried_job_id, {"completed"})
        assert terminal["errors"] == []