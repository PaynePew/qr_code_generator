import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET", "test-secret-value")
os.environ.setdefault("BASE_URL", "http://testserver")

from main import app
from models import Base
from router import get_db


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


class TestCreateEndpoint:
    def test_create_returns_200_with_required_fields(self, client):
        resp = client.post("/api/qr/create", json={"url": "https://example.com/page"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "short_url" in data
        assert "qr_code_url" in data
        assert "original_url" in data

    def test_token_is_7_chars(self, client):
        resp = client.post("/api/qr/create", json={"url": "https://example.com/page"})
        assert len(resp.json()["token"]) == 7

    def test_short_url_contains_token(self, client):
        resp = client.post("/api/qr/create", json={"url": "https://example.com/page"})
        data = resp.json()
        assert data["token"] in data["short_url"]

    def test_original_url_is_normalized(self, client):
        resp = client.post("/api/qr/create", json={"url": "http://EXAMPLE.COM/page"})
        assert resp.json()["original_url"] == "https://example.com/page"

    def test_two_posts_same_url_produce_different_tokens(self, client):
        r1 = client.post("/api/qr/create", json={"url": "https://example.com/same"})
        r2 = client.post("/api/qr/create", json={"url": "https://example.com/same"})
        assert r1.json()["token"] != r2.json()["token"]

    def test_rejects_javascript_scheme(self, client):
        resp = client.post("/api/qr/create", json={"url": "javascript:alert(1)"})
        assert resp.status_code == 422

    def test_rejects_localhost(self, client):
        resp = client.post("/api/qr/create", json={"url": "https://localhost/admin"})
        assert resp.status_code == 422

    def test_rejects_private_ip(self, client):
        resp = client.post("/api/qr/create", json={"url": "https://192.168.1.1/internal"})
        assert resp.status_code == 422

    def test_rejects_file_scheme(self, client):
        resp = client.post("/api/qr/create", json={"url": "file:///etc/passwd"})
        assert resp.status_code == 422


class TestRedirectEndpoint:
    def test_redirect_returns_302(self, client):
        create_resp = client.post("/api/qr/create", json={"url": "https://example.com/target"})
        token = create_resp.json()["token"]
        resp = client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 302

    def test_redirect_location_header_is_original_url(self, client):
        create_resp = client.post("/api/qr/create", json={"url": "https://example.com/target"})
        token = create_resp.json()["token"]
        resp = client.get(f"/r/{token}", follow_redirects=False)
        assert resp.headers["location"] == "https://example.com/target"

    def test_invalid_token_returns_404(self, client):
        resp = client.get("/r/INVALID1", follow_redirects=False)
        assert resp.status_code == 404


class TestCreateWithExpiration:
    def test_create_accepts_expires_at(self, client):
        resp = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/page", "expires_at": "2099-01-01T00:00:00"},
        )
        assert resp.status_code == 200

    def test_create_without_expires_at_is_still_valid(self, client):
        resp = client.post("/api/qr/create", json={"url": "https://example.com/page"})
        assert resp.status_code == 200


class TestInfoEndpoint:
    def test_info_returns_200_for_active_link(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/info"}).json()["token"]
        resp = client.get(f"/api/qr/{token}")
        assert resp.status_code == 200

    def test_info_returns_404_for_unknown_token(self, client):
        resp = client.get("/api/qr/NOTEXIST")
        assert resp.status_code == 404

    def test_info_response_shape(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/shape"}).json()["token"]
        data = client.get(f"/api/qr/{token}").json()
        for field in (
            "token", "original_url", "short_url", "qr_code_url",
            "status", "created_at", "updated_at", "expires_at",
        ):
            assert field in data

    def test_info_status_active_for_live_link(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/active"}).json()["token"]
        data = client.get(f"/api/qr/{token}").json()
        assert data["status"] == "active"

    def test_info_status_deleted_after_delete(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/del"}).json()["token"]
        client.delete(f"/api/qr/{token}")
        data = client.get(f"/api/qr/{token}").json()
        assert data["status"] == "deleted"

    def test_info_status_expired_for_past_expiry(self, client):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/exp", "expires_at": "2000-01-01T00:00:00"},
        ).json()["token"]
        data = client.get(f"/api/qr/{token}").json()
        assert data["status"] == "expired"

    def test_info_status_active_for_future_expiry(self, client):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/future", "expires_at": "2099-01-01T00:00:00"},
        ).json()["token"]
        data = client.get(f"/api/qr/{token}").json()
        assert data["status"] == "active"

    def test_info_returns_200_for_deleted_link(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/d2"}).json()["token"]
        client.delete(f"/api/qr/{token}")
        assert client.get(f"/api/qr/{token}").status_code == 200

    def test_info_returns_200_for_expired_link(self, client):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/e2", "expires_at": "2000-01-01T00:00:00"},
        ).json()["token"]
        assert client.get(f"/api/qr/{token}").status_code == 200


class TestPatchEndpoint:
    def test_patch_updates_original_url(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/old"}).json()["token"]
        resp = client.patch(f"/api/qr/{token}", json={"original_url": "https://example.com/new"})
        assert resp.status_code == 200
        assert resp.json()["original_url"] == "https://example.com/new"

    def test_patch_redirect_uses_updated_url(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/orig"}).json()["token"]
        client.patch(f"/api/qr/{token}", json={"original_url": "https://example.com/updated"})
        resp = client.get(f"/r/{token}", follow_redirects=False)
        assert resp.headers["location"] == "https://example.com/updated"

    def test_patch_returns_410_for_deleted_link(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/p1"}).json()["token"]
        client.delete(f"/api/qr/{token}")
        resp = client.patch(f"/api/qr/{token}", json={"original_url": "https://example.com/new"})
        assert resp.status_code == 410

    def test_patch_reactivates_expired_link_with_future_expiry(self, client):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/reactivate", "expires_at": "2000-01-01T00:00:00"},
        ).json()["token"]
        resp = client.patch(f"/api/qr/{token}", json={"expires_at": "2099-01-01T00:00:00"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_patch_removes_expiration_with_null(self, client):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/nullexp", "expires_at": "2099-01-01T00:00:00"},
        ).json()["token"]
        resp = client.patch(f"/api/qr/{token}", json={"expires_at": None})
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None

    def test_patch_empty_body_returns_422(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/empty"}).json()["token"]
        resp = client.patch(f"/api/qr/{token}", json={})
        assert resp.status_code == 422

    def test_patch_returns_404_for_unknown_token(self, client):
        resp = client.patch("/api/qr/NOTEXIST", json={"original_url": "https://example.com/x"})
        assert resp.status_code == 404

    def test_patch_sets_updated_at(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/upd"}).json()["token"]
        before = client.get(f"/api/qr/{token}").json()["updated_at"]
        client.patch(f"/api/qr/{token}", json={"original_url": "https://example.com/new2"})
        after = client.get(f"/api/qr/{token}").json()["updated_at"]
        assert after >= before


class TestDeleteEndpoint:
    def test_delete_returns_200(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/delete"}).json()["token"]
        assert client.delete(f"/api/qr/{token}").status_code == 200

    def test_delete_is_idempotent(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/idem"}).json()["token"]
        assert client.delete(f"/api/qr/{token}").status_code == 200
        assert client.delete(f"/api/qr/{token}").status_code == 200

    def test_delete_returns_404_for_unknown_token(self, client):
        assert client.delete("/api/qr/NOTEXIST").status_code == 404


class TestRedirectLifecycle:
    def test_redirect_returns_410_after_delete(self, client):
        token = client.post("/api/qr/create", json={"url": "https://example.com/gone"}).json()["token"]
        client.delete(f"/api/qr/{token}")
        resp = client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 410

    def test_redirect_returns_410_for_expired_link(self, client):
        token = client.post(
            "/api/qr/create",
            json={"url": "https://example.com/expgone", "expires_at": "2000-01-01T00:00:00"},
        ).json()["token"]
        resp = client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 410


class TestEnvVarRequirements:
    def test_secret_env_var_required(self):
        secret = os.environ.pop("SECRET", None)
        try:
            import importlib
            import main as m
            with pytest.raises((RuntimeError, KeyError, Exception)):
                with TestClient(m.app) as c:
                    c.get("/")
        finally:
            if secret is not None:
                os.environ["SECRET"] = secret

    def test_base_url_env_var_required(self):
        base_url = os.environ.pop("BASE_URL", None)
        try:
            import main as m
            with pytest.raises((RuntimeError, KeyError, Exception)):
                with TestClient(m.app) as c:
                    c.get("/")
        finally:
            if base_url is not None:
                os.environ["BASE_URL"] = base_url
