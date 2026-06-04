"""Tests for the unified error envelope (ADR 0012).

Every API error — AppError, Pydantic validation, framework HTTPException, and
uncaught exceptions — must return:
    { "error": { "code": "<ErrorCode>", "message": "...", "details": {...} } }

Tests are organised by handler:
- AppError handler (intentional typed errors)
- RequestValidationError handler (Pydantic 422 -> VALIDATION_ERROR)
- StarletteHTTPException handler (framework 404/405 etc.)
- Catch-all Exception handler (-> INTERNAL_ERROR, no stack leak)

Specific-error rulings from ADR 0012 are also exercised here:
- Non-owner access -> 404 NOT_FOUND (not 403)
- Mutating a deleted Link -> 409 LINK_DELETED
- Redirect on non-active Link -> 410 LINK_GONE
- Demo account write -> 403 DEMO_READ_ONLY
- Auth 401 -> UNAUTHENTICATED
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.errors import AppError, ErrorCode
from backend.main import app

# ---------------------------------------------------------------------------
# Unit: AppError itself
# ---------------------------------------------------------------------------


class TestAppError:
    def test_has_code_status_message(self):
        err = AppError(ErrorCode.NOT_FOUND, 404, "not found")
        assert err.code is ErrorCode.NOT_FOUND
        assert err.status == 404
        assert err.message == "not found"

    def test_is_exception(self):
        assert isinstance(AppError(ErrorCode.INTERNAL_ERROR, 500, "boom"), Exception)

    def test_details_defaults_to_empty_dict(self):
        err = AppError(ErrorCode.NOT_FOUND, 404, "x")
        assert err.details == {}

    def test_details_can_be_set(self):
        err = AppError(ErrorCode.VALIDATION_ERROR, 422, "bad", details={"field": "url"})
        assert err.details == {"field": "url"}


# ---------------------------------------------------------------------------
# Unit: ErrorCode taxonomy — every required code must exist
# ---------------------------------------------------------------------------


class TestErrorCodeTaxonomy:
    @pytest.mark.parametrize(
        "name",
        [
            "UNAUTHENTICATED",
            "DEMO_READ_ONLY",
            "FORBIDDEN",
            "NOT_FOUND",
            "LINK_GONE",
            "LINK_DELETED",
            "VALIDATION_ERROR",
            "INVALID_URL",
            "INVALID_IMAGE",
            "FILE_TOO_LARGE",
            "RATE_LIMITED",
            "TOKEN_ALLOCATION_FAILED",
            "INTERNAL_ERROR",
        ],
    )
    def test_code_exists(self, name):
        assert hasattr(ErrorCode, name), f"ErrorCode.{name} missing"

    def test_codes_are_strings(self):
        # StrEnum: the string value IS the member name (stable API contract).
        assert str(ErrorCode.NOT_FOUND) == "NOT_FOUND"
        assert str(ErrorCode.VALIDATION_ERROR) == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Integration: envelope shape via actual HTTP calls
# ---------------------------------------------------------------------------


class TestEnvelopeShape:
    """All errors must carry the { "error": { "code", "message", "details" } } envelope."""

    def test_404_returns_envelope(self, auth_client):
        resp = auth_client.get("/api/qr/NOEXIST")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]

    def test_401_returns_envelope(self, client):
        resp = client.get("/api/qr")
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "UNAUTHENTICATED"

    def test_422_validation_returns_envelope(self, auth_client):
        # Pydantic RequestValidationError via create with a missing required field.
        resp = auth_client.post("/api/qr/create", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_framework_404_returns_envelope(self, client):
        # A path that does not exist triggers StarletteHTTPException 404.
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "NOT_FOUND"

    def test_422_invalid_url_carries_invalid_url_code(self, auth_client):
        resp = auth_client.post("/api/qr/create", json={"url": "javascript:alert(1)"})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "INVALID_URL"

    def test_no_stack_trace_in_500(self):
        """Catch-all handler must not leak stack / exception detail to the client."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.main import _handle_unexpected_error

        # Build a minimal app wired with the real catch-all handler.
        mini = FastAPI()
        mini.add_exception_handler(Exception, _handle_unexpected_error)  # type: ignore[arg-type]

        @mini.get("/boom")
        def _boom():
            raise RuntimeError("secret internal detail")

        with TestClient(mini, raise_server_exceptions=False) as c:
            resp = c.get("/boom")
        assert resp.status_code == 500
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert "secret internal detail" not in resp.text
        assert "Traceback" not in resp.text


# ---------------------------------------------------------------------------
# Integration: ADR 0012 rulings
# ---------------------------------------------------------------------------


class TestADR0012Rulings:
    def test_non_owner_access_returns_404_not_403(self, db_session, auth_client):
        """Non-owner on owner-only resource -> 404 NOT_FOUND (owner-404 rule)."""
        from backend.auth import get_current_user
        from backend.database import get_db
        from tests.conftest import make_user

        # Create a link owned by user A (auth_client's owner).
        create_resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/secret"}
        )
        assert create_resp.status_code == 200
        token = create_resp.json()["token"]

        # User B tries to access the link — should get 404, not 403.
        user_b = make_user(db_session)

        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: user_b
        try:
            client_b = TestClient(app, raise_server_exceptions=False)
            resp = client_b.get(f"/api/qr/{token}")
            assert resp.status_code == 404
            body = resp.json()
            assert body["error"]["code"] == "NOT_FOUND"
        finally:
            app.dependency_overrides.clear()

    def test_mutating_deleted_link_returns_409_link_deleted(self, auth_client):
        """Mutation on deleted Link -> 409 LINK_DELETED (not 410)."""
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/del"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        resp = auth_client.patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/new"}
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "LINK_DELETED"

    def test_redirect_non_active_returns_410_link_gone(self, auth_client):
        """Redirect on non-active Link -> 410 LINK_GONE."""
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/gone"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        resp = auth_client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 410
        body = resp.json()
        assert body["error"]["code"] == "LINK_GONE"

    def test_demo_write_returns_403_demo_read_only(self, db_session):
        """Demo account mutation -> 403 DEMO_READ_ONLY."""
        from backend.auth import get_current_user
        from backend.database import get_db
        from tests.conftest import make_user

        demo = make_user(db_session, is_demo=True)

        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: demo
        try:
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post("/api/qr/create", json={"url": "https://example.com"})
            assert resp.status_code == 403
            body = resp.json()
            assert body["error"]["code"] == "DEMO_READ_ONLY"
        finally:
            app.dependency_overrides.clear()
