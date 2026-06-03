"""Single ownership rule for owner-only Link endpoints (ADR 0009).

This is the one place that decides "may this User act on this Link?" for the
owner-only surface (info, analytics, PATCH, DELETE). A non-owner — including the
holder of a legacy ownerless Link — is treated as if the Link does not exist:
we raise ``LinkNotFoundError`` so the router returns **404, not 403**, never
leaking that the Token is real (ADR 0009 closes the redirect-hijack hole).

Framework-free by design (the three-layer rule): it raises a typed domain error;
the HTTP layer maps it. The unauthenticated case (no session -> 401) is handled
upstream by ``get_current_user`` and never reaches here.
"""
from __future__ import annotations

from .link_state import LinkNotFoundError
from .models import Link, User


def authorize_owner(link: Link, user: User) -> None:
    """Pass silently if ``user`` owns ``link``; otherwise raise as not-found.

    Non-owner and ownerless Links both raise ``LinkNotFoundError`` so a stranger
    cannot distinguish "this Token is not yours" from "this Token does not
    exist" (ADR 0009: 404, not 403).
    """
    if link.owner_id is None or link.owner_id != user.id:
        raise LinkNotFoundError(link.token)
