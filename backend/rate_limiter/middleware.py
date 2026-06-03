"""Rate-limit middleware: per-user create cap + per-IP auth-endpoint guard.

ADR 0009 re-architecture (partially reverses ADR 0007): anonymous create no
longer exists, so ``POST /api/qr/create`` is limited per **user** — a generous
per-account quota — while the per-IP limiter relocates to guard the auth
endpoint (``POST /api/auth/session``) against account-farming.

Two independent limiters back the two rules. The shared engine
(:class:`RateLimiter`) is keyed by an opaque string, so the create rule keys by
``user:<id>`` (read from the session cookie, the same id the auth dependency
would resolve) and the auth rule keys by client IP. An unauthenticated create is
*not* rate-limited here — it carries no user key — because the route's
``get_current_user`` rejects it with 401 anyway, and account-farming is capped at
the auth endpoint rather than on create.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .. import session as session_module
from .ip_extraction import extract_client_ip
from .limiter import CheckResult, RateLimiter

logger = logging.getLogger(__name__)

_CREATE_PATH = "/api/qr/create"
_AUTH_PATH = "/api/auth/session"

# Per-user create limiter. The IP limiter relocated to the auth endpoint, so
# these env vars now govern a per-account quota (defaults unchanged from the
# former per-IP create limits — they read as a generous per-user ceiling).
_create_limiter: RateLimiter | None = None
# Per-IP auth-endpoint limiter (account-farming guard). Tighter defaults than
# create: a real person signs in a handful of times an hour, never dozens.
_auth_limiter: RateLimiter | None = None


def _get_create_limiter() -> RateLimiter:
    global _create_limiter
    if _create_limiter is None:
        hourly = int(os.environ.get("RATE_LIMIT_HOURLY", "30"))
        daily = int(os.environ.get("RATE_LIMIT_DAILY", "200"))
        _create_limiter = RateLimiter(hourly_limit=hourly, daily_limit=daily)
    return _create_limiter


def _get_auth_limiter() -> RateLimiter:
    global _auth_limiter
    if _auth_limiter is None:
        hourly = int(os.environ.get("AUTH_RATE_LIMIT_HOURLY", "10"))
        daily = int(os.environ.get("AUTH_RATE_LIMIT_DAILY", "40"))
        _auth_limiter = RateLimiter(hourly_limit=hourly, daily_limit=daily)
    return _auth_limiter


def _is_enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"


def _client_ip(request: Request) -> str:
    trusted_proxies = int(os.environ.get("TRUSTED_PROXIES", "0"))
    return extract_client_ip(request, trusted_proxies) or "unknown"


def _ratelimit_headers(result: CheckResult) -> dict[str, str]:
    return {
        "RateLimit-Limit": str(result.limit),
        "RateLimit-Remaining": str(result.remaining),
        "RateLimit-Reset": str(result.reset_seconds),
        "RateLimit-Policy": result.policy,
    }


@dataclass(frozen=True)
class _Rule:
    """A rate-limited (method, path) and how to key + which limiter to use."""

    method: str
    path: str
    limiter: Callable[[], RateLimiter]
    # Returns the bucket key, or None to skip limiting this request entirely.
    key_for: Callable[[Request], str | None]


def _create_key(request: Request) -> str | None:
    """Key the create cap by the authenticated user.

    Resolves the same User id ``get_current_user`` would from the session cookie.
    Returns None for an unauthenticated request so it is not limited here — the
    route's ``get_current_user`` will 401 it, and account-farming is guarded at
    the auth endpoint, not on create.
    """
    config = session_module.SessionConfig()
    raw_cookie = request.cookies.get(session_module.COOKIE_NAME, "")
    user_id = session_module.read_session(raw_cookie, config)
    return f"user:{user_id}" if user_id is not None else None


def _auth_key(request: Request) -> str | None:
    """Key the auth-endpoint cap by client IP (account-farming guard)."""
    return _client_ip(request)


_RULES: tuple[_Rule, ...] = (
    _Rule(method="POST", path=_CREATE_PATH, limiter=_get_create_limiter, key_for=_create_key),
    _Rule(method="POST", path=_AUTH_PATH, limiter=_get_auth_limiter, key_for=_auth_key),
)


def _match_rule(request: Request) -> _Rule | None:
    for rule in _RULES:
        if request.method == rule.method and request.url.path == rule.path:
            return rule
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rule = _match_rule(request)
        if rule is None or not _is_enabled():
            return await call_next(request)

        key = rule.key_for(request)
        if key is None:
            # Nothing to key on (e.g. unauthenticated create) — let the route decide.
            return await call_next(request)

        limiter = rule.limiter()
        try:
            result = limiter.check(key)
        except Exception:
            logger.error("RateLimiter.check raised an exception", exc_info=True)
            return await call_next(request)

        if not result.allowed:
            limiter.log_denied(
                key, result.deny_bucket, result.limit, result.retry_after_seconds, rule.path
            )
            return JSONResponse(
                content={"detail": "Rate limit exceeded"},
                status_code=429,
                headers={
                    **_ratelimit_headers(result),
                    "Retry-After": str(result.retry_after_seconds),
                },
            )

        response = await call_next(request)
        for name, value in _ratelimit_headers(result).items():
            response.headers[name] = value
        return response

    @classmethod
    def reset_for_tests(cls) -> None:
        global _create_limiter, _auth_limiter
        _create_limiter = None
        _auth_limiter = None
