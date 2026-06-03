"""links.label: optional per-token owner label

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-03

Adds a nullable ``label`` column (max 100 chars) to ``links`` for ADR 0010
(per-token labels). Labels are owner-private, non-unique, and optional — no
unique constraint is added. The column is capped at the router edge before
persisting so no CHECK constraint is needed at the DB layer.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("links", sa.Column("label", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("links", "label")
