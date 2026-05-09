from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .link_state import LinkNotFoundError, ensure_patchable
from .models import Link
from .token_generator import allocate_token, TokenCollisionError


def get_link(db: Session, token: str) -> Link:
    link = db.query(Link).filter(Link.token == token).first()
    if link is None:
        raise LinkNotFoundError(token)
    return link


def create_link(
    db: Session,
    *,
    normalized_url: str,
    secret: str,
    expires_at: Optional[datetime],
    now: datetime,
) -> Link:
    holder: list[Link] = []

    def try_insert(token: str):
        # Savepoint — collision rolls back only to here, not the whole txn.
        with db.begin_nested():
            link = Link(
                token=token,
                original_url=normalized_url,
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
            )
            db.add(link)
            db.flush()
            holder.append(link)

    try:
        allocate_token(normalized_url, secret, try_insert)
        db.commit()
    except TokenCollisionError:
        db.rollback()
        raise
    return holder[0]


def apply_patch(
    db: Session,
    link: Link,
    *,
    fields: set[str],
    original_url: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    now: datetime,
) -> Link:
    ensure_patchable(link, now)
    if "original_url" in fields:
        link.original_url = original_url
    if "expires_at" in fields:
        link.expires_at = expires_at
    link.updated_at = now
    db.commit()
    db.refresh(link)
    return link


def mark_deleted(db: Session, link: Link, now: datetime) -> None:
    if link.deleted_at is None:
        link.deleted_at = now
        db.commit()
