from datetime import datetime, timezone, timedelta

from models import Link
from qr_generator import generate_qr_png

PNG_MAGIC = b"\x89PNG"


# --- unit tests for qr_generator ---

class TestQrGenerator:
    def test_returns_bytes(self):
        result = generate_qr_png("http://testserver/r/abc1234")
        assert isinstance(result, bytes)

    def test_starts_with_png_magic(self):
        result = generate_qr_png("http://testserver/r/abc1234")
        assert result[:4] == PNG_MAGIC

    def test_different_urls_produce_different_images(self):
        a = generate_qr_png("http://testserver/r/aaaaaaa")
        b = generate_qr_png("http://testserver/r/bbbbbbb")
        assert a != b

    def test_same_url_produces_same_image(self):
        url = "http://testserver/r/abc1234"
        assert generate_qr_png(url) == generate_qr_png(url)


# --- integration tests for GET /api/qr/{token}/image ---

def _insert_link(db_session, token, deleted=False, expired=False):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    link = Link(
        token=token,
        original_url="https://example.com/page",
        created_at=now,
        updated_at=now,
        deleted_at=now if deleted else None,
        expires_at=(now - timedelta(days=1)) if expired else None,
    )
    db_session.add(link)
    db_session.commit()
    return link


class TestQrImageEndpoint:
    def test_active_link_returns_200(self, client, db_session):
        _insert_link(db_session, "active1")
        resp = client.get("/api/qr/active1/image")
        assert resp.status_code == 200

    def test_active_link_content_type_is_png(self, client, db_session):
        _insert_link(db_session, "active2")
        resp = client.get("/api/qr/active2/image")
        assert resp.headers["content-type"] == "image/png"

    def test_active_link_body_starts_with_png_magic(self, client, db_session):
        _insert_link(db_session, "active3")
        resp = client.get("/api/qr/active3/image")
        assert resp.content[:4] == PNG_MAGIC

    def test_deleted_link_returns_200(self, client, db_session):
        _insert_link(db_session, "delet01", deleted=True)
        resp = client.get("/api/qr/delet01/image")
        assert resp.status_code == 200

    def test_expired_link_returns_200(self, client, db_session):
        _insert_link(db_session, "expir01", expired=True)
        resp = client.get("/api/qr/expir01/image")
        assert resp.status_code == 200

    def test_unknown_token_returns_404(self, client):
        resp = client.get("/api/qr/unknown/image")
        assert resp.status_code == 404
