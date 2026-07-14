"""Persist idempotent analysis admission keys.

Revision ID: 0002_analysis_idempotency
Revises: 0001_initial
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_analysis_idempotency"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SCHEMA = "app"
CONSTRAINT_NAME = "uq_tasks_actor_workspace_idempotency"


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "tasks",
        sa.Column("request_payload_hash", sa.String(length=64), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.execute(
        sa.text(
            "UPDATE app.tasks "
            "SET idempotency_key = 'legacy:' || id::text, "
            "request_payload_hash = md5(request_payload::text)"
        )
    )
    op.alter_column(
        "tasks",
        "idempotency_key",
        nullable=False,
        schema=PRODUCT_SCHEMA,
    )
    op.alter_column(
        "tasks",
        "request_payload_hash",
        nullable=False,
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "tasks",
        ["tenant_id", "workspace_id", "owner_user_id", "idempotency_key"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        CONSTRAINT_NAME,
        "tasks",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_column("tasks", "request_payload_hash", schema=PRODUCT_SCHEMA)
    op.drop_column("tasks", "idempotency_key", schema=PRODUCT_SCHEMA)
