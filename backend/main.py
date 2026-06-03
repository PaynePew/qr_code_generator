import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth_router import auth_router
from .authorization import DemoReadOnlyError
from .link_state import LinkAlreadyDeletedError, LinkNotFoundError
from .router import router, redirect_router
from .rate_limiter.middleware import RateLimitMiddleware

_logger = logging.getLogger(__name__)

load_dotenv()


def _parse_bool(val: str, name: str) -> bool:
    if val.lower() not in ("true", "false"):
        raise RuntimeError(f"{name} must be 'true' or 'false', got: {val!r}")
    return val.lower() == "true"


def _parse_positive_int(val: str, name: str) -> int:
    try:
        n = int(val)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got: {val!r}")
    if n <= 0:
        raise RuntimeError(f"{name} must be a positive integer, got: {n}")
    return n


def _parse_non_negative_int(val: str, name: str) -> int:
    try:
        n = int(val)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got: {val!r}")
    if n < 0:
        raise RuntimeError(f"{name} must be a non-negative integer, got: {n}")
    return n


def _detect_worker_count() -> int:
    """Best-effort worker count from well-known environment variables."""
    for var in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        val = os.environ.get(var, "").strip()
        if val:
            try:
                n = int(val)
                if n > 0:
                    return n
            except ValueError:
                pass
    return 1


def _maybe_warn_multi_worker() -> None:
    """Emit a WARNING if the environment suggests more than one worker process."""
    workers = _detect_worker_count()
    if workers > 1:
        _logger.warning(
            "In-memory rate limiter is per-process: %d workers detected means the "
            "effective per-IP limit is %d× the configured value. Replace the storage "
            "layer before using multi-worker deploys (see ADR 0007).",
            workers,
            workers,
        )


def _validate_window_pair(hourly_var: str, hourly_default: str, daily_var: str, daily_default: str):
    """Validate one hourly/daily limiter pair: positive ints with daily >= hourly."""
    hourly = _parse_positive_int(os.environ.get(hourly_var, hourly_default), hourly_var)
    daily = _parse_positive_int(os.environ.get(daily_var, daily_default), daily_var)
    if daily < hourly:
        raise RuntimeError(f"{daily_var} ({daily}) must be >= {hourly_var} ({hourly})")


def _validate_rate_limit_env():
    _parse_bool(os.environ.get("RATE_LIMIT_ENABLED", "true"), "RATE_LIMIT_ENABLED")
    # Per-user create limiter.
    _validate_window_pair("RATE_LIMIT_HOURLY", "30", "RATE_LIMIT_DAILY", "200")
    # Per-IP auth-endpoint limiter (account-farming guard, ADR 0009). Same
    # env-driven, validated-at-startup contract as the create limiter.
    _validate_window_pair("AUTH_RATE_LIMIT_HOURLY", "10", "AUTH_RATE_LIMIT_DAILY", "40")


def _validate_trusted_proxies_env():
    _parse_non_negative_int(os.environ.get("TRUSTED_PROXIES", "0"), "TRUSTED_PROXIES")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("SECRET"):
        raise RuntimeError("SECRET environment variable must be set")
    if not os.environ.get("BASE_URL"):
        raise RuntimeError("BASE_URL environment variable must be set")
    _validate_rate_limit_env()
    _validate_trusted_proxies_env()
    _maybe_warn_multi_worker()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
# Credentialed CORS (cookies must flow) forbids wildcard methods/headers — they
# must be enumerated (ADR 0009). Same-origin prod needs no CORS; this serves the
# dev Vite origin only.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://localhost:\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(LinkNotFoundError)
async def _link_not_found(_: Request, exc: LinkNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Token not found"})


@app.exception_handler(LinkAlreadyDeletedError)
async def _link_already_deleted(_: Request, exc: LinkAlreadyDeletedError) -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": "Link is deleted"})


@app.exception_handler(DemoReadOnlyError)
async def _demo_read_only(_: Request, exc: DemoReadOnlyError) -> JSONResponse:
    # ADR 0009: the read-only demo account hit a mutation. The body carries a
    # distinct `code` so the frontend renders a "log in to create" nudge instead
    # of a generic error (it cannot infer demo-ness from the 403 alone).
    return JSONResponse(
        status_code=403,
        content={"detail": "Demo account is read-only", "code": "DEMO_READ_ONLY"},
    )


app.include_router(auth_router)
app.include_router(router)
app.include_router(redirect_router)
