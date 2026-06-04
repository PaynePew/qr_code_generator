"""Per-token labels for Links — ADR 0010, issue qr_code_generator-ai0.

End-to-end coverage:
- create with and without label;
- PATCH sets, renames, and clears a label;
- GET /api/qr and GET /api/qr/{token} expose label;
- label is trimmed and capped at 100 chars;
- labels are non-unique (two Links may share the same text);
- same owner POSTing the same URL × 4 yields 4 distinct tokens (no dedup);
- Alembic migration is exercised implicitly (conftest runs alembic upgrade head).
"""

from __future__ import annotations


def _create(client, url: str, label: str | None = None) -> str:
    body: dict = {"url": url}
    if label is not None:
        body["label"] = label
    resp = client.post("/api/qr/create", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


class TestCreateWithLabel:
    def test_create_without_label_returns_null_label(self, auth_client):
        token = _create(auth_client, "https://example.com/no-label")
        info = auth_client.get(f"/api/qr/{token}").json()
        assert info["label"] is None

    def test_create_with_label_returns_label(self, auth_client):
        token = _create(auth_client, "https://example.com/label", label="Lobby poster")
        info = auth_client.get(f"/api/qr/{token}").json()
        assert info["label"] == "Lobby poster"

    def test_create_trims_label_whitespace(self, auth_client):
        token = _create(auth_client, "https://example.com/trim", label="  trimmed  ")
        info = auth_client.get(f"/api/qr/{token}").json()
        assert info["label"] == "trimmed"

    def test_create_caps_label_at_100_chars(self, auth_client):
        long_label = "x" * 120
        token = _create(auth_client, "https://example.com/long", label=long_label)
        info = auth_client.get(f"/api/qr/{token}").json()
        assert info["label"] == "x" * 100

    def test_labels_not_unique_across_owner_links(self, auth_client):
        """Same label text may appear on multiple of an owner's Links."""
        token1 = _create(auth_client, "https://example.com/dup1", label="shared")
        token2 = _create(auth_client, "https://example.com/dup2", label="shared")
        info1 = auth_client.get(f"/api/qr/{token1}").json()
        info2 = auth_client.get(f"/api/qr/{token2}").json()
        assert info1["label"] == "shared"
        assert info2["label"] == "shared"

    def test_four_posts_same_url_yield_four_distinct_tokens(self, auth_client):
        """ADR 0010: no deduplication — each POST mints a fresh token."""
        url = "https://example.com/dedup-check"
        tokens = [_create(auth_client, url, label=f"L{i}") for i in range(4)]
        assert len(set(tokens)) == 4


class TestPatchLabel:
    def test_patch_sets_label(self, auth_client):
        token = _create(auth_client, "https://example.com/patch-set")
        resp = auth_client.patch(f"/api/qr/{token}", json={"label": "Newsletter"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "Newsletter"

    def test_patch_renames_label(self, auth_client):
        token = _create(
            auth_client, "https://example.com/patch-rename", label="Old name"
        )
        resp = auth_client.patch(f"/api/qr/{token}", json={"label": "New name"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "New name"

    def test_patch_clears_label_with_null(self, auth_client):
        token = _create(
            auth_client, "https://example.com/patch-clear", label="Will be gone"
        )
        resp = auth_client.patch(f"/api/qr/{token}", json={"label": None})
        assert resp.status_code == 200
        assert resp.json()["label"] is None

    def test_patch_trims_label(self, auth_client):
        token = _create(auth_client, "https://example.com/patch-trim")
        resp = auth_client.patch(f"/api/qr/{token}", json={"label": "  padded  "})
        assert resp.status_code == 200
        assert resp.json()["label"] == "padded"

    def test_patch_caps_label_at_100_chars(self, auth_client):
        token = _create(auth_client, "https://example.com/patch-cap")
        resp = auth_client.patch(f"/api/qr/{token}", json={"label": "y" * 150})
        assert resp.status_code == 200
        assert resp.json()["label"] == "y" * 100

    def test_patch_label_alone_is_valid(self, auth_client):
        """label-only PATCH is a valid update (no other field required)."""
        token = _create(auth_client, "https://example.com/label-only")
        resp = auth_client.patch(f"/api/qr/{token}", json={"label": "solo"})
        assert resp.status_code == 200


class TestListIncludesLabel:
    def test_list_includes_label_field(self, auth_client):
        _create(auth_client, "https://example.com/list-label", label="my label")
        items = auth_client.get("/api/qr").json()["items"]
        assert "label" in items[0]

    def test_list_label_value_matches_create(self, auth_client):
        token = _create(auth_client, "https://example.com/list-val", label="tag1")
        items = auth_client.get("/api/qr").json()["items"]
        item = next(i for i in items if i["token"] == token)
        assert item["label"] == "tag1"

    def test_list_null_label_when_unlabeled(self, auth_client):
        token = _create(auth_client, "https://example.com/list-null")
        items = auth_client.get("/api/qr").json()["items"]
        item = next(i for i in items if i["token"] == token)
        assert item["label"] is None
