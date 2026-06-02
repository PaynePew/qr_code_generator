from __future__ import annotations

from starlette.requests import Request


def _client_host(request: Request) -> str | None:
    return request.client.host if request.client else None


def extract_client_ip(request: Request, trusted_proxies: int) -> str | None:
    """Return the best-guess client IP for *request*.

    trusted_proxies=0  → ignore X-Forwarded-For, use request.client.host.
    trusted_proxies=N  → take XFF entry at position -(N+1) from the right
                         (one hop left of the N trusted proxy entries at the end).
                         Falls back to request.client.host when XFF is absent or
                         has fewer than N+1 entries.
    Returns None only when neither XFF nor request.client yields an address.
    """
    if trusted_proxies == 0:
        return _client_host(request)

    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return _client_host(request)

    entries = [e.strip() for e in xff.split(",") if e.strip()]
    if len(entries) >= trusted_proxies + 1:
        return entries[-(trusted_proxies + 1)]

    return _client_host(request)
