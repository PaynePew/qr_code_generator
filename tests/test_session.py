"""Pure-logic tests for the signed cookie session (no DB).

Assert the externally-observable contract: a freshly-issued cookie round-trips
to its user id, while a tampered, foreign-secret, or expired cookie reads back as
"no session" (None) rather than raising — so a bad cookie is indistinguishable
from no cookie at the dependency boundary.
"""

from __future__ import annotations

import pytest

from backend import session
from backend.session import SessionConfig


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("SECRET", "unit-test-secret")
    monkeypatch.delenv("SESSION_MAX_AGE", raising=False)
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    return SessionConfig()


class TestRoundTrip:
    def test_issued_cookie_reads_back_user_id(self, config):
        cookie = session.issue_session(42, config)
        assert session.read_session(cookie, config) == 42


class TestRejection:
    def test_empty_cookie_is_no_session(self, config):
        assert session.read_session("", config) is None

    def test_tampered_cookie_is_no_session(self, config):
        cookie = session.issue_session(7, config)
        assert session.read_session(cookie + "x", config) is None

    def test_cookie_from_other_secret_is_no_session(self, monkeypatch):
        monkeypatch.setenv("SECRET", "secret-a")
        cfg_a = SessionConfig()
        cookie = session.issue_session(7, cfg_a)

        monkeypatch.setenv("SECRET", "secret-b")
        cfg_b = SessionConfig()
        assert session.read_session(cookie, cfg_b) is None

    def test_expired_cookie_is_no_session(self, monkeypatch):
        monkeypatch.setenv("SECRET", "unit-test-secret")
        cfg = SessionConfig()
        cookie = session.issue_session(7, cfg)
        # A negative max_age makes even a just-issued cookie already expired,
        # deterministically exercising the SignatureExpired path without sleeping.
        monkeypatch.setenv("SESSION_MAX_AGE", "-1")
        expired_cfg = SessionConfig()
        assert session.read_session(cookie, expired_cfg) is None


class TestConfig:
    def test_secure_defaults_true_for_prod(self, monkeypatch):
        monkeypatch.setenv("SECRET", "x")
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        assert SessionConfig().cookie_secure is True

    def test_secure_can_be_disabled_for_local_http(self, monkeypatch):
        monkeypatch.setenv("SECRET", "x")
        monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
        assert SessionConfig().cookie_secure is False

    def test_secure_rejects_non_boolean(self, monkeypatch):
        monkeypatch.setenv("SECRET", "x")
        monkeypatch.setenv("SESSION_COOKIE_SECURE", "yes")
        with pytest.raises(RuntimeError):
            SessionConfig()

    def test_missing_secret_raises(self, monkeypatch):
        monkeypatch.delenv("SECRET", raising=False)
        with pytest.raises(RuntimeError):
            SessionConfig()
