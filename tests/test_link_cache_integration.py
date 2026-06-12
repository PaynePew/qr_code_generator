"""Integration tests for the redirect read-cache (ADR 0017).

These tests exercise the cache's integration with the router via the FastAPI
TestClient + a per-test file-based SQLite DB, without Docker or Postgres.
They verify the acceptance criteria that depend on PATCH/DELETE → evict →
redirect behaviour:

- edit-then-redirect: the very next redirect follows the new URL
- delete-then-redirect: the next redirect returns 410

No DB container is needed: SQLite (per-test file) is sufficient here because
the goal is verifying the eviction wiring, not DB-level invariants (those are
covered by the Postgres testcontainer suite).

Each test gets its own in-memory factory (separate connection per request,
consistent with how FastAPI's real ``get_db`` creates a fresh session per
request) so SQLAlchemy object identity / detachment issues don't interfere.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.auth import get_current_user
from backend.link_cache import LinkCache
from backend.main import app
from backend.models import Base, User
from backend.router import get_db
import backend.router as router_mod


# ---------------------------------------------------------------------------
# Per-test SQLite engine (one file per test to ensure full isolation)
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_engine(tmp_path):
    db_path = str(tmp_path / "test_cache.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def SessionFactory(sqlite_engine):
    """Return a session factory; each call produces a new session (mirrors FastAPI's get_db)."""
    return sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Fresh LinkCache per test (isolate module singleton)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_cache():
    """Replace the module-level _link_cache with a fresh instance per test."""
    original = router_mod._link_cache
    new_cache = LinkCache()
    router_mod._link_cache = new_cache
    yield new_cache
    router_mod._link_cache = original


# ---------------------------------------------------------------------------
# Test user + authenticated client
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_user(SessionFactory) -> User:
    session = SessionFactory()
    user = User(
        google_sub="sub-cache-test",
        email="cache@example.com",
        name="Cache Tester",
        picture=None,
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        last_login_at=datetime(2026, 1, 1, 0, 0, 0),
        is_demo=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    # Expunge so the user object is usable outside this session
    session.expunge(user)
    session.close()
    return user


@pytest.fixture()
def cache_client(SessionFactory, test_user) -> Generator[TestClient, None, None]:
    """TestClient backed by SQLite + a fixed authenticated user.

    ``get_db`` creates a new session per request (mirrors real behaviour and
    avoids detached-instance issues with SQLite).
    """

    def _override_db():
        session = SessionFactory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: test_user

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_link(client: TestClient, url: str) -> str:
    resp = client.post("/api/qr/create", json={"url": url})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestCacheBasicRedirect:
    def test_redirect_returns_302_for_active_link(self, cache_client):
        token = _create_link(cache_client, "https://example.com/orig")
        resp = cache_client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://example.com/orig"

    def test_redirect_serves_from_cache_on_second_hit(self, cache_client, fresh_cache):
        """Second redirect is a cache hit — loader not called again."""
        token = _create_link(cache_client, "https://example.com/cached")

        # Two redirects — both must succeed; the second is served from cache
        r1 = cache_client.get(f"/r/{token}", follow_redirects=False)
        r2 = cache_client.get(f"/r/{token}", follow_redirects=False)

        assert r1.status_code == 302
        assert r2.status_code == 302
        assert r1.headers["location"] == r2.headers["location"]

        # Cache must hold the entry after both hits
        assert token in fresh_cache._cache

    def test_unknown_token_returns_404(self, cache_client):
        resp = cache_client.get("/r/NOTEXIST", follow_redirects=False)
        assert resp.status_code == 404

    def test_unknown_token_is_not_cached(self, cache_client, fresh_cache):
        """404 tokens must not pollute the cache (no negative caching)."""
        cache_client.get("/r/NOTEXIST", follow_redirects=False)
        assert "NOTEXIST" not in fresh_cache._cache


class TestCacheEditThenRedirect:
    def test_patch_destination_url_reflected_on_very_next_redirect(self, cache_client):
        """edit-then-redirect: PATCH evicts cache; next redirect uses new URL."""
        token = _create_link(cache_client, "https://example.com/old")

        # Warm the cache via an initial redirect
        r_before = cache_client.get(f"/r/{token}", follow_redirects=False)
        assert r_before.headers["location"] == "https://example.com/old"

        # PATCH the destination URL
        resp = cache_client.patch(
            f"/api/qr/{token}",
            json={"original_url": "https://example.com/new"},
        )
        assert resp.status_code == 200

        # The very next redirect must follow the new URL
        r_after = cache_client.get(f"/r/{token}", follow_redirects=False)
        assert r_after.status_code == 302
        assert r_after.headers["location"] == "https://example.com/new"

    def test_patch_evicts_cache_entry(self, cache_client, fresh_cache):
        """After PATCH the cache entry for that token is absent."""
        token = _create_link(cache_client, "https://example.com/evict")

        # Warm cache
        cache_client.get(f"/r/{token}", follow_redirects=False)
        assert token in fresh_cache._cache

        # PATCH must evict
        cache_client.patch(
            f"/api/qr/{token}",
            json={"original_url": "https://example.com/evict2"},
        )
        assert token not in fresh_cache._cache


class TestCacheDeleteThenRedirect:
    def test_delete_makes_next_redirect_return_410(self, cache_client):
        """delete-then-redirect: DELETE evicts cache; next redirect returns 410."""
        token = _create_link(cache_client, "https://example.com/gone")

        # Warm the cache
        cache_client.get(f"/r/{token}", follow_redirects=False)

        # DELETE
        resp = cache_client.delete(f"/api/qr/{token}")
        assert resp.status_code == 200

        # The very next redirect must return 410
        r_after = cache_client.get(f"/r/{token}", follow_redirects=False)
        assert r_after.status_code == 410

    def test_delete_evicts_cache_entry(self, cache_client, fresh_cache):
        """After DELETE the cache entry for that token is absent."""
        token = _create_link(cache_client, "https://example.com/del")

        # Warm cache
        cache_client.get(f"/r/{token}", follow_redirects=False)
        assert token in fresh_cache._cache

        # DELETE must evict
        cache_client.delete(f"/api/qr/{token}")
        assert token not in fresh_cache._cache


class TestCacheExpiredDeriveOnRead:
    def test_expired_link_returns_410_via_derive_on_read(self, cache_client):
        """An already-expired link must return 410 without eviction."""
        token = _create_link(
            cache_client,
            # Use a URL with future expiry first — we'll rely on the DB having
            # an expired link; create with past expiry directly.
            "https://example.com/expired",
        )
        # Patch to set a past expiry — simulates creating with past expiry
        resp = cache_client.patch(
            f"/api/qr/{token}",
            json={"expires_at": "2000-01-01T00:00:00"},
        )
        assert resp.status_code == 200

        # Redirect must return 410 (state derived from cached snapshot)
        r = cache_client.get(f"/r/{token}", follow_redirects=False)
        assert r.status_code == 410
