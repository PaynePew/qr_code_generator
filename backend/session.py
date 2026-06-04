"""Signed, app-issued cookie session (ADR 0009).

After the backend verifies Google's ID token once, it issues its *own* session
rather than reusing Google's token: a short, signed payload carrying only the
User id, serialized with itsdangerous under the app ``SECRET``. A tampered or
expired cookie fails to load and is treated as no session at all. Cookie
attributes (httpOnly + SameSite=Lax always; Secure under ``SESSION_COOKIE_SECURE``
in prod) are applied where the cookie is set, in the auth router.
"""

from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "session"
_SALT = "qr-code-generator.session.v1"
_DEFAULT_MAX_AGE = 60 * 60 * 24 * 14  # 14 days


class SessionConfig:
    """Resolved-at-call session settings sourced from the environment."""

    def __init__(self) -> None:
        secret = os.environ.get("SECRET")
        if not secret:
            raise RuntimeError("SECRET environment variable must be set")
        self.secret = secret
        self.max_age = int(os.environ.get("SESSION_MAX_AGE", _DEFAULT_MAX_AGE))
        self.cookie_secure = _env_bool("SESSION_COOKIE_SECURE", default=True)


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    if raw.lower() not in ("true", "false"):
        raise RuntimeError(f"{name} must be 'true' or 'false', got: {raw!r}")
    return raw.lower() == "true"


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt=_SALT)


def issue_session(user_id: int, config: SessionConfig) -> str:
    """Return a signed session value carrying ``user_id``."""
    return _serializer(config.secret).dumps({"uid": user_id})


def read_session(raw_cookie: str, config: SessionConfig) -> int | None:
    """Return the User id from a valid cookie, or None if absent/invalid/expired."""
    if not raw_cookie:
        return None
    try:
        payload = _serializer(config.secret).loads(raw_cookie, max_age=config.max_age)
    except (BadSignature, SignatureExpired):
        return None
    uid = payload.get("uid") if isinstance(payload, dict) else None
    return uid if isinstance(uid, int) else None
