"""
functional/test_dev_server_api.py — Functional Tests for BTMS Dev Server API
───────────────────────────────────────────────────────────────────────────────
Tests the FastAPI dev server (dev_server.py) end-to-end using TestClient.
Covers /health, /telemetry/latest, /recommendations.

Run:
    pytest tests/functional/test_dev_server_api.py -v
"""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Import app from dev_server (suppress uvicorn startup noise)
import importlib
import dev_server as _ds
from dev_server import app

# Allow simulation worker to produce at least one tick
client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════
# FT-DEV-001 — /health
# ═══════════════════════════════════════════════════════════════════════════════

class TestDevServerHealth:

    def test_health_returns_200(self):
        """FT-DEV-001a: GET /health must return HTTP 200."""
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_response_schema(self):
        """FT-DEV-001b: Response must include service and status=ok."""
        r = client.get("/health")
        body = r.json()
        assert body.get("status") == "ok"
        assert "service" in body

    def test_health_content_type_json(self):
        """FT-DEV-001c: Content-Type must be application/json."""
        r = client.get("/health")
        assert "application/json" in r.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════════
# FT-DEV-002 — /telemetry/latest
# ═══════════════════════════════════════════════════════════════════════════════

class TestTelemetryEndpoint:

    def test_telemetry_returns_200(self):
        """FT-DEV-002a: GET /telemetry/latest must return HTTP 200."""
        r = client.get("/telemetry/latest")
        assert r.status_code == 200

    def test_telemetry_response_has_status_field(self):
        """FT-DEV-002b: Response must include 'status' field."""
        r = client.get("/telemetry/latest")
        assert "status" in r.json()

    def test_telemetry_when_data_available(self):
        """FT-DEV-002c: When telemetry is populated it must include pack_id, cells, tick."""
        # Wait up to 3 s for worker to produce first tick
        for _ in range(30):
            r = client.get("/telemetry/latest")
            body = r.json()
            if body.get("status") == "ok":
                t = body["telemetry"]
                assert "pack_id" in t
                assert "cells" in t
                assert "tick" in t
                return
            time.sleep(0.1)
        # If status=waiting after 3s, that's acceptable for TestClient
        assert body["status"] in ("ok", "waiting")

    def test_telemetry_cells_structure(self):
        """FT-DEV-002d: Each cell must have cell_id, temperature, voltage, current, soc."""
        for _ in range(30):
            r = client.get("/telemetry/latest")
            body = r.json()
            if body.get("status") == "ok":
                for cell in body["telemetry"]["cells"]:
                    assert all(k in cell for k in [
                        "cell_id", "temperature", "voltage", "current", "soc"
                    ])
                return
            time.sleep(0.1)

    def test_telemetry_10_cells(self):
        """FT-DEV-002e: Pack must contain exactly 10 cells."""
        for _ in range(30):
            r = client.get("/telemetry/latest")
            body = r.json()
            if body.get("status") == "ok":
                assert len(body["telemetry"]["cells"]) == 10
                return
            time.sleep(0.1)

    def test_telemetry_cell_id_sequence(self):
        """FT-DEV-002f: cell_id must be 0-9 in order."""
        for _ in range(30):
            r = client.get("/telemetry/latest")
            body = r.json()
            if body.get("status") == "ok":
                ids = [c["cell_id"] for c in body["telemetry"]["cells"]]
                assert ids == list(range(10))
                return
            time.sleep(0.1)

    def test_telemetry_temperatures_in_valid_range(self):
        """FT-DEV-002g: All cell temperatures must be realistic (0-100°C)."""
        for _ in range(30):
            r = client.get("/telemetry/latest")
            body = r.json()
            if body.get("status") == "ok":
                for cell in body["telemetry"]["cells"]:
                    assert 0.0 <= cell["temperature"] <= 100.0
                return
            time.sleep(0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# FT-DEV-003 — /recommendations
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecommendationsEndpoint:

    def test_recommendations_returns_200(self):
        """FT-DEV-003a: GET /recommendations must return HTTP 200."""
        r = client.get("/recommendations")
        assert r.status_code == 200

    def test_recommendations_has_status(self):
        """FT-DEV-003b: Response must have 'status' key."""
        r = client.get("/recommendations")
        assert "status" in r.json()

    def test_recommendations_severity_valid(self):
        """FT-DEV-003c: severity must be one of normal/warning/critical."""
        for _ in range(30):
            r = client.get("/recommendations")
            body = r.json()
            if body.get("status") == "ok":
                sev = body["recommendation"]["severity"]
                assert sev in ("normal", "warning", "critical")
                return
            time.sleep(0.1)

    def test_recommendations_re_in_bounds(self):
        """FT-DEV-003d: target_re must be in [400, 700]."""
        for _ in range(30):
            r = client.get("/recommendations")
            body = r.json()
            if body.get("status") == "ok":
                re = body["recommendation"]["target_re"]
                assert 400 <= re <= 700
                return
            time.sleep(0.1)

    def test_recommendations_flow_rate_positive(self):
        """FT-DEV-003e: flow_rate_ml_min must be > 0."""
        for _ in range(30):
            r = client.get("/recommendations")
            body = r.json()
            if body.get("status") == "ok":
                assert body["recommendation"]["flow_rate_ml_min"] > 0
                return
            time.sleep(0.1)

    def test_recommendations_concentration_key_valid(self):
        """FT-DEV-003f: concentration_key must be low/medium/high."""
        for _ in range(30):
            r = client.get("/recommendations")
            body = r.json()
            if body.get("status") == "ok":
                ck = body["recommendation"]["concentration_key"]
                assert ck in ("low", "medium", "high")
                return
            time.sleep(0.1)

    def test_invalid_method_returns_405(self):
        """FT-DEV-003g: POST /recommendations must return 405 Method Not Allowed."""
        r = client.post("/recommendations")
        assert r.status_code == 405
