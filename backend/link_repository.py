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


def list_links_for_owner(
    db: Session, owner_id: int, *, include_deleted: bool = False
) -> list[Link]:
    """The caller's own Links, newest-first, for the owner dashboard (ADR 0009).

    Scoped to ``owner_id`` so a user never sees another user's Links; ownerless
    legacy Links (``owner_id IS NULL``) never match. Soft-deleted Links are
    excluded by default and reachable via ``include_deleted=True`` (the trash
    filter). State and scan counts are layered on at the router edge.
    """
    query = db.query(Link).filter(Link.owner_id == owner_id)
    if not include_deleted:
        query = query.filter(Link.deleted_at.is_(None))
    return query.order_by(Link.created_at.desc(), Link.id.desc()).all()


def create_link(
    db: Session,
    *,
    normalized_url: str,
    secret: str,
    owner_id: int,
    expires_at: Optional[datetime],
    now: datetime,
    label: Optional[str] = None,
) -> Link:
    holder: list[Link] = []

    def try_insert(token: str):
        # Savepoint — collision rolls back only to here, not the whole txn.
        with db.begin_nested():
            link = Link(
                token=token,
                original_url=normalized_url,
                owner_id=owner_id,
                label=label,
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
    label: Optional[str] = None,
    now: datetime,
) -> Link:
    ensure_patchable(link, now)
    if "original_url" in fields:
        link.original_url = original_url
    if "expires_at" in fields:
        link.expires_at = expires_at
    if "label" in fields:
        link.label = label
    link.updated_at = now
    db.commit()
    db.refresh(link)
    return link


def mark_deleted(db: Session, link: Link, now: datetime) -> None:
    if link.deleted_at is None:
        link.deleted_at = now
        db.commit()
