"""Persist auditable Product Run checkpoint fork lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_run_fork_lineage"
down_revision = "0008_oidc_identity_issuer"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("forked_from_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column("forked_from_checkpoint_id", sa.String(length=255), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_runs_fork_checkpoint_scope",
        "runs",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            "checkpoint_id",
        ],
        schema=PRODUCT_SCHEMA,
    )
    op.create_foreign_key(
        "fk_runs_fork_source_scope",
        "runs",
        "runs",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "forked_from_run_id",
            "forked_from_checkpoint_id",
        ],
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            "checkpoint_id",
        ],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_runs_fork_not_self",
        "runs",
        "forked_from_run_id IS NULL OR forked_from_run_id <> id",
        schema=PRODUCT_SCHEMA,
    )
    op.create_check_constraint(
        "ck_runs_fork_lineage_complete",
        "runs",
        "(forked_from_run_id IS NULL) = (forked_from_checkpoint_id IS NULL)",
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_runs_tenant_workspace_fork_source",
        "runs",
        ["tenant_id", "workspace_id", "forked_from_run_id"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runs_tenant_workspace_fork_source",
        table_name="runs",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "ck_runs_fork_lineage_complete",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_runs_fork_not_self",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "fk_runs_fork_source_scope",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_runs_fork_checkpoint_scope",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.drop_column("runs", "forked_from_checkpoint_id", schema=PRODUCT_SCHEMA)
    op.drop_column("runs", "forked_from_run_id", schema=PRODUCT_SCHEMA)
