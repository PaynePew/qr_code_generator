"""HTTP-layer auth glue: resolve the session cookie to the current User.

``get_current_user`` is the FastAPI dependency every owner-only endpoint will
depend on. It reads the signed session cookie, loads the referenced User, and
raises 401 when the cookie is absent, invalid/expired, or points at a User that
no longer exists — so "no session" and "bad session" are one outcome to the
caller (ADR 0009). This is the only auth seam that touches the web framework;
verification and persistence stay in their own framework-free modules.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from . import session as session_module
from . import user_repository
from .database import get_db
from .errors import unauthenticated
from .logging_config import bind_user_id
from .models import User


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated User, or raise 401 if there is no valid session.

    Also binds the resolved user_id to the per-request log context (ADR 0013)
    so every subsequent log record in this request carries user_id.
    """
    config = session_module.SessionConfig()
    raw_cookie = request.cookies.get(session_module.COOKIE_NAME, "")
    user_id = session_module.read_session(raw_cookie, config)
    if user_id is None:
        raise unauthenticated()

    user = user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise unauthenticated()

    bind_user_id(user.id)
    return user
