"""Unit tests for the link_cache deep module (ADR 0017).

Tests cover: cache hit / miss, load-on-miss, eviction, derive-on-read
semantics (expired entry yields 410 without eviction), and no-negative-caching.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.link_cache import LinkCache, LinkSnapshot
from backend.link_state import LinkState, derive_state
from backend.models import Link

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_link(
    token: str = "abc1234",
    original_url: str = "https://example.com",
    expires_at: datetime | None = None,
    deleted_at: datetime | None = None,
) -> Link:
    link = MagicMock(spec=Link)
    link.token = token
    link.original_url = original_url
    link.expires_at = expires_at
    link.deleted_at = deleted_at
    return link


def _future() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)


def _past() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Unit tests: LinkCache
# ---------------------------------------------------------------------------


class TestLinkCacheMiss:
    def test_miss_calls_loader(self):
        """First access calls loader exactly once."""
        cache = LinkCache()
        link = _make_link()
        loader = MagicMock(return_value=link)

        cache.get_or_load("abc1234", loader)

        loader.assert_called_once()

    def test_miss_returns_snapshot_matching_link(self):
        cache = LinkCache()
        link = _make_link(
            original_url="https://target.example",
            expires_at=_future(),
        )
        snapshot = cache.get_or_load("abc1234", lambda: link)

        assert snapshot.original_url == "https://target.example"
        assert snapshot.expires_at == link.expires_at
        assert snapshot.deleted_at is None


class TestLinkCacheHit:
    def test_hit_does_not_call_loader_again(self):
        """Second access is served from cache — loader not called a second time."""
        cache = LinkCache()
        link = _make_link()
        loader = MagicMock(return_value=link)

        cache.get_or_load("abc1234", loader)
        cache.get_or_load("abc1234", loader)

        assert loader.call_count == 1

    def test_hit_returns_same_snapshot(self):
        cache = LinkCache()
        link = _make_link(original_url="https://hit.example")
        loader = MagicMock(return_value=link)

        s1 = cache.get_or_load("abc1234", loader)
        s2 = cache.get_or_load("abc1234", loader)

        assert s1.original_url == s2.original_url == "https://hit.example"


class TestLinkCacheEvict:
    def test_evict_forces_loader_on_next_access(self):
        """After evict(), the next get_or_load calls loader again."""
        cache = LinkCache()
        link = _make_link()
        loader = MagicMock(return_value=link)

        cache.get_or_load("abc1234", loader)
        cache.evict("abc1234")
        cache.get_or_load("abc1234", loader)

        assert loader.call_count == 2

    def test_evict_unknown_token_is_noop(self):
        """Evicting an absent token does not raise."""
        cache = LinkCache()
        cache.evict("nothere")  # Must not raise


class TestLinkCacheNoNegativeCaching:
    def test_loader_exception_is_not_cached(self):
        """If the loader raises (token not found), the cache stays empty."""
        from backend.link_state import LinkNotFoundError

        cache = LinkCache()

        def bad_loader():
            raise LinkNotFoundError("notfound")

        with pytest.raises(LinkNotFoundError):
            cache.get_or_load("notfound", bad_loader)

        # A second call with a valid loader should work (no stale negative entry)
        link = _make_link(token="notfound")
        snapshot = cache.get_or_load("notfound", lambda: link)
        assert snapshot.original_url == link.original_url


class TestDeriveStateOnRead:
    """Cached entries derive state at read time, so expiry resolves automatically."""

    def test_active_link_resolves_to_active(self):
        snapshot = LinkSnapshot(
            original_url="https://example.com",
            expires_at=_future(),
            deleted_at=None,
        )
        # Synthesize a Link-like object for derive_state
        link = _make_link(
            expires_at=snapshot.expires_at, deleted_at=snapshot.deleted_at
        )
        assert derive_state(link, _now()) == LinkState.ACTIVE

    def test_expired_snapshot_resolves_to_expired_without_eviction(self):
        """An entry past expires_at yields EXPIRED via derive_state — no eviction needed."""
        cache = LinkCache()
        link = _make_link(expires_at=_past())
        loader = MagicMock(return_value=link)

        # Warm the cache
        cache.get_or_load("abc1234", loader)
        # Second hit — must still return the cached snapshot (no eviction)
        snapshot = cache.get_or_load("abc1234", loader)

        assert loader.call_count == 1  # Not re-loaded; still cached

        # derive_state on the snapshot must yield EXPIRED
        link_like = _make_link(
            expires_at=snapshot.expires_at, deleted_at=snapshot.deleted_at
        )
        assert derive_state(link_like, _now()) == LinkState.EXPIRED

    def test_deleted_snapshot_resolves_to_deleted(self):
        cache = LinkCache()
        link = _make_link(deleted_at=_past())
        snapshot = cache.get_or_load("abc1234", lambda: link)

        link_like = _make_link(
            expires_at=snapshot.expires_at, deleted_at=snapshot.deleted_at
        )
        assert derive_state(link_like, _now()) == LinkState.DELETED
