from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    picture: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_login_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    original_url: Mapped[str] = mapped_column(String, nullable=False)
    # owner_id is nullable: legacy pre-auth Links stay ownerless (NULL) and still
    # redirect, but never surface in any dashboard ("start empty", ADR 0009).
    # Every newly-minted Link is stamped with its creator (login-to-create).
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, default=None
    )
    # Optional owner-authored name for this Link (ADR 0010). Nullable, non-unique;
    # trimmed and capped at 100 chars at the router edge before persisting.
    label: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String, nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)


class LinkCustomization(Base):
    """Persisted customization for a Link's QR image (ADR 0011).

    One row per Link (1:1 enforced by UNIQUE on link_id).  Created or replaced
    on each successful PUT /api/qr/{token}/customization.

    - ``style_json``   — serialized style recipe (colours, dot style, etc.).
    - ``image_key``    — storage key of the composite QR PNG (immutable versioned key).
    - ``logo_key``     — storage key of the uploaded logo, nullable.
    - ``updated_at``   — wall-clock time of the last successful PUT.
    """

    __tablename__ = "link_customizations"
    __table_args__ = (
        UniqueConstraint("link_id", name="uq_link_customizations_link_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("links.id", ondelete="CASCADE"), nullable=False
    )
    style_json: Mapped[str] = mapped_column(Text, nullable=False)
    image_key: Mapped[str] = mapped_column(String, nullable=False)
    logo_key: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
