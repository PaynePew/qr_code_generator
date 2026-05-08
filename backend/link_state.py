from datetime import datetime
from enum import StrEnum

from .models import Link


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
