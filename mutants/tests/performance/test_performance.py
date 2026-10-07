"""
performance/test_performance.py — Performance Tests for BTMS
─────────────────────────────────────────────────────────────
Tests throughput, latency, and resource usage of:
  - CFD physics functions (in-process)
  - Auth service endpoints (TestClient)
  - Dev server endpoints (TestClient)

Uses timeit / time for microsecond-level benchmarks, and
requests against live servers for realistic latency checks.

Run:
    pytest tests/performance/test_performance.py -v -s
    pytest tests/performance/test_performance.py -v --html=tests/reports/performance_report.html
"""

import sys
import math
import time
import timeit
import socket
import statistics
import threading
import importlib.util
import concurrent.futures
from pathlib import Path
from typing import Callable

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module(mod_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, mod_path)
    mod = importlib.util.module_from_spec(spec)
    mod_dir = str(mod_path.parent)
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    spec.loader.exec_module(mod)
    return mod


_ai = _load_module(ROOT / "ai_engine" / "main.py", "ai_main_perf")
_ing = _load_module(ROOT / "ingestion" / "app.py", "ing_app_perf")

nanofluid_properties = _ai.nanofluid_properties
compute_nusselt = _ai.compute_nusselt
compute_flow_velocity = _ai.compute_flow_velocity
cfd_optimise = _ai.cfd_optimise

normalise_temperature = _ing.normalise_temperature
enrich_payload = _ing.enrich_payload

from fastapi.testclient import TestClient

# Auth service TestClient
sys.path.insert(0, str(ROOT / "auth_service"))
import main as auth_main
auth_client = TestClient(auth_main.app)

import dev_server as ds_module
dev_client = TestClient(ds_module.app)



# ── Helpers ───────────────────────────────────────────────────────────────────

def _cells(temps, voltage=3.6, current=2.5, soc=90.0):
    return [{"cell_id": i, "temperature": t, "voltage": voltage,
             "current": current, "soc": soc, "temperature_norm": t / 60.0}
            for i, t in enumerate(temps)]


def _bench(fn: Callable, n: int = 1000) -> dict:
    """Run fn n times and return latency stats in milliseconds."""
    times = []
    for _ in range(n):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return {
        "n": n,
        "min_ms": round(min(times), 4),
        "max_ms": round(max(times), 4),
        "mean_ms": round(statistics.mean(times), 4),
        "p95_ms": round(sorted(times)[int(0.95 * n)], 4),
        "p99_ms": round(sorted(times)[int(0.99 * n)], 4),
    }


