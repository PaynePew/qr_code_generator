import pytest
from backend.url_validator import validate_and_normalize, InvalidURLError


class TestNormalization:
    def test_coerces_http_to_https(self):
        result = validate_and_normalize("http://example.com/path")
        assert result.startswith("https://")

    def test_lowercases_host(self):
        result = validate_and_normalize("https://EXAMPLE.COM/path")
        assert "example.com" in result

    def test_removes_default_port_443(self):
        result = validate_and_normalize("https://example.com:443/path")
        assert ":443" not in result

    def test_removes_default_port_80(self):
        result = validate_and_normalize("http://example.com:80/path")
        assert ":80" not in result

    def test_keeps_non_default_port(self):
        result = validate_and_normalize("https://example.com:8080/path")
        assert ":8080" in result

    def test_removes_trailing_slash_from_path(self):
        result = validate_and_normalize("https://example.com/path/")
        assert result == "https://example.com/path"

    def test_keeps_root_slash(self):
        result = validate_and_normalize("https://example.com/")
        assert result == "https://example.com/"

    def test_adds_root_slash_when_no_path(self):
        result = validate_and_normalize("https://example.com")
        assert result == "https://example.com/"

    def test_sorts_query_params(self):
        result = validate_and_normalize("https://example.com/?z=1&a=2&m=3")
        assert result == "https://example.com/?a=2&m=3&z=1"

    def test_all_normalizations_combined(self):
        result = validate_and_normalize("http://EXAMPLE.COM:80/PATH/?z=last&a=first")
        assert result == "https://example.com/PATH?a=first&z=last"


class TestValidURLs:
    def test_valid_https_url(self):
        result = validate_and_normalize("https://example.com/page")
        assert result == "https://example.com/page"

    def test_valid_http_url(self):
        result = validate_and_normalize("http://example.com/page")
        assert result == "https://example.com/page"

    def test_url_with_query_string(self):
        result = validate_and_normalize("https://example.com/search?q=hello")
        assert "q=hello" in result


class TestBlockedSchemes:
    def test_rejects_javascript_scheme(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("javascript:alert(1)")

    def test_rejects_file_scheme(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("file:///etc/passwd")

    def test_rejects_data_scheme(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("data:text/html,<h1>hi</h1>")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("ftp://example.com/file.txt")


class TestBlockedIPs:
    def test_rejects_localhost(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("https://localhost/admin")

    def test_rejects_loopback_127(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("https://127.0.0.1/admin")

    def test_rejects_private_10_range(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("https://10.0.0.1/internal")

    def test_rejects_private_192_168_range(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("https://192.168.1.1/router")

    def test_rejects_private_172_16_range(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("https://172.16.0.1/internal")

    def test_rejects_link_local_169_254(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("https://169.254.169.254/metadata")

    def test_rejects_ipv6_loopback(self):
        with pytest.raises(InvalidURLError):
            validate_and_normalize("https://[::1]/admin")
