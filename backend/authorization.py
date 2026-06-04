"""Authorization rules for the owner-only Link surface (ADR 0009).

Two framework-free rules live here, each raising a typed ``AppError`` that the
HTTP layer's unified exception handler (ADR 0012) turns into the envelope:

- ``authorize_owner`` — the one place that decides "may this User act on this
  Link?" for info / analytics / PATCH / DELETE. A non-owner (including the holder
  of a legacy ownerless Link) raises ``AppError(NOT_FOUND, 404)`` so the router
  returns **404, not 403**, never leaking that the Token is real (owner-404 rule,
  ADR 0012 / ADR 0009).
- ``forbid_if_demo`` — the shared demo account is read-only by construction; any
  mutation by it raises ``AppError(DEMO_READ_ONLY, 403)`` so the frontend can
  render a "log in to create" nudge rather than a raw error.

Framework-free by design (the three-layer rule). ``AppError`` lives in
``backend.errors`` which has no web-framework imports, so this module stays clean.
The unauthenticated case (no session -> 401) is handled upstream by
``get_current_user`` and never reaches here.
"""

from __future__ import annotations

from .errors import AppError, ErrorCode
from .models import Link, User


def authorize_owner(link: Link, user: User) -> None:
    """Pass silently if ``user`` owns ``link``; otherwise raise as not-found.

    Non-owner and ownerless Links both raise ``AppError(NOT_FOUND, 404)`` so a
    stranger cannot distinguish "this Token is not yours" from "this Token does
    not exist" (ADR 0009 / ADR 0012: owner-404 rule).
    """
    if link.owner_id is None or link.owner_id != user.id:
        raise AppError(ErrorCode.NOT_FOUND, 404, f"Token not found: {link.token}")


def forbid_if_demo(user: User) -> None:
    """Pass silently for a real User; raise ``AppError(DEMO_READ_ONLY, 403)`` for the demo one.

    The demo account is read-only so its richly-seeded data stays pristine for
    the next guest (ADR 0009). Call this on every mutating endpoint before any
    write — guests who want to create use the real 2-second login.
    """
    if user.is_demo:
        raise AppError(ErrorCode.DEMO_READ_ONLY, 403, "Demo account is read-only")
