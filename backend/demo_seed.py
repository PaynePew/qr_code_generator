"""Idempotent seeding of the shared read-only demo account (ADR 0009).

A guest enters one demo account and must see a dashboard + analytics that look
*alive*: several Links across states (active / expired / deleted) with a
multi-day scan spread. ``seed_demo`` provisions exactly that and is safe to run
repeatedly — deploys re-run it — by keying the account on a fixed
``google_sub`` and short-circuiting once the account already owns Links (the
seeded data *is* the demo; the account is read-only so it never drifts).

This is persistence/setup code: it owns its inserts and makes no authorization
or HTTP decision (those live in ``authorization``/the router). It is runnable as
a deploy step: ``python -m backend.demo_seed`` (reads ``DATABASE_URL`` +
``SECRET`` from the environment, like the app).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import link_repository
from .models import Link, Scan, User
from .timeutil import now_utc

# Fixed identity for the one shared demo account. `google_sub` is Google's
# subject id for real users; this sentinel can never collide with one (Google
# subs are numeric strings), so the upsert stays idempotent across deploys.
DEMO_GOOGLE_SUB = "demo-account"
DEMO_EMAIL = "demo@qrcode.paynepew.dev"
DEMO_NAME = "Demo Account"


@dataclass(frozen=True)
class _SeedLink:
    """One Link to seed: its destination, an optional expiry, soft-delete, and a
    per-day scan plan (``day_offset`` is days *before* ``now``)."""

    url: str
    expires_at: datetime | None
    deleted: bool
    scans_by_day_offset: dict[int, int]


def _seed_plan(now: datetime) -> list[_SeedLink]:
    """The demo dataset: state variety + a multi-day scan spread for analytics."""
    return [
        # Active, no expiry — the headline Link, busiest across several days.
        _SeedLink(
            url="https://paynepew.dev",
            expires_at=None,
            deleted=False,
            scans_by_day_offset={0: 5, 1: 8, 2: 3, 4: 6, 6: 2},
        ),
        # Active, expires in the future — still redirectable today.
        _SeedLink(
            url="https://github.com/PaynePew/qr_code_generator",
            expires_at=now + timedelta(days=30),
            deleted=False,
            scans_by_day_offset={1: 2, 3: 4, 5: 1},
        ),
        # Expired — past expiry, reactivatable in the dashboard.
        _SeedLink(
            url="https://example.com/spring-campaign",
            expires_at=now - timedelta(days=2),
            deleted=False,
            scans_by_day_offset={5: 7, 6: 4, 8: 2},
        ),
        # Deleted (soft) — lives only in the trash view.
        _SeedLink(
            url="https://example.com/old-flyer",
            expires_at=None,
            deleted=True,
            scans_by_day_offset={7: 1, 9: 2},
        ),
    ]


def _get_or_create_demo_user(db: Session, *, now: datetime) -> User:
    """Return the demo User, creating it on first run (keyed on ``google_sub``)."""
    user = db.query(User).filter(User.google_sub == DEMO_GOOGLE_SUB).one_or_none()
    if user is not None:
        return user
    user = User(
        google_sub=DEMO_GOOGLE_SUB,
        email=DEMO_EMAIL,
        name=DEMO_NAME,
        picture=None,
        created_at=now,
        last_login_at=now,
        is_demo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_demo(db: Session, *, secret: str, now: datetime) -> User:
    """Idempotently provision the demo account and return it.

    First run: create the demo User and populate it with multi-state Links and a
    multi-day scan spread. Subsequent runs: no-op once the account already owns
    Links, so re-running on every deploy never duplicates data.
    """
    user = _get_or_create_demo_user(db, now=now)

    # Idempotency guard: the seeded data is the demo. If it is already populated,
    # do not add more (a re-run must not pile up Links/Scans).
    already_seeded = db.query(Link).filter(Link.owner_id == user.id).first() is not None
    if already_seeded:
        return user

    for plan in _seed_plan(now):
        link = link_repository.create_link(
            db,
            normalized_url=plan.url,
            secret=secret,
            owner_id=user.id,
            expires_at=plan.expires_at,
            now=now,
        )
        if plan.deleted:
            link_repository.mark_deleted(db, link, now)
        _seed_scans(db, token=link.token, now=now, plan=plan.scans_by_day_offset)

    return user


def _seed_scans(
    db: Session, *, token: str, now: datetime, plan: dict[int, int]
) -> None:
    """Insert Scans for ``token`` per ``plan`` (``day_offset`` -> count), where the
    offset counts days before ``now``.

    Scans land at distinct times within the day so the per-day rollups look
    natural. Status mirrors real redirects: 302 for served, with the occasional
    410 to show a "gone" outcome in the breakdown (CONTEXT.md Scan semantics).
    """
    for day_offset, count in plan.items():
        day = now - timedelta(days=day_offset)
        for i in range(count):
            scanned_at = day.replace(hour=9, minute=0, second=0) + timedelta(
                minutes=37 * i
            )
            status_code = 410 if i % 7 == 6 else 302
            db.add(
                Scan(
                    token=token,
                    scanned_at=scanned_at,
                    status_code=status_code,
                    ip_address=None,
                    user_agent="DemoSeed/1.0",
                )
            )
    db.commit()


def _main() -> None:
    """Deploy-step entrypoint: seed against the app's configured database."""
    import os

    from .database import SessionLocal

    secret = os.environ.get("SECRET")
    if not secret:
        raise RuntimeError("SECRET environment variable must be set")

    now = now_utc()
    db = SessionLocal()
    try:
        user = seed_demo(db, secret=secret, now=now)
        link_count = db.query(Link).filter(Link.owner_id == user.id).count()
        # Deliberate stdout in a one-off script (not the request path): a deploy
        # operator needs to see the outcome.
        print(f"Demo account ready: user_id={user.id}, links={link_count}")
    finally:
        db.close()


if __name__ == "__main__":
    _main()
