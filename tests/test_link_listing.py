"""Owner-scoped Link listing for the dashboard (ADR 0009, Phase 1).

``link_repository.list_links_for_owner`` backs ``GET /api/qr``: it returns the
caller's own Links, newest-first, excluding soft-deleted by default with the
deleted set reachable via ``include_deleted=True`` (the trash filter).

Behavioral contract (asserted here, not internals):
- owner isolation: only the given owner's Links come back, never another user's;
- ownerless (legacy, owner_id IS NULL) Links never surface;
- ordering: newest-first by created_at;
- soft-deleted excluded by default; reachable via include_deleted=True.
"""

from datetime import datetime, timedelta

from backend import link_repository
from backend.models import Link
from tests.conftest import make_user

NOW = datetime(2026, 6, 3, 12, 0, 0)
SECRET = "listing-test-secret"


def _create(
    db_session,
    owner_id: int,
    *,
    created_at: datetime,
    url: str = "https://example.com/x",
):
    return link_repository.create_link(
        db_session,
        normalized_url=url,
        secret=SECRET,
        owner_id=owner_id,
        expires_at=None,
        now=created_at,
    )


class TestOwnerIsolation:
    def test_returns_only_the_owners_links(self, db_session):
        owner = make_user(db_session)
        other = make_user(db_session, email="other@example.com")
        mine = _create(db_session, owner.id, created_at=NOW)
        _create(db_session, other.id, created_at=NOW)

        links = link_repository.list_links_for_owner(db_session, owner.id)

        assert [link.token for link in links] == [mine.token]

    def test_excludes_ownerless_legacy_links(self, db_session):
        owner = make_user(db_session)
        legacy = Link(
            token="LEGACYL",
            original_url="https://example.com/legacy",
            owner_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
        db_session.add(legacy)
        db_session.commit()
        mine = _create(db_session, owner.id, created_at=NOW)

        links = link_repository.list_links_for_owner(db_session, owner.id)

        assert [link.token for link in links] == [mine.token]

    def test_empty_when_owner_has_no_links(self, db_session):
        owner = make_user(db_session)
        assert link_repository.list_links_for_owner(db_session, owner.id) == []


class TestOrdering:
    def test_newest_first(self, db_session):
        owner = make_user(db_session)
        oldest = _create(db_session, owner.id, created_at=NOW - timedelta(days=2))
        middle = _create(db_session, owner.id, created_at=NOW - timedelta(days=1))
        newest = _create(db_session, owner.id, created_at=NOW)

        links = link_repository.list_links_for_owner(db_session, owner.id)

        assert [link.token for link in links] == [
            newest.token,
            middle.token,
            oldest.token,
        ]


class TestDeletedFiltering:
    def test_excludes_soft_deleted_by_default(self, db_session):
        owner = make_user(db_session)
        kept = _create(db_session, owner.id, created_at=NOW)
        gone = _create(db_session, owner.id, created_at=NOW - timedelta(hours=1))
        link_repository.mark_deleted(db_session, gone, NOW)

        links = link_repository.list_links_for_owner(db_session, owner.id)

        assert [link.token for link in links] == [kept.token]

    def test_include_deleted_returns_deleted_too(self, db_session):
        owner = make_user(db_session)
        kept = _create(db_session, owner.id, created_at=NOW)
        gone = _create(db_session, owner.id, created_at=NOW - timedelta(hours=1))
        link_repository.mark_deleted(db_session, gone, NOW)

        links = link_repository.list_links_for_owner(
            db_session, owner.id, include_deleted=True
        )

        # Still newest-first; the deleted one is now present.
        assert [link.token for link in links] == [kept.token, gone.token]
