"""Per-user create cap + per-IP auth-endpoint cap (ADR 0009 rate-limit re-architecture).

ADR 0009 partially reverses ADR 0007: anonymous create no longer exists, so the
create limiter is keyed by the authenticated **user** (a generous per-account
quota), and the per-IP limiter relocates to guard the auth endpoint
(``POST /api/auth/session``) against account-farming.

These tests assert external behavior through the FastAPI app with an injected
clock (matching the existing limiter integration tests):

- the create cap counts per user, so two users are independent on one IP and one
  user is capped across IPs;
- the auth endpoint cap counts per IP, independent of any session;
- both still emit IETF RateLimit headers and a 429 with Retry-After.
"""

from __future__ import annotations

import itertools

import pytest
from fastapi.testclient import TestClient

from backend import session as session_module
from backend.main import app
from backend.router import get_db
from tests.conftest import make_user

_counter = itertools.count(1)


def _login_as(client, user):
    """Authenticate the client by setting a real signed session cookie.

    The middleware keys the create cap off the *cookie's* uid (the same id
    get_current_user resolves), so a real cookie — not a dependency override —
    is what exercises per-user keying. A fresh SESSION_COOKIE_SECURE=false in the
    test env keeps the cookie storable over the HTTP TestClient.
    """
    config = session_module.SessionConfig()
    client.cookies.set(
        session_module.COOKIE_NAME, session_module.issue_session(user.id, config)
    )


def _create(client, *, ip="1.2.3.4"):
    # One trusted proxy → client is the rightmost XFF entry, so send just `ip`.
    return client.post(
        "/api/qr/create",
        json={"url": f"https://example.com/p{next(_counter)}"},
        headers={"x-forwarded-for": ip},
    )


def _start_session(client, *, ip="9.9.9.9"):
    # The auth endpoint is mocked to fail verification (401), but the per-IP
    # limiter runs in middleware *before* the route, so a denied request still
    # counts toward the cap. We only assert the limiter outcome here.
    return client.post(
        "/api/auth/session",
        json={"credential": "irrelevant"},
        headers={"x-forwarded-for": ip},
    )


def _reset_middleware():
    from backend.rate_limiter.middleware import RateLimitMiddleware

    RateLimitMiddleware.reset_for_tests()


# ── Per-user create cap ─────────────────────────────────────────────────────


@pytest.fixture
def per_user_env(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_HOURLY", "3")
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    # Cookie must be storable over the HTTP TestClient for per-user keying.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


def test_create_cap_is_per_user_not_per_ip(db_session, per_user_env):
    """Exceeding the per-user create quota returns 429 — counted per account."""
    _reset_middleware()
    user = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        _login_as(c, user)
        # Same user, *different* IPs each request: the cap must still trip,
        # proving the key is the user, not the IP.
        for i in range(3):
            assert _create(c, ip=f"10.0.0.{i}").status_code == 200
        r = _create(c, ip="10.0.0.99")
    app.dependency_overrides.clear()

    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert "retry-after" in r.headers
    assert "ratelimit-limit" in r.headers


def test_two_users_share_an_ip_independently(db_session, per_user_env):
    """Two distinct users on one IP get independent create quotas."""
    _reset_middleware()
    user_a = make_user(db_session)
    user_b = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as c:
        _login_as(c, user_a)
        for _ in range(3):
            assert _create(c, ip="172.16.0.1").status_code == 200
        # user_a is now capped on this IP.
        assert _create(c, ip="172.16.0.1").status_code == 429

        # Same IP, different user → still allowed (per-user, not per-IP).
        _login_as(c, user_b)
        assert _create(c, ip="172.16.0.1").status_code == 200
    app.dependency_overrides.clear()


def test_create_clock_advance_unlocks_one_more_for_same_user(db_session, monkeypatch):
    """Per-user create bucket refills on the injected clock (clock-injected, like the IP limiter)."""
    import backend.rate_limiter.middleware as mw_module
    from backend.rate_limiter.limiter import RateLimiter
    from backend.rate_limiter.middleware import RateLimitMiddleware

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_HOURLY", "3")
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    RateLimitMiddleware.reset_for_tests()

    clock = [0.0]
    monkeypatch.setattr(
        mw_module,
        "_create_limiter",
        RateLimiter(hourly_limit=3, clock=lambda: clock[0]),
    )

    user = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        _login_as(c, user)
        for _ in range(3):
            assert _create(c).status_code == 200
        assert _create(c).status_code == 429
        clock[0] = 1201.0  # one hourly token refills at 3600/3 = 1200s
        assert _create(c).status_code == 200
    app.dependency_overrides.clear()


# ── Per-IP auth-endpoint cap ────────────────────────────────────────────────


@pytest.fixture
def auth_limit_env(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AUTH_RATE_LIMIT_HOURLY", "3")
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123.apps.googleusercontent.com")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")


def test_auth_endpoint_is_per_ip_capped(db_session, auth_limit_env):
    """Repeated session attempts from one IP hit the per-IP auth cap with a 429."""
    _reset_middleware()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        # Verification is unmocked → each attempt 401s, but the per-IP limiter
        # runs before the route and counts every attempt.
        for _ in range(3):
            assert _start_session(c, ip="203.0.113.7").status_code == 401
        r = _start_session(c, ip="203.0.113.7")
    app.dependency_overrides.clear()

    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert "retry-after" in r.headers


def test_auth_cap_two_ips_are_independent(db_session, auth_limit_env):
    """The auth cap is per IP: one IP being capped does not affect another."""
    _reset_middleware()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        for _ in range(3):
            _start_session(c, ip="198.51.100.1")
        assert _start_session(c, ip="198.51.100.1").status_code == 429
        assert _start_session(c, ip="198.51.100.2").status_code == 401
    app.dependency_overrides.clear()


def test_create_and_auth_limiters_do_not_share_state(db_session, monkeypatch):
    """Exhausting the auth cap does not consume the create cap (separate limiters)."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_HOURLY", "3")
    monkeypatch.setenv("AUTH_RATE_LIMIT_HOURLY", "3")
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123.apps.googleusercontent.com")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    _reset_middleware()

    user = make_user(db_session)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        # Exhaust the auth cap from this IP.
        for _ in range(4):
            _start_session(c, ip="192.0.2.50")
        assert _start_session(c, ip="192.0.2.50").status_code == 429

        # Create from the same IP as the same user is still allowed: the create
        # limiter is a different bucket keyed by user.
        _login_as(c, user)
        assert _create(c, ip="192.0.2.50").status_code == 200
    app.dependency_overrides.clear()
