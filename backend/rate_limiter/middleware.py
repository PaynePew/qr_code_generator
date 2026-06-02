import logging
import os
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .ip_extraction import extract_client_ip
from .limiter import CheckResult, RateLimiter

logger = logging.getLogger(__name__)

_TARGET_PATH = "/api/qr/create"
_TARGET_METHOD = "POST"

_limiter: Optional[RateLimiter] = None


def _get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        hourly = int(os.environ.get("RATE_LIMIT_HOURLY", "30"))
        daily = int(os.environ.get("RATE_LIMIT_DAILY", "200"))
        _limiter = RateLimiter(hourly_limit=hourly, daily_limit=daily)
    return _limiter


def _is_enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"


def _ratelimit_headers(result: CheckResult) -> dict[str, str]:
    return {
        "RateLimit-Limit": str(result.limit),
        "RateLimit-Remaining": str(result.remaining),
        "RateLimit-Reset": str(result.reset_seconds),
        "RateLimit-Policy": result.policy,
    }


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != _TARGET_METHOD or request.url.path != _TARGET_PATH:
            return await call_next(request)

        if not _is_enabled():
            return await call_next(request)

        trusted_proxies = int(os.environ.get("TRUSTED_PROXIES", "0"))
        ip = extract_client_ip(request, trusted_proxies) or "unknown"
        try:
            result = _get_limiter().check(ip)
        except Exception:
            logger.error("RateLimiter.check raised an exception", exc_info=True)
            return await call_next(request)

        if not result.allowed:
            _get_limiter().log_denied(
                ip, result.deny_bucket, result.limit, result.retry_after_seconds, _TARGET_PATH
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
    def reset_for_tests(cls):
        global _limiter
        _limiter = None
