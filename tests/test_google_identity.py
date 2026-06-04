"""Tests for the google_identity module.

Google's ID-token verification is mocked: these tests assert that the module
maps Google's outcomes onto our domain types (valid claims vs a single typed
rejection), not that Google's own crypto works. ADR 0009 requires verifying
signature, audience, issuer and expiry; google-auth's verify_oauth2_token does
that and raises ValueError / GoogleAuthError on failure, which we normalize.
"""

from __future__ import annotations

import pytest
from google.auth.exceptions import GoogleAuthError

from backend import google_identity
from backend.google_identity import GoogleIdentity, InvalidGoogleTokenError

CLIENT_ID = "client-123.apps.googleusercontent.com"

VALID_CLAIMS = {
    "sub": "google-subject-abc",
    "email": "alice@example.com",
    "name": "Alice Example",
    "picture": "https://example.com/alice.png",
    "iss": "https://accounts.google.com",
    "aud": CLIENT_ID,
    "exp": 9999999999,
}


def _patch_verify(monkeypatch, result=None, raises=None):
    def fake_verify(token, request, audience):
        assert audience == CLIENT_ID
        if raises is not None:
            raise raises
        return result

    monkeypatch.setattr(google_identity, "_verify_oauth2_token", fake_verify)


class TestVerifyValidToken:
    def test_returns_identity_with_claims(self, monkeypatch):
        _patch_verify(monkeypatch, result=VALID_CLAIMS)
        identity = google_identity.verify_google_id_token("any-token", CLIENT_ID)
        assert identity == GoogleIdentity(
            google_sub="google-subject-abc",
            email="alice@example.com",
            name="Alice Example",
            picture="https://example.com/alice.png",
        )

    def test_tolerates_missing_optional_claims(self, monkeypatch):
        _patch_verify(
            monkeypatch,
            result={
                "sub": "sub-only",
                "email": "bob@example.com",
                "iss": "https://accounts.google.com",
                "aud": CLIENT_ID,
            },
        )
        identity = google_identity.verify_google_id_token("any-token", CLIENT_ID)
        assert identity.google_sub == "sub-only"
        assert identity.email == "bob@example.com"
        assert identity.name is None
        assert identity.picture is None


class TestVerifyRejectsBadTokens:
    def test_rejects_expired_token(self, monkeypatch):
        # google-auth raises ValueError("Token expired ...") on expiry.
        _patch_verify(monkeypatch, raises=ValueError("Token expired"))
        with pytest.raises(InvalidGoogleTokenError):
            google_identity.verify_google_id_token("expired", CLIENT_ID)

    def test_rejects_wrong_audience(self, monkeypatch):
        _patch_verify(monkeypatch, raises=ValueError("Token has wrong audience"))
        with pytest.raises(InvalidGoogleTokenError):
            google_identity.verify_google_id_token("wrong-aud", CLIENT_ID)

    def test_rejects_bad_signature(self, monkeypatch):
        _patch_verify(
            monkeypatch, raises=ValueError("Could not verify token signature")
        )
        with pytest.raises(InvalidGoogleTokenError):
            google_identity.verify_google_id_token("bad-sig", CLIENT_ID)

    def test_rejects_wrong_issuer(self, monkeypatch):
        # google-auth raises GoogleAuthError (not ValueError) for a wrong issuer.
        _patch_verify(monkeypatch, raises=GoogleAuthError("Wrong issuer"))
        with pytest.raises(InvalidGoogleTokenError):
            google_identity.verify_google_id_token("wrong-iss", CLIENT_ID)

    def test_rejects_token_missing_subject(self, monkeypatch):
        # A verified token without a subject is unusable as an identity key.
        _patch_verify(
            monkeypatch,
            result={"email": "x@example.com", "aud": CLIENT_ID},
        )
        with pytest.raises(InvalidGoogleTokenError):
            google_identity.verify_google_id_token("no-sub", CLIENT_ID)

    def test_rejects_token_missing_email(self, monkeypatch):
        _patch_verify(
            monkeypatch,
            result={"sub": "sub-x", "aud": CLIENT_ID},
        )
        with pytest.raises(InvalidGoogleTokenError):
            google_identity.verify_google_id_token("no-email", CLIENT_ID)
