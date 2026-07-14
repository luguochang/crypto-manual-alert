"""Persist the official assistant identifier for Product runs.

Revision ID: 0004_official_assistant_id
Revises: 0003_tenant_actor_ids
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_official_assistant_id"
down_revision: str | None = "0003_tenant_actor_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("official_assistant_id", sa.String(length=255), nullable=True),
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(
        "runs",
        "official_assistant_id",
        schema=PRODUCT_SCHEMA,
    )