def _server_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# PERF-001 — CFD Physics Function Benchmarks (in-process, no network)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCFDPerformance:

    def test_nanofluid_properties_throughput_1000_calls(self):
        """PERF-001a: nanofluid_properties must handle 1000 calls in < 50 ms total."""
        stats = _bench(lambda: nanofluid_properties(0.015), n=1000)
        print(f"\n[PERF] nanofluid_properties x1000: {stats}")
        total_ms = stats["mean_ms"] * 1000
        assert total_ms < 50.0, f"1000 calls took {total_ms:.1f} ms > 50 ms threshold"

    def test_compute_nusselt_mean_latency_under_threshold(self):
        """PERF-001b: compute_nusselt mean latency must be < 0.05 ms per call."""
        stats = _bench(lambda: compute_nusselt(550, 6.5), n=1000)
        print(f"\n[PERF] compute_nusselt: {stats}")
        assert stats["mean_ms"] < 0.05, (
            f"compute_nusselt mean={stats['mean_ms']} ms exceeds 0.05 ms"
        )

    def test_compute_flow_velocity_sub_microsecond(self):
        """PERF-001c: compute_flow_velocity must average < 0.1 ms per call."""
        props = nanofluid_properties(0.015)
        stats = _bench(lambda: compute_flow_velocity(550, props), n=1000)
        print(f"\n[PERF] compute_flow_velocity: {stats}")
        assert stats["mean_ms"] < 0.1

    def test_cfd_optimise_mean_under_1ms(self):
        """PERF-001d: cfd_optimise (full pipeline) mean latency must be < 1 ms."""
        cells = _cells([30.0] * 10)
        stats = _bench(lambda: cfd_optimise(cells, ml_severity="normal"), n=500)
        print(f"\n[PERF] cfd_optimise: {stats}")
        assert stats["mean_ms"] < 1.0, (
            f"cfd_optimise mean={stats['mean_ms']} ms exceeds 1 ms SLA"
        )

    def test_cfd_optimise_p99_under_5ms(self):
        """PERF-001e: cfd_optimise p99 latency must be < 5 ms."""
        cells = _cells([30.0] * 10)
        stats = _bench(lambda: cfd_optimise(cells, ml_severity="warning"), n=500)
        print(f"\n[PERF] cfd_optimise p99: {stats}")
        assert stats["p99_ms"] < 5.0, (
            f"cfd_optimise p99={stats['p99_ms']} ms exceeds 5 ms SLA"
        )

    def test_normalise_temperature_throughput_10k(self):
        """PERF-001f: normalise_temperature must handle 10,000 calls in < 100 ms."""
        stats = _bench(lambda: normalise_temperature(35.0), n=10000)
        print(f"\n[PERF] normalise_temperature x10000: {stats}")
        total_ms = stats["mean_ms"] * 10000
        assert total_ms < 100.0, f"10k calls took ~{total_ms:.1f} ms"

    def test_enrich_payload_10_cells_under_1ms(self):
        """PERF-001g: enrich_payload for 10-cell pack must be < 1 ms mean."""
        payload = {
            "tick": 1,
            "pack_id": "BTMS-PACK-001",
            "cells": [{"cell_id": i, "temperature": 30.0, "voltage": 3.6,
                        "current": 2.5, "soc": 90.0} for i in range(10)],
        }
        stats = _bench(lambda: enrich_payload(payload), n=1000)
        print(f"\n[PERF] enrich_payload 10-cell: {stats}")
        assert stats["mean_ms"] < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# PERF-002 — Auth Service API Latency (TestClient — in-process)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthServicePerformance:

    def test_health_endpoint_p99_under_100ms(self):
        """PERF-002a: Auth /auth/health p99 latency must be < 100 ms."""
        stats = _bench(lambda: auth_client.get("/auth/health"), n=200)
        print(f"\n[PERF] auth /health: {stats}")
        assert stats["p99_ms"] < 100.0

    def test_login_mean_under_500ms(self):
        """PERF-002b: Auth /auth/login mean latency must be < 500 ms (bcrypt is slow by design)."""
        import uuid
        uid = uuid.uuid4().hex[:8]
        user = {"username": f"perf_{uid}", "email": f"perf_{uid}@test.local", "password": "PerfTest1!"}
        auth_client.post("/auth/register", json=user)
        login_data = {"username": user["username"], "password": user["password"]}
        stats = _bench(lambda: auth_client.post("/auth/login", json=login_data), n=5)
        print(f"\n[PERF] auth /login (bcrypt): {stats}")
        assert stats["mean_ms"] < 500.0, (
            f"Login mean={stats['mean_ms']} ms exceeds 500 ms SLA (bcrypt rounds may need tuning)"
        )

    def test_me_endpoint_with_valid_token_under_50ms(self):
        """PERF-002c: /auth/me with cached valid token must be < 50 ms mean."""
        import uuid
        uid = uuid.uuid4().hex[:8]
        user = {"username": f"me_{uid}", "email": f"me_{uid}@test.local", "password": "MeTest1!"}
        r = auth_client.post("/auth/register", json=user)
        token = r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        stats = _bench(lambda: auth_client.get("/auth/me", headers=headers), n=100)
        print(f"\n[PERF] auth /me: {stats}")
        assert stats["mean_ms"] < 50.0


