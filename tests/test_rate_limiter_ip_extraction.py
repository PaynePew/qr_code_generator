"""Unit tests for backend.rate_limiter.ip_extraction.extract_client_ip.

Model (de-facto X-Forwarded-For): each trusted reverse proxy appends the address
it received the request FROM (its upstream), NOT its own address. So with N
trusted proxies the real client is the Nth entry from the right (``entries[-N]``);
entries further left are client-supplied and untrusted. trusted_proxies=0 ignores
XFF entirely and uses the socket peer.

This deployment runs one edge Caddy (N=1), which sets XFF to the real client IP
(a single entry) → client = entries[-1].
"""

from unittest.mock import MagicMock

from backend.rate_limiter.ip_extraction import extract_client_ip


def _req(xff=None, client_host="10.0.0.1"):
    """Build a minimal request-like mock."""
    req = MagicMock()
    if xff is not None:
        req.headers.get.side_effect = lambda key, default=None: (
            xff if key == "x-forwarded-for" else default
        )
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
    def test_single_entry_xff_is_the_client(self):
        # One edge Caddy sets XFF to the real client IP (one entry).
        req = _req(xff="1.2.3.4", client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "1.2.3.4"

    def test_spoofed_left_entry_ignored_rightmost_is_trusted(self):
        # Client spoofs "9.9.9.9"; Caddy appends the real peer "1.2.3.4". With
        # N=1 the trusted client is the rightmost entry; the spoof is ignored.
        req = _req(xff="9.9.9.9, 1.2.3.4", client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "1.2.3.4"

    def test_no_xff_falls_back_to_client_host(self):
        req = _req(xff=None, client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "10.0.0.1"


class TestTrustedProxiesTwo:
    def test_two_hops_client_is_second_from_right(self):
        # client -> outer LB (appends client) -> Caddy (appends LB) -> app
        req = _req(xff="1.2.3.4, 172.16.0.9", client_host="10.0.0.1")
        assert extract_client_ip(req, 2) == "1.2.3.4"

    def test_spoof_with_two_hops_ignored(self):
        # Client spoofs "9.9.9.9"; after 2 hops XFF = [spoof, client, LB].
        req = _req(xff="9.9.9.9, 1.2.3.4, 172.16.0.9", client_host="10.0.0.1")
        assert extract_client_ip(req, 2) == "1.2.3.4"


class TestXffShorterThanN:
    def test_fewer_entries_than_n_falls_back(self):
        # N=3 but XFF has 2 entries → cannot identify the trusted client → fall back.
        req = _req(xff="1.2.3.4, 10.0.0.1", client_host="192.168.0.1")
        assert extract_client_ip(req, 3) == "192.168.0.1"


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
    def test_whitespace_around_single_entry_stripped(self):
        req = _req(xff="  1.2.3.4  ", client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "1.2.3.4"

    def test_mixed_whitespace_multi_hop(self):
        req = _req(xff=" a , b ", client_host="c")
        assert extract_client_ip(req, 2) == "a"

    def test_ipv6_casing_preserved(self):
        # IPv6 addresses may use upper or lower hex; the value is returned as-is.
        req = _req(xff="2001:DB8::1", client_host="10.0.0.1")
        assert extract_client_ip(req, 1) == "2001:DB8::1"
