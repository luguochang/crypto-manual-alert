"""Bind improvement reviews to official Aegra interrupt receipts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027_improvement_review_runtime"
down_revision = "0026_improvement_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "improvement_reviews",
        "task_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        schema="app",
    )
    op.add_column(
        "improvement_reviews",
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        schema="app",
    )
    op.add_column(
        "improvement_reviews",
        sa.Column("official_assistant_id", sa.String(255), nullable=True),
        schema="app",
    )
    op.add_column(
        "improvement_reviews",
        sa.Column("official_thread_id", sa.String(255), nullable=True),
        schema="app",
    )
    op.add_column(
        "improvement_reviews",
        sa.Column("official_run_id", sa.String(255), nullable=True),
        schema="app",
    )
    op.add_column(
        "improvement_reviews",
        sa.Column("official_interrupt_id", sa.String(255), nullable=True),
        schema="app",
    )
    op.add_column(
        "improvement_reviews",
        sa.Column(
            "interrupt_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema="app",
    )
    op.add_column(
        "improvement_reviews",
        sa.Column(
            "checkpoint",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema="app",
    )
    op.execute(
        "UPDATE app.improvement_reviews "
        "SET idempotency_key = 'legacy:' || id::text "
        "WHERE idempotency_key IS NULL"
    )
    op.alter_column(
        "improvement_reviews",
        "idempotency_key",
        existing_type=sa.String(255),
        nullable=False,
        schema="app",
    )
    op.create_unique_constraint(
        "uq_improvement_reviews_actor_idempotency",
        "improvement_reviews",
        ["tenant_id", "workspace_id", "owner_user_id", "idempotency_key"],
        schema="app",
    )
    op.create_unique_constraint(
        "uq_improvement_reviews_official_thread",
        "improvement_reviews",
        ["official_thread_id"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_improvement_reviews_official_thread",
        "improvement_reviews",
        type_="unique",
        schema="app",
    )
    op.drop_constraint(
        "uq_improvement_reviews_actor_idempotency",
        "improvement_reviews",
        type_="unique",
        schema="app",
    )
    for column in (
        "checkpoint",
        "interrupt_payload",
        "official_interrupt_id",
        "official_run_id",
        "official_thread_id",
        "official_assistant_id",
        "idempotency_key",
    ):
        op.drop_column("improvement_reviews", column, schema="app")
    op.alter_column(
        "improvement_reviews",
        "task_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        schema="app",
    )
