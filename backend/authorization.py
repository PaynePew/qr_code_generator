"""Authorization rules for the owner-only Link surface (ADR 0009).

Two framework-free rules live here, each raising a typed domain error the HTTP
layer maps:

- ``authorize_owner`` — the one place that decides "may this User act on this
  Link?" for info / analytics / PATCH / DELETE. A non-owner (including the holder
  of a legacy ownerless Link) is treated as if the Link does not exist: it raises
  ``LinkNotFoundError`` so the router returns **404, not 403**, never leaking that
  the Token is real (closes the redirect-hijack hole).
- ``forbid_if_demo`` — the shared demo account is read-only by construction; any
  mutation by it raises ``DemoReadOnlyError`` (mapped to **403 DEMO_READ_ONLY**)
  so the frontend can render a "log in to create" nudge rather than a raw error.

Framework-free by design (the three-layer rule). The unauthenticated case
(no session -> 401) is handled upstream by ``get_current_user`` and never reaches
here.
"""
from __future__ import annotations

from .link_state import LinkNotFoundError
from .models import Link, User


class DemoReadOnlyError(Exception):
    """Raised when the read-only demo account attempts a mutation (ADR 0009).

    Mapped to HTTP 403 with code ``DEMO_READ_ONLY`` so the frontend tells it
    apart from a 401 (no session) or an owner 404 and shows a login nudge.
    """


def authorize_owner(link: Link, user: User) -> None:
    """Pass silently if ``user`` owns ``link``; otherwise raise as not-found.

    Non-owner and ownerless Links both raise ``LinkNotFoundError`` so a stranger
    cannot distinguish "this Token is not yours" from "this Token does not
    exist" (ADR 0009: 404, not 403).
    """
    if link.owner_id is None or link.owner_id != user.id:
        raise LinkNotFoundError(link.token)


def forbid_if_demo(user: User) -> None:
    """Pass silently for a real User; raise ``DemoReadOnlyError`` for the demo one.

    The demo account is read-only so its richly-seeded data stays pristine for
    the next guest (ADR 0009). Call this on every mutating endpoint before any
    write — guests who want to create use the real 2-second login.
    """
    if user.is_demo:
        raise DemoReadOnlyError()
