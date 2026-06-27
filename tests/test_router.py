import os

import pytest
from fastapi.testclient import TestClient


class TestCreateEndpoint:
    def test_unauthenticated_create_returns_401(self, client):
        # Login-to-create (ADR 0009): no session -> 401, no Link minted.
        resp = client.post("/api/qr/create", json={"url": "https://example.com/page"})
        assert resp.status_code == 401

    def test_create_returns_200_with_required_fields(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/page"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "short_url" in data
        assert "qr_code_url" in data
        assert "original_url" in data

    def test_token_is_7_chars(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/page"}
        )
        assert len(resp.json()["token"]) == 7

    def test_short_url_contains_token(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/page"}
        )
        data = resp.json()
        assert data["token"] in data["short_url"]

    def test_original_url_is_normalized(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "http://EXAMPLE.COM/page"}
        )
        assert resp.json()["original_url"] == "https://example.com/page"

    def test_two_posts_same_url_produce_different_tokens(self, auth_client):
        r1 = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/same"}
        )
        r2 = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/same"}
        )
        assert r1.json()["token"] != r2.json()["token"]

    def test_rejects_javascript_scheme(self, auth_client):
        resp = auth_client.post("/api/qr/create", json={"url": "javascript:alert(1)"})
        assert resp.status_code == 422

    def test_rejects_localhost(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "https://localhost/admin"}
        )
        assert resp.status_code == 422

    def test_rejects_private_ip(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "https://192.168.1.1/internal"}
        )
        assert resp.status_code == 422

    def test_rejects_file_scheme(self, auth_client):
        resp = auth_client.post("/api/qr/create", json={"url": "file:///etc/passwd"})
        assert resp.status_code == 422


class TestRedirectEndpoint:
    def test_redirect_returns_302(self, auth_client):
        create_resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/target"}
        )
        token = create_resp.json()["token"]
        # Redirect is public — assert it via the unauthenticated client.
        resp = auth_client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 302

    def test_redirect_location_header_is_original_url(self, auth_client):
        create_resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/target"}
        )
        token = create_resp.json()["token"]
        resp = auth_client.get(f"/r/{token}", follow_redirects=False)
        assert resp.headers["location"] == "https://example.com/target"

    def test_invalid_token_returns_404(self, client):
        resp = client.get("/r/INVALID1", follow_redirects=False)
        assert resp.status_code == 404


class TestCreateWithExpiration:
    def test_create_accepts_expires_at(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/page",
                "expires_at": "2099-01-01T00:00:00",
            },
        )
        assert resp.status_code == 200

    def test_create_without_expires_at_is_still_valid(self, auth_client):
        resp = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/page"}
        )
        assert resp.status_code == 200


class TestInfoEndpoint:
    def test_info_returns_200_for_active_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/info"}
        ).json()["token"]
        resp = auth_client.get(f"/api/qr/{token}")
        assert resp.status_code == 200

    def test_info_returns_404_for_unknown_token(self, auth_client):
        # Owner-only now (ADR 0009): an authenticated caller asking for a token
        # that does not exist gets 404 — same response a non-owner gets, so
        # existence is not leaked. (Unauthenticated -> 401, covered elsewhere.)
        resp = auth_client.get("/api/qr/NOTEXIST")
        assert resp.status_code == 404

    def test_info_response_shape(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/shape"}
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}").json()
        for field in (
            "token",
            "original_url",
            "short_url",
            "qr_code_url",
            "status",
            "created_at",
            "updated_at",
            "expires_at",
        ):
            assert field in data

    def test_info_status_active_for_live_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/active"}
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}").json()
        assert data["status"] == "active"

    def test_info_status_deleted_after_delete(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/del"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        data = auth_client.get(f"/api/qr/{token}").json()
        assert data["status"] == "deleted"

    def test_info_status_expired_for_past_expiry(self, auth_client):
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/exp",
                "expires_at": "2000-01-01T00:00:00",
            },
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}").json()
        assert data["status"] == "expired"

    def test_info_status_active_for_future_expiry(self, auth_client):
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/future",
                "expires_at": "2099-01-01T00:00:00",
            },
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}").json()
        assert data["status"] == "active"

    def test_info_returns_200_for_deleted_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/d2"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        assert auth_client.get(f"/api/qr/{token}").status_code == 200

    def test_info_returns_200_for_expired_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create",
            json={"url": "https://example.com/e2", "expires_at": "2000-01-01T00:00:00"},
        ).json()["token"]
        assert auth_client.get(f"/api/qr/{token}").status_code == 200


