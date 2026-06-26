from __future__ import annotations

from starlette.requests import Request


def _client_host(request: Request) -> str | None:
    return request.client.host if request.client else None


def extract_client_ip(request: Request, trusted_proxies: int) -> str | None:
    """Return the best-guess client IP for *request*.

    trusted_proxies=0  → ignore X-Forwarded-For, use request.client.host (the
                         socket peer).
    trusted_proxies=N  → trust the rightmost N entries of X-Forwarded-For, set by
                         our own N reverse proxies. Per the de-facto XFF contract
                         each proxy appends the address it RECEIVED THE REQUEST
                         FROM (its upstream) — NOT its own address — so after N
                         trusted hops the real client is the Nth entry from the
                         right (``entries[-N]``). Anything further LEFT is
                         client-supplied and untrusted (XFF-spoofing guard). Falls
                         back to request.client.host when XFF is absent or has
                         fewer than N entries.

    Example — this deployment runs one edge Caddy in front of the app (N=1):
    Caddy sets XFF to the real client IP (a single entry), so the client is
    ``entries[-1]``. (The earlier ``-(N+1)`` form assumed each proxy appended its
    OWN address, which Caddy does not — that off-by-one made every request resolve
    to the private Caddy container IP: NULL geo + one shared rate-limit bucket.)

    Returns None only when neither XFF nor request.client yields an address.
    """
    if trusted_proxies == 0:
        return _client_host(request)

    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return _client_host(request)

    entries = [e.strip() for e in xff.split(",") if e.strip()]
    if len(entries) >= trusted_proxies:
        return entries[-trusted_proxies]

    return _client_host(request)
