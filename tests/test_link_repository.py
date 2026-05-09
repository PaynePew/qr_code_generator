from datetime import datetime, timedelta

import pytest

from backend import link_repository
from backend.link_state import LinkAlreadyDeletedError, LinkNotFoundError
from backend.models import Link


NOW = datetime(2026, 5, 8, 12, 0, 0)
SECRET = "unit-test-secret"


class TestGetLink:
    def test_returns_link_when_present(self, db_session):
        link = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/a",
            secret=SECRET,
            expires_at=None,
            now=NOW,
        )
        fetched = link_repository.get_link(db_session, link.token)
        assert fetched.token == link.token

    def test_raises_typed_error_when_absent(self, db_session):
        with pytest.raises(LinkNotFoundError) as exc:
            link_repository.get_link(db_session, "MISSING")
        assert exc.value.token == "MISSING"


class TestCreateLink:
    def test_inserts_with_7_char_token(self, db_session):
        link = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/b",
            secret=SECRET,
            expires_at=None,
            now=NOW,
        )
        assert len(link.token) == 7

    def test_persists_normalized_url_and_timestamps(self, db_session):
        link = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/c",
            secret=SECRET,
            expires_at=None,
            now=NOW,
        )
        row = db_session.query(Link).filter(Link.token == link.token).first()
        assert row.original_url == "https://example.com/c"
        assert row.created_at == NOW
        assert row.updated_at == NOW
        assert row.deleted_at is None

    def test_optional_expires_at_is_persisted(self, db_session):
        future = NOW + timedelta(days=7)
        link = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/d",
            secret=SECRET,
            expires_at=future,
            now=NOW,
        )
        assert link.expires_at == future

    def test_two_calls_same_url_return_different_tokens(self, db_session):
        a = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/same",
            secret=SECRET,
            expires_at=None,
            now=NOW,
        )
        b = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/same",
            secret=SECRET,
            expires_at=None,
            now=NOW,
        )
        # ADR 0002 — no deduplication.
        assert a.token != b.token


class TestApplyPatch:
    def _seed(self, db_session, **kwargs):
        return link_repository.create_link(
            db_session,
            normalized_url=kwargs.get("normalized_url", "https://example.com/seed"),
            secret=SECRET,
            expires_at=kwargs.get("expires_at"),
            now=NOW,
        )

    def test_updates_only_listed_fields(self, db_session):
        link = self._seed(db_session)
        later = NOW + timedelta(hours=1)
        link_repository.apply_patch(
            db_session,
            link,
            fields={"original_url"},
            original_url="https://example.com/new",
            expires_at=None,  # should be ignored — not in fields
            now=later,
        )
        assert link.original_url == "https://example.com/new"
        assert link.expires_at is None
        assert link.updated_at == later

    def test_clears_expires_at_when_passed_none(self, db_session):
        future = NOW + timedelta(days=1)
        link = self._seed(db_session, expires_at=future)
        link_repository.apply_patch(
            db_session,
            link,
            fields={"expires_at"},
            expires_at=None,
            now=NOW,
        )
        assert link.expires_at is None

    def test_no_fields_only_bumps_updated_at(self, db_session):
        link = self._seed(db_session)
        later = NOW + timedelta(hours=2)
        original_url = link.original_url
        link_repository.apply_patch(
            db_session,
            link,
            fields=set(),
            now=later,
        )
        assert link.original_url == original_url
        assert link.updated_at == later

    def test_refuses_to_patch_deleted_link(self, db_session):
        # ADR 0001 enforced at the repository.
        link = self._seed(db_session)
        link_repository.mark_deleted(db_session, link, NOW)

        with pytest.raises(LinkAlreadyDeletedError) as exc:
            link_repository.apply_patch(
                db_session,
                link,
                fields={"original_url"},
                original_url="https://example.com/anything",
                now=NOW + timedelta(hours=1),
            )
        assert exc.value.token == link.token

    def test_patches_expired_link_for_reactivation(self, db_session):
        # ADR 0001: expired is reversible.
        past = NOW - timedelta(days=1)
        link = self._seed(db_session, expires_at=past)
        future = NOW + timedelta(days=30)
        link_repository.apply_patch(
            db_session,
            link,
            fields={"expires_at"},
            expires_at=future,
            now=NOW,
        )
        assert link.expires_at == future


class TestMarkDeleted:
    def test_sets_deleted_at(self, db_session):
        link = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/del",
            secret=SECRET,
            expires_at=None,
            now=NOW,
        )
        link_repository.mark_deleted(db_session, link, NOW)
        assert link.deleted_at == NOW

    def test_idempotent_does_not_overwrite(self, db_session):
        link = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/idem",
            secret=SECRET,
            expires_at=None,
            now=NOW,
        )
        first = NOW
        second = NOW + timedelta(hours=1)
        link_repository.mark_deleted(db_session, link, first)
        link_repository.mark_deleted(db_session, link, second)
        assert link.deleted_at == first
