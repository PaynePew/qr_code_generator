"""GET /api/qr — the owner dashboard list endpoint (ADR 0009, Phase 1).

Server-driven dashboard: the caller's own Links with state + total scan count,
newest-first, deleted excluded by default (deleted reachable via a trash
filter), wrapped in an ``items`` + ``next_cursor`` envelope (no pagination logic
yet — next_cursor is a forward-compatibility placeholder).

Integration coverage:
- auth required: no session -> 401;
- owner isolation: only the caller's Links, never another user's or ownerless;
- each item carries status + scan_count, and scan_count is correct;
- ordering newest-first; deleted excluded by default; trash filter exposes them;
- the response envelope shape.
"""
from datetime import datetime

from tests.conftest import make_user


def _create(client, url: str, expires_at: str | None = None) -> str:
    body: dict = {"url": url}
    if expires_at is not None:
        body["expires_at"] = expires_at
    return client.post("/api/qr/create", json=body).json()["token"]


class TestAuthRequired:
    def test_unauthenticated_list_returns_401(self, client):
        # Owner-scoped (ADR 0009): no session -> 401, same as the other
        # owner-only endpoints.
        assert client.get("/api/qr").status_code == 401


class TestEnvelopeShape:
    def test_returns_items_and_next_cursor(self, auth_client):
        _create(auth_client, "https://example.com/a")
        data = auth_client.get("/api/qr").json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert "next_cursor" in data
        assert data["next_cursor"] is None

    def test_empty_account_returns_empty_items(self, auth_client):
        data = auth_client.get("/api/qr").json()
        assert data == {"items": [], "next_cursor": None}

    def test_item_shape_carries_state_and_scan_count(self, auth_client):
        _create(auth_client, "https://example.com/shape")
        item = auth_client.get("/api/qr").json()["items"][0]
        for field in ("token", "original_url", "short_url", "status", "scan_count", "created_at"):
            assert field in item


class TestOwnerIsolation:
    def test_lists_only_callers_links(self, auth_client, owner, db_session):
        from backend import link_repository

        mine = _create(auth_client, "https://example.com/mine")
        # A second user's Link must not appear for the authed caller.
        other = make_user(db_session, email="other@example.com")
        link_repository.create_link(
            db_session,
            normalized_url="https://example.com/theirs",
            secret="x",
            owner_id=other.id,
            expires_at=None,
            now=datetime(2026, 6, 3, 12, 0, 0),
        )

        tokens = [item["token"] for item in auth_client.get("/api/qr").json()["items"]]

        assert tokens == [mine]


class TestScanCount:
    def test_scan_count_reflects_redirects(self, auth_client):
        token = _create(auth_client, "https://example.com/scanned")
        auth_client.get(f"/r/{token}", follow_redirects=False)
        auth_client.get(f"/r/{token}", follow_redirects=False)

        item = auth_client.get("/api/qr").json()["items"][0]

        assert item["token"] == token
        assert item["scan_count"] == 2

    def test_scan_count_zero_when_never_scanned(self, auth_client):
        _create(auth_client, "https://example.com/quiet")
        item = auth_client.get("/api/qr").json()["items"][0]
        assert item["scan_count"] == 0


class TestStatusAndOrdering:
    def test_status_active_for_live_link(self, auth_client):
        _create(auth_client, "https://example.com/live")
        item = auth_client.get("/api/qr").json()["items"][0]
        assert item["status"] == "active"

    def test_status_expired_for_past_expiry(self, auth_client):
        _create(auth_client, "https://example.com/old", expires_at="2000-01-01T00:00:00")
        item = auth_client.get("/api/qr").json()["items"][0]
        assert item["status"] == "expired"

    def test_newest_first(self, auth_client):
        first = _create(auth_client, "https://example.com/1")
        second = _create(auth_client, "https://example.com/2")
        third = _create(auth_client, "https://example.com/3")

        tokens = [item["token"] for item in auth_client.get("/api/qr").json()["items"]]

        assert tokens == [third, second, first]


class TestDeletedFiltering:
    def test_deleted_excluded_by_default(self, auth_client):
        kept = _create(auth_client, "https://example.com/keep")
        gone = _create(auth_client, "https://example.com/gone")
        auth_client.delete(f"/api/qr/{gone}")

        tokens = [item["token"] for item in auth_client.get("/api/qr").json()["items"]]

        assert gone not in tokens
        assert kept in tokens

    def test_trash_filter_includes_deleted(self, auth_client):
        gone = _create(auth_client, "https://example.com/trash")
        auth_client.delete(f"/api/qr/{gone}")

        items = auth_client.get("/api/qr", params={"deleted": "true"}).json()["items"]
        deleted = next(item for item in items if item["token"] == gone)

        assert deleted["status"] == "deleted"
