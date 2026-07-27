"""Add durable worker lease fields for Memory and Outcome jobs."""

from alembic import op
import sqlalchemy as sa


revision = "0024_memory_outcome_leases"
down_revision = "0023_memory_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("memory_deletion_jobs", "outcome_observations"):
        op.add_column(
            table,
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            schema="app",
        )
        op.add_column(table, sa.Column("lease_owner", sa.String(255), nullable=True), schema="app")
        op.add_column(
            table,
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            schema="app",
        )
        op.add_column(
            table,
            sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
            schema="app",
        )


def downgrade() -> None:
    for table in ("outcome_observations", "memory_deletion_jobs"):
        for column in ("attempt", "lease_expires_at", "lease_owner", "available_at"):
            op.drop_column(table, column, schema="app")
