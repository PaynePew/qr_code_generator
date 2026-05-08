import json
from datetime import datetime, timedelta

import pytest

from backend.link_state import LinkState, derive_state
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
