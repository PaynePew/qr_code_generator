from datetime import datetime
from enum import StrEnum

from .models import Link


class LinkNotFoundError(Exception):
    """Raised when a token does not resolve to a Link row."""

    def __init__(self, token: str):
        super().__init__(f"Token not found: {token}")
        self.token = token


class LinkAlreadyDeletedError(Exception):
    """Raised when a mutation attempts to operate on a Link in DELETED state.

    Terminal state per ADR 0001.
    """

    def __init__(self, token: str):
        super().__init__(f"Link is deleted: {token}")
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


def derive_state(link: Link, now: datetime) -> LinkState:
    if link.deleted_at is not None:
        return LinkState.DELETED
    if link.expires_at is not None and link.expires_at <= now:
        return LinkState.EXPIRED
    return LinkState.ACTIVE


def ensure_patchable(link: Link, now: datetime) -> None:
    """Domain precondition for any PATCH-style mutation. Enforces ADR 0001."""
    if not derive_state(link, now).is_patchable:
        raise LinkAlreadyDeletedError(link.token)
