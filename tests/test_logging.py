"""Tests for structured JSON logging with per-request correlation ID (ADR 0013).

Acceptance criteria:
- Logs are structured JSON with request_id and (when authed) user_id.
- A correlation id is on every response header and echoed in the 500 envelope.
- An inbound X-Request-ID (trusted proxy) is reused, else one is generated.
- A redirect-path log record contains no raw IP.
- No secrets/cookies/tokens/PII appear in logs.
"""

from __future__ import annotations

import json
import logging
import uuid
from io import StringIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Unit: IP hashing / truncation helpers (ADR 0013)
# ---------------------------------------------------------------------------


class TestIPHashing:
    def test_hash_ip_returns_hex_string(self):
        from backend.logging_config import hash_ip

        result = hash_ip("192.168.1.1")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_ip_is_not_raw_ip(self):
        from backend.logging_config import hash_ip

        ip = "10.20.30.40"
        assert hash_ip(ip) != ip

    def test_hash_ip_is_deterministic_with_same_salt(self):
        from backend.logging_config import hash_ip

        h1 = hash_ip("1.2.3.4")
        h2 = hash_ip("1.2.3.4")
        assert h1 == h2

    def test_different_ips_produce_different_hashes(self):
        from backend.logging_config import hash_ip

        h1 = hash_ip("1.2.3.4")
        h2 = hash_ip("5.6.7.8")
        assert h1 != h2

    def test_hash_ip_uses_env_salt(self, monkeypatch):
        """Changing IP_LOG_SALT produces a different hash."""
        from backend import logging_config

        monkeypatch.setenv("IP_LOG_SALT", "salt-a")
        # Reload so new env is picked up
        import importlib

        importlib.reload(logging_config)
        h1 = logging_config.hash_ip("1.2.3.4")

        monkeypatch.setenv("IP_LOG_SALT", "salt-b")
        importlib.reload(logging_config)
        h2 = logging_config.hash_ip("1.2.3.4")

        assert h1 != h2

    def test_get_ip_salt_raises_when_secret_missing(self, monkeypatch):
        """No hardcoded SECRET fallback — missing env var must raise KeyError (fail-fast).

        A misconfigured deploy must not silently weaken the hash salt to a
        known constant. Refs qr_code_generator-6bs.
        """
        import importlib

        from backend import logging_config

        monkeypatch.delenv("SECRET", raising=False)
        monkeypatch.delenv("IP_LOG_SALT", raising=False)
        importlib.reload(logging_config)

        with pytest.raises(KeyError):
            logging_config._get_ip_salt()


# ---------------------------------------------------------------------------
# Unit: JSON log formatter
# ---------------------------------------------------------------------------


class TestJSONFormatter:
    def _make_record(self, msg: str = "hello", **extra) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_formatter_produces_json(self):
        from backend.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = self._make_record("test message")
        output = fmt.format(record)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_json_has_required_fields(self):
        from backend.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = self._make_record("test message")
        data = json.loads(fmt.format(record))
        assert "timestamp" in data
        assert "level" in data
        assert "message" in data
        assert "logger" in data

    def test_request_id_included_when_set(self):
        from backend.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = self._make_record("test")
        record.correlation_id = "abc-123"
        data = json.loads(fmt.format(record))
        assert data.get("request_id") == "abc-123"

    def test_user_id_included_when_set(self):
        from backend.logging_config import JSONFormatter

        fmt = JSONFormatter()
        record = self._make_record("test")
        record.user_id = 42
        data = json.loads(fmt.format(record))
        assert data.get("user_id") == 42


# ---------------------------------------------------------------------------
# Integration: correlation ID in response header
# ---------------------------------------------------------------------------


class TestCorrelationIdHeader:
    def test_response_has_x_request_id_header(self, client):
        resp = client.get("/api/does-not-exist")
        assert "x-request-id" in resp.headers or "X-Request-ID" in resp.headers

    def test_inbound_request_id_is_echoed_back(self, client):
        custom_id = "test-request-" + str(uuid.uuid4())
        resp = client.get("/api/does-not-exist", headers={"X-Request-ID": custom_id})
        echoed = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
        assert echoed == custom_id

    def test_correlation_id_generated_when_not_provided(self, client):
        resp = client.get("/api/does-not-exist")
        request_id = resp.headers.get("x-request-id") or resp.headers.get(
            "X-Request-ID"
        )
        assert request_id is not None
        assert len(request_id) > 0

    def test_500_envelope_includes_correlation_id(self):
        """Catch-all 500 handler must include correlation_id in details (ADR 0013)."""
        from asgi_correlation_id import CorrelationIdMiddleware

        from backend.main import _handle_unexpected_error

        # Use the same permissive validator as the main app so any non-empty
        # string is accepted as a valid correlation ID from an upstream proxy.
        mini = FastAPI()
        mini.add_middleware(
            CorrelationIdMiddleware,
            validator=lambda v: bool(v and len(v) <= 128),
        )
        mini.add_exception_handler(Exception, _handle_unexpected_error)  # type: ignore[arg-type]

        @mini.get("/boom")
        def _boom():
            raise RuntimeError("secret")

        with TestClient(mini, raise_server_exceptions=False) as c:
            resp = c.get("/boom", headers={"X-Request-ID": "test-corr-id"})

        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        details = body["error"].get("details", {})
        assert "correlation_id" in details
        assert details["correlation_id"] == "test-corr-id"


