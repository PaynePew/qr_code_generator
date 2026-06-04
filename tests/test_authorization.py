"""Owner-only authorization on info / analytics / PATCH / DELETE (ADR 0009).

The authorization matrix (ADR 0009, closes the redirect-hijack hole):
- Public:      GET /r/{token} (redirect), GET /api/qr/{token}/image (QR PNG).
- Owner-only:  GET /api/qr/{token} (info), GET .../analytics, PATCH, DELETE.

A non-owner — a logged-in User who is not the Link's ``owner_id`` — gets
**404, not 403**, so Token existence is not leaked. An unauthenticated caller
gets 401 (no session) via ``get_current_user``. ADR 0006 still binds: analytics
never exposes raw scanner IPs (regressed below).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend import link_repository
from backend.auth import get_current_user
from backend.authorization import authorize_owner, forbid_if_demo
from backend.errors import AppError, ErrorCode
from backend.main import app
from backend.models import Link, User
from backend.router import get_db
from tests.conftest import make_user

NOW = datetime(2026, 6, 3, 12, 0, 0)
NOW_URL = "https://example.com/owned"
SECRET = "authz-test-secret"


@pytest.fixture
def as_user(db_session):
    """Return a factory yielding a TestClient authenticated as a given User.

    Lets one test mint a Link as user A, then issue requests as user B to
    exercise the non-owner path. Each call re-asserts the override so it is
    correct for the *next* request; teardown clears it.
    """
    clients: list[TestClient] = []

    def override_get_db():
        yield db_session

    def _make(user: User) -> TestClient:
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: user
        c = TestClient(app, raise_server_exceptions=True)
        c.__enter__()
        clients.append(c)
        return c

    yield _make

    for c in clients:
        c.__exit__(None, None, None)
    app.dependency_overrides.clear()


def _mint(client: TestClient, url: str = NOW_URL) -> str:
    return client.post("/api/qr/create", json={"url": url}).json()["token"]


def _mint_owned(db_session, owner: User, url: str = NOW_URL) -> str:
    """Persist a Link owned by ``owner`` directly via the repository.

    Used by the unauthenticated cases so no ``get_current_user`` override is in
    play — the request under test must hit the real 401 path.
    """
    link = link_repository.create_link(
        db_session,
        normalized_url=url,
        secret=SECRET,
        owner_id=owner.id,
        expires_at=None,
        now=NOW,
    )
    return link.token


# ---------------------------------------------------------------------------
# Domain rule (framework-free): authorize_owner
# ---------------------------------------------------------------------------


class TestAuthorizeOwnerRule:
    def _link(self, owner_id: int | None) -> Link:
        return Link(
            token="ABC1234",
            original_url=NOW_URL,
            owner_id=owner_id,
            created_at=None,
            updated_at=None,
        )

    def _user(self, uid: int) -> User:
        u = User(
            google_sub=f"s{uid}",
            email="x@example.com",
            created_at=None,
            last_login_at=None,
        )
        u.id = uid
        return u

    def test_owner_passes(self):
        # No exception means authorized.
        authorize_owner(self._link(owner_id=7), self._user(7))

    def test_non_owner_raises_not_found_app_error(self):
        # ADR 0012: authorize_owner raises AppError(NOT_FOUND, 404) — owner-404 rule.
        with pytest.raises(AppError) as exc:
            authorize_owner(self._link(owner_id=7), self._user(99))
        assert exc.value.code is ErrorCode.NOT_FOUND
        assert exc.value.status == 404

    def test_ownerless_link_is_never_owned(self):
        # Legacy pre-auth Link (owner_id NULL) is owned by no one -> 404 for all.
        with pytest.raises(AppError) as exc:
            authorize_owner(self._link(owner_id=None), self._user(7))
        assert exc.value.code is ErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# Domain rule (framework-free): forbid_if_demo (read-only demo account, ADR 0009)
# ---------------------------------------------------------------------------


class TestForbidIfDemoRule:
    def _user(self, *, is_demo: bool) -> User:
        u = User(
            google_sub="s1",
            email="x@example.com",
            created_at=None,
            last_login_at=None,
            is_demo=is_demo,
        )
        u.id = 1
        return u

    def test_real_user_passes(self):
        # No exception means the mutation may proceed.
        forbid_if_demo(self._user(is_demo=False))

    def test_demo_user_raises_app_error_demo_read_only(self):
        # The shared demo account is read-only by construction (ADR 0009):
        # any mutation is rejected so the seeded data stays pristine.
        # Now raises AppError(DEMO_READ_ONLY, 403) per ADR 0012.
        with pytest.raises(AppError) as exc:
            forbid_if_demo(self._user(is_demo=True))
        assert exc.value.code is ErrorCode.DEMO_READ_ONLY
        assert exc.value.status == 403


# ---------------------------------------------------------------------------
# Integration: the full authorization matrix per owner-only endpoint
# ---------------------------------------------------------------------------


class TestOwnerOnlyInfo:
    def test_owner_gets_200(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint(as_user(owner))
        assert as_user(owner).get(f"/api/qr/{token}").status_code == 200

    def test_non_owner_gets_404(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        stranger = make_user(db_session, email="stranger@example.com")
        token = _mint(as_user(owner))
        assert as_user(stranger).get(f"/api/qr/{token}").status_code == 404

    def test_unauthenticated_gets_401(self, db_session, client):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint_owned(db_session, owner)
        assert client.get(f"/api/qr/{token}").status_code == 401


class TestOwnerOnlyAnalytics:
    def test_owner_gets_200(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint(as_user(owner))
        assert as_user(owner).get(f"/api/qr/{token}/analytics").status_code == 200

    def test_non_owner_gets_404(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        stranger = make_user(db_session, email="stranger@example.com")
        token = _mint(as_user(owner))
        assert as_user(stranger).get(f"/api/qr/{token}/analytics").status_code == 404

    def test_unauthenticated_gets_401(self, db_session, client):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint_owned(db_session, owner)
        assert client.get(f"/api/qr/{token}/analytics").status_code == 401

    def test_non_owner_404_does_not_leak_scanner_ips(self, db_session, as_user):
        # ADR 0006 + 0009: a non-owner gets a not-found body, never aggregates
        # and certainly never raw IPs.
        owner = make_user(db_session, email="owner@example.com")
        stranger = make_user(db_session, email="stranger@example.com")
        token = _mint(as_user(owner))
        as_user(owner).get(f"/r/{token}", follow_redirects=False)  # log a scan
        resp = as_user(stranger).get(f"/api/qr/{token}/analytics")
        assert resp.status_code == 404
        assert "ip_address" not in resp.text
        assert "recent_scans" not in resp.text


class TestOwnerOnlyPatch:
    def test_owner_can_repoint(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint(as_user(owner))
        resp = as_user(owner).patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/new"}
        )
        assert resp.status_code == 200
        assert resp.json()["original_url"] == "https://example.com/new"

    def test_non_owner_cannot_repoint_gets_404(self, db_session, as_user):
        # The hijack hole: a stranger who photographed the QR must not repoint it.
        owner = make_user(db_session, email="owner@example.com")
        stranger = make_user(db_session, email="stranger@example.com")
        token = _mint(as_user(owner))
        resp = as_user(stranger).patch(
            f"/api/qr/{token}",
            json={"original_url": "https://evil.example.com/malware"},
        )
        assert resp.status_code == 404

    def test_non_owner_patch_leaves_url_unchanged(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        stranger = make_user(db_session, email="stranger@example.com")
        token = _mint(as_user(owner))
        as_user(stranger).patch(
            f"/api/qr/{token}",
            json={"original_url": "https://evil.example.com/malware"},
        )
        # The destination the owner sees is still the original.
        assert as_user(owner).get(f"/api/qr/{token}").json()["original_url"] == NOW_URL

    def test_unauthenticated_gets_401(self, db_session, client):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint_owned(db_session, owner)
        resp = client.patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/x"}
        )
        assert resp.status_code == 401


class TestOwnerOnlyDelete:
    def test_owner_can_delete(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint(as_user(owner))
        assert as_user(owner).delete(f"/api/qr/{token}").status_code == 200

    def test_non_owner_cannot_delete_gets_404(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        stranger = make_user(db_session, email="stranger@example.com")
        token = _mint(as_user(owner))
        assert as_user(stranger).delete(f"/api/qr/{token}").status_code == 404

    def test_non_owner_delete_leaves_link_active(self, db_session, as_user):
        owner = make_user(db_session, email="owner@example.com")
        stranger = make_user(db_session, email="stranger@example.com")
        token = _mint(as_user(owner))
        as_user(stranger).delete(f"/api/qr/{token}")
        # Owner's Link is untouched; redirect still works.
        assert (
            as_user(owner).get(f"/r/{token}", follow_redirects=False).status_code == 302
        )

    def test_unauthenticated_gets_401(self, db_session, client):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint_owned(db_session, owner)
        assert client.delete(f"/api/qr/{token}").status_code == 401


# ---------------------------------------------------------------------------
# Regression: the public surface stays public
# ---------------------------------------------------------------------------


class TestPublicSurfaceUnchanged:
    def test_redirect_is_public_for_anyone(self, db_session, as_user, client):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint(as_user(owner))
        resp = client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == NOW_URL

    def test_qr_image_is_public_for_anyone(self, db_session, as_user, client):
        owner = make_user(db_session, email="owner@example.com")
        token = _mint(as_user(owner))
        resp = client.get(f"/api/qr/{token}/image")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_qr_image_for_unknown_token_is_404(self, client):
        # Regression: unknown token still 404s (the image endpoint resolves the
        # Link to confirm existence even though the PNG only encodes the URL).
        assert client.get("/api/qr/NOTREAL/image").status_code == 404


# ---------------------------------------------------------------------------
# Read-only demo account: mutations -> 403 DEMO_READ_ONLY, reads still work
# ---------------------------------------------------------------------------


class TestDemoReadOnly:
    """ADR 0009: the shared demo account can browse the full dashboard but every
    mutation is rejected with 403 + code DEMO_READ_ONLY (so the frontend renders
    a login nudge, not a raw error). The 403 must beat an owner-404: the demo
    user owns its seeded Links, yet still cannot PATCH/DELETE them.
    """

    def test_demo_create_is_forbidden(self, db_session, as_user):
        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        resp = as_user(demo).post("/api/qr/create", json={"url": NOW_URL})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "DEMO_READ_ONLY"

    def test_demo_patch_own_link_is_forbidden_with_code(self, db_session, as_user):
        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        token = _mint_owned(db_session, demo)  # demo owns it
        resp = as_user(demo).patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/new"}
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "DEMO_READ_ONLY"

    def test_demo_delete_own_link_is_forbidden_with_code(self, db_session, as_user):
        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        token = _mint_owned(db_session, demo)
        resp = as_user(demo).delete(f"/api/qr/{token}")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "DEMO_READ_ONLY"

    def test_demo_patch_does_not_mutate_the_link(self, db_session, as_user):
        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        token = _mint_owned(db_session, demo)
        as_user(demo).patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/changed"}
        )
        # The seeded destination is untouched — read-only really means read-only.
        assert as_user(demo).get(f"/api/qr/{token}").json()["original_url"] == NOW_URL

    def test_demo_can_read_dashboard_list(self, db_session, as_user):
        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        _mint_owned(db_session, demo)
        resp = as_user(demo).get("/api/qr")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_demo_can_read_own_link_info_and_analytics(self, db_session, as_user):
        demo = make_user(db_session, email="demo@example.com", is_demo=True)
        token = _mint_owned(db_session, demo)
        assert as_user(demo).get(f"/api/qr/{token}").status_code == 200
        assert as_user(demo).get(f"/api/qr/{token}/analytics").status_code == 200