class TestPatchEndpoint:
    def test_patch_updates_original_url(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/old"}
        ).json()["token"]
        resp = auth_client.patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/new"}
        )
        assert resp.status_code == 200
        assert resp.json()["original_url"] == "https://example.com/new"

    def test_patch_redirect_uses_updated_url(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/orig"}
        ).json()["token"]
        auth_client.patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/updated"}
        )
        resp = auth_client.get(f"/r/{token}", follow_redirects=False)
        assert resp.headers["location"] == "https://example.com/updated"

    def test_patch_returns_409_link_deleted_for_deleted_link(self, auth_client):
        # ADR 0012: mutation on a deleted (terminal) Link -> 409 LINK_DELETED.
        # The Link still exists in trash; the request conflicts with terminal state.
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/p1"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        resp = auth_client.patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/new"}
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "LINK_DELETED"

    def test_patch_reactivates_expired_link_with_future_expiry(self, auth_client):
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/reactivate",
                "expires_at": "2000-01-01T00:00:00",
            },
        ).json()["token"]
        resp = auth_client.patch(
            f"/api/qr/{token}", json={"expires_at": "2099-01-01T00:00:00"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_patch_removes_expiration_with_null(self, auth_client):
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/nullexp",
                "expires_at": "2099-01-01T00:00:00",
            },
        ).json()["token"]
        resp = auth_client.patch(f"/api/qr/{token}", json={"expires_at": None})
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None

    def test_patch_empty_body_returns_422(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/empty"}
        ).json()["token"]
        resp = auth_client.patch(f"/api/qr/{token}", json={})
        assert resp.status_code == 422

    def test_patch_rejects_unknown_field(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/unknown"}
        ).json()["token"]
        resp = auth_client.patch(f"/api/qr/{token}", json={"url": "https://new.com"})
        assert resp.status_code == 422
        assert "url" in resp.text

    def test_patch_rejects_null_original_url(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/null"}
        ).json()["token"]
        resp = auth_client.patch(f"/api/qr/{token}", json={"original_url": None})
        assert resp.status_code == 422
        assert "null" in resp.text.lower() or "none" in resp.text.lower()

    def test_patch_rejects_empty_original_url(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/blank"}
        ).json()["token"]
        resp = auth_client.patch(f"/api/qr/{token}", json={"original_url": ""})
        assert resp.status_code == 422

    def test_patch_returns_404_for_unknown_token(self, auth_client):
        # Owner-only now (ADR 0009): authenticated + unknown token -> 404.
        resp = auth_client.patch(
            "/api/qr/NOTEXIST", json={"original_url": "https://example.com/x"}
        )
        assert resp.status_code == 404

    def test_patch_sets_updated_at(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/upd"}
        ).json()["token"]
        before = auth_client.get(f"/api/qr/{token}").json()["updated_at"]
        auth_client.patch(
            f"/api/qr/{token}", json={"original_url": "https://example.com/new2"}
        )
        after = auth_client.get(f"/api/qr/{token}").json()["updated_at"]
        assert after >= before


class TestDeleteEndpoint:
    def test_delete_returns_200(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/delete"}
        ).json()["token"]
        assert auth_client.delete(f"/api/qr/{token}").status_code == 200

    def test_delete_is_idempotent(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/idem"}
        ).json()["token"]
        assert auth_client.delete(f"/api/qr/{token}").status_code == 200
        assert auth_client.delete(f"/api/qr/{token}").status_code == 200

    def test_delete_returns_404_for_unknown_token(self, auth_client):
        # Owner-only now (ADR 0009): authenticated + unknown token -> 404.
        assert auth_client.delete("/api/qr/NOTEXIST").status_code == 404


class TestRedirectLifecycle:
    def test_redirect_returns_410_after_delete(self, auth_client):
        token = auth_client.post(
            "/api/qr/create", json={"url": "https://example.com/gone"}
        ).json()["token"]
        auth_client.delete(f"/api/qr/{token}")
        resp = auth_client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 410

    def test_redirect_returns_410_for_expired_link(self, auth_client):
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/expgone",
                "expires_at": "2000-01-01T00:00:00",
            },
        ).json()["token"]
        resp = auth_client.get(f"/r/{token}", follow_redirects=False)
        assert resp.status_code == 410


