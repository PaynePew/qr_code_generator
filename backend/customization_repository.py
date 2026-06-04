"""Persistence layer for Link customization (ADR 0011).

Owns all SQLAlchemy queries against ``link_customizations``.  No HTTP or
business logic lives here — that stays at the router / domain layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .models import LinkCustomization


def get_customization(db: Session, link_id: int) -> LinkCustomization | None:
    """Return the customization row for ``link_id``, or None if absent."""
    return (
        db.query(LinkCustomization).filter(LinkCustomization.link_id == link_id).first()
    )


def upsert_customization(
    db: Session,
    *,
    link_id: int,
    style_json: str,
    image_key: str,
    logo_key: str | None,
    now: datetime,
) -> LinkCustomization:
    """Create or replace the customization row for ``link_id``.

    On re-styling the image_key MUST already point to the newly-stored composite
    (a different versioned key from the previous one).  The old composite is left
    in storage and reaped by the S3 lifecycle rule (ADR 0011).
    """
    row = get_customization(db, link_id)
    if row is None:
        row = LinkCustomization(
            link_id=link_id,
            style_json=style_json,
            image_key=image_key,
            logo_key=logo_key,
            updated_at=now,
        )
        db.add(row)
    else:
        row.style_json = style_json
        row.image_key = image_key
        row.logo_key = logo_key
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def delete_customization(db: Session, link_id: int) -> None:
    """Remove the customization row for ``link_id``.  No-ops if absent."""
    row = get_customization(db, link_id)
    if row is not None:
        db.delete(row)
        db.commit()
