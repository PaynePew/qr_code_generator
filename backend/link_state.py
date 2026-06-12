from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from .errors import AppError, ErrorCode
from .models import Link


class _LinkStateSource(Protocol):
    """Structural interface consumed by ``derive_state``.

    Both ``Link`` (ORM model) and ``LinkSnapshot`` (cache dataclass) satisfy
    this protocol so ``derive_state`` works with either without a ``type: ignore``.
    """

    deleted_at: datetime | None
    expires_at: datetime | None


class LinkNotFoundError(AppError):
    """Raised when a token does not resolve to a Link row.

    Subclasses AppError so it is caught by the unified handler (ADR 0012) and
    returns 404 NOT_FOUND without a separate exception handler in main.py.
    """

    def __init__(self, token: str) -> None:
        super().__init__(ErrorCode.NOT_FOUND, 404, f"Token not found: {token}")
        self.token = token


class LinkAlreadyDeletedError(AppError):
    """Raised when a mutation attempts to operate on a Link in DELETED state.

    Terminal state per ADR 0001. Subclasses AppError so it returns 409
    LINK_DELETED via the unified handler (ADR 0012).
    """

    def __init__(self, token: str) -> None:
        super().__init__(ErrorCode.LINK_DELETED, 409, f"Link {token!r} is deleted")
        self.token = token


class LinkState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DELETED = "deleted"

    @property
    def is_redirectable(self) -> bool:
        return self is LinkState.ACTIVE

    @property
    def is_patchable(self) -> bool:
        # ADR 0001: deleted is terminal; expired is reversible via PATCH expires_at.
        return self is not LinkState.DELETED


def derive_state(link: _LinkStateSource, now: datetime) -> LinkState:
    if link.deleted_at is not None:
        return LinkState.DELETED
    if link.expires_at is not None and link.expires_at <= now:
        return LinkState.EXPIRED
    return LinkState.ACTIVE


def ensure_patchable(link: Link, now: datetime) -> None:
    """Domain precondition for any PATCH-style mutation. Enforces ADR 0001."""
    if not derive_state(link, now).is_patchable:
        raise LinkAlreadyDeletedError(link.token)
