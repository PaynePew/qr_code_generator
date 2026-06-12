"""scan_derivation — the single place that touches raw IP and User-Agent.

This is a **deep module** (ADR 0016 / privacy-by-construction). It derives
coarse, non-identifying attributes from raw scanner inputs and discards the
raw values; neither the IP nor the User-Agent string is ever returned or
stored by functions in this module.

Public surface:
    derive_geo(ip)          -> (country: str | None, subdivision: str | None)
    derive_device_class(ua) -> str

Privacy guarantees enforced structurally:
- ``derive_geo`` returns only (country_iso2, subdivision_iso) — city, lat/long
  and the IP itself are read internally but never returned (ADR 0016 amendment
  2026-06-12: city derived-and-discarded, subdivision kept).
- ``derive_device_class`` returns one of five coarse labels — the raw UA string
  is never returned.
- This module never imports from the HTTP layer (no FastAPI / Starlette).
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GeoIP — country + subdivision (city discarded)
# ---------------------------------------------------------------------------

_GEOIP_READER = None
_GEOIP_TRIED = False


def _get_geoip_reader():
    """Return a cached geoip2 Reader, or None if unavailable.

    Opened lazily on first call; errors are logged and the module degrades
    gracefully (returns None for all geo fields) so a missing .mmdb never
    takes down the redirect path.
    """
    global _GEOIP_READER, _GEOIP_TRIED
    if _GEOIP_TRIED:
        return _GEOIP_READER
    _GEOIP_TRIED = True

    db_path = os.environ.get("GEOIP_DB_PATH", "").strip()
    if not db_path:
        logger.warning(
            "scan_derivation: GEOIP_DB_PATH not set — geo fields will be NULL"
        )
        return None

    try:
        import geoip2.database  # noqa: PLC0415

        _GEOIP_READER = geoip2.database.Reader(db_path)
        logger.info("scan_derivation: GeoLite2-City reader opened from %s", db_path)
    except Exception:
        logger.exception(
            "scan_derivation: failed to open GeoLite2-City DB at %s — "
            "geo fields will be NULL",
            db_path,
        )
    return _GEOIP_READER


def derive_geo(ip: str | None) -> tuple[str | None, str | None]:
    """Derive (country_iso2, subdivision_iso) from a raw IP address.

    The raw IP is used only inside this function and is never returned.
    City, lat/long, and all other GeoLite2 fields are discarded (ADR 0016
    amendment: city is derived-and-discarded, not stored).

    Returns (None, None) when:
    - ``ip`` is None or empty,
    - GEOIP_DB_PATH is not set,
    - the IP is private / unroutable and not in the database,
    - any lookup error occurs.
    """
    if not ip:
        return None, None

    reader = _get_geoip_reader()
    if reader is None:
        return None, None

    try:
        record = reader.city(ip)
        country: str | None = record.country.iso_code or None
        # most_specific is the first (and for most countries only) subdivision.
        subdivision: str | None = None
        if record.subdivisions and record.subdivisions.most_specific.iso_code:
            subdivision = record.subdivisions.most_specific.iso_code
        # city / lat / long intentionally not read — derive-then-discard (ADR 0016).
        return country, subdivision
    except Exception:
        # AddressNotFoundError, ValueError for invalid IP, etc.
        return None, None


# ---------------------------------------------------------------------------
# Device class — coarse UA classification (no raw UA returned)
# ---------------------------------------------------------------------------

_BOT_PATTERN = re.compile(
    r"(bot|crawl|spider|slurp|mediapartners|adsbot|facebot|bingpreview"
    r"|google-read|applebot|yandex|baidu|duckduck|archive\.org_bot"
    r"|semrush|ahrefsbot|mj12bot|dotbot|blexbot|sogou|exabot|ia_archiver)",
    re.IGNORECASE,
)
_MOBILE_PATTERN = re.compile(
    r"(mobile|android(?!.*tablet)|iphone|ipod|blackberry|windows phone"
    r"|opera mini|opera mobi|iemobile|wpdesktop|symbian|nokia|samsung"
    r"|xiaomi|oppo|vivo|huawei|htc|lg|motorola|palm|kindle(?!.*fire hd))",
    re.IGNORECASE,
)
_TABLET_PATTERN = re.compile(
    r"(tablet|ipad|kindle|silk|playbook|nexus 7|nexus 10|gt-p|sm-t"
    r"|surface|kfthwi|kfjwi|kftt|kfot|kfsowi|xoom)",
    re.IGNORECASE,
)


def derive_device_class(user_agent: str | None) -> str:
    """Classify a raw User-Agent string into one of five coarse labels.

    Labels: "bot" | "mobile" | "tablet" | "desktop" | "unknown"

    The raw ``user_agent`` string is consumed and discarded inside this function;
    only the label is returned (ADR 0016: raw UA never stored).

    ``None`` or empty UA → "unknown".
    """
    if not user_agent:
        return "unknown"

    ua = user_agent.strip()
    if not ua:
        return "unknown"

    if _BOT_PATTERN.search(ua):
        return "bot"
    if _TABLET_PATTERN.search(ua):
        return "tablet"
    if _MOBILE_PATTERN.search(ua):
        return "mobile"
    # Any non-empty, non-bot, non-mobile, non-tablet UA is assumed desktop.
    return "desktop"


# ---------------------------------------------------------------------------
# Test-seam: allow tests to reset the lazy reader (e.g. to inject a fake path)
# ---------------------------------------------------------------------------


def _reset_reader_for_tests() -> None:
    """Reset the module-level reader state so tests can inject GEOIP_DB_PATH."""
    global _GEOIP_READER, _GEOIP_TRIED
    _GEOIP_READER = None
    _GEOIP_TRIED = False
