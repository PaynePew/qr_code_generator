"""Tests for the QR customization storage backend (ADR 0011).

All storage tests run against InMemoryGateway — no real S3 needed.

Coverage:
- InMemoryGateway unit tests
- Image validation helpers (sniff_image_content_type, strip_png_exif, size cap)
- Alembic migration: link_customizations table exists after upgrade
- PUT /api/qr/{token}/customization — happy path, validation, auth, re-style
- GET /api/qr/{token}/customization — happy path, auth, 404 when absent
- GET /api/qr/{token}/image — serves stored composite when present, else vanilla
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import Link, LinkCustomization
from backend.storage import (
    MAX_IMAGE_BYTES,
    InMemoryGateway,
    sniff_image_content_type,
    strip_png_exif,
)

from .conftest import make_user

# ---------------------------------------------------------------------------
# Minimal valid images for tests
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff\xe0"


def _minimal_png() -> bytes:
    """Return a syntactically valid 1×1 white PNG (no palette chunks)."""
    import io as _io

    import qrcode

    img = qrcode.make("http://example.com")
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _minimal_jpeg() -> bytes:
    """Return the smallest JPEG magic bytes that pass magic-byte sniffing."""
    # We only need to pass sniff_image_content_type — 3 bytes is enough.
    return _JPEG_MAGIC + b"\x00" * 10


def _insert_link(db_session: Session, token: str) -> Link:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    link = Link(
        token=token,
        original_url="https://example.com/page",
        created_at=now,
        updated_at=now,
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link


def _insert_owned_link(db_session: Session, token: str, owner_id: int) -> Link:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    link = Link(
        token=token,
        original_url="https://example.com/owned",
        owner_id=owner_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link


# ---------------------------------------------------------------------------
# InMemoryGateway unit tests
# ---------------------------------------------------------------------------


class TestInMemoryGateway:
    def test_put_and_get_roundtrip(self):
        gw = InMemoryGateway()
        gw.put("k1", b"hello", "image/png")
        assert gw.get("k1") == b"hello"

    def test_get_missing_returns_none(self):
        gw = InMemoryGateway()
        assert gw.get("nonexistent") is None

    def test_exists_true_after_put(self):
        gw = InMemoryGateway()
        gw.put("k2", b"data", "image/png")
        assert gw.exists("k2") is True

    def test_exists_false_when_absent(self):
        gw = InMemoryGateway()
        assert gw.exists("missing") is False

    def test_delete_removes_key(self):
        gw = InMemoryGateway()
        gw.put("k3", b"to-delete", "image/png")
        gw.delete("k3")
        assert gw.get("k3") is None

    def test_delete_noop_on_missing(self):
        gw = InMemoryGateway()
        gw.delete("ghost")  # must not raise

    def test_url_for_uses_base_url(self):
        gw = InMemoryGateway(base_url="http://fake-storage")
        assert (
            gw.url_for("qr/tok/composite_abc.png")
            == "http://fake-storage/qr/tok/composite_abc.png"
        )

    def test_put_overwrites_existing(self):
        gw = InMemoryGateway()
        gw.put("dup", b"v1", "image/png")
        gw.put("dup", b"v2", "image/png")
        assert gw.get("dup") == b"v2"

    def test_list_keys(self):
        gw = InMemoryGateway()
        gw.put("a", b"1", "image/png")
        gw.put("b", b"2", "image/jpeg")
        assert set(gw.list_keys()) == {"a", "b"}


# ---------------------------------------------------------------------------
# Image validation helper tests
# ---------------------------------------------------------------------------


class TestSniffImageContentType:
    def test_png_magic_detected(self):
        data = _PNG_MAGIC + b"\x00" * 100
        assert sniff_image_content_type(data) == "image/png"

    def test_jpeg_magic_detected(self):
        data = b"\xff\xd8\xff" + b"\x00" * 20
        assert sniff_image_content_type(data) == "image/jpeg"

    def test_gif87_detected(self):
        data = b"GIF87a" + b"\x00" * 20
        assert sniff_image_content_type(data) == "image/gif"

    def test_gif89_detected(self):
        data = b"GIF89a" + b"\x00" * 20
        assert sniff_image_content_type(data) == "image/gif"

    def test_webp_detected(self):
        data = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20
        assert sniff_image_content_type(data) == "image/webp"

    def test_random_bytes_returns_none(self):
        assert sniff_image_content_type(b"\x00\x01\x02\x03" * 10) is None

    def test_empty_bytes_returns_none(self):
        assert sniff_image_content_type(b"") is None


class TestStripPngExif:
    def test_non_png_returned_unchanged(self):
        data = b"\xff\xd8\xff" + b"\x00" * 20
        assert strip_png_exif(data) == data

    def test_png_without_exif_unchanged(self):
        png = _minimal_png()
        result = strip_png_exif(png)
        # Should still be a valid PNG (magic preserved)
        assert result[:8] == _PNG_MAGIC
        # Should be same or smaller (no exif to strip in a clean PNG)
        assert len(result) <= len(png)

    def test_png_magic_preserved_after_strip(self):
        png = _minimal_png()
        result = strip_png_exif(png)
        assert result[:8] == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Migration: link_customizations table exists
# ---------------------------------------------------------------------------


class TestLinkCustomizationMigration:
    def test_table_exists(self, db_session: Session):
        """link_customizations table must exist after alembic upgrade head."""
        from sqlalchemy import text

        result = db_session.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_name = 'link_customizations'"
            )
        )
        rows = result.fetchall()
        assert len(rows) == 1, (
            "link_customizations table not found — migration may not have run"
        )

    def test_unique_constraint_on_link_id(self, db_session: Session):
        """Inserting two customizations for the same link_id must fail."""
        from sqlalchemy.exc import IntegrityError

        user = make_user(db_session)
        link = _insert_owned_link(db_session, "mig0001", user.id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row1 = LinkCustomization(
            link_id=link.id,
            style_json='{"color":"#000"}',
            image_key="k1",
            logo_key=None,
            updated_at=now,
        )
        db_session.add(row1)
        db_session.commit()

        row2 = LinkCustomization(
            link_id=link.id,
            style_json='{"color":"#fff"}',
            image_key="k2",
            logo_key=None,
            updated_at=now,
        )
        db_session.add(row2)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ---------------------------------------------------------------------------
# PUT /api/qr/{token}/customization
# ---------------------------------------------------------------------------


def _put_customization(
    client: TestClient,
    token: str,
    *,
    style: dict | None = None,
    image_bytes: bytes | None = None,
    logo_bytes: bytes | None = None,
):
    """Helper: POST a customization via multipart/form-data."""
    if style is None:
        style = {
            "foreground": "#000000",
            "background": "#ffffff",
            "dot_style": "square",
        }
    if image_bytes is None:
        image_bytes = _minimal_png()

    files: list = [
        ("image", ("composite.png", image_bytes, "image/png")),
    ]
    if logo_bytes is not None:
        files.append(("logo", ("logo.png", logo_bytes, "image/png")))

    data = {"style": json.dumps(style)}
    return client.put(f"/api/qr/{token}/customization", data=data, files=files)


class TestPutCustomization:
    def test_happy_path_returns_200(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0001", owner.id)
        resp = _put_customization(auth_client, "put0001")
        assert resp.status_code == 200

    def test_response_contains_token_and_image_key(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0002", owner.id)
        resp = _put_customization(auth_client, "put0002")
        body = resp.json()
        assert body["token"] == "put0002"
        assert "image_key" in body
        assert body["image_key"].startswith("qr/put0002/composite_")

    def test_image_key_includes_versioned_uuid(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0003", owner.id)
        resp1 = _put_customization(auth_client, "put0003")
        resp2 = _put_customization(auth_client, "put0003")
        # Two calls must produce different image_keys (re-style writes new versioned key)
        assert resp1.json()["image_key"] != resp2.json()["image_key"]

    def test_composite_persisted_in_storage(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        from backend.main import app
        from backend.router import _get_storage

        gw = InMemoryGateway()
        app.dependency_overrides[_get_storage] = lambda: gw

        try:
            _insert_owned_link(db_session, "put0004", owner.id)
            resp = _put_customization(auth_client, "put0004")
            key = resp.json()["image_key"]
            assert gw.exists(key), "composite should be stored in gateway"
        finally:
            # Remove only the storage override; leave other overrides intact
            app.dependency_overrides.pop(_get_storage, None)

    def test_non_image_upload_rejected_422(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0005", owner.id)
        resp = _put_customization(
            auth_client, "put0005", image_bytes=b"not an image at all"
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_IMAGE"

    def test_oversized_upload_rejected_413(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0006", owner.id)
        big = _PNG_MAGIC + b"\x00" * (MAX_IMAGE_BYTES + 1)
        resp = _put_customization(auth_client, "put0006", image_bytes=big)
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"

    def test_invalid_style_json_rejected_422(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0007", owner.id)
        files = [("image", ("c.png", _minimal_png(), "image/png"))]
        data = {"style": "not-json{{"}
        resp = auth_client.put("/api/qr/put0007/customization", data=data, files=files)
        assert resp.status_code == 422

    def test_style_must_be_json_object(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0008", owner.id)
        files = [("image", ("c.png", _minimal_png(), "image/png"))]
        data = {"style": json.dumps([1, 2, 3])}  # array, not object
        resp = auth_client.put("/api/qr/put0008/customization", data=data, files=files)
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client: TestClient, db_session: Session):
        _insert_link(db_session, "put0009")
        resp = _put_customization(client, "put0009")
        assert resp.status_code == 401

    def test_non_owner_returns_404(self, db_session: Session):
        """A user who doesn't own the link gets 404 (owner-404 rule)."""
        from backend.auth import get_current_user
        from backend.main import app
        from backend.router import get_db

        owner = make_user(db_session)
        other = make_user(db_session)
        _insert_owned_link(db_session, "put0010", owner.id)

        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: other
        with TestClient(app, raise_server_exceptions=True) as c:
            resp = _put_customization(c, "put0010")
        app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_logo_key_stored_when_logo_provided(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        from backend.main import app
        from backend.router import _get_storage

        gw = InMemoryGateway()
        app.dependency_overrides[_get_storage] = lambda: gw

        try:
            _insert_owned_link(db_session, "put0011", owner.id)
            resp = _put_customization(auth_client, "put0011", logo_bytes=_minimal_png())
            body = resp.json()
            assert body["logo_key"] is not None
            assert gw.exists(body["logo_key"]), "logo should be stored in gateway"
        finally:
            app.dependency_overrides.pop(_get_storage, None)

    def test_logo_key_none_when_no_logo(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "put0012", owner.id)
        resp = _put_customization(auth_client, "put0012")
        assert resp.json()["logo_key"] is None

    def test_re_style_writes_new_versioned_key_old_object_untouched(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        """Second PUT must write a new key; the first object must still exist (ADR 0011)."""
        from backend.main import app
        from backend.router import _get_storage

        gw = InMemoryGateway()
        app.dependency_overrides[_get_storage] = lambda: gw

        try:
            _insert_owned_link(db_session, "put0013", owner.id)
            resp1 = _put_customization(auth_client, "put0013")
            key1 = resp1.json()["image_key"]

            resp2 = _put_customization(auth_client, "put0013")
            key2 = resp2.json()["image_key"]

            assert key1 != key2, "re-style must produce a new versioned key"
            assert gw.exists(key1), "old composite must remain untouched"
            assert gw.exists(key2), "new composite must be stored"
        finally:
            app.dependency_overrides.pop(_get_storage, None)


# ---------------------------------------------------------------------------
# GET /api/qr/{token}/customization
# ---------------------------------------------------------------------------


class TestGetCustomization:
    def _store_customization(self, auth_client: TestClient, token: str) -> dict:
        resp = _put_customization(auth_client, token)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_happy_path_returns_200(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "get0001", owner.id)
        self._store_customization(auth_client, "get0001")
        resp = auth_client.get("/api/qr/get0001/customization")
        assert resp.status_code == 200

    def test_response_contains_style_and_urls(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "get0002", owner.id)
        self._store_customization(auth_client, "get0002")
        resp = auth_client.get("/api/qr/get0002/customization")
        body = resp.json()
        assert "style" in body
        assert "image_url" in body
        assert "updated_at" in body
        assert body["token"] == "get0002"

    def test_returns_404_when_no_customization(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "get0003", owner.id)
        resp = auth_client.get("/api/qr/get0003/customization")
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client: TestClient, db_session: Session):
        _insert_link(db_session, "get0004")
        resp = client.get("/api/qr/get0004/customization")
        assert resp.status_code == 401

    def test_non_owner_returns_404(self, db_session: Session):
        from backend.auth import get_current_user
        from backend.main import app
        from backend.router import get_db

        owner = make_user(db_session)
        other = make_user(db_session)
        _insert_owned_link(db_session, "get0005", owner.id)

        # First store via owner
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: owner
        with TestClient(app, raise_server_exceptions=True) as c:
            _put_customization(c, "get0005")
        app.dependency_overrides.clear()

        # Then try to GET as other
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: other
        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.get("/api/qr/get0005/customization")
        app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_logo_url_present_when_logo_stored(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        from backend.main import app
        from backend.router import _get_storage

        gw = InMemoryGateway()
        app.dependency_overrides[_get_storage] = lambda: gw

        try:
            _insert_owned_link(db_session, "get0006", owner.id)
            _put_customization(auth_client, "get0006", logo_bytes=_minimal_png())
            resp = auth_client.get("/api/qr/get0006/customization")
            assert resp.json()["logo_url"] is not None
        finally:
            app.dependency_overrides.pop(_get_storage, None)

    def test_logo_url_none_when_no_logo(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        _insert_owned_link(db_session, "get0007", owner.id)
        _put_customization(auth_client, "get0007")
        resp = auth_client.get("/api/qr/get0007/customization")
        assert resp.json()["logo_url"] is None


# ---------------------------------------------------------------------------
# GET /api/qr/{token}/image — serves stored composite when present
# ---------------------------------------------------------------------------


class TestQrImageWithCustomization:
    def test_uncustomized_link_still_returns_vanilla_png(
        self, client: TestClient, db_session: Session
    ):
        _insert_link(db_session, "img0001")
        resp = client.get("/api/qr/img0001/image")
        assert resp.status_code == 200
        assert resp.content[:4] == b"\x89PNG"

    def test_customized_link_serves_stored_composite(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        """After PUT, GET /image must return the stored composite, not vanilla."""
        from backend.main import app
        from backend.router import _get_storage

        fake_composite = _minimal_png()
        gw = InMemoryGateway()
        app.dependency_overrides[_get_storage] = lambda: gw

        try:
            _insert_owned_link(db_session, "img0002", owner.id)
            put_resp = _put_customization(
                auth_client, "img0002", image_bytes=fake_composite
            )
            assert put_resp.status_code == 200

            img_resp = auth_client.get("/api/qr/img0002/image")
            assert img_resp.status_code == 200
            assert img_resp.content == fake_composite
        finally:
            app.dependency_overrides.pop(_get_storage, None)

    def test_unknown_token_still_returns_404(self, client: TestClient):
        resp = client.get("/api/qr/unknown99/image")
        assert resp.status_code == 404
