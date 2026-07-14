"""Persist interrupt projections and Run resume lineage.

Revision ID: 0006_interrupt_projection
Revises: 0005_run_recovery_state
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_interrupt_projection"
down_revision: str | None = "0005_run_recovery_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SCHEMA = "app"
INTERRUPT_STATUSES = (
    "pending",
    "responding",
    "resolved",
    "expired",
    "cancelled",
)
REVIEW_POLICIES = (
    "bypass",
    "required",
)
OBSERVED_TERMINAL_STATUSES = (
    "error",
    "success",
    "timeout",
)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "review_policy",
            sa.String(length=32),
            server_default=sa.text("'bypass'"),
            nullable=False,
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_check_constraint(
        "ck_workspaces_review_policy",
        "workspaces",
        f"review_policy IN ({_sql_values(REVIEW_POLICIES)})",
        schema=PRODUCT_SCHEMA,
    )

    op.add_column(
        "runs",
        sa.Column(
            "resume_of_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column(
            "observed_terminal_status",
            sa.String(length=32),
            nullable=True,
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_check_constraint(
        "ck_runs_observed_terminal_status",
        "runs",
        "observed_terminal_status IS NULL OR "
        f"observed_terminal_status IN ({_sql_values(OBSERVED_TERMINAL_STATUSES)})",
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_runs_projection_scope",
        "runs",
        ["tenant_id", "workspace_id", "owner_user_id", "task_id", "id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_runs_resume_of_run",
        "runs",
        ["resume_of_run_id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_check_constraint(
        "ck_runs_resume_not_self",
        "runs",
        "resume_of_run_id IS NULL OR resume_of_run_id <> id",
        schema=PRODUCT_SCHEMA,
    )
    op.create_foreign_key(
        "fk_runs_resume_scope",
        "runs",
        "runs",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "resume_of_run_id",
        ],
        ["tenant_id", "workspace_id", "owner_user_id", "task_id", "id"],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_runs_tenant_workspace_resume",
        "runs",
        ["tenant_id", "workspace_id", "resume_of_run_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "interrupt_inbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tenants.id",
                name="fk_interrupt_inbox_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.workspaces.id",
                name="fk_interrupt_inbox_workspace_id_workspaces",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.users.id",
                name="fk_interrupt_inbox_owner_user_id_users",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_interrupt_inbox_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("official_interrupt_id", sa.String(length=255), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=255), nullable=False),
        sa.Column(
            "response_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "response",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interrupt_inbox"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_interrupt_inbox_run_scope",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "official_interrupt_id",
            "checkpoint_id",
            "response_version",
            name="uq_interrupt_inbox_scope_response",
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(INTERRUPT_STATUSES)})",
            name="ck_interrupt_inbox_status",
        ),
        sa.CheckConstraint(
            "response_version >= 1",
            name="ck_interrupt_inbox_response_version",
        ),
        sa.CheckConstraint(
            "responded_at IS NULL OR response IS NOT NULL",
            name="ck_interrupt_inbox_response_timestamp",
        ),
        sa.CheckConstraint(
            "status <> 'pending' OR (response IS NULL AND responded_at IS NULL)",
            name="ck_interrupt_inbox_pending_empty",
        ),
        sa.CheckConstraint(
            "status NOT IN ('responding', 'resolved') OR response IS NOT NULL",
            name="ck_interrupt_inbox_active_response",
        ),
        sa.CheckConstraint(
            "status <> 'resolved' OR responded_at IS NOT NULL",
            name="ck_interrupt_inbox_resolved_timestamp",
        ),
        sa.CheckConstraint(
            "status <> 'expired' OR expires_at IS NOT NULL",
            name="ck_interrupt_inbox_expired_timestamp",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_interrupt_inbox_scope_status_expiry",
        "interrupt_inbox",
        ["tenant_id", "workspace_id", "owner_user_id", "status", "expires_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_interrupt_inbox_scope_task_status",
        "interrupt_inbox",
        ["tenant_id", "workspace_id", "task_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_interrupt_inbox_scope_run_status",
        "interrupt_inbox",
        ["tenant_id", "workspace_id", "run_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_interrupt_inbox_checkpoint_interrupt",
        "interrupt_inbox",
        ["checkpoint_id", "official_interrupt_id"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interrupt_inbox_checkpoint_interrupt",
        table_name="interrupt_inbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_interrupt_inbox_scope_run_status",
        table_name="interrupt_inbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_interrupt_inbox_scope_task_status",
        table_name="interrupt_inbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_interrupt_inbox_scope_status_expiry",
        table_name="interrupt_inbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("interrupt_inbox", schema=PRODUCT_SCHEMA)

    op.drop_index(
        "ix_runs_tenant_workspace_resume",
        table_name="runs",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "fk_runs_resume_scope",
        "runs",
        type_="foreignkey",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "ck_runs_resume_not_self",
        "runs",
        type_="check",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "uq_runs_resume_of_run",
        "runs",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "uq_runs_projection_scope",
        "runs",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "ck_runs_observed_terminal_status",
        "runs",
        type_="check",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_column(
        "runs",
        "observed_terminal_status",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_column("runs", "resume_of_run_id", schema=PRODUCT_SCHEMA)

    op.drop_constraint(
        "ck_workspaces_review_policy",
        "workspaces",
        type_="check",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_column("workspaces", "review_policy", schema=PRODUCT_SCHEMA)