class TestEnvVarRequirements:
    def test_secret_env_var_required(self):
        secret = os.environ.pop("SECRET", None)
        try:
            import backend.main as m

            with pytest.raises((RuntimeError, KeyError, Exception)):
                with TestClient(m.app) as c:
                    c.get("/")
        finally:
            if secret is not None:
                os.environ["SECRET"] = secret

    def test_base_url_env_var_required(self):
        base_url = os.environ.pop("BASE_URL", None)
        try:
            import backend.main as m

            with pytest.raises((RuntimeError, KeyError, Exception)):
                with TestClient(m.app) as c:
                    c.get("/")
        finally:
            if base_url is not None:
                os.environ["BASE_URL"] = base_url


class TestStorageGatewaySelection:
    """Gateway is env-driven at startup: LocalDiskGateway when AWS_S3_BUCKET absent
    (dev default), S3Gateway when AWS_S3_BUCKET + AWS_REGION are set (ADR 0011)."""

    def test_build_storage_gateway_returns_local_disk_when_no_bucket(self, tmp_path):
        from backend.router import build_storage_gateway
        from backend.storage import LocalDiskGateway

        env = {
            "SECRET": "x",
            "BASE_URL": "http://example.com",
            "LOCAL_STORAGE_DIR": str(tmp_path / "storage"),
        }
        gw = build_storage_gateway(env)
        assert isinstance(gw, LocalDiskGateway)

    def test_build_storage_gateway_returns_s3_when_bucket_and_region_set(self):
        from backend.router import build_storage_gateway
        from backend.storage import S3Gateway

        env = {
            "SECRET": "x",
            "BASE_URL": "http://example.com",
            "AWS_S3_BUCKET": "my-bucket",
            "AWS_REGION": "us-east-1",
        }
        gw = build_storage_gateway(env)
        assert isinstance(gw, S3Gateway)

    def test_build_storage_gateway_passes_endpoint_url_when_set(self):
        from backend.router import build_storage_gateway
        from backend.storage import S3Gateway

        env = {
            "SECRET": "x",
            "BASE_URL": "http://example.com",
            "AWS_S3_BUCKET": "my-bucket",
            "AWS_REGION": "us-east-1",
            "AWS_ENDPOINT_URL": "http://localhost:9000",
        }
        gw = build_storage_gateway(env)
        assert isinstance(gw, S3Gateway)
        # The endpoint URL must be reflected in url_for output
        url = gw.url_for("qr/tok/composite_abc.png")
        assert "localhost:9000" in url

    def test_build_storage_gateway_raises_when_bucket_set_without_region(self):
        from backend.router import build_storage_gateway

        env = {
            "SECRET": "x",
            "BASE_URL": "http://example.com",
            "AWS_S3_BUCKET": "my-bucket",
            # AWS_REGION intentionally absent
        }
        with pytest.raises(RuntimeError, match="AWS_REGION"):
            build_storage_gateway(env)

    def test_lifespan_wires_s3gateway_when_env_present(self):
        """App startup must replace _storage_gateway with S3Gateway when env is set."""
        import backend.main as main_mod
        import backend.router as router_mod
        from backend.storage import S3Gateway

        env_patch = {
            "SECRET": "x",
            "BASE_URL": "http://example.com",
            "AWS_S3_BUCKET": "test-bucket",
            "AWS_REGION": "eu-west-1",
        }
        original_env = {}
        for k, v in env_patch.items():
            original_env[k] = os.environ.get(k)
            os.environ[k] = v
        # Remove any accidentally-set region before test (to isolate)
        removed_extra = {}
        for k in ("AWS_ENDPOINT_URL",):
            if k in os.environ:
                removed_extra[k] = os.environ.pop(k)

        try:
            with TestClient(main_mod.app) as _:
                # During lifespan the module-level gateway should be S3Gateway
                assert isinstance(router_mod._storage_gateway, S3Gateway), (
                    f"Expected S3Gateway, got {type(router_mod._storage_gateway)}"
                )
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            for k, v in removed_extra.items():
                os.environ[k] = v
