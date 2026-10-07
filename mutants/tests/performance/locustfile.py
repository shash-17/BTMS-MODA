"""
performance/locustfile.py — Locust Load Test for BTMS
───────────────────────────────────────────────────────
Simulates realistic concurrent users hitting the BTMS API.

Run (requires live servers):
    locust -f tests/performance/locustfile.py --host=http://localhost:8000 \
           --users=50 --spawn-rate=5 --run-time=60s --headless \
           --html=tests/reports/locust_report.html

User scenarios:
  - BTMSDashboardUser: Polls telemetry + recommendations (simulates React dashboard)
  - BTMSAuthUser: Registers, logs in, hits /auth/me (simulates auth flow)
"""

import uuid
import json
import random
from locust import HttpUser, TaskSet, task, between, events


# ─── Dashboard polling user ────────────────────────────────────────────────────

class DashboardTasks(TaskSet):

    @task(3)
    def poll_telemetry(self):
        """Weight 3 — primary dashboard polling loop."""
        with self.client.get(
            "/telemetry/latest",
            name="/telemetry/latest",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                body = r.json()
                if body.get("status") in ("ok", "waiting"):
                    r.success()
                else:
                    r.failure(f"Unexpected body status: {body.get('status')}")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def poll_recommendations(self):
        """Weight 2 — recommendations sidebar refresh."""
        with self.client.get(
            "/recommendations",
            name="/recommendations",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(1)
    def health_check(self):
        """Weight 1 — liveness probe."""
        with self.client.get(
            "/health",
            name="/health",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"HTTP {r.status_code}")


class BTMSDashboardUser(HttpUser):
    """Simulates a React dashboard polling every 1–3 seconds."""
    tasks = [DashboardTasks]
    wait_time = between(1, 3)
    host = "http://localhost:8000"


# ─── Auth flow user ───────────────────────────────────────────────────────────

class AuthTasks(TaskSet):

    def on_start(self):
        """Register and login once per virtual user."""
        uid = uuid.uuid4().hex[:8]
        self.user_data = {
            "username": f"loc_user_{uid}",
            "email": f"loc_{uid}@btms.local",
            "password": "LoadTest@1234",
        }
        self.token = None

        r = self.client.post(
            "/auth/register",
            json=self.user_data,
            name="/auth/register [setup]",
        )
        if r.status_code == 201:
            self.token = r.json().get("token")

    @task(4)
    def get_me(self):
        """Weight 4 — most frequent auth action: verify own identity."""
        if not self.token:
            return
        with self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/auth/me",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code == 401:
                r.failure("Token rejected")
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(2)
    def login(self):
        """Weight 2 — periodic re-login (simulates session refresh)."""
        with self.client.post(
            "/auth/login",
            json={
                "username": self.user_data["username"],
                "password": self.user_data["password"],
            },
            name="/auth/login",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                self.token = r.json().get("token")
                r.success()
            else:
                r.failure(f"HTTP {r.status_code}")

    @task(1)
    def health(self):
        """Weight 1 — auth health check."""
        self.client.get("/auth/health", name="/auth/health")


class BTMSAuthUser(HttpUser):
    """Simulates an authenticated user interacting with the auth service."""
    tasks = [AuthTasks]
    wait_time = between(2, 5)
    host = "http://localhost:9000"


# ─── Custom event hooks for reporting ─────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "=" * 60)
    print("  BTMS Locust Load Test Started")
    print("  Targets: http://localhost:8000  (dev server)")
    print("           http://localhost:9000  (auth service)")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats.total
    print("\n" + "=" * 60)
    print("  BTMS Locust Load Test Completed")
    print(f"  Total requests : {stats.num_requests}")
    print(f"  Failures       : {stats.num_failures}")
    print(f"  Avg latency    : {stats.avg_response_time:.1f} ms")
    print(f"  p95 latency    : {stats.get_response_time_percentile(0.95):.1f} ms")
    print(f"  p99 latency    : {stats.get_response_time_percentile(0.99):.1f} ms")
    print(f"  Requests/sec   : {stats.total_rps:.1f}")
    print("=" * 60)