# ═══════════════════════════════════════════════════════════════════════════════
# PERF-003 — Dev Server API Latency (TestClient — in-process)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDevServerPerformance:

    def test_health_endpoint_mean_under_10ms(self):
        """PERF-003a: Dev /health mean latency must be < 10 ms."""
        stats = _bench(lambda: dev_client.get("/health"), n=500)
        print(f"\n[PERF] dev /health: {stats}")
        assert stats["mean_ms"] < 10.0

    def test_telemetry_endpoint_mean_under_50ms(self):
        """PERF-003b: Dev /telemetry/latest mean latency must be < 50 ms."""
        # Allow worker to produce one tick
        for _ in range(20):
            if dev_client.get("/telemetry/latest").json().get("status") == "ok":
                break
            time.sleep(0.1)
        stats = _bench(lambda: dev_client.get("/telemetry/latest"), n=200)
        print(f"\n[PERF] dev /telemetry/latest: {stats}")
        assert stats["mean_ms"] < 50.0

    def test_recommendations_endpoint_mean_under_50ms(self):
        """PERF-003c: Dev /recommendations mean latency must be < 50 ms."""
        stats = _bench(lambda: dev_client.get("/recommendations"), n=200)
        print(f"\n[PERF] dev /recommendations: {stats}")
        assert stats["mean_ms"] < 50.0

    def test_concurrent_telemetry_requests_no_deadlock(self):
        """PERF-003d: 20 concurrent /telemetry/latest requests must all succeed."""
        results = []

        def fetch():
            r = dev_client.get("/telemetry/latest")
            results.append(r.status_code)

        threads = [threading.Thread(target=fetch) for _ in range(20)]
        [t.start() for t in threads]
        [t.join(timeout=5) for t in threads]

        assert len(results) == 20, f"Only {len(results)} of 20 threads completed"
        assert all(s == 200 for s in results), (
            f"Non-200 responses in concurrent test: {set(results)}"
        )

    def test_cfd_pipeline_simulation_rate(self):
        """PERF-003e: Full simulation pipeline (simulate+CFD) must run >= 10 ticks/sec."""
        import dev_server
        start = time.perf_counter()
        for _ in range(50):
            cells = [dev_server.simulate_cell(i) for i in range(10)]
            dev_server.cfd_optimise(cells)
        elapsed = time.perf_counter() - start
        rate = 50 / elapsed
        print(f"\n[PERF] Simulation pipeline: {rate:.1f} ticks/sec")
        assert rate >= 10.0, f"Pipeline rate {rate:.1f} ticks/sec < 10 ticks/sec requirement"


# ═══════════════════════════════════════════════════════════════════════════════
# PERF-004 — Live Server Latency (skipped if servers offline)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLiveServerPerformance:

    @pytest.mark.skipif(
        not _server_reachable("localhost", 8000),
        reason="Dev server not running on localhost:8000"
    )
    def test_live_dev_server_health_p95_under_20ms(self):
        """PERF-004a: Live /health p95 latency must be < 20 ms over network."""
        import requests
        times = []
        for _ in range(50):
            start = time.perf_counter()
            r = requests.get("http://localhost:8000/health", timeout=5)
            times.append((time.perf_counter() - start) * 1000)
            assert r.status_code == 200

        p95 = sorted(times)[int(0.95 * len(times))]
        print(f"\n[PERF LIVE] /health p95={p95:.2f} ms")
        assert p95 < 20.0, f"Live /health p95={p95:.2f} ms exceeds 20 ms"

    @pytest.mark.skipif(
        not _server_reachable("localhost", 8000),
        reason="Dev server not running on localhost:8000"
    )
    def test_live_telemetry_throughput_50_requests(self):
        """PERF-004b: 50 live /telemetry/latest requests must complete in < 5 seconds."""
        import requests
        start = time.perf_counter()
        for _ in range(50):
            r = requests.get("http://localhost:8000/telemetry/latest", timeout=5)
            assert r.status_code == 200
        elapsed = time.perf_counter() - start
        print(f"\n[PERF LIVE] 50x /telemetry/latest in {elapsed:.2f}s")
        assert elapsed < 5.0, f"50 requests took {elapsed:.2f}s > 5s"
