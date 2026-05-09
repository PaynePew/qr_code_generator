import json
from datetime import datetime, timedelta

import pytest

from backend.link_state import (
    LinkAlreadyDeletedError,
    LinkNotFoundError,
    LinkState,
    derive_state,
    ensure_patchable,
)
from backend.models import Link


NOW = datetime(2026, 5, 8, 12, 0, 0)


def _link(*, deleted_at=None, expires_at=None) -> Link:
    return Link(
        token="ABCDEFG",
        original_url="https://example.com/x",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
        deleted_at=deleted_at,
        expires_at=expires_at,
    )


class TestDeriveState:
    def test_active_when_no_deleted_no_expires(self):
        assert derive_state(_link(), NOW) is LinkState.ACTIVE

    def test_active_when_expires_in_future(self):
        future = NOW + timedelta(days=1)
        assert derive_state(_link(expires_at=future), NOW) is LinkState.ACTIVE

    def test_expired_when_expires_in_past(self):
        past = NOW - timedelta(days=1)
        assert derive_state(_link(expires_at=past), NOW) is LinkState.EXPIRED

    def test_expired_at_boundary_now_equal(self):
        assert derive_state(_link(expires_at=NOW), NOW) is LinkState.EXPIRED

    def test_deleted_takes_precedence_over_expired(self):
        past = NOW - timedelta(days=1)
        link = _link(deleted_at=NOW, expires_at=past)
        assert derive_state(link, NOW) is LinkState.DELETED

    def test_deleted_takes_precedence_over_active(self):
        future = NOW + timedelta(days=1)
        link = _link(deleted_at=NOW, expires_at=future)
        assert derive_state(link, NOW) is LinkState.DELETED


class TestIsRedirectable:
    def test_active_is_redirectable(self):
        assert LinkState.ACTIVE.is_redirectable is True

    def test_expired_is_not_redirectable(self):
        assert LinkState.EXPIRED.is_redirectable is False

    def test_deleted_is_not_redirectable(self):
        assert LinkState.DELETED.is_redirectable is False


class TestIsPatchable:
    """Locks ADR 0001 in code: deleted is terminal; expired is reversible."""

    def test_active_is_patchable(self):
        assert LinkState.ACTIVE.is_patchable is True

    def test_expired_is_patchable(self):
        # ADR 0001: a user may extend expires_at to re-activate an expired link.
        assert LinkState.EXPIRED.is_patchable is True

    def test_deleted_is_not_patchable(self):
        # ADR 0001: deleted is terminal.
        assert LinkState.DELETED.is_patchable is False


class TestEnsurePatchable:
    """ADR 0001 enforcement at the domain layer."""

    def test_active_does_not_raise(self):
        ensure_patchable(_link(), NOW)

    def test_expired_does_not_raise(self):
        # ADR 0001: expired is reversible via PATCH expires_at.
        past = NOW - timedelta(days=1)
        ensure_patchable(_link(expires_at=past), NOW)

    def test_deleted_raises_link_already_deleted(self):
        link = _link(deleted_at=NOW)
        with pytest.raises(LinkAlreadyDeletedError) as exc:
            ensure_patchable(link, NOW)
        assert exc.value.token == "ABCDEFG"

    def test_deleted_and_expired_still_raises(self):
        # deleted takes precedence over expired in derivation; same here.
        past = NOW - timedelta(days=1)
        link = _link(deleted_at=NOW, expires_at=past)
        with pytest.raises(LinkAlreadyDeletedError):
            ensure_patchable(link, NOW)


class TestTypedExceptions:
    def test_link_not_found_carries_token(self):
        err = LinkNotFoundError("ABCDEFG")
        assert err.token == "ABCDEFG"

    def test_link_already_deleted_carries_token(self):
        err = LinkAlreadyDeletedError("XYZ1234")
        assert err.token == "XYZ1234"


class TestSerialization:
    @pytest.mark.parametrize("state,expected", [
        (LinkState.ACTIVE,  "active"),
        (LinkState.EXPIRED, "expired"),
        (LinkState.DELETED, "deleted"),
    ])
    def test_str_value(self, state, expected):
        assert str(state) == expected
        assert state == expected

    def test_json_serializes_to_lowercase_string(self):
        payload = {"status": LinkState.ACTIVE}
        assert json.dumps(payload) == '{"status": "active"}'
