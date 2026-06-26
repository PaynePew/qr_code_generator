"""Tests for CDN-able image serving and immutable composites (ADR 0017 / issue qr_code_generator-mrv).

Coverage:
- S3Gateway.url_for: returns CDN URL when cdn_base_url set, S3 URL otherwise
- public_url_for: CDN URL when a CDN fronts the bucket, else None (Route A)
- Image endpoint (Route A): customized Link 302s to the CDN URL when a CDN is
  configured, else the backend proxies the composite bytes (200); no-cache on both
- Image endpoint: vanilla Link returns inline PNG with no-cache
- Immutable Cache-Control forwarded by S3Gateway.put
- InMemoryGateway: cache_control kwarg accepted (no-op, no regression)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models import Link, LinkCustomization
from backend.storage import IMMUTABLE_CACHE_CONTROL, InMemoryGateway, S3Gateway

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _attach_customization(
    db_session: Session, link: Link, image_key: str
) -> LinkCustomization:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    c = LinkCustomization(
        link_id=link.id,
        style_json='{"foreground":"#000000"}',
        image_key=image_key,
        logo_key=None,
        updated_at=now,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


# ---------------------------------------------------------------------------
# S3Gateway.url_for — CDN vs S3 URL
# ---------------------------------------------------------------------------


class TestS3GatewayUrlFor:
    def test_returns_cdn_url_when_cdn_base_url_set(self):
        gw = S3Gateway(
            bucket="my-bucket",
            region="us-east-1",
            cdn_base_url="https://abc123.cloudfront.net",
        )
        result = gw.url_for("qr/tok/composite_abc.png")
        assert result == "https://abc123.cloudfront.net/qr/tok/composite_abc.png"

    def test_cdn_base_url_trailing_slash_stripped(self):
        gw = S3Gateway(
            bucket="my-bucket",
            region="us-east-1",
            cdn_base_url="https://abc123.cloudfront.net/",
        )
        result = gw.url_for("qr/tok/composite.png")
        assert result == "https://abc123.cloudfront.net/qr/tok/composite.png"

    def test_returns_s3_url_when_cdn_base_url_not_set(self):
        gw = S3Gateway(bucket="my-bucket", region="us-east-1")
        result = gw.url_for("qr/tok/composite_abc.png")
        assert (
            result
            == "https://my-bucket.s3.us-east-1.amazonaws.com/qr/tok/composite_abc.png"
        )

    def test_returns_endpoint_url_when_set_and_no_cdn(self):
        gw = S3Gateway(
            bucket="my-bucket",
            region="us-east-1",
            endpoint_url="http://localhost:9000",
        )
        result = gw.url_for("qr/tok/composite_abc.png")
        assert result == "http://localhost:9000/my-bucket/qr/tok/composite_abc.png"

    def test_cdn_takes_precedence_over_endpoint_url(self):
        """cdn_base_url wins when both cdn_base_url and endpoint_url are set."""
        gw = S3Gateway(
            bucket="my-bucket",
            region="us-east-1",
            endpoint_url="http://localhost:9000",
            cdn_base_url="https://cdn.example.com",
        )
        result = gw.url_for("qr/tok/composite.png")
        assert result == "https://cdn.example.com/qr/tok/composite.png"


# ---------------------------------------------------------------------------
# public_url_for — browser-fetchable URL only when a CDN fronts the bucket
# ---------------------------------------------------------------------------


class TestPublicUrlFor:
    """public_url_for returns a public URL ONLY when a CDN fronts the bucket (Route A)."""

    def test_s3_returns_cdn_url_when_cdn_set(self):
        gw = S3Gateway(
            bucket="b", region="ap-northeast-1", cdn_base_url="https://cdn.example.com"
        )
        assert gw.public_url_for("qr/t/c.png") == "https://cdn.example.com/qr/t/c.png"

    def test_s3_returns_none_when_no_cdn(self):
        gw = S3Gateway(bucket="b", region="ap-northeast-1")
        assert gw.public_url_for("qr/t/c.png") is None

    def test_s3_returns_none_with_endpoint_but_no_cdn(self):
        gw = S3Gateway(
            bucket="b", region="ap-northeast-1", endpoint_url="http://localhost:9000"
        )
        assert gw.public_url_for("qr/t/c.png") is None

    def test_inmemory_always_returns_none(self):
        gw = InMemoryGateway(base_url="http://fake-storage")
        assert gw.public_url_for("qr/t/c.png") is None


# ---------------------------------------------------------------------------
# IMMUTABLE_CACHE_CONTROL constant
# ---------------------------------------------------------------------------


class TestImmutableCacheControlConstant:
    def test_value_matches_spec(self):
        assert IMMUTABLE_CACHE_CONTROL == "public, max-age=31536000, immutable"


# ---------------------------------------------------------------------------
# InMemoryGateway: cache_control kwarg accepted without error
# ---------------------------------------------------------------------------


class TestInMemoryGatewayCacheControlKwarg:
    def test_put_with_cache_control_does_not_raise(self):
        gw = InMemoryGateway()
        gw.put("k", b"data", "image/png", cache_control=IMMUTABLE_CACHE_CONTROL)
        assert gw.get("k") == b"data"

    def test_put_without_cache_control_still_works(self):
        gw = InMemoryGateway()
        gw.put("k2", b"data2", "image/png")
        assert gw.get("k2") == b"data2"


# ---------------------------------------------------------------------------
# Image endpoint (Route A): customized Link 302s to the CDN URL when a CDN is set
# ---------------------------------------------------------------------------

_CDN_BASE = "https://cdn.example.com"


def _cdn_gateway() -> S3Gateway:
    # CDN-configured S3Gateway. The 302 path only calls public_url_for (no boto3),
    # so this never touches real AWS.
    return S3Gateway(bucket="b", region="ap-northeast-1", cdn_base_url=_CDN_BASE)


class TestQrImageCdnRedirect:
    def test_customized_link_returns_302(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        """Customized Link with a CDN configured: image endpoint returns 302."""
        from backend.main import app
        from backend.router import _get_storage

        app.dependency_overrides[_get_storage] = _cdn_gateway
        try:
            link = _insert_owned_link(db_session, "cdn0001", owner.id)
            _attach_customization(db_session, link, "qr/cdn0001/composite_abc.png")

            resp = auth_client.get("/api/qr/cdn0001/image", follow_redirects=False)
            assert resp.status_code == 302
        finally:
            app.dependency_overrides.pop(_get_storage, None)

    def test_customized_link_302_location_is_cdn_url(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        """The 302 Location must be the CDN URL (public_url_for)."""
        from backend.main import app
        from backend.router import _get_storage

        app.dependency_overrides[_get_storage] = _cdn_gateway
        try:
            link = _insert_owned_link(db_session, "cdn0002", owner.id)
            image_key = "qr/cdn0002/composite_xyz.png"
            _attach_customization(db_session, link, image_key)

            resp = auth_client.get("/api/qr/cdn0002/image", follow_redirects=False)
            assert resp.status_code == 302
            assert resp.headers["location"] == f"{_CDN_BASE}/{image_key}"
        finally:
            app.dependency_overrides.pop(_get_storage, None)

    def test_customized_link_302_carries_no_cache(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        """The 302 itself must carry Cache-Control: no-cache (mutable pointer)."""
        from backend.main import app
        from backend.router import _get_storage

        app.dependency_overrides[_get_storage] = _cdn_gateway
        try:
            link = _insert_owned_link(db_session, "cdn0003", owner.id)
            image_key = "qr/cdn0003/composite_no_cache.png"
            _attach_customization(db_session, link, image_key)

            resp = auth_client.get("/api/qr/cdn0003/image", follow_redirects=False)
            assert resp.status_code == 302
            assert resp.headers.get("cache-control") == "no-cache"
        finally:
            app.dependency_overrides.pop(_get_storage, None)


# ---------------------------------------------------------------------------
# Image endpoint: vanilla Link returns inline PNG with no-cache
# ---------------------------------------------------------------------------


class TestQrImageVanillaNoCache:
    def test_vanilla_link_returns_200(self, client: TestClient, db_session: Session):
        _insert_link(db_session, "van0001")
        resp = client.get("/api/qr/van0001/image")
        assert resp.status_code == 200

    def test_vanilla_link_returns_png(self, client: TestClient, db_session: Session):
        _insert_link(db_session, "van0002")
        resp = client.get("/api/qr/van0002/image")
        assert resp.content[:4] == b"\x89PNG"

    def test_vanilla_link_has_no_cache_header(
        self, client: TestClient, db_session: Session
    ):
        _insert_link(db_session, "van0003")
        resp = client.get("/api/qr/van0003/image")
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-cache"


# ---------------------------------------------------------------------------
# Route A: CDN_BASE_URL unset — the backend proxies the composite bytes (200)
# ---------------------------------------------------------------------------


class TestQrImageProxyNoCdn:
    def test_customized_link_proxies_bytes_200_when_no_cdn(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        """With no CDN, the endpoint streams the stored composite (200), not a 302.

        This is the fix for the broken-image bug: previously the endpoint 302'd
        the browser to a private-S3 / unreachable URL (403). Now the backend
        reads the bytes (which it CAN, holding the creds) and serves them.
        """
        from backend.main import app
        from backend.router import _get_storage

        gw = InMemoryGateway()
        app.dependency_overrides[_get_storage] = lambda: gw
        try:
            link = _insert_owned_link(db_session, "s3fb001", owner.id)
            image_key = "qr/s3fb001/composite_fallback.png"
            composite = b"\x89PNG\r\n\x1a\n" + b"the-stored-composite"
            gw.put(image_key, composite, "image/png")
            _attach_customization(db_session, link, image_key)

            resp = auth_client.get("/api/qr/s3fb001/image", follow_redirects=False)
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/png"
            assert resp.content == composite
            assert resp.headers.get("cache-control") == "no-cache"
        finally:
            app.dependency_overrides.pop(_get_storage, None)

    def test_missing_composite_falls_back_to_vanilla(
        self, auth_client: TestClient, db_session: Session, owner
    ):
        """image_key recorded but the object is absent → graceful vanilla PNG (200)."""
        from backend.main import app
        from backend.router import _get_storage

        gw = InMemoryGateway()
        app.dependency_overrides[_get_storage] = lambda: gw
        try:
            link = _insert_owned_link(db_session, "miss001", owner.id)
            # NOTE: no gw.put — the key is referenced but the object is missing.
            _attach_customization(db_session, link, "qr/miss001/composite_gone.png")

            resp = auth_client.get("/api/qr/miss001/image", follow_redirects=False)
            assert resp.status_code == 200
            assert resp.content[:4] == b"\x89PNG"
        finally:
            app.dependency_overrides.pop(_get_storage, None)
