"""Mint a signed session cookie for the Playwright E2E auth bypass (bead 8vd).

Google login can't be automated, so E2E tests don't log in: the session cookie
is just an itsdangerous-signed ``{uid}`` (backend/session.py), so a test mints
one for a known user and injects it via ``context.addCookies`` — no Google
round-trip. This helper idempotently ensures the demo account exists (seeding
its multi-state Links so the dashboard has something to render) and prints, as
one JSON line, the cookie name + signed value + the user id.

Run from the repo root with the SAME env the backend uses:
    SECRET=... DATABASE_URL=... python scripts/mint_session_cookie.py
"""

import json
import os

from backend.database import SessionLocal
from backend.demo_seed import seed_demo
from backend.session import COOKIE_NAME, SessionConfig, issue_session
from backend.timeutil import now_utc


def main() -> None:
    secret = os.environ.get("SECRET")
    if not secret:
        raise SystemExit("SECRET environment variable must be set")

    db = SessionLocal()
    try:
        user = seed_demo(db, secret=secret, now=now_utc())
        cookie_value = issue_session(user.id, SessionConfig())
        uid = user.id
    finally:
        db.close()

    print(json.dumps({"name": COOKIE_NAME, "value": cookie_value, "uid": uid}))


if __name__ == "__main__":
    main()
