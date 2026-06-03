"""Integration tests for the auth endpoints (DB-touching — Postgres testcontainer).

Covers the ADR 0009 acceptance matrix end-to-end through the FastAPI app:
posting a valid Google credential creates-or-updates a User and sets an httpOnly
session cookie; the current-user endpoint reflects a valid cookie and 401s
without one; logout clears the cookie; and an invalid Google credential is
rejected. Google verification is mocked at the auth_router seam so no network or
real token is needed.

The TestClient speaks HTTP, so SESSION_COOKIE_SECURE is forced false here; the
Secure attribute itself is asserted in the cookie-attributes test via the raw
Set-Cookie header.
"""
from __future__ import annotations

import pytest

from backend import auth_router as auth_router_module
from backend import session as session_module
from backend.google_identity import GoogleIdentity, InvalidGoogleTokenError
from backend.models import User

CLIENT_ID = "client-123.apps.googleusercontent.com"

IDENTITY = GoogleIdentity(
    google_sub="sub-int-1",
    email="alice@example.com",
    name="Alice",
    picture="https://example.com/a.png",
)


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    # TestClient is HTTP-only; don't mark the cookie Secure or it won't be stored.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


def _mock_verify(monkeypatch, identity=IDENTITY, raises=None):
    def fake(token, client_id):
        assert client_id == CLIENT_ID
        if raises is not None:
            raise raises
        return identity

    monkeypatch.setattr(
        auth_router_module.google_identity, "verify_google_id_token", fake
    )


class TestStartSession:
    def test_valid_credential_creates_user_and_sets_cookie(self, client, db_session, monkeypatch):
        _mock_verify(monkeypatch)
        resp = client.post("/api/auth/session", json={"credential": "good-token"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "alice@example.com"
        assert body["is_demo"] is False
        # A User row was persisted.
        assert db_session.query(User).filter(User.google_sub == "sub-int-1").count() == 1
        # The session cookie was set.
        assert session_module.COOKIE_NAME in resp.cookies

    def test_cookie_is_httponly_lax_and_secure_flag_present(self, client, monkeypatch):
        # Assert attributes on the raw Set-Cookie header (Secure on in prod mode).
        monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
        _mock_verify(monkeypatch)
        resp = client.post("/api/auth/session", json={"credential": "good-token"})
        set_cookie = resp.headers["set-cookie"].lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "secure" in set_cookie

    def test_repeat_login_updates_same_user(self, client, db_session, monkeypatch):
        _mock_verify(monkeypatch)
        client.post("/api/auth/session", json={"credential": "good-token"})

        renamed = GoogleIdentity(google_sub="sub-int-1", email="alice@new.example.com", name="Alice2")
        _mock_verify(monkeypatch, identity=renamed)
        resp = client.post("/api/auth/session", json={"credential": "good-token-2"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@new.example.com"
        assert db_session.query(User).filter(User.google_sub == "sub-int-1").count() == 1

    def test_invalid_credential_is_rejected_401(self, client, monkeypatch):
        _mock_verify(monkeypatch, raises=InvalidGoogleTokenError("nope"))
        resp = client.post("/api/auth/session", json={"credential": "bad-token"})
        assert resp.status_code == 401
        assert session_module.COOKIE_NAME not in resp.cookies

    def test_missing_client_id_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        resp = client.post("/api/auth/session", json={"credential": "good-token"})
        assert resp.status_code == 503


class TestCurrentUser:
    def test_me_returns_user_with_valid_cookie(self, client, monkeypatch):
        _mock_verify(monkeypatch)
        client.post("/api/auth/session", json={"credential": "good-token"})
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_me_returns_401_without_cookie(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_returns_401_with_tampered_cookie(self, client):
        client.cookies.set(session_module.COOKIE_NAME, "not-a-valid-signed-cookie")
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_returns_401_when_session_user_no_longer_exists(self, client):
        # A correctly-signed cookie for a user id that isn't in the DB → 401,
        # not a 500 — the dependency must treat a dangling session as no session.
        config = session_module.SessionConfig()
        client.cookies.set(
            session_module.COOKIE_NAME, session_module.issue_session(999_999, config)
        )
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestEndSession:
    def test_logout_clears_cookie_and_me_then_401(self, client, monkeypatch):
        _mock_verify(monkeypatch)
        client.post("/api/auth/session", json={"credential": "good-token"})
        assert client.get("/api/auth/me").status_code == 200

        logout = client.delete("/api/auth/session")
        assert logout.status_code == 200
        # Cookie jar cleared; subsequent me is unauthenticated.
        assert client.get("/api/auth/me").status_code == 401


class TestDemoSession:
    """Guest entry (ADR 0009): "Try as guest" starts a session as the shared
    read-only demo account with no Google credential — the backend resolves the
    seeded demo User and issues the same kind of session cookie."""

    def test_enters_demo_account_and_sets_cookie(self, client, db_session):
        from tests.conftest import make_user

        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        resp = client.post("/api/auth/demo-session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == demo.id
        assert body["is_demo"] is True
        assert session_module.COOKIE_NAME in resp.cookies
        # The session is real: /me now reflects the demo user.
        assert client.get("/api/auth/me").json()["is_demo"] is True

    def test_returns_503_when_demo_account_not_seeded(self, client):
        # No demo row exists — this is an ops/seed gap, not a client error.
        resp = client.post("/api/auth/demo-session")
        assert resp.status_code == 503
        assert session_module.COOKIE_NAME not in resp.cookies
