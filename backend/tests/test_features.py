"""Tests for the /api/features endpoint and feature_breakdown analytics."""
from __future__ import annotations

import json

from starlette.testclient import TestClient

from app import db
from app.main import app


client = TestClient(app)


def _seed_feature_data() -> None:
    """Insert sample feature metrics into the database."""
    db.init_db()
    with db.connect() as conn:
        for day in ("2026-06-14", "2026-06-15"):
            conn.execute(
                "INSERT INTO daily_feature_metrics "
                "(date, feature, interactions, code_generations, code_acceptances, "
                "loc_suggested, loc_accepted, loc_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (day, "code_completion", 0, 300, 120, 600, 240, 5),
            )
            conn.execute(
                "INSERT INTO daily_feature_metrics "
                "(date, feature, interactions, code_generations, code_acceptances, "
                "loc_suggested, loc_accepted, loc_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (day, "agent_mode", 25, 50, 20, 100, 40, 20),
            )


def test_features_endpoint_returns_aggregated_features() -> None:
    """GET /api/features returns summed feature metrics across the window."""
    _seed_feature_data()
    resp = client.get("/api/features?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "features" in data
    assert "window_start" in data
    by_feat = {f["feature"]: f for f in data["features"]}
    # Two days summed
    assert by_feat["code_completion"]["code_generations"] == 600
    assert by_feat["agent_mode"]["interactions"] == 50
    assert by_feat["agent_mode"]["loc_deleted"] == 40


def test_features_endpoint_empty_db() -> None:
    """Returns empty features list when no data exists."""
    db.init_db()
    resp = client.get("/api/features?days=30")
    assert resp.status_code == 200
    assert resp.json()["features"] == []


def test_replace_feature_rows_upserts() -> None:
    """replace_feature_rows should overwrite existing rows for the same date."""
    db.init_db()
    rows = [
        {"feature": "code_completion", "interactions": 0, "code_generations": 100,
         "code_acceptances": 50, "loc_suggested": 200, "loc_accepted": 80, "loc_deleted": 0},
    ]
    db.replace_feature_rows("2026-06-15", rows)
    # Replace with new values
    rows[0]["code_generations"] = 999
    db.replace_feature_rows("2026-06-15", rows)
    with db.connect() as conn:
        result = conn.execute(
            "SELECT code_generations FROM daily_feature_metrics WHERE date = ?",
            ("2026-06-15",),
        ).fetchone()
    assert result["code_generations"] == 999
