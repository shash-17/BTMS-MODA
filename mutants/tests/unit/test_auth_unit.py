"""
unit/test_auth_unit.py — Unit Tests for BTMS Auth Service
──────────────────────────────────────────────────────────
Tests JWT token creation/decoding, password hashing utilities,
Pydantic validators, and pure auth logic without any HTTP layer.

Run:
    pytest tests/unit/test_auth_unit.py -v
"""

import sys
import time
import datetime
from pathlib import Path

import pytest
import bcrypt
import jwt as pyjwt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auth_service"))

from main import (
    create_token,
    decode_token,
    JWT_SECRET,
    JWT_ALGO,
    JWT_EXPIRY,
)


# ═══════════════════════════════════════════════════════════════════════════════
# UT-AUTH-001 — create_token
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateToken:

    def test_creates_a_string(self):
        """UT-AUTH-001a: create_token must return a non-empty string."""
        token = create_token(1, "testuser", "operator")
        assert isinstance(token, str) and len(token) > 10

    def test_token_is_valid_jwt(self):
        """UT-AUTH-001b: Token must be decodable as a valid JWT."""
        token = create_token(1, "testuser", "operator")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert payload is not None

    def test_token_contains_sub_field(self):
        """UT-AUTH-001c: JWT payload must contain 'sub' field with user ID."""
        token = create_token(42, "alice", "operator")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert payload["sub"] == "42"

    def test_token_contains_username(self):
        """UT-AUTH-001d: JWT payload must contain 'username'."""
        token = create_token(1, "alice", "operator")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert payload["username"] == "alice"

    def test_token_contains_role(self):
        """UT-AUTH-001e: JWT payload must contain 'role'."""
        token = create_token(1, "admin", "admin")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert payload["role"] == "admin"

    def test_token_has_expiry(self):
        """UT-AUTH-001f: JWT must have an 'exp' claim."""
        token = create_token(1, "testuser", "operator")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert "exp" in payload

    def test_token_expiry_is_future(self):
        """UT-AUTH-001g: exp must be in the future."""
        token = create_token(1, "testuser", "operator")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert payload["exp"] > time.time()

    def test_tokens_for_different_users_differ(self):
        """UT-AUTH-001h: Tokens for different user IDs must be different."""
        t1 = create_token(1, "alice", "operator")
        t2 = create_token(2, "bob", "operator")
        assert t1 != t2

    def test_admin_and_operator_tokens_differ(self):
        """UT-AUTH-001i: Tokens for different roles must differ."""
        t_op = create_token(1, "user", "operator")
        t_ad = create_token(1, "user", "admin")
        assert t_op != t_ad


# ═══════════════════════════════════════════════════════════════════════════════
# UT-AUTH-002 — decode_token
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecodeToken:

    def test_decodes_valid_token(self):
        """UT-AUTH-002a: decode_token must return payload for valid token."""
        token = create_token(10, "charlie", "operator")
        payload = decode_token(token)
        assert payload["username"] == "charlie"

    def test_raises_on_invalid_signature(self):
        """UT-AUTH-002b: Tampered token must raise HTTPException 401."""
        from fastapi import HTTPException
        token = create_token(1, "testuser", "operator") + "tampered"
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_raises_on_expired_token(self):
        """UT-AUTH-002c: Expired token must raise HTTPException 401."""
        from fastapi import HTTPException
        # Create a token that expired 1 second ago
        payload = {
            "sub": "1",
            "username": "testuser",
            "role": "operator",
            "iat": datetime.datetime.utcnow() - datetime.timedelta(hours=25),
            "exp": datetime.datetime.utcnow() - datetime.timedelta(seconds=1),
        }
        expired_token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(expired_token)
        assert exc_info.value.status_code == 401

    def test_raises_on_junk_token(self):
        """UT-AUTH-002d: Random string must raise HTTPException 401."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            decode_token("this.is.not.a.jwt")

    def test_raises_on_wrong_secret(self):
        """UT-AUTH-002e: Token signed with wrong secret must raise 401."""
        from fastapi import HTTPException
        payload = {
            "sub": "1", "username": "hack", "role": "admin",
            "iat": datetime.datetime.utcnow(),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        }
        bad_token = pyjwt.encode(payload, "wrong-secret", algorithm=JWT_ALGO)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(bad_token)
        assert exc_info.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# UT-AUTH-003 — Password Hashing (bcrypt)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPasswordHashing:

    def test_hash_is_not_plaintext(self):
        """UT-AUTH-003a: Hashed password must not equal the plaintext."""
        pw = b"securepassword"
        hashed = bcrypt.hashpw(pw, bcrypt.gensalt())
        assert hashed != pw

    def test_correct_password_verifies(self):
        """UT-AUTH-003b: checkpw must return True for correct password."""
        pw = b"mypassword123"
        hashed = bcrypt.hashpw(pw, bcrypt.gensalt())
        assert bcrypt.checkpw(pw, hashed)

    def test_wrong_password_fails_verification(self):
        """UT-AUTH-003c: checkpw must return False for wrong password."""
        pw = b"correctpassword"
        wrong = b"wrongpassword"
        hashed = bcrypt.hashpw(pw, bcrypt.gensalt())
        assert not bcrypt.checkpw(wrong, hashed)

    def test_same_password_gives_different_hashes(self):
        """UT-AUTH-003d: bcrypt must produce unique salt per call (rainbow table resistance)."""
        pw = b"samepassword"
        h1 = bcrypt.hashpw(pw, bcrypt.gensalt())
        h2 = bcrypt.hashpw(pw, bcrypt.gensalt())
        assert h1 != h2

    def test_hashed_starts_with_bcrypt_prefix(self):
        """UT-AUTH-003e: bcrypt hash must start with $2b$ prefix."""
        pw = b"testpw"
        hashed = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
        assert hashed.startswith("$2b$")


# ═══════════════════════════════════════════════════════════════════════════════
# UT-AUTH-004 — Input Validation (Pydantic models via direct validation)
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:

    def test_short_username_rejected(self):
        """UT-AUTH-004a: Username shorter than 3 chars must be rejected."""
        from pydantic import ValidationError
        from main import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(username="ab", email="test@test.com", password="password123")

    def test_long_username_rejected(self):
        """UT-AUTH-004b: Username longer than 32 chars must be rejected."""
        from pydantic import ValidationError
        from main import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(username="a" * 33, email="test@test.com", password="password123")

    def test_special_chars_in_username_rejected(self):
        """UT-AUTH-004c: Username with special chars must be rejected."""
        from pydantic import ValidationError
        from main import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(username="user@name!", email="test@test.com", password="password123")

    def test_short_password_rejected(self):
        """UT-AUTH-004d: Password shorter than 6 chars must be rejected."""
        from pydantic import ValidationError
        from main import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(username="validuser", email="test@test.com", password="abc")

    def test_valid_registration_data_accepted(self):
        """UT-AUTH-004e: Valid registration data must pass validation."""
        from main import RegisterRequest
        req = RegisterRequest(username="validuser", email="user@example.com", password="securepass")
        assert req.username == "validuser"

    def test_username_lowercased(self):
        """UT-AUTH-004f: Username must be stored as lowercase."""
        from main import RegisterRequest
        req = RegisterRequest(username="UserName", email="user@example.com", password="securepass")
        assert req.username == "username"
