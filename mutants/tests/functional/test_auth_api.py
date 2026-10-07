"""
functional/test_auth_api.py — Functional (API Integration) Tests for Auth Service
────────────────────────────────────────────────────────────────────────────────────
Uses FastAPI TestClient (no live server needed) to test end-to-end request/response
behaviour of the auth_service REST endpoints.

Run:
    pytest tests/functional/test_auth_api.py -v
    pytest tests/functional/test_auth_api.py -v --html=tests/reports/functional_report.html
"""

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auth_service"))

from main import app

client = TestClient(app, raise_server_exceptions=False)


def _unique_user():
    uid = uuid.uuid4().hex[:8]
    return {
        "username": f"testuser_{uid}",
        "email": f"test_{uid}@btms.local",
        "password": "Test@1234",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FT-AUTH-001 — Health Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:

    def test_health_returns_200(self):
        """FT-AUTH-001a: GET /auth/health must return HTTP 200."""
        r = client.get("/auth/health")
        assert r.status_code == 200

    def test_health_response_schema(self):
        """FT-AUTH-001b: Health response must include status=ok."""
        r = client.get("/auth/health")
        body = r.json()
        assert body.get("status") == "ok"
        assert "service" in body


# ═══════════════════════════════════════════════════════════════════════════════
# FT-AUTH-002 — Register
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegisterEndpoint:

    def test_register_new_user_returns_201(self):
        """FT-AUTH-002a: POST /auth/register with valid data must return HTTP 201."""
        r = client.post("/auth/register", json=_unique_user())
        assert r.status_code == 201

    def test_register_returns_token_and_user(self):
        """FT-AUTH-002b: Registration response must include 'token' and 'user'."""
        r = client.post("/auth/register", json=_unique_user())
        body = r.json()
        assert "token" in body
        assert "user" in body

    def test_register_user_object_contains_expected_fields(self):
        """FT-AUTH-002c: User object must contain id, username, email, role."""
        r = client.post("/auth/register", json=_unique_user())
        user = r.json()["user"]
        assert all(k in user for k in ["id", "username", "email", "role"])

    def test_register_sets_default_role_to_operator(self):
        """FT-AUTH-002d: New users must have role='operator' by default."""
        r = client.post("/auth/register", json=_unique_user())
        assert r.json()["user"]["role"] == "operator"

    def test_register_duplicate_username_returns_409(self):
        """FT-AUTH-002e: Registering the same username twice must return HTTP 409."""
        user = _unique_user()
        client.post("/auth/register", json=user)
        r2 = client.post("/auth/register", json=user)
        assert r2.status_code == 409

    def test_register_duplicate_email_returns_409(self):
        """FT-AUTH-002f: Same email with different username must return HTTP 409."""
        user = _unique_user()
        client.post("/auth/register", json=user)
        user["username"] = "different_" + user["username"]
        r2 = client.post("/auth/register", json=user)
        assert r2.status_code == 409

    def test_register_with_empty_password_returns_422(self):
        """FT-AUTH-002g: Missing password must return HTTP 422."""
        r = client.post("/auth/register", json={
            "username": "someuser", "email": "e@test.com", "password": ""
        })
        assert r.status_code in (400, 422)

    def test_register_with_short_password_returns_422(self):
        """FT-AUTH-002h: Password < 6 chars must be rejected."""
        r = client.post("/auth/register", json={
            "username": "someuser99", "email": "e99@test.com", "password": "abc"
        })
        assert r.status_code in (400, 422)

    def test_register_token_is_valid_jwt(self):
        """FT-AUTH-002i: Returned token must be a valid 3-part JWT."""
        r = client.post("/auth/register", json=_unique_user())
        token = r.json()["token"]
        assert len(token.split(".")) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# FT-AUTH-003 — Login
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoginEndpoint:

    @pytest.fixture
    def registered_user(self):
        user = _unique_user()
        client.post("/auth/register", json=user)
        return user

    def test_valid_login_returns_200(self, registered_user):
        """FT-AUTH-003a: POST /auth/login with valid creds must return HTTP 200."""
        r = client.post("/auth/login", json={
            "username": registered_user["username"],
            "password": registered_user["password"],
        })
        assert r.status_code == 200

    def test_login_returns_token_and_user(self, registered_user):
        """FT-AUTH-003b: Login response must include 'token' and 'user'."""
        r = client.post("/auth/login", json={
            "username": registered_user["username"],
            "password": registered_user["password"],
        })
        body = r.json()
        assert "token" in body and "user" in body

    def test_wrong_password_returns_401(self, registered_user):
        """FT-AUTH-003c: Wrong password must return HTTP 401."""
        r = client.post("/auth/login", json={
            "username": registered_user["username"],
            "password": "wrongpassword",
        })
        assert r.status_code == 401

    def test_nonexistent_user_returns_401(self):
        """FT-AUTH-003d: Non-existent user must return HTTP 401."""
        r = client.post("/auth/login", json={
            "username": "ghost_user_xyz",
            "password": "anypassword",
        })
        assert r.status_code == 401

    def test_can_login_with_email(self, registered_user):
        """FT-AUTH-003e: Login must accept email in the username field."""
        r = client.post("/auth/login", json={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# FT-AUTH-004 — /auth/me (protected endpoint)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMeEndpoint:

    @pytest.fixture
    def auth_token(self):
        user = _unique_user()
        r = client.post("/auth/register", json=user)
        return r.json()["token"]

    def test_me_with_valid_token_returns_200(self, auth_token):
        """FT-AUTH-004a: GET /auth/me with valid Bearer token must return 200."""
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        assert r.status_code == 200

    def test_me_returns_user_profile_fields(self, auth_token):
        """FT-AUTH-004b: /auth/me response must include id, username, email, role."""
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        body = r.json()
        assert all(k in body for k in ["id", "username", "email", "role"])

    def test_me_without_token_returns_403_or_401(self):
        """FT-AUTH-004c: /auth/me without token must return 401 or 403."""
        r = client.get("/auth/me")
        assert r.status_code in (401, 403)

    def test_me_with_invalid_token_returns_401(self):
        """FT-AUTH-004d: /auth/me with invalid token must return 401."""
        r = client.get("/auth/me", headers={"Authorization": "Bearer invalidtoken.garbage.here"})
        assert r.status_code == 401

    def test_me_with_tampered_token_returns_401(self, auth_token):
        """FT-AUTH-004e: /auth/me with tampered token must return 401."""
        tampered = auth_token + "tampered"
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# FT-AUTH-005 — Logout
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogoutEndpoint:

    @pytest.fixture
    def auth_token(self):
        user = _unique_user()
        r = client.post("/auth/register", json=user)
        return r.json()["token"]

    def test_logout_returns_200_with_valid_token(self, auth_token):
        """FT-AUTH-005a: POST /auth/logout with valid token must return 200."""
        r = client.post("/auth/logout", headers={"Authorization": f"Bearer {auth_token}"})
        assert r.status_code == 200

    def test_logout_returns_ok_status(self, auth_token):
        """FT-AUTH-005b: Logout response must include status=ok."""
        r = client.post("/auth/logout", headers={"Authorization": f"Bearer {auth_token}"})
        assert r.json().get("status") == "ok"

    def test_logout_without_token_returns_401_or_403(self):
        """FT-AUTH-005c: Logout without token must return 401 or 403."""
        r = client.post("/auth/logout")
        assert r.status_code in (401, 403)
