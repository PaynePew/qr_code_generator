"""link_customization: server-side QR customization storage (ADR 0011)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-03

Adds ``link_customizations`` table (1:1 with ``links``) that persists the QR
customization recipe (style_json), the composite image storage key (image_key),
an optional logo storage key (logo_key), and updated_at.

The UNIQUE constraint on ``link_id`` enforces the 1:1 relationship at the DB
layer; CASCADE DELETE keeps orphans from accumulating when a Link is removed.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "link_customizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("style_json", sa.Text(), nullable=False),
        sa.Column("image_key", sa.String(), nullable=False),
        sa.Column("logo_key", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["link_id"], ["links.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_id", name="uq_link_customizations_link_id"),
    )


def downgrade() -> None:
    op.drop_table("link_customizations")
