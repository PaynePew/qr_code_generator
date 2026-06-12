"""In-process redirect read-cache (ADR 0017).

A ``cachetools.TTLCache`` keyed by Token stores the minimal snapshot needed to
serve the redirect without hitting Postgres on every scan.

Design contract (from ADR 0017):

- **Cache unit**: ``token → LinkSnapshot(original_url, expires_at, deleted_at)``
  — the three fields required to *derive* Link state, nothing more.
- **Derive-state-on-read**: every cache hit recomputes
  ``derive_state(snapshot, now())``.  Expiry therefore resolves automatically
  once ``now()`` passes ``expires_at``; no eviction is needed for natural
  time-based transitions.
- **Active eviction at exactly two points**: PATCH and DELETE.  Both can change
  data that affects redirect outcome.  A create mints a fresh un-cached token —
  no eviction needed.  The async scan write never mutates a Link.
- **TTL = 300 s as a pure safety net**.  Active eviction does the real work; the
  TTL only bounds the blast radius of a missed-eviction bug to five minutes.
- **No negative caching** of unknown (404) tokens — a flood of random garbage
  tokens would each be unique (zero repeat hits) while bloating memory.
- **Correct only at one worker** (in-process).  Going multi-worker requires a
  shared Redis layer (ADR 0017; prerequisite recorded there).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Callable

from cachetools import TTLCache

from .models import Link

# Safety-net TTL (seconds).  Active eviction is the primary correctness
# mechanism; this constant only bounds missed-eviction blast radius.
_TTL_SECONDS = 300

# Maximum number of entries.  Each entry is a tiny dataclass; 4096 covers
# a large fleet of active tokens with negligible memory (< 1 MB).
_MAX_SIZE = 4096


@dataclass(frozen=True, slots=True)
class LinkSnapshot:
    """Minimal cache unit — the three fields needed to derive redirect state."""

    original_url: str
    expires_at: datetime | None
    deleted_at: datetime | None


class LinkCache:
    """Thread-safe in-process TTL cache for redirect Link lookups.

    This is a **deep module** (no framework imports; pure domain logic).  The
    router owns the only instance (``_link_cache``) and calls ``get_or_load``,
    ``evict`` at the two mutation points.
    """

    def __init__(self, ttl: int = _TTL_SECONDS, maxsize: int = _MAX_SIZE) -> None:
        self._cache: TTLCache[str, LinkSnapshot] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = Lock()

    def get_or_load(self, token: str, loader: Callable[[], Link]) -> LinkSnapshot:
        """Return a cached snapshot, or call *loader* to populate the cache.

        *loader* is called **only on a cache miss** and must return the Link
        object for *token* (raising ``LinkNotFoundError`` if absent — the
        exception propagates unchanged so the router still returns 404).

        No negative caching: an unknown token never enters the cache.
        """
        with self._lock:
            snapshot = self._cache.get(token)
            if snapshot is not None:
                return snapshot

        # Load outside the lock to avoid holding it during a DB round-trip.
        link = loader()

        snapshot = LinkSnapshot(
            original_url=link.original_url,
            expires_at=link.expires_at,
            deleted_at=link.deleted_at,
        )
        with self._lock:
            # Re-check — another thread might have loaded concurrently.
            if token not in self._cache:
                self._cache[token] = snapshot
            else:
                snapshot = self._cache[token]
        return snapshot

    def evict(self, token: str) -> None:
        """Remove *token* from the cache (no-op if absent).

        Must be called by PATCH and DELETE after the DB mutation commits so the
        very next redirect re-reads the authoritative state from Postgres.
        """
        with self._lock:
            self._cache.pop(token, None)


# Module-level singleton used by the router.
# Tests may replace this with a fresh LinkCache() instance to isolate state.
_link_cache: LinkCache = LinkCache()
