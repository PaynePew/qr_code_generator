"""Link ownership: login-to-create + owner stamping (ADR 0009, Phase 1).

Behavioral coverage for the ownership slice:
- Creating a Link requires a logged-in User (401 otherwise) and stamps the
  caller as ``owner_id``.
- The Alembic migration adds ``links.owner_id`` (nullable, FK to users.id).
- Legacy pre-auth Links (``owner_id IS NULL``) still redirect.

Owner-only authorization on info/analytics/PATCH/DELETE (non-owner -> 404) is a
separate slice and is intentionally not asserted here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import inspect

from backend import link_repository
from backend.models import Link
from tests.conftest import make_user

NOW = datetime(2026, 6, 3, 12, 0, 0)
SECRET = "ownership-test-secret"


class TestLoginToCreate:
    def test_unauthenticated_create_is_rejected_401(self, client):
        # No session -> get_current_user raises 401 before any Link is minted.
        resp = client.post("/api/qr/create", json={"url": "https://example.com/x"})
        assert resp.status_code == 401

    def test_unauthenticated_create_persists_no_link(self, client, db_session):
        client.post("/api/qr/create", json={"url": "https://example.com/none"})
        assert db_session.query(Link).count() == 0

    def test_authenticated_create_returns_200(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/ok"}
        )
        assert resp.status_code == 200

    def test_authenticated_create_stamps_owner(self, auth_client, owner, db_session):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/mine"}
        ).json()["token"]
        link = db_session.query(Link).filter(Link.token == token).one()
        assert link.owner_id == owner.id

    def test_each_user_owns_their_own_creations(self, auth_client, owner, db_session):
        # auth_client is authenticated as ``owner``; a second user's id is
        # never stamped onto that client's Links.
        other = make_user(db_session, email="other@example.com")
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/sep"}
        ).json()["token"]
        link = db_session.query(Link).filter(Link.token == token).one()
        assert link.owner_id == owner.id
        assert link.owner_id != other.id


class TestOwnershipMigration:
    def test_links_table_has_owner_id_column(self, db_engine):
        columns = {c["name"] for c in inspect(db_engine).get_columns("links")}
        assert "owner_id" in columns

    def test_owner_id_is_nullable(self, db_engine):
        owner_col = next(
            c
            for c in inspect(db_engine).get_columns("links")
            if c["name"] == "owner_id"
        )
        assert owner_col["nullable"] is True

    def test_owner_id_has_foreign_key_to_users(self, db_engine):
        fks = inspect(db_engine).get_foreign_keys("links")
        owner_fk = next(fk for fk in fks if "owner_id" in fk["constrained_columns"])
        assert owner_fk["referred_table"] == "users"
        assert owner_fk["referred_columns"] == ["id"]


class TestLegacyOwnerlessLinkRedirects:
    def test_ownerless_link_still_redirects(self, client, db_session):
        # A pre-auth Link inserted directly with no owner (owner_id NULL) keeps
        # redirecting — "start empty" migration: it just never appears in a
        # dashboard (ADR 0009).
        legacy = Link(
            token="LEGACY1",
            original_url="https://example.com/legacy",
            owner_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
        db_session.add(legacy)
        db_session.commit()

        resp = client.get("/r/LEGACY1", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://example.com/legacy"


class TestCreateLinkRepositoryStampsOwner:
    def test_create_link_persists_owner_id(self, db_session):
        owner = make_user(db_session)
        link = link_repository.create_link(
            db_session,
            normalized_url="https://example.com/repo",
            secret=SECRET,
            owner_id=owner.id,
            expires_at=None,
            now=NOW,
        )
        row = db_session.query(Link).filter(Link.token == link.token).one()
        assert row.owner_id == owner.id
