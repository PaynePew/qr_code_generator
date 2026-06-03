"""Auth endpoints: start a session from a Google credential, end it, report me.

ADR 0009 login flow: the client posts the Google-issued ID token once; we verify
it, upsert the User by Google subject id, and set our own signed session cookie
(httpOnly + SameSite=Lax always, Secure in prod). Logout clears that cookie; the
current-user endpoint reflects it back. Google's token is never reused as the
session.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import google_identity
from . import session as session_module
from . import user_repository
from .auth import get_current_user
from .google_identity import InvalidGoogleTokenError
from .models import User
from .router import _now_utc, get_db

auth_router = APIRouter(prefix="/api/auth")


def _google_client_id() -> str:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
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
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Verify a Google credential, upsert the User, and set the session cookie."""
    client_id = _google_client_id()
    try:
        identity = google_identity.verify_google_id_token(body.credential, client_id)
    except InvalidGoogleTokenError:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

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
        raise HTTPException(status_code=503, detail="Demo account is not available")

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
