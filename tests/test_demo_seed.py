"""Tests for the idempotent demo-account seed (DB-touching — Postgres testcontainer).

ADR 0009: a guest enters one shared, read-only demo account. ``seed_demo`` must
populate it with several Links across states (active / expired / deleted) and a
multi-day scan spread so the analytics views look alive — and be safe to run
repeatedly (deploys re-run it) without duplicating data.

These assert observable persisted state, not the seed's internals: how many
Links/Scans exist, which states they span, and that a second run is a no-op.
"""
from __future__ import annotations

from datetime import datetime

from backend import demo_seed, scan_repository
from backend.link_repository import list_links_for_owner
from backend.link_state import LinkState, derive_state
from backend.models import Scan, User

NOW = datetime(2026, 6, 3, 12, 0, 0)
SECRET = "demo-seed-test-secret"


def _all_links(db_session, user: User):
    return list_links_for_owner(db_session, user.id, include_deleted=True)


class TestSeedDemo:
    def test_creates_a_demo_flagged_user(self, db_session):
        user = demo_seed.seed_demo(db_session, secret=SECRET, now=NOW)
        assert user.is_demo is True
        # Persisted exactly once and resolvable as the demo account.
        assert db_session.query(User).filter(User.is_demo.is_(True)).count() == 1

    def test_seeds_links_across_active_expired_and_deleted(self, db_session):
        user = demo_seed.seed_demo(db_session, secret=SECRET, now=NOW)
        links = _all_links(db_session, user)
        states = {derive_state(link, NOW) for link in links}
        # The analytics/dashboard demo is only convincing with state variety.
        assert {LinkState.ACTIVE, LinkState.EXPIRED, LinkState.DELETED} <= states

    def test_every_seeded_link_is_owned_by_the_demo_user(self, db_session):
        user = demo_seed.seed_demo(db_session, secret=SECRET, now=NOW)
        links = _all_links(db_session, user)
        assert links, "expected at least one seeded Link"
        assert all(link.owner_id == user.id for link in links)

    def test_seeds_scans_spread_over_multiple_days(self, db_session):
        demo_seed.seed_demo(db_session, secret=SECRET, now=NOW)
        scan_days = {s.scanned_at.date() for s in db_session.query(Scan).all()}
        # "Multi-day scan spread (so analytics looks alive)" — the acceptance bar.
        assert len(scan_days) >= 3

    def test_active_link_has_a_nonzero_scan_count(self, db_session):
        user = demo_seed.seed_demo(db_session, secret=SECRET, now=NOW)
        links = _all_links(db_session, user)
        counts = scan_repository.scan_counts_for_tokens(
            db_session, [link.token for link in links]
        )
        assert any(count > 0 for count in counts.values())

    def test_is_idempotent_no_duplicate_users_or_links(self, db_session):
        first = demo_seed.seed_demo(db_session, secret=SECRET, now=NOW)
        links_after_first = len(_all_links(db_session, first))
        scans_after_first = db_session.query(Scan).count()

        second = demo_seed.seed_demo(db_session, secret=SECRET, now=NOW)

        # Same account, same data — a re-run must not pile up Links or Scans.
        assert second.id == first.id
        assert db_session.query(User).filter(User.is_demo.is_(True)).count() == 1
        assert len(_all_links(db_session, second)) == links_after_first
        assert db_session.query(Scan).count() == scans_after_first
