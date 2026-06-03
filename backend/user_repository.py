"""Persistence for User identities (mirrors link_repository).

Owns the queries that read and upsert the ``User`` row keyed by Google's stable
subject id; it makes no authorization or business decisions. The upsert uses
Postgres ``INSERT ... ON CONFLICT (google_sub) DO UPDATE`` so a concurrent
first-login race resolves to a single row atomically instead of a unique-
violation, and a returning login refreshes the mutable profile in one statement.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .google_identity import GoogleIdentity
from .models import User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_demo_user(db: Session) -> User | None:
    """Return the single shared read-only demo account, or None if unseeded.

    Backs the guest-entry endpoint (ADR 0009): a guest has no Google credential,
    so the session starts from this row rather than an upsert. There is one demo
    account by construction (seeded idempotently); the earliest id is returned
    deterministically if more than one ever exists.
    """
    return (
        db.query(User)
        .filter(User.is_demo.is_(True))
        .order_by(User.id.asc())
        .first()
    )


def upsert_user(db: Session, identity: GoogleIdentity, *, now: datetime) -> User:
    """Create the User on first sign-in, or refresh its profile on a repeat sign-in.

    ``created_at`` is set only on insert; ``is_demo`` is never modified here (the
    demo flag is owned by seeding, not by a login).
    """
    stmt = (
        insert(User)
        .values(
            google_sub=identity.google_sub,
            email=identity.email,
            name=identity.name,
            picture=identity.picture,
            created_at=now,
            last_login_at=now,
        )
        .on_conflict_do_update(
            index_elements=[User.google_sub],
            set_={
                "email": identity.email,
                "name": identity.name,
                "picture": identity.picture,
                "last_login_at": now,
            },
        )
        .returning(User)
    )
    user = db.execute(stmt).scalar_one()
    db.commit()
    db.refresh(user)
    return user
