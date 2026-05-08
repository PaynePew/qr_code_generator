import ipaddress
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse


class InvalidURLError(ValueError):
    pass


def validate_and_normalize(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidURLError(f"Malformed URL: {e}")

    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError(f"Non-http(s) scheme rejected: {parsed.scheme!r}")

    host = parsed.hostname or ""
    if not host:
        raise InvalidURLError("URL must have a host")

    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise InvalidURLError("Loopback address rejected")

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None  # Not an IP address — fine

    if addr is not None and (addr.is_loopback or addr.is_private or addr.is_link_local):
        raise InvalidURLError(f"Private/loopback IP rejected: {host}")

    scheme = "https"
    host_lower = host.lower()

    port = parsed.port
    if port in (80, 443):
        port = None

    if port:
        netloc = f"{host_lower}:{port}"
    else:
        netloc = host_lower

    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        netloc = f"{userinfo}@{netloc}"

    path = parsed.path
    if not path:
        path = "/"
    elif path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query_params = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    query = urlencode(query_params)

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))
