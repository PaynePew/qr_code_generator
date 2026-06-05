"""CORS preflight coverage.

The app uses credentialed CORS (cookies must flow), so methods are enumerated
explicitly (wildcards are forbidden with credentials). The customization
endpoint is a PUT; PUT was missing from ``allow_methods`` once, so the browser
preflight (OPTIONS) returned 400 and customization uploads failed cross-origin.

These tests touch no DB — the CORS middleware answers the preflight before
routing — so they request no db fixtures and run without a testcontainer.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

_DEV_ORIGIN = "http://localhost:5173"


def _preflight(method: str):
    client = TestClient(app)
    return client.options(
        "/api/qr/abc1234/customization",
        headers={
            "Origin": _DEV_ORIGIN,
            "Access-Control-Request-Method": method,
        },
    )


def test_cors_preflight_allows_put_for_customization():
    """Regression (bead 65g): PUT must be allowed so the customization upload's
    browser preflight succeeds cross-origin."""
    resp = _preflight("PUT")
    assert resp.status_code == 200
    assert "PUT" in resp.headers.get("access-control-allow-methods", "")
    assert resp.headers.get("access-control-allow-origin") == _DEV_ORIGIN


def test_cors_preflight_allows_the_other_mutating_methods():
    for method in ("POST", "PATCH", "DELETE"):
        resp = _preflight(method)
        assert resp.status_code == 200, method
        assert method in resp.headers.get("access-control-allow-methods", "")