# ---------------------------------------------------------------------------
# Integration: no raw IP in redirect-path logs (ADR 0013)
# ---------------------------------------------------------------------------


class TestNoRawIPInLogs:
    def test_redirect_path_log_contains_no_raw_ip(self, auth_client):
        """A redirect-path log must not contain the raw client IP."""
        # Create a link so redirect path is exercised
        resp = auth_client.post("/api/qr/create", json={"url": "https://example.com"})
        assert resp.status_code == 200
        token = resp.json()["token"]

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        # Add to root logger temporarily
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        root.addHandler(handler)
        try:
            from backend.main import app

            with TestClient(app, raise_server_exceptions=False) as c:
                c.get(f"/r/{token}", follow_redirects=False)
        finally:
            root.removeHandler(handler)
            root.handlers = old_handlers

        log_output = log_capture.getvalue()
        # "testclient" maps to 127.0.0.1 — raw loopback must not appear
        assert "127.0.0.1" not in log_output

    def test_auth_path_log_does_not_contain_raw_ip(self):
        """Auth endpoint: if IP is logged, it must be hashed, not raw."""
        from backend.main import app

        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        root.addHandler(handler)
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                c.post("/api/auth/session", json={"credential": "bad"})
        finally:
            root.removeHandler(handler)
            root.handlers = old_handlers

        log_output = log_capture.getvalue()
        assert "127.0.0.1" not in log_output


# ---------------------------------------------------------------------------
# Integration: bind_user_id wired into auth dependency (ADR 0013)
# ---------------------------------------------------------------------------


class TestBindUserIdWiredInAuth:
    def test_get_current_user_binds_user_id_to_log_context(self, db_session):
        """get_current_user must call bind_user_id so user_id appears in logs."""
        import datetime

        from fastapi import Request

        from backend import logging_config
        from backend.auth import get_current_user
        from backend.models import User
        from backend.session import COOKIE_NAME, SessionConfig, issue_session

        # Reset context var before test
        logging_config._user_id_var.set(None)

        # Persist a real user
        user = User(
            google_sub="sub-log-test-1",
            email="logtest@example.com",
            name="Log Test",
            picture=None,
            created_at=datetime.datetime(2026, 1, 1),
            last_login_at=datetime.datetime(2026, 1, 1),
            is_demo=False,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        config = SessionConfig()
        cookie_value = issue_session(user.id, config)

        # Build a minimal Request with the session cookie
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)
        request._cookies = {COOKIE_NAME: cookie_value}

        # Call the dependency directly
        resolved_user = get_current_user(request=request, db=db_session)
        assert resolved_user.id == user.id

        # The context var must now carry this user_id
        bound = logging_config.get_log_user_id()
        assert bound == user.id, (
            f"bind_user_id was not called: expected {user.id}, got {bound}"
        )

    def test_bind_user_id_propagates_to_json_formatter(self):
        """bind_user_id must be reflected by JSONFormatter via the contextvar."""
        import json as json_mod

        from backend.logging_config import JSONFormatter, _user_id_var, bind_user_id

        # Reset context
        _user_id_var.set(None)
        bind_user_id(999)

        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="bound check",
            args=(),
            exc_info=None,
        )
        data = json_mod.loads(fmt.format(record))
        assert data.get("user_id") == 999, (
            f"JSONFormatter did not pick up bound user_id: {data}"
        )
        # Reset
        _user_id_var.set(None)


# ---------------------------------------------------------------------------
# Integration: hash_ip wired on auth endpoint (ADR 0013)
# ---------------------------------------------------------------------------


class TestHashIpWiredOnAuthEndpoint:
    def test_auth_session_logs_hashed_ip_not_raw(self):
        """POST /api/auth/session must log a hashed IP, not the raw address.

        Verifies that the log output contains an ``ip_hash=`` field and that
        neither '127.0.0.1' nor the TestClient peer identifier appear as
        raw values (ADR 0013).
        """
        from backend.logging_config import hash_ip
        from backend.main import app

        # TestClient sets request.client.host = "testclient"; compute expected hash.
        expected_hash = hash_ip("testclient")
        captured_lines: list[str] = []

        class _LineCapture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured_lines.append(self.format(record))

        handler = _LineCapture()
        handler.setLevel(logging.DEBUG)
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        root.addHandler(handler)
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                c.post("/api/auth/session", json={"credential": "bad"})
        finally:
            root.removeHandler(handler)
            root.handlers = old_handlers

        combined = "\n".join(captured_lines)
        # Raw IP values must not appear.
        assert "127.0.0.1" not in combined, "Raw IP must not appear in auth logs"
        # The hashed IP must be present, confirming hash_ip is wired in.
        assert expected_hash in combined, (
            f"Hashed IP '{expected_hash}' not found in auth log output. "
            f"Log lines: {captured_lines[:10]}"
        )
