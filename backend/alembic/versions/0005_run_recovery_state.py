"""Persist Product Run reconciliation and projection state.

Revision ID: 0005_run_recovery_state
Revises: 0004_official_assistant_id
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_run_recovery_state"
down_revision: str | None = "0004_official_assistant_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SCHEMA = "app"
RECONCILIATION_INDEX = "ix_runs_status_reconcile_deadline"


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("reconciliation_deadline_at", sa.DateTime(timezone=True)),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column(
            "projection_fence",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column("terminal_output_hash", sa.String(length=64)),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        schema=PRODUCT_SCHEMA,
    )
    op.execute(
        sa.text(
            "UPDATE app.runs "
            "SET reconciliation_deadline_at = started_at + interval '15 minutes' "
            "WHERE reconciliation_deadline_at IS NULL AND started_at IS NOT NULL "
            "AND status IN ('queued', 'running')"
        )
    )
    op.create_index(
        RECONCILIATION_INDEX,
        "runs",
        ["status", "reconciliation_deadline_at"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(RECONCILIATION_INDEX, table_name="runs", schema=PRODUCT_SCHEMA)
    op.drop_column("runs", "cancel_requested_at", schema=PRODUCT_SCHEMA)
    op.drop_column("runs", "terminal_output_hash", schema=PRODUCT_SCHEMA)
    op.drop_column("runs", "projection_fence", schema=PRODUCT_SCHEMA)
    op.drop_column("runs", "reconciliation_deadline_at", schema=PRODUCT_SCHEMA)
