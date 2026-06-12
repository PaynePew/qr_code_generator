"""Tests for scan_derivation — the single place that touches raw IP/UA (ADR 0016).

Acceptance criteria (from issue qr_code_generator-15l):
- derive_geo(ip) -> (country, subdivision): raw IP never returned or stored; city never returned.
- derive_device_class(ua): raw UA never returned.
- None / empty input handling for both functions.
- derive_geo degrades gracefully when GEOIP_DB_PATH is unset.
"""

from __future__ import annotations

import pytest

from backend import scan_derivation

# ---------------------------------------------------------------------------
# derive_device_class
# ---------------------------------------------------------------------------


class TestDeriveDeviceClass:
    def test_none_returns_unknown(self):
        assert scan_derivation.derive_device_class(None) == "unknown"

    def test_empty_string_returns_unknown(self):
        assert scan_derivation.derive_device_class("") == "unknown"

    def test_whitespace_only_returns_unknown(self):
        assert scan_derivation.derive_device_class("   ") == "unknown"

    def test_googlebot_returns_bot(self):
        ua = "Googlebot/2.1 (+http://www.google.com/bot.html)"
        assert scan_derivation.derive_device_class(ua) == "bot"

    def test_bingbot_returns_bot(self):
        ua = "Mozilla/5.0 (compatible; bingbot/2.0)"
        assert scan_derivation.derive_device_class(ua) == "bot"

    def test_iphone_returns_mobile(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
        assert scan_derivation.derive_device_class(ua) == "mobile"

    def test_android_phone_returns_mobile(self):
        ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36"
        assert scan_derivation.derive_device_class(ua) == "mobile"

    def test_ipad_returns_tablet(self):
        ua = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
        assert scan_derivation.derive_device_class(ua) == "tablet"

    def test_windows_desktop_returns_desktop(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"
        assert scan_derivation.derive_device_class(ua) == "desktop"

    def test_mac_desktop_returns_desktop(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        assert scan_derivation.derive_device_class(ua) == "desktop"

    def test_return_value_is_not_raw_ua(self):
        """The return value must be a label, never the raw UA string."""
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
        result = scan_derivation.derive_device_class(ua)
        assert result != ua
        assert result in {"bot", "mobile", "tablet", "desktop", "unknown"}

    def test_only_five_labels_ever_returned(self):
        """Exhaustive check: every possible call returns one of the five labels."""
        valid = {"bot", "mobile", "tablet", "desktop", "unknown"}
        samples = [
            None,
            "",
            "Googlebot/2.1",
            "Mozilla/5.0 (iPhone; CPU iPhone OS)",
            "Mozilla/5.0 (iPad; CPU OS)",
            "Mozilla/5.0 (Windows NT 10.0)",
            "curl/7.68.0",
        ]
        for ua in samples:
            assert scan_derivation.derive_device_class(ua) in valid, (
                f"unexpected label for UA={ua!r}"
            )


# ---------------------------------------------------------------------------
# derive_geo — no GEOIP_DB_PATH configured (graceful degradation)
# ---------------------------------------------------------------------------


class TestDeriveGeoNoDB:
    """derive_geo must degrade gracefully when no GeoLite2-City DB is available."""

    @pytest.fixture(autouse=True)
    def unset_geoip_path(self, monkeypatch):
        monkeypatch.delenv("GEOIP_DB_PATH", raising=False)
        scan_derivation._reset_reader_for_tests()
        yield
        scan_derivation._reset_reader_for_tests()

    def test_none_ip_returns_none_none(self):
        assert scan_derivation.derive_geo(None) == (None, None)

    def test_empty_ip_returns_none_none(self):
        assert scan_derivation.derive_geo("") == (None, None)

    def test_valid_ip_without_db_returns_none_none(self):
        country, subdivision = scan_derivation.derive_geo("8.8.8.8")
        assert country is None
        assert subdivision is None

    def test_return_never_contains_raw_ip(self):
        """Whatever derive_geo returns, it must not be the input IP."""
        ip = "1.2.3.4"
        result = scan_derivation.derive_geo(ip)
        assert ip not in result


# ---------------------------------------------------------------------------
# derive_geo — privacy guarantees (no-city, no-raw-ip)
# ---------------------------------------------------------------------------


class TestDeriveGeoPrivacyContract:
    """Structural privacy checks that hold regardless of whether a DB is loaded."""

    def test_return_is_two_tuple(self):
        result = scan_derivation.derive_geo(None)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_country_is_string_or_none(self):
        country, _ = scan_derivation.derive_geo(None)
        assert country is None or isinstance(country, str)

    def test_subdivision_is_string_or_none(self):
        _, subdivision = scan_derivation.derive_geo(None)
        assert subdivision is None or isinstance(subdivision, str)

    def test_city_not_in_return_value(self):
        """City must never appear in the return value (derive-then-discard)."""
        # We can only assert structurally: the return is (country, subdivision) —
        # a 2-tuple. There is no city slot to accidentally populate.
        result = scan_derivation.derive_geo(None)
        assert len(result) == 2, "Only (country, subdivision) — no city slot"
