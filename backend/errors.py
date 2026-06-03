"""Unified error envelope: ErrorCode taxonomy and AppError hierarchy (ADR 0012).

Every API error response takes this shape:
    { "error": { "code": "<ErrorCode>", "message": "<human>", "details": {} } }

``code`` is the stable machine contract the frontend branches on — never silently
re-purposed, evolved additively. ``message`` is human-facing and free to reword.
``details`` carries structured extras (validation fields, retry_after, …).

Application code raises ``AppError`` (or a sub-class) instead of bare
``HTTPException`` so the error contract is visible in the Python type system.
Four exception handlers in ``main.py`` normalize every error surface:
  1. AppError — intentional typed errors
  2. RequestValidationError — Pydantic 422 -> VALIDATION_ERROR
  3. StarletteHTTPException — framework 404/405 etc., status -> code
  4. catch-all Exception — -> INTERNAL_ERROR, logged, never leaks internals
"""
from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable machine-readable codes the frontend branches on (ADR 0012).

    Values MUST match the enum name exactly — the string "NOT_FOUND" is the
    published API contract. Never repurpose a code; deprecate and add instead.
    """

    # 401 — no or invalid session
    UNAUTHENTICATED = "UNAUTHENTICATED"
    # 403 — demo account attempted a mutation
    DEMO_READ_ONLY = "DEMO_READ_ONLY"
    # 403 — existence is acceptable to reveal (rare; prefer NOT_FOUND)
    FORBIDDEN = "FORBIDDEN"
    # 404 — resource not found, OR non-owner on owner-only (owner-404 rule)
    NOT_FOUND = "NOT_FOUND"
    # 410 — public redirect on a non-active Link
    LINK_GONE = "LINK_GONE"
    # 409 — mutation attempted on a deleted (terminal) Link
    LINK_DELETED = "LINK_DELETED"
    # 422 — generic Pydantic / field-level validation failure
    VALIDATION_ERROR = "VALIDATION_ERROR"
    # 422 — URL failed scheme / host / private-IP validation
    INVALID_URL = "INVALID_URL"
    # 422 — uploaded image is not a valid image format
    INVALID_IMAGE = "INVALID_IMAGE"
    # 413 — upload exceeds the size ceiling
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    # 429 — per-user create quota or per-IP auth quota exceeded
    RATE_LIMITED = "RATE_LIMITED"
    # 500 — token generation exhausted its retry budget
    TOKEN_ALLOCATION_FAILED = "TOKEN_ALLOCATION_FAILED"
    # 500 — catch-all; no internals leaked
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Typed application error — raised by domain/router code, caught by ``main.py``.

    Raising ``AppError`` (not ``HTTPException``) makes the error contract visible
    in the Python type system and ensures the unified envelope is always returned.

    Args:
        code: Stable ``ErrorCode`` the frontend branches on.
        status: HTTP status code for the response.
        message: Human-facing description (free to reword / localise).
        details: Optional structured extras (validation fields, retry_after, …).
    """

    def __init__(
        self,
        code: ErrorCode,
        status: int,
        message: str,
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.details: dict = details if details is not None else {}


# ---------------------------------------------------------------------------
# Pre-built convenience factories — use these over ad-hoc AppError() calls
# so error shapes stay consistent across the codebase.
# ---------------------------------------------------------------------------


def not_found(message: str = "Not found") -> AppError:
    """404 NOT_FOUND — resource absent or non-owner (owner-404 rule, ADR 0012)."""
    return AppError(ErrorCode.NOT_FOUND, 404, message)


def unauthenticated(message: str = "Not authenticated") -> AppError:
    """401 UNAUTHENTICATED — no or invalid session."""
    return AppError(ErrorCode.UNAUTHENTICATED, 401, message)


def demo_read_only(message: str = "Demo account is read-only") -> AppError:
    """403 DEMO_READ_ONLY — shared demo account attempted a mutation."""
    return AppError(ErrorCode.DEMO_READ_ONLY, 403, message)


def link_deleted(token: str) -> AppError:
    """409 LINK_DELETED — mutation attempted on a deleted (terminal) Link."""
    return AppError(ErrorCode.LINK_DELETED, 409, f"Link {token!r} is deleted")


def link_gone(token: str) -> AppError:
    """410 LINK_GONE — public redirect attempted on a non-active Link."""
    return AppError(ErrorCode.LINK_GONE, 410, f"Link {token!r} is gone")


def invalid_url(detail: str) -> AppError:
    """422 INVALID_URL — URL failed validation."""
    return AppError(ErrorCode.INVALID_URL, 422, detail)


def invalid_image(detail: str = "Upload is not a valid image") -> AppError:
    """422 INVALID_IMAGE — uploaded bytes failed image validation (ADR 0011)."""
    return AppError(ErrorCode.INVALID_IMAGE, 422, detail)


def file_too_large(limit_bytes: int) -> AppError:
    """413 FILE_TOO_LARGE — upload exceeds the size ceiling (ADR 0011)."""
    limit_mb = limit_bytes / (1024 * 1024)
    return AppError(
        ErrorCode.FILE_TOO_LARGE,
        413,
        f"Upload exceeds the {limit_mb:.0f} MiB size limit",
        details={"limit_bytes": limit_bytes},
    )


def token_allocation_failed() -> AppError:
    """500 TOKEN_ALLOCATION_FAILED — token generator exhausted its retry budget."""
    return AppError(
        ErrorCode.TOKEN_ALLOCATION_FAILED,
        500,
        "Token generation failed; please retry",
    )
