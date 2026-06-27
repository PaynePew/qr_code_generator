"""Tests for LocalDiskGateway — the on-disk dev storage gateway (no S3 needed).

Covers the properties the local-dev fix relies on: bytes persist across gateway
instances (i.e. across backend restarts), the store is non-public so the image /
logo endpoints proxy via ``get``, and app-generated keys round-trip while a
traversal key is refused.
"""

from __future__ import annotations

import pytest

from backend.storage import LocalDiskGateway

_KEY = "qr/abc123/composite_deadbeef.png"
_DATA = b"\x89PNG\r\n\x1a\n-not-a-real-png-but-bytes"


def test_put_then_get_roundtrips(tmp_path):
    gw = LocalDiskGateway(tmp_path)
    gw.put(_KEY, _DATA, "image/png")
    assert gw.get(_KEY) == _DATA


def test_get_missing_key_returns_none(tmp_path):
    gw = LocalDiskGateway(tmp_path)
    assert gw.get("qr/none/missing.png") is None


def test_bytes_persist_across_instances(tmp_path):
    """A new gateway over the same dir reads prior writes — i.e. survives restart."""
    LocalDiskGateway(tmp_path).put(_KEY, _DATA, "image/png")
    # Simulate an `uvicorn --reload` restart: a brand-new gateway, same dir.
    assert LocalDiskGateway(tmp_path).get(_KEY) == _DATA


def test_public_url_for_is_none_so_endpoints_proxy(tmp_path):
    gw = LocalDiskGateway(tmp_path)
    gw.put(_KEY, _DATA, "image/png")
    assert gw.public_url_for(_KEY) is None


def test_exists_reflects_writes_and_deletes(tmp_path):
    gw = LocalDiskGateway(tmp_path)
    assert gw.exists(_KEY) is False
    gw.put(_KEY, _DATA, "image/png")
    assert gw.exists(_KEY) is True
    gw.delete(_KEY)
    assert gw.exists(_KEY) is False


def test_delete_missing_key_is_noop(tmp_path):
    LocalDiskGateway(tmp_path).delete("qr/none/missing.png")  # no raise


def test_nested_key_creates_parent_dirs(tmp_path):
    gw = LocalDiskGateway(tmp_path)
    gw.put("qr/deep/nest/composite_x.png", _DATA, "image/png")
    assert (tmp_path / "qr" / "deep" / "nest" / "composite_x.png").read_bytes() == _DATA


def test_traversal_key_is_rejected(tmp_path):
    gw = LocalDiskGateway(tmp_path)
    with pytest.raises(ValueError, match="escapes storage root"):
        gw.put("../escape.png", _DATA, "image/png")
