"""Add owner-scoped Product feedback."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_feedback"
down_revision = "0012_run_retry_lineage"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating IN ('positive', 'negative')",
            name="ck_feedback_rating",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            [f"{PRODUCT_SCHEMA}.tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{PRODUCT_SCHEMA}.runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"],
            [f"{PRODUCT_SCHEMA}.artifact_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_feedback_workspace_idempotency",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "run_id",
            name="uq_feedback_owner_run",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_feedback_tenant_workspace_run",
        "feedback",
        ["tenant_id", "workspace_id", "run_id"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feedback_tenant_workspace_run",
        table_name="feedback",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("feedback", schema=PRODUCT_SCHEMA)
