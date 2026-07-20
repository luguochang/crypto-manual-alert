"""Add durable retry lineage to Product Runs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_run_retry_lineage"
down_revision = "0011_notification_destinations"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("retry_of_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_runs_retry_of_run",
        "runs",
        ["retry_of_run_id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_foreign_key(
        "fk_runs_retry_scope",
        "runs",
        "runs",
        ["tenant_id", "workspace_id", "owner_user_id", "task_id", "retry_of_run_id"],
        ["tenant_id", "workspace_id", "owner_user_id", "task_id", "id"],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_runs_retry_not_self",
        "runs",
        "retry_of_run_id IS NULL OR retry_of_run_id <> id",
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_runs_tenant_workspace_retry",
        "runs",
        ["tenant_id", "workspace_id", "retry_of_run_id"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runs_tenant_workspace_retry",
        table_name="runs",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "ck_runs_retry_not_self",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "fk_runs_retry_scope",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_runs_retry_of_run",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.drop_column("runs", "retry_of_run_id", schema=PRODUCT_SCHEMA)
