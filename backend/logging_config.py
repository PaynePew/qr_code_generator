"""Structured JSON logging with per-request correlation ID (ADR 0013).

Key decisions:
- JSON formatter emits one structured log record per line.
- Per-request correlation ID via ``asgi-correlation-id``; reads inbound
  ``X-Request-ID`` from a trusted proxy or generates a UUID4.
- ``CorrelationIdFilter`` injects ``correlation_id`` into every log record;
  the JSON formatter picks it up as ``request_id``.
- Post-auth ``user_id`` is bound via ``bind_user_id``, called by
  ``auth.get_current_user`` after session decoding so every subsequent log
  record in the request carries the user_id field.
- No raw IP ever enters a log record (ADR 0013):
  - Redirect path: logs no IP at all.
  - Abuse-relevant paths (auth endpoint): ``hash_ip`` is called in
    ``auth_router.start_session`` to log a salted HMAC-SHA256 digest so
    "one source hammering" is detectable without retaining the raw address.
- Log rotation with ~30-day retention is configured by ``configure_logging``.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone

from asgi_correlation_id import CorrelationIdFilter, correlation_id

# ---------------------------------------------------------------------------
# Per-request user_id context variable
# ---------------------------------------------------------------------------

_user_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "log_user_id", default=None
)


def bind_user_id(user_id: int) -> None:
    """Bind the authenticated user_id to the current request context.

    Call this after session decoding so every subsequent log record in this
    request includes the user_id field.
    """
    _user_id_var.set(user_id)


def get_log_user_id() -> int | None:
    """Return the user_id bound to the current request context, or None."""
    return _user_id_var.get()


# ---------------------------------------------------------------------------
# IP hashing (ADR 0013 — abuse-relevant paths only)
# ---------------------------------------------------------------------------


def _get_ip_salt() -> bytes:
    """Return the per-deployment salt for IP hashing.

    Reads ``IP_LOG_SALT`` when set; otherwise derives the salt from ``SECRET``
    (which startup validation already requires). Raises ``KeyError`` if neither
    is present so a misconfigured deploy fails fast rather than silently
    weakening the hash salt to a known constant (ADR 0013).
    """
    explicit = os.environ.get("IP_LOG_SALT")
    if explicit:
        return explicit.encode()
    # SECRET is enforced at startup; KeyError here signals a misconfigured deploy.
    secret = os.environ["SECRET"]
    return f"ip-log-{secret}".encode()


def hash_ip(ip: str) -> str:
    """Return a salted HMAC-SHA256 hex digest of *ip* (first 16 chars).

    Enough entropy to detect a single source hammering many endpoints, but
    not enough to reconstruct the original address (ADR 0013).
    """
    salt = _get_ip_salt()
    digest = hmac.new(salt, ip.encode(), hashlib.sha256).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# JSON log formatter
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    Standard fields:
        timestamp   ISO-8601 UTC
        level       log level name
        logger      logger name
        message     formatted message

    Optional fields (added when present on the record):
        request_id  correlation ID from ``CorrelationIdFilter``
        user_id     authenticated user ID from ``_user_id_var``
        exc_info    exception class name (only when an exception is attached)
    """

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        if record.exc_info:
            # Render the exception so it is captured before we discard it.
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        obj: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }

        # Correlation ID (injected by CorrelationIdFilter)
        cid = getattr(record, "correlation_id", None) or correlation_id.get(None)
        if cid:
            obj["request_id"] = cid

        # Authenticated user_id
        uid = getattr(record, "user_id", None) or _user_id_var.get()
        if uid is not None:
            obj["user_id"] = uid

        # Exception info — type name only in the structured record; full trace
        # should go to a separate "exc_text" field for log aggregators.
        if record.exc_info and record.exc_info[1] is not None:
            obj["exc_type"] = type(record.exc_info[1]).__name__
            if record.exc_text:
                obj["exc_text"] = record.exc_text

        return json.dumps(obj, default=str)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

_ROTATION_WHEN = "midnight"
_BACKUP_COUNT = 30  # ~30-day retention


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging with rotation and correlation ID filter.

    Safe to call multiple times (idempotent after first call via root-logger
    handler check).
    """
    root = logging.getLogger()
    if any(
        isinstance(h, logging.StreamHandler) and getattr(h, "_json_configured", False)
        for h in root.handlers
    ):
        return  # Already configured.

    root.setLevel(level)

    # Console handler — always present.
    console = logging.StreamHandler()
    console.setFormatter(JSONFormatter())
    console.addFilter(CorrelationIdFilter(default_value="-"))
    console._json_configured = True  # type: ignore[attr-defined]
    root.addHandler(console)

    # File handler with daily rotation (skip in test environments).
    if os.environ.get("LOG_TO_FILE", "false").lower() == "true":
        log_dir = os.environ.get("LOG_DIR", "logs")
        log_file = os.path.join(log_dir, "app.log")
        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file,
                when=_ROTATION_WHEN,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(JSONFormatter())
            file_handler.addFilter(CorrelationIdFilter(default_value="-"))
            root.addHandler(file_handler)
        except OSError:
            root.warning("Could not create log file handler at %s", log_file)
