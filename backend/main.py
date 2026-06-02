import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import engine
from .link_state import LinkAlreadyDeletedError, LinkNotFoundError
from .models import Base
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


def _validate_rate_limit_env():
    _parse_bool(os.environ.get("RATE_LIMIT_ENABLED", "true"), "RATE_LIMIT_ENABLED")
    hourly = _parse_positive_int(os.environ.get("RATE_LIMIT_HOURLY", "30"), "RATE_LIMIT_HOURLY")
    daily = _parse_positive_int(os.environ.get("RATE_LIMIT_DAILY", "200"), "RATE_LIMIT_DAILY")
    if daily < hourly:
        raise RuntimeError(
            f"RATE_LIMIT_DAILY ({daily}) must be >= RATE_LIMIT_HOURLY ({hourly})"
        )


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
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LinkNotFoundError)
async def _link_not_found(_: Request, exc: LinkNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Token not found"})


@app.exception_handler(LinkAlreadyDeletedError)
async def _link_already_deleted(_: Request, exc: LinkAlreadyDeletedError) -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": "Link is deleted"})


app.include_router(router)
app.include_router(redirect_router)
