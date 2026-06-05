"""Unit tests for the shared UTC datetime helpers (``backend.timeutil``).

These pin the serialization convention behind beads s4l/8s8: stored datetimes
are naive UTC, and crossing the API wire requires an explicit UTC marker so the
frontend's ``new Date()`` does not parse them as local time and render them off
by the viewer's offset.
"""

from datetime import datetime, timedelta, timezone

from backend.timeutil import iso_utc, now_utc, to_naive_utc


class TestNowUtc:
    def test_returns_naive_datetime(self):
        # The app's storage convention is naive UTC (tzinfo stripped).
        assert now_utc().tzinfo is None


class TestIsoUtc:
    def test_naive_datetime_tagged_as_utc(self):
        # A naive (assumed-UTC) datetime gains an explicit +00:00 offset.
        result = iso_utc(datetime(2026, 6, 5, 14, 0, 0))
        assert result is not None
        assert result.endswith("+00:00")
        assert datetime.fromisoformat(result).utcoffset() == timedelta(0)

    def test_none_passes_through(self):
        assert iso_utc(None) is None

    def test_already_aware_not_double_tagged(self):
        aware = datetime(2026, 6, 5, 14, 0, 0, tzinfo=timezone.utc)
        result = iso_utc(aware)
        # Idempotent: an already-aware UTC datetime keeps a single +00:00.
        assert result.count("+00:00") == 1
        assert datetime.fromisoformat(result) == aware


class TestToNaiveUtc:
    """Inbound mirror of iso_utc: normalize any datetime to naive UTC (bead r5n)."""

    def test_aware_non_utc_converted_then_stripped(self):
        # +08:00 midnight is 16:00 the previous day in UTC — convert, don't drop.
        dt = datetime(2099, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        result = to_naive_utc(dt)
        assert result == datetime(2098, 12, 31, 16, 0, 0)
        assert result.tzinfo is None

    def test_aware_negative_offset_rolls_forward(self):
        # -05:00 rolls the instant forward: 00:00-05:00 is 05:00 the same day UTC.
        dt = datetime(2099, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
        result = to_naive_utc(dt)
        assert result == datetime(2099, 1, 1, 5, 0, 0)
        assert result.tzinfo is None

    def test_aware_utc_stripped_in_place(self):
        dt = datetime(2099, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert to_naive_utc(dt) == datetime(2099, 1, 1, 0, 0, 0)

    def test_naive_assumed_utc_passes_through(self):
        dt = datetime(2099, 1, 1, 0, 0, 0)
        result = to_naive_utc(dt)
        assert result == dt
        assert result.tzinfo is None

    def test_none_passes_through(self):
        assert to_naive_utc(None) is None
