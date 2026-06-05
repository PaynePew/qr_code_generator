"""Shared UTC datetime helpers.

The app stores datetimes as naive UTC (``now_utc`` strips tzinfo). Serializing
them needs an explicit UTC marker: a bare ``isoformat()`` on a naive value emits
no offset, so the frontend's ``new Date()`` parses it as *local* time and
renders it off by the viewer's UTC offset (beads s4l, 8s8). This is the single
home for that convention so router and analytics serialize identically.
"""

from datetime import datetime, timezone
from typing import Optional


def now_utc() -> datetime:
    """Current time as a naive-UTC datetime (the app's storage convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """Serialize a stored (naive-UTC) datetime as a tz-qualified ISO string.

    Tags a naive value as UTC; ``None`` passes through; an already-aware value
    is left untouched (idempotent).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize an inbound datetime to naive UTC (the storage convention).

    The inbound mirror of ``iso_utc``: a tz-aware value is converted to UTC
    before its tzinfo is stripped — NOT dropped, since dropping an offset would
    store the wrong instant (bead r5n). A naive value is assumed already-UTC and
    passes through; ``None`` passes through.
    """
    if dt is None:
        return None
    # Guard the astimezone: on a naive value it would assume system-local time.
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)
