"""Verify a Google ID token and extract the identity claims we trust.

Deep module (ADR 0009): the caller hands in a raw Google ID token and our OAuth
client id and gets back a small, validated ``GoogleIdentity`` — or a single
typed ``InvalidGoogleTokenError`` if the token fails *any* check (signature,
audience, issuer, expiry, or a missing required claim). google-auth performs the
cryptographic verification against Google's published certs; we collapse its two
failure types (``ValueError`` for crypto/audience/expiry, ``GoogleAuthError``
for issuer) into one domain error so callers never branch on Google's
internals. This module is pure domain — it must not import a web framework.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token


class InvalidGoogleTokenError(Exception):
    """Raised when a Google ID token fails verification or lacks a required claim.

    Deliberately opaque: it does not distinguish expired / wrong-audience /
    bad-signature so the auth endpoint cannot leak which check failed.
    """


@dataclass(frozen=True)
class GoogleIdentity:
    """The subset of verified Google claims the app keys identity on."""

    google_sub: str
    email: str
    name: str | None = None
    picture: str | None = None


def _verify_oauth2_token(token: str, request: object, audience: str) -> dict:
    """Seam over google-auth so tests can mock verification without network."""
    return google_id_token.verify_oauth2_token(token, request, audience)


def verify_google_id_token(token: str, client_id: str) -> GoogleIdentity:
    """Verify ``token`` was issued by Google for ``client_id`` and return its identity.

    Raises ``InvalidGoogleTokenError`` if verification fails for any reason or a
    required claim (subject, email) is absent.
    """
    request = google_requests.Request()
    try:
        claims = _verify_oauth2_token(token, request, client_id)
    except (ValueError, GoogleAuthError) as exc:
        raise InvalidGoogleTokenError("Google ID token verification failed") from exc

    google_sub = claims.get("sub")
    email = claims.get("email")
    if not google_sub or not email:
        raise InvalidGoogleTokenError("Google ID token is missing required claims")

    return GoogleIdentity(
        google_sub=google_sub,
        email=email,
        name=claims.get("name"),
        picture=claims.get("picture"),
    )
