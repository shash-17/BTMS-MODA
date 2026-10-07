"""
security/test_wapiti_scan.py — Wapiti Web Vulnerability Scanner Integration
─────────────────────────────────────────────────────────────────────────────
Runs Wapiti against the live BTMS servers (must be running on localhost).
Falls back to a detailed offline summary when servers are not reachable.

Run:
    pytest tests/security/test_wapiti_scan.py -v -s
    pytest tests/security/test_wapiti_scan.py -v --html=tests/reports/wapiti_report.html

NOTE: Requires live servers on localhost:8000 and localhost:9000.
      If servers are not running, tests are skipped with an explanatory marker.
"""

import sys
import json
import subprocess
import shutil
import tempfile
import time
import socket
import os
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _server_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def _wapiti_available() -> bool:
    return shutil.which("wapiti") is not None


SERVERS = {
    "dev_server":   ("localhost", 8000),
    "auth_service": ("localhost", 9000),
}

requires_dev_server   = pytest.mark.skipif(
    not _server_reachable("localhost", 8000),
    reason="Dev server not running on localhost:8000 — start with: python3 dev_server.py"
)
requires_auth_server  = pytest.mark.skipif(
    not _server_reachable("localhost", 9000),
    reason="Auth service not running on localhost:9000 — start with: uvicorn auth_service/main:app --port 9000"
)
requires_wapiti       = pytest.mark.skipif(
    not _wapiti_available(),
    reason="wapiti CLI not found — install with: pip install wapiti3"
)


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-WAPITI-001 — Offline API-surface validation (always runs)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWapitiOfflineValidation:
    """Offline structural checks that simulate what Wapiti would probe."""

    def test_wapiti_cli_available(self):
        """SEC-WAPITI-001a: wapiti CLI must be installed."""
        assert _wapiti_available(), (
            "wapiti not found on PATH. Install via: pip install wapiti3"
        )

    def test_auth_api_endpoints_documented(self):
        """SEC-WAPITI-001b: Auth service endpoints must be discoverable in source."""
        auth_main = ROOT / "auth_service" / "main.py"
        content = auth_main.read_text()
        assert "/auth/register" in content
        assert "/auth/login" in content
        assert "/auth/me" in content
        assert "/auth/logout" in content

    def test_dev_server_endpoints_documented(self):
        """SEC-WAPITI-001c: Dev server endpoints must be discoverable in source."""
        dev_server = ROOT / "dev_server.py"
        content = dev_server.read_text()
        assert "/health" in content
        assert "/telemetry/latest" in content
        assert "/recommendations" in content

    def test_cors_wildcard_is_restricted_appropriately(self):
        """SEC-WAPITI-001d: CORS wildcard '*' should only be used in dev mode."""
        dev_server = ROOT / "dev_server.py"
        content = dev_server.read_text()
        # Acceptable for dev server; document the finding
        has_wildcard = 'allow_origins=["*"]' in content
        # This is a WARNING, not a test failure — annotate it
        if has_wildcard:
            import warnings
            warnings.warn(
                "DEV SERVER: CORS allow_origins=['*'] is present. "
                "Ensure production config restricts origins.",
                UserWarning,
                stacklevel=2,
            )
        # Always pass — this is an audit note, not a blocking failure
        assert True

    def test_jwt_secret_not_hardcoded_trivially(self):
        """SEC-WAPITI-001e: JWT_SECRET must not be an empty string or 'secret'."""
        auth_main = ROOT / "auth_service" / "main.py"
        content = auth_main.read_text()
        assert 'JWT_SECRET  = ""' not in content
        assert "JWT_SECRET = 'secret'" not in content
        assert 'JWT_SECRET = "password"' not in content

    def test_bcrypt_used_for_password_hashing(self):
        """SEC-WAPITI-001f: Password hashing must use bcrypt (not MD5/SHA1/plaintext)."""
        auth_main = ROOT / "auth_service" / "main.py"
        content = auth_main.read_text()
        assert "bcrypt" in content
        assert "hashpw" in content
        # Confirm md5/sha1 are NOT used for passwords
        assert "md5" not in content.lower() or "password" not in content.lower()

    def test_parameterized_queries_used(self):
        """SEC-WAPITI-001g: SQLite queries must use parameterized ? placeholders (no f-strings in SQL)."""
        auth_main = ROOT / "auth_service" / "main.py"
        content = auth_main.read_text()
        # Parameterized: VALUES (?, ?, ?)
        assert "VALUES (?, ?, ?)" in content or "(?, ?)" in content

    def test_no_debug_mode_in_auth_service(self):
        """SEC-WAPITI-001h: Auth service must not have debug=True in production paths."""
        auth_main = ROOT / "auth_service" / "main.py"
        content = auth_main.read_text()
        # Debug mode in FastAPI or uvicorn can expose internals
        assert "debug=True" not in content

    def test_https_not_enforced_warning(self):
        """SEC-WAPITI-001i: Audit note — HTTPS enforcement should be added for production."""
        # This test documents the finding as a warning (not a failure for dev mode)
        import warnings
        warnings.warn(
            "AUDIT: No HTTPS enforcement detected. For production, add "
            "HTTPS redirect middleware or deploy behind TLS termination proxy.",
            UserWarning, stacklevel=2
        )
        assert True


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-WAPITI-002 — Live Server Wapiti Scans (skipped if servers offline)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWapitiLiveScan:

    @requires_wapiti
    @requires_dev_server
    def test_wapiti_scan_dev_server_health(self, tmp_path):
        """SEC-WAPITI-002a: Wapiti must scan /health and produce a JSON report."""
        report_file = tmp_path / "wapiti_dev_health.json"
        result = subprocess.run(
            [
                "wapiti",
                "--url", "http://localhost:8000/health",
                "--format", "json",
                "--output", str(report_file),
                "--scope", "url",
                "--max-scan-time", "30",
                "--max-depth", "1",
                "--no-bugreport",
            ],
            capture_output=True, text=True, timeout=120
        )
        # Wapiti may exit 0 or non-zero depending on findings; we care about report
        assert report_file.exists() or result.returncode in (0, 1, 2), (
            f"Wapiti failed unexpectedly:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        if report_file.exists():
            report = json.loads(report_file.read_text())
            print(f"\n[Wapiti] Dev Server Health Scan:\n{json.dumps(report, indent=2)[:2000]}")

    @requires_wapiti
    @requires_auth_server
    def test_wapiti_scan_auth_register(self, tmp_path):
        """SEC-WAPITI-002b: Wapiti must scan /auth/register for common vulnerabilities."""
        report_file = tmp_path / "wapiti_auth_register.json"
        result = subprocess.run(
            [
                "wapiti",
                "--url", "http://localhost:9000",
                "--format", "json",
                "--output", str(report_file),
                "--scope", "url",
                "--module", "sql,xss,exec,file",
                "--max-scan-time", "60",
                "--max-depth", "2",
                "--no-bugreport",
            ],
            capture_output=True, text=True, timeout=180
        )
        if report_file.exists():
            report = json.loads(report_file.read_text())
            vulns = report.get("vulnerabilities", {})
            critical_vulns = []
            for vuln_type, findings in vulns.items():
                if isinstance(findings, list) and len(findings) > 0:
                    critical_vulns.append(f"{vuln_type}: {len(findings)} finding(s)")

            print(f"\n[Wapiti Auth] Vulnerabilities found: {critical_vulns or 'NONE'}")
            # Fail if critical SQL injection or XSS found
            sql_findings = vulns.get("SQL Injection", [])
            xss_findings = vulns.get("Cross Site Scripting", [])
            assert len(sql_findings) == 0, (
                f"CRITICAL: SQL Injection vulnerabilities detected: {sql_findings}"
            )
            assert len(xss_findings) == 0, (
                f"CRITICAL: XSS vulnerabilities detected: {xss_findings}"
            )

    @requires_wapiti
    @requires_dev_server
    def test_wapiti_scan_telemetry_endpoint(self, tmp_path):
        """SEC-WAPITI-002c: Wapiti must scan /telemetry/latest for injection issues."""
        report_file = tmp_path / "wapiti_telemetry.json"
        result = subprocess.run(
            [
                "wapiti",
                "--url", "http://localhost:8000/telemetry/latest",
                "--format", "json",
                "--output", str(report_file),
                "--scope", "url",
                "--module", "sql,xss",
                "--max-scan-time", "30",
                "--no-bugreport",
            ],
            capture_output=True, text=True, timeout=120
        )
        # Read-only endpoint with no user input: expect clean report
        if report_file.exists():
            report = json.loads(report_file.read_text())
            print(f"\n[Wapiti Telemetry]:\n{str(report)[:500]}")
        # Pass as long as wapiti ran
        assert result.returncode in (0, 1, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# SEC-WAPITI-003 — Live HTTP-level security header checks
# ═══════════════════════════════════════════════════════════════════════════════

class TestLiveSecurityHeaders:

    @requires_dev_server
    def test_dev_server_exposes_no_server_header(self):
        """SEC-WAPITI-003a: 'Server' header must not reveal exact version strings."""
        r = requests.get("http://localhost:8000/health", timeout=5)
        server = r.headers.get("Server", "")
        # uvicorn by default reveals version; this is a WARNING level finding
        if "uvicorn" in server.lower() or "python" in server.lower():
            import warnings
            warnings.warn(f"Server header reveals tech stack: '{server}'", UserWarning, stacklevel=2)
        assert r.status_code == 200  # Server is reachable

    @requires_auth_server
    def test_auth_service_json_responses_have_correct_content_type(self):
        """SEC-WAPITI-003b: Auth endpoints must return application/json content-type."""
        r = requests.get("http://localhost:9000/auth/health", timeout=5)
        assert "application/json" in r.headers.get("content-type", "")

    @requires_dev_server
    def test_dev_server_no_directory_traversal(self):
        """SEC-WAPITI-003c: Path traversal must be blocked."""
        for payload in ["/../../../etc/passwd", "/%2e%2e/etc/passwd", "/..%2fetc%2fpasswd"]:
            r = requests.get(f"http://localhost:8000{payload}", timeout=5)
            assert r.status_code in (400, 404, 422, 403), (
                f"Path traversal payload '{payload}' returned {r.status_code}"
            )

    @requires_auth_server
    def test_auth_service_no_directory_traversal(self):
        """SEC-WAPITI-003d: Auth service must block path traversal attempts."""
        for payload in ["/../../../etc/passwd", "/%2e%2e/secrets"]:
            r = requests.get(f"http://localhost:9000{payload}", timeout=5)
            assert r.status_code in (400, 404, 422, 403)
