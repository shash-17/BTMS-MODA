"""
security/test_auth_security.py — Security Tests for BTMS Auth Service
───────────────────────────────────────────────────────────────────────
Custom Python-based security tests that do NOT require a live server.
Covers: injection, JWT tampering, brute-force, rate-limit signals,
header security, and input boundary attacks.

Run:
    pytest tests/security/test_auth_security.py -v
    pytest tests/security/test_auth_security.py -v --html=tests/reports/security_report.html
"""

import sys
import uuid
import json
import base64
import datetime
from pathlib import Path

import pytest
import jwt as pyjwt
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auth_service"))

from main import app, JWT_SECRET, JWT_ALGO

client = TestClient(app, raise_server_exceptions=False)


def _unique_user():
    uid = uuid.uuid4().hex[:8]
    return {
        "username": f"sec_user_{uid}",
        "email": f"sec_{uid}@btms.local",
        "password": "SecPass@1234",
    }


def _register_and_login():
    user = _unique_user()
    client.post("/auth/register", json=user)
    r = client.post("/auth/login", json={"username": user["username"], "password": user["password"]})
    return r.json().get("token", ""), user


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-001 — SQL Injection Attempts
# ═══════════════════════════════════════════════════════════════════════════════

class TestSQLInjection:

    @pytest.mark.parametrize("payload", [
        {"username": "' OR '1'='1", "password": "anything"},
        {"username": "admin'--", "password": "anything"},
        {"username": "'; DROP TABLE users;--", "password": "x"},
        {"username": "' UNION SELECT * FROM users--", "password": "x"},
        {"username": "1; SELECT sleep(5)--", "password": "x"},
    ])
    def test_sql_injection_in_login_returns_401_not_200(self, payload):
        """SEC-001: SQL injection in username must never grant access (returns 401/422)."""
        r = client.post("/auth/login", json=payload)
        assert r.status_code in (401, 422, 400), (
            f"SQL injection payload succeeded or caused server error: "
            f"status={r.status_code}, payload={payload['username']}"
        )

    @pytest.mark.parametrize("username", [
        "' OR '1'='1",
        "admin'--",
        "x'; INSERT INTO users VALUES(999,'hacked','h@h.com','x','admin',datetime('now'),null)--",
    ])
    def test_sql_injection_in_register_username_rejected(self, username):
        """SEC-001b: SQL injection patterns in username must be rejected."""
        r = client.post("/auth/register", json={
            "username": username,
            "email": "test@test.com",
            "password": "validpass123",
        })
        assert r.status_code in (400, 409, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-002 — JWT Tampering
# ═══════════════════════════════════════════════════════════════════════════════

class TestJWTTampering:

    def test_none_algorithm_attack(self):
        """SEC-002a: 'none' algorithm JWT must be rejected."""
        payload = {
            "sub": "1",
            "username": "admin",
            "role": "admin",
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        }
        # Manually craft a none-alg token
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(
            json.dumps({"sub": "1", "username": "admin", "role": "admin"}).encode()
        ).rstrip(b"=").decode()
        none_token = f"{header}.{body}."
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {none_token}"})
        assert r.status_code == 401

    def test_modified_role_in_jwt(self):
        """SEC-002b: Modifying role claim in JWT body must be rejected (signature invalid)."""
        token, user = _register_and_login()
        parts = token.split(".")
        # Decode and modify payload
        import json, base64
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        decoded["role"] = "admin"
        new_body = base64.urlsafe_b64encode(
            json.dumps(decoded).encode()
        ).rstrip(b"=").decode()
        tampered_token = f"{parts[0]}.{new_body}.{parts[2]}"
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
        assert r.status_code == 401

    def test_empty_bearer_token_rejected(self):
        """SEC-002c: Empty Bearer token must be rejected."""
        r = client.get("/auth/me", headers={"Authorization": "Bearer "})
        assert r.status_code in (401, 403, 422)

    def test_expired_token_rejected(self):
        """SEC-002d: Manually expired JWT must be rejected."""
        payload = {
            "sub": "1",
            "username": "expireduser",
            "role": "operator",
            "iat": datetime.datetime.utcnow() - datetime.timedelta(hours=48),
            "exp": datetime.datetime.utcnow() - datetime.timedelta(hours=24),
        }
        expired = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_jwt_signed_with_wrong_key_rejected(self):
        """SEC-002e: JWT signed with a different secret must be rejected."""
        payload = {
            "sub": "1", "username": "hacker", "role": "admin",
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        }
        bad_token = pyjwt.encode(payload, "wrong-secret-key", algorithm=JWT_ALGO)
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401

    def test_hs256_downgrade_to_rs256_rejected(self):
        """SEC-002f: Claiming RS256 algorithm in header but using symmetric key must be rejected."""
        # Craft a fake RS256 header pointing to HS256 logic
        fake_header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(
            json.dumps({"sub": "1", "username": "hack", "role": "admin"}).encode()
        ).rstrip(b"=").decode()
        bad_token = f"{fake_header}.{body}.fakesig"
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-003 — Brute Force & Credential Stuffing Simulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestBruteForceSimulation:

    def test_repeated_wrong_passwords_always_return_401(self):
        """SEC-003a: Repeated wrong-password login attempts must consistently return 401."""
        user = _unique_user()
        client.post("/auth/register", json=user)
        for _ in range(10):
            r = client.post("/auth/login", json={
                "username": user["username"],
                "password": "wrongpassword",
            })
            assert r.status_code == 401, "Brute force attempt unexpectedly succeeded"

    def test_correct_password_still_works_after_failed_attempts(self):
        """SEC-003b: Valid login must work after multiple failed attempts."""
        user = _unique_user()
        client.post("/auth/register", json=user)
        for _ in range(5):
            client.post("/auth/login", json={
                "username": user["username"],
                "password": "wrongpassword",
            })
        r = client.post("/auth/login", json={
            "username": user["username"],
            "password": user["password"],
        })
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-004 — XSS & Injection in Registration Fields
# ═══════════════════════════════════════════════════════════════════════════════

class TestXSSAndInjection:

    @pytest.mark.parametrize("xss_payload", [
        "<script>alert('xss')</script>",
        "javascript:alert(1)",
        "\"><img src=x onerror=alert(1)>",
        "'; alert(document.cookie); //",
    ])
    def test_xss_in_username_rejected(self, xss_payload):
        """SEC-004a: XSS patterns in username must be rejected by validator."""
        r = client.post("/auth/register", json={
            "username": xss_payload,
            "email": "xss@test.com",
            "password": "validpassword",
        })
        assert r.status_code in (400, 409, 422)

    def test_oversized_username_rejected(self):
        """SEC-004b: Extremely long username (>32 chars) must be rejected."""
        r = client.post("/auth/register", json={
            "username": "a" * 200,
            "email": "long@test.com",
            "password": "validpassword",
        })
        assert r.status_code in (400, 422)

    def test_null_bytes_in_username_rejected(self):
        """SEC-004c: Null bytes in username must be rejected."""
        r = client.post("/auth/register", json={
            "username": "user\x00name",
            "email": "null@test.com",
            "password": "validpassword",
        })
        assert r.status_code in (400, 422)

    def test_unicode_overflow_in_username_rejected(self):
        """SEC-004d: Non-ASCII unicode in username must be rejected by alphanumeric validator."""
        r = client.post("/auth/register", json={
            "username": "用户名测试",
            "email": "unicode@test.com",
            "password": "validpassword",
        })
        assert r.status_code in (400, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-005 — CORS / HTTP Method Security
# ═══════════════════════════════════════════════════════════════════════════════

class TestHTTPMethodSecurity:

    def test_delete_on_auth_endpoints_returns_405(self):
        """SEC-005a: DELETE on /auth/login must return 405."""
        r = client.delete("/auth/login")
        assert r.status_code in (405, 404)

    def test_patch_on_auth_register_returns_405(self):
        """SEC-005b: PATCH on /auth/register must return 405."""
        r = client.patch("/auth/register")
        assert r.status_code in (405, 404)

    def test_get_on_auth_login_returns_405(self):
        """SEC-005c: GET on /auth/login (POST-only) must return 405."""
        r = client.get("/auth/login")
        assert r.status_code in (405, 404)

    def test_credentials_not_in_404_response(self):
        """SEC-005d: 404 responses must not leak internal paths or credentials."""
        r = client.get("/auth/nonexistent_endpoint_xyz")
        assert r.status_code == 404
        body = r.text.lower()
        assert "password" not in body
        assert "jwt_secret" not in body
        assert "btms-super-secret" not in body


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-006 — Password Security
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasswordSecurity:

    def test_password_not_in_register_response(self):
        """SEC-006a: Registration response must never contain the plaintext password."""
        user = _unique_user()
        r = client.post("/auth/register", json=user)
        body = r.text
        assert user["password"] not in body

    def test_password_not_in_login_response(self):
        """SEC-006b: Login response must never contain the plaintext password."""
        user = _unique_user()
        client.post("/auth/register", json=user)
        r = client.post("/auth/login", json={
            "username": user["username"],
            "password": user["password"],
        })
        body = r.text
        assert user["password"] not in body

    def test_password_not_in_me_response(self):
        """SEC-006c: /auth/me response must not contain password hash."""
        token, user = _register_and_login()
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        body = r.json()
        assert "password" not in body
        assert "password_hash" not in body


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-007 — Content-Type Enforcement
# ═══════════════════════════════════════════════════════════════════════════════

class TestContentTypeEnforcement:

    def test_login_with_form_data_rejected(self):
        """SEC-007a: Sending form data instead of JSON to /auth/login must return 422."""
        r = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code in (415, 422)

    def test_register_with_malformed_json_returns_422(self):
        """SEC-007b: Malformed JSON body must return 422."""
        r = client.post(
            "/auth/register",
            content=b"not-valid-json{{{",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422
