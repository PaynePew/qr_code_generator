import os
import pytest
from fastapi.testclient import TestClient


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
