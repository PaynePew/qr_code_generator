"""Tests for user_repository (DB-touching — Postgres testcontainer).

Exercises the Postgres ON CONFLICT upsert path: a first sign-in creates the
User; a repeat sign-in for the same google_sub updates the mutable profile
fields and last_login_at without minting a second row (ADR 0009 keys identity on
Google's stable subject id).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend import user_repository
from backend.google_identity import GoogleIdentity
from backend.models import User

NOW = datetime(2026, 6, 3, 12, 0, 0)

IDENTITY = GoogleIdentity(
    google_sub="sub-123",
    email="alice@example.com",
    name="Alice",
    picture="https://example.com/a.png",
)


class TestUpsertUser:
    def test_first_login_creates_user(self, db_session):
        user = user_repository.upsert_user(db_session, IDENTITY, now=NOW)
        assert user.id is not None
        assert user.google_sub == "sub-123"
        assert user.email == "alice@example.com"
        assert user.name == "Alice"
        assert user.picture == "https://example.com/a.png"
        assert user.created_at == NOW
        assert user.last_login_at == NOW
        assert user.is_demo is False

    def test_repeat_login_updates_in_place(self, db_session):
        first = user_repository.upsert_user(db_session, IDENTITY, now=NOW)
        first_id = first.id

        later = NOW + timedelta(days=1)
        changed = GoogleIdentity(
            google_sub="sub-123",
            email="alice@newmail.example.com",
            name="Alice Renamed",
            picture="https://example.com/new.png",
        )
        second = user_repository.upsert_user(db_session, changed, now=later)

        # Same row — no duplicate minted on the unique google_sub.
        assert second.id == first_id
        assert db_session.query(User).filter(User.google_sub == "sub-123").count() == 1
        # Profile + last_login refreshed; created_at preserved.
        assert second.email == "alice@newmail.example.com"
        assert second.name == "Alice Renamed"
        assert second.picture == "https://example.com/new.png"
        assert second.last_login_at == later
        assert second.created_at == NOW

    def test_distinct_subjects_create_distinct_users(self, db_session):
        a = user_repository.upsert_user(db_session, IDENTITY, now=NOW)
        other = GoogleIdentity(google_sub="sub-999", email="bob@example.com")
        b = user_repository.upsert_user(db_session, other, now=NOW)
        assert a.id != b.id
        assert db_session.query(User).count() == 2


class TestGetUserById:
    def test_returns_user_when_present(self, db_session):
        created = user_repository.upsert_user(db_session, IDENTITY, now=NOW)
        fetched = user_repository.get_user_by_id(db_session, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_returns_none_when_absent(self, db_session):
        assert user_repository.get_user_by_id(db_session, 999_999) is None


class TestGetDemoUser:
    """The guest-entry endpoint resolves the single shared demo account here
    (ADR 0009) — it has no Google credential to upsert from."""

    def test_returns_none_when_no_demo_account_seeded(self, db_session):
        # A non-demo user existing must not be mistaken for the demo account.
        user_repository.upsert_user(db_session, IDENTITY, now=NOW)
        assert user_repository.get_demo_user(db_session) is None

    def test_returns_the_demo_flagged_user(self, db_session):
        from tests.conftest import make_user

        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        found = user_repository.get_demo_user(db_session)
        assert found is not None
        assert found.id == demo.id
        assert found.is_demo is True
