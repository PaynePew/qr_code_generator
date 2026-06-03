"""Tests for structured JSON logging with per-request correlation ID (ADR 0013).

Acceptance criteria:
- Logs are structured JSON with request_id and (when authed) user_id.
- A correlation id is on every response header and echoed in the 500 envelope.
- An inbound X-Request-ID (trusted proxy) is reused, else one is generated.
- A redirect-path log record contains no raw IP.
- No secrets/cookies/tokens/PII appear in logs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
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


# ---------------------------------------------------------------------------
# Unit: JSON log formatter
# ---------------------------------------------------------------------------


class TestJSONFormatter:
    def _make_record(self, msg: str = "hello", **extra) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
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
        request_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) > 0

    def test_500_envelope_includes_correlation_id(self):
        """Catch-all 500 handler must include correlation_id in details (ADR 0013)."""
        from backend.main import _handle_unexpected_error
        from asgi_correlation_id import CorrelationIdMiddleware

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
