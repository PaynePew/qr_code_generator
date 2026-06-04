"""Auth endpoints: start a session from a Google credential, end it, report me.

ADR 0009 login flow: the client posts the Google-issued ID token once; we verify
it, upsert the User by Google subject id, and set our own signed session cookie
(httpOnly + SameSite=Lax always, Secure in prod). Logout clears that cookie; the
current-user endpoint reflects it back. Google's token is never reused as the
session.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import google_identity, user_repository
from . import session as session_module
from .auth import get_current_user
from .errors import AppError, ErrorCode
from .google_identity import InvalidGoogleTokenError
from .logging_config import hash_ip
from .models import User
from .rate_limiter.ip_extraction import extract_client_ip
from .router import _now_utc, get_db

_logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth")


def _google_client_id() -> str:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise AppError(
            ErrorCode.INTERNAL_ERROR, 503, "Google sign-in is not configured"
        )
    return client_id


def _user_response(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "is_demo": user.is_demo,
    }


def _set_session_cookie(
    response: Response,
    user_id: int,
    config: session_module.SessionConfig,
) -> None:
    response.set_cookie(
        key=session_module.COOKIE_NAME,
        value=session_module.issue_session(user_id, config),
        max_age=config.max_age,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )


class SessionRequest(BaseModel):
    credential: str


@auth_router.post("/session")
def start_session(
    body: SessionRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Verify a Google credential, upsert the User, and set the session cookie.

    Abuse-relevant path: logs a hashed client IP (ADR 0013) so account-farming
    attempts are detectable without retaining the raw address.
    """
    trusted_proxies = int(os.environ.get("TRUSTED_PROXIES", "0"))
    raw_ip = extract_client_ip(request, trusted_proxies)
    if raw_ip:
        _logger.info("auth attempt ip_hash=%s", hash_ip(raw_ip))

    client_id = _google_client_id()
    try:
        identity = google_identity.verify_google_id_token(body.credential, client_id)
    except InvalidGoogleTokenError:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Invalid Google credential")

    user = user_repository.upsert_user(db, identity, now=_now_utc())
    _set_session_cookie(response, user.id, session_module.SessionConfig())
    return _user_response(user)


@auth_router.post("/demo-session")
def start_demo_session(
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Start a session as the shared read-only demo account — no credential ("Try
    as guest", ADR 0009). The demo account is seeded out of band (``demo_seed``);
    if it is absent that is an ops gap (503), not a client error. The session
    cookie issued is identical in kind to a real login — read-only is enforced
    server-side by the ``DEMO_READ_ONLY`` guard, not by a weaker session.
    """
    demo = user_repository.get_demo_user(db)
    if demo is None:
        raise AppError(ErrorCode.INTERNAL_ERROR, 503, "Demo account is not available")

    _set_session_cookie(response, demo.id, session_module.SessionConfig())
    return _user_response(demo)


@auth_router.delete("/session")
def end_session(response: Response) -> dict:
    """Clear the session cookie (logout)."""
    config = session_module.SessionConfig()
    response.delete_cookie(
        key=session_module.COOKIE_NAME,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )
    return {"status": "signed_out"}


@auth_router.get("/me")
def current_user(user: User = Depends(get_current_user)) -> dict:
    """Report the authenticated User (401 when there is no valid session)."""
    return _user_response(user)
