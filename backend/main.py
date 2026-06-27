from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware, correlation_id
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# Load .env BEFORE importing backend modules that read env vars at import time:
# database.py builds the SQLAlchemy engine from DATABASE_URL on import, and the
# session/auth layer reads SECRET. If load_dotenv() runs AFTER these imports (as
# it used to), `uvicorn backend.main:app` from a shell that has not exported the
# vars falls back to the password-less DB default ("postgresql://localhost/...")
# and every DB-backed request 500s with "no password supplied". Prod is immune
# (Docker injects env via env_file), so this only ever bit local dev.
load_dotenv()

from . import router as _router_module  # noqa: E402
from .auth_router import auth_router  # noqa: E402
from .errors import AppError, ErrorCode  # noqa: E402
from .logging_config import configure_logging  # noqa: E402
from .rate_limiter.middleware import RateLimitMiddleware  # noqa: E402
from .router import build_storage_gateway, redirect_router, router  # noqa: E402
from .storage import S3Gateway  # noqa: E402

_logger = logging.getLogger(__name__)

configure_logging()


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


def _validate_window_pair(
    hourly_var: str, hourly_default: str, daily_var: str, daily_default: str
):
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

    # Env-driven gateway selection (ADR 0011): replace the module-level default
    # with S3Gateway when AWS_S3_BUCKET + AWS_REGION are set, else the dev
    # LocalDiskGateway (on-disk, no AWS). build_storage_gateway raises
    # RuntimeError on misconfiguration so the app refuses to start rather than
    # silently using local storage in prod.
    gateway = build_storage_gateway(dict(os.environ))
    _router_module._storage_gateway = gateway
    if isinstance(gateway, S3Gateway):
        _logger.info(
            "Storage gateway: S3Gateway (bucket=%s, region=%s)",
            os.environ.get("AWS_S3_BUCKET"),
            os.environ.get("AWS_REGION"),
        )
    else:
        _logger.info(
            "Storage gateway: %s (no AWS_S3_BUCKET configured)",
            type(gateway).__name__,
        )

    yield


def _error_body(
    code: ErrorCode | str, message: str, details: dict | None = None
) -> dict:
    """Build the unified error envelope body (ADR 0012)."""
    return {"error": {"code": str(code), "message": message, "details": details or {}}}


# ---------------------------------------------------------------------------
# Unified exception handlers — ADR 0012
# ---------------------------------------------------------------------------

# HTTP status -> ErrorCode mapping for framework-generated exceptions
# (StarletteHTTPException). Only the common ones need explicit entries; the
# fallback is INTERNAL_ERROR for 5xx and NOT_FOUND for unknown 4xx.
_HTTP_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.VALIDATION_ERROR,
    409: ErrorCode.LINK_DELETED,
    410: ErrorCode.LINK_GONE,
    413: ErrorCode.FILE_TOO_LARGE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


app = FastAPI(lifespan=lifespan)
# CorrelationIdMiddleware runs outermost so the ID is available from the
# very first log record in every request.  It reads X-Request-ID from a
# trusted proxy or generates a UUID4 when absent, and echoes it in the
# response X-Request-ID header (ADR 0013).
app.add_middleware(
    CorrelationIdMiddleware,
    # Accept any non-empty header value so nginx-style IDs (hex32) and
    # custom proxy values pass through unchanged.  The default validator
    # only accepts strict UUID4 strings, which is too narrow for proxies
    # that generate non-UUID correlation IDs.
    validator=lambda v: bool(v and len(v) <= 128),
)
app.add_middleware(RateLimitMiddleware)
# Credentialed CORS (cookies must flow) forbids wildcard methods/headers — they
# must be enumerated (ADR 0009). Same-origin prod needs no CORS; this serves the
# dev Vite origin only.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://localhost:\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.exception_handler(AppError)
async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    """Handler 1 of 4 — intentional typed application errors (ADR 0012)."""
    return JSONResponse(
        status_code=exc.status,
        content=_error_body(exc.code, exc.message, exc.details),
    )


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handler 2 of 4 — Pydantic 422 -> VALIDATION_ERROR envelope (ADR 0012).

    The raw ``errors()`` list is preserved in ``details.fields`` so the frontend
    can highlight individual form fields, but the top-level code is always the
    stable ``VALIDATION_ERROR``.
    """
    details = {"fields": exc.errors()}
    return JSONResponse(
        status_code=422,
        content=_error_body(ErrorCode.VALIDATION_ERROR, "Validation error", details),
    )


@app.exception_handler(StarletteHTTPException)
async def _handle_http_exception(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handler 3 of 4 — framework HTTPExceptions (404, 405, …) to envelope (ADR 0012).

    Preserves any extra response headers the framework attached (e.g. Allow: for
    405 Method Not Allowed).
    """
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else "Request error"
    headers: dict[str, str] = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, message),
        headers=headers,
    )


@app.exception_handler(Exception)
async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """Handler 4 of 4 — catch-all; logged with a correlation id, never leaks internals.

    No stack trace or exception message is returned to the client (ADR 0012).
    The correlation id is echoed in ``details.correlation_id`` so the caller can
    provide it when reporting the issue (ADR 0013).
    """
    cid = correlation_id.get(None)
    _logger.exception("Unhandled exception: %s", type(exc).__name__)
    details: dict | None = {"correlation_id": cid} if cid else None
    return JSONResponse(
        status_code=500,
        content=_error_body(
            ErrorCode.INTERNAL_ERROR, "An unexpected error occurred", details
        ),
    )


app.include_router(auth_router)
app.include_router(router)
app.include_router(redirect_router)


# ---------------------------------------------------------------------------
# Liveness probe + SPA serving (Phase 6 deploy)
# ---------------------------------------------------------------------------


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Container liveness probe — deliberately independent of the SPA and DB.

    Answers "is the process up", not "is every dependency ready" (readiness is a
    separate concern). The prod compose healthcheck hits this, so it must not
    depend on the static build or a DB round-trip.
    """
    return {"status": "ok"}


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side deep routes.

    Plain ``StaticFiles(html=True)`` serves index.html only for "/", so a
    refresh on a client route like ``/links/abc`` would 404. This returns
    index.html for any unmatched path EXCEPT the API/redirect prefixes, which
    must keep returning a real 404 (→ JSON error envelope, ADR 0012) instead of
    HTML.
    """

    _RESERVED = ("api/", "r/")

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Match on the scope URL path (forward-slash, mount-relative), NOT the
            # ``path`` arg — StaticFiles os-normalizes it, so on Windows it is
            # backslash-separated and an "api/" prefix check would silently miss.
            request_path = scope.get("path", "").lstrip("/")
            if exc.status_code == 404 and not request_path.startswith(self._RESERVED):
                return await super().get_response("index.html", scope)
            raise


# Mount the built SPA as the single same-origin upstream (SPA + /api + /r in one
# container behind the shared edge Caddy). Mounted AFTER the routers so /api and
# /r win. Gated by SERVE_SPA (the production image sets SERVE_SPA=true in the
# Dockerfile): tests and the CI backend job leave it unset, so unmatched paths
# keep returning JSON 404 envelopes (ADR 0012) instead of the SPA index.html.
# The directory check is a belt-and-suspenders guard against a missing build.
_SPA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.environ.get("SERVE_SPA", "").lower() == "true" and os.path.isdir(_SPA_DIR):
    app.mount("/", SPAStaticFiles(directory=_SPA_DIR, html=True), name="spa")
