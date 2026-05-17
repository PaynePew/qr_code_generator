"""Unit tests for backend.rate_limiter.ip_extraction.extract_client_ip.

AC coverage:
  - trusted_proxies=0 ignores XFF, returns request.client.host
  - trusted_proxies=1 with a single-untrusted-entry XFF (N+1=2 CSV entries) returns that entry
  - trusted_proxies=1 with multi-hop XFF returns the rightmost-untrusted boundary
  - trusted_proxies=N greater than XFF entry count falls back to request.client.host
  - Missing XFF returns request.client.host
  - Missing both (no XFF, no client) returns None
  - Whitespace around XFF values is stripped
"""
import pytest
from unittest.mock import MagicMock

from backend.rate_limiter.ip_extraction import extract_client_ip


def _req(xff=None, client_host="10.0.0.1"):
    """Build a minimal request-like mock."""
    req = MagicMock()
    if xff is not None:
        req.headers.get.side_effect = lambda key, default=None: xff if key == "x-forwarded-for" else default
    else:
        req.headers.get.return_value = None
    if client_host is not None:
        req.client.host = client_host
    else:
        req.client = None
    return req


class TestTrustedProxiesZero:
    def test_ignores_xff_returns_client_host(self):
        req = _req(xff="1.2.3.4", client_host="192.168.1.1")
        assert extract_client_ip(req, 0) == "192.168.1.1"

    def test_ignores_xff_even_when_xff_present(self):
        req = _req(xff="203.0.113.1, 198.51.100.1", client_host="10.1.2.3")
        assert extract_client_ip(req, 0) == "10.1.2.3"

    def test_returns_none_when_no_client(self):
        req = _req(xff="1.2.3.4", client_host=None)
        assert extract_client_ip(req, 0) is None


class TestTrustedProxiesOne:
    def test_single_untrusted_entry_xff_returns_that_entry(self):
        # XFF has N+1 = 2 entries: "client_ip, proxy_ip".
        # After skipping the 1 trusted proxy entry, one untrusted entry remains.
        req = _req(xff="1.2.3.4, 10.0.0.1", client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "1.2.3.4"

    def test_multi_hop_xff_returns_rightmost_untrusted_boundary(self):
        # XFF = "client, untrusted_proxy, trusted_proxy_entry"
        # With N=1, skip the last entry (added by the 1 trusted hop) and return the one before it.
        req = _req(xff="1.2.3.4, 10.0.0.1, 192.168.1.1", client_host="192.168.1.1")
        assert extract_client_ip(req, 1) == "10.0.0.1"

    def test_xff_shorter_than_n_plus_1_falls_back_to_client_host(self):
        # XFF has only 1 entry but we need >= N+1 = 2 entries: fall back.
        req = _req(xff="1.2.3.4", client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "10.0.0.1"


class TestTrustedProxiesGreaterThanXffLength:
    def test_n_greater_than_xff_length_falls_back(self):
        # N=3, XFF has 2 entries: N > len(entries) → fall back.
        req = _req(xff="1.2.3.4, 10.0.0.1", client_host="192.168.0.1")
        assert extract_client_ip(req, 3) == "192.168.0.1"

    def test_n_equals_xff_length_falls_back(self):
        # N=2, XFF has 2 entries: len == N (< N+1) → fall back.
        req = _req(xff="1.2.3.4, 10.0.0.1", client_host="192.168.0.1")
        assert extract_client_ip(req, 2) == "192.168.0.1"


class TestMissingXff:
    def test_no_xff_header_returns_client_host(self):
        req = _req(xff=None, client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "10.0.0.1"

    def test_no_xff_no_client_returns_none(self):
        req = _req(xff=None, client_host=None)
        assert extract_client_ip(req, 1) is None


class TestMissingBoth:
    def test_no_xff_no_client_returns_none(self):
        req = _req(xff=None, client_host=None)
        assert extract_client_ip(req, 0) is None


class TestWhitespaceAndCasing:
    def test_whitespace_around_xff_entries_stripped(self):
        req = _req(xff="  1.2.3.4  ,  10.0.0.1  ", client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "1.2.3.4"

    def test_extra_whitespace_in_single_entry_stripped(self):
        req = _req(xff="  203.0.113.99  ,  10.10.10.1  ", client_host="10.10.10.1")
        assert extract_client_ip(req, 1) == "203.0.113.99"

    def test_mixed_whitespace_multi_hop(self):
        req = _req(xff=" a , b , c ", client_host="c")
        assert extract_client_ip(req, 1) == "b"

    def test_ipv6_casing_preserved(self):
        # IPv6 addresses may use upper or lower hex; the value is returned as-is.
        req = _req(xff="::1, 2001:DB8::1", client_host="2001:DB8::1")
        assert extract_client_ip(req, 1) == "::1"
