"""API timestamps cross the wire with a UTC marker — endpoint guards (bead s4l).

Stored datetimes are naive UTC (``router.now_utc`` strips tzinfo). Serializing
them with a bare ``.isoformat()`` emits no ``Z``/offset, so the frontend's
``new Date()`` parses them as *local* time -> off by the viewer's UTC offset
(~8h for the UTC+8 reporter). The fix tags every outgoing timestamp as UTC via
``timeutil.iso_utc``.

The ``iso_utc`` unit tests live in test_timeutil.py; this module guards the
router endpoints (info/list). The customization ``updated_at`` is guarded in
test_customization.py; analytics ``scanned_at`` in test_analytics_aggregate.py.
"""

from datetime import datetime


def _is_tz_aware_iso(value: str) -> bool:
    """A serialized timestamp string parses back to a tz-aware datetime."""
    return datetime.fromisoformat(value).tzinfo is not None


class TestEndpointTimestampsCarryUtcMarker:
    def test_info_payload_timestamps_are_tz_aware(self, auth_client):
        # GET /api/qr/{token} returns the full _link_response (create itself
        # returns no timestamps). Covers all three datetime fields incl.
        # expires_at.
        token = auth_client.post(
            "/api/qr/create",
            json={"url": "https://example.com/tz", "expires_at": "2099-01-01T00:00:00"},
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}").json()
        assert _is_tz_aware_iso(data["created_at"])
        assert _is_tz_aware_iso(data["updated_at"])
        assert _is_tz_aware_iso(data["expires_at"])

    def test_list_payload_created_at_is_tz_aware(self, auth_client):
        auth_client.post("/api/qr/create", json={"url": "https://example.com/tz3"})
        item = auth_client.get("/api/qr").json()["items"][0]
        assert _is_tz_aware_iso(item["created_at"])


class TestExpiresAtInputNormalizedToUtc:
    def test_offset_bearing_expires_at_converted_not_dropped(self, auth_client):
        # bead r5n: an offset-bearing expires_at must be CONVERTED to UTC, not
        # have its offset silently dropped. 2099-01-01T00:00:00+08:00 is the
        # prior day 16:00Z.
        token = auth_client.post(
            "/api/qr/create",
            json={
                "url": "https://example.com/tzin",
                "expires_at": "2099-01-01T00:00:00+08:00",
            },
        ).json()["token"]
        data = auth_client.get(f"/api/qr/{token}").json()
        assert data["expires_at"] == "2098-12-31T16:00:00+00:00"
