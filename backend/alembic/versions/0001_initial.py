"""Create the Product PostgreSQL core schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SCHEMA = "app"

RUN_STATUSES = (
    "queued",
    "running",
    "waiting_human",
    "succeeded",
    "blocked",
    "failed",
    "cancelled",
)

TASK_COMMAND_TYPES = (
    "submit",
    "respond",
    "cancel_run",
    "cancel_task",
    "retry",
    "fork",
)

TASK_COMMAND_STATUSES = (
    "pending",
    "dispatching",
    "dispatched",
    "rejected",
    "cancelled",
    "failed",
)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def _tenant_id(table_name: str) -> sa.Column:
    return sa.Column(
        "tenant_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(
            f"{PRODUCT_SCHEMA}.tenants.id",
            name=f"fk_{table_name}_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )


def _workspace_id(table_name: str) -> sa.Column:
    return sa.Column(
        "workspace_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(
            f"{PRODUCT_SCHEMA}.workspaces.id",
            name=f"fk_{table_name}_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        nullable=False,
    )


def _user_id(table_name: str, column_name: str, *, ondelete: str = "RESTRICT") -> sa.Column:
    return sa.Column(
        column_name,
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(
            f"{PRODUCT_SCHEMA}.users.id",
            name=f"fk_{table_name}_{column_name}_users",
            ondelete=ondelete,
        ),
        nullable=False,
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _primary_key(table_name: str) -> sa.PrimaryKeyConstraint:
    return sa.PrimaryKeyConstraint("id", name=f"pk_{table_name}")


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema(PRODUCT_SCHEMA, if_not_exists=True))

    op.create_table(
        "tenants",
        _id(),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        _created_at(),
        _updated_at(),
        _primary_key("tenants"),
        sa.UniqueConstraint("external_id", name="uq_tenants_external_id"),
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "users",
        _id(),
        _tenant_id("users"),
        sa.Column("external_subject", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        _created_at(),
        _updated_at(),
        _primary_key("users"),
        sa.UniqueConstraint("external_subject", name="uq_users_external_subject"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_users_tenant_subject",
        "users",
        ["tenant_id", "external_subject"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "workspaces",
        _id(),
        _tenant_id("workspaces"),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        _created_at(),
        _updated_at(),
        _primary_key("workspaces"),
        sa.UniqueConstraint("external_id", name="uq_workspaces_external_id"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_workspaces_tenant_external",
        "workspaces",
        ["tenant_id", "external_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "memberships",
        _id(),
        _tenant_id("memberships"),
        _workspace_id("memberships"),
        _user_id("memberships", "user_id", ondelete="CASCADE"),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _created_at(),
        _updated_at(),
        _primary_key("memberships"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_memberships_workspace_user",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_memberships_tenant_workspace_user",
        "memberships",
        ["tenant_id", "workspace_id", "user_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "threads",
        _id(),
        _tenant_id("threads"),
        _workspace_id("threads"),
        _user_id("threads", "owner_user_id"),
        sa.Column("official_thread_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _created_at(),
        _updated_at(),
        _primary_key("threads"),
        sa.UniqueConstraint(
            "workspace_id",
            "official_thread_id",
            name="uq_threads_workspace_official_thread",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_threads_tenant_workspace_created",
        "threads",
        ["tenant_id", "workspace_id", "created_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_threads_tenant_workspace_owner",
        "threads",
        ["tenant_id", "workspace_id", "owner_user_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "tasks",
        _id(),
        _tenant_id("tasks"),
        _workspace_id("tasks"),
        _user_id("tasks", "owner_user_id"),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.threads.id",
                name="fk_tasks_thread_id_threads",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        _primary_key("tasks"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_tasks_tenant_workspace_status",
        "tasks",
        ["tenant_id", "workspace_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_tasks_tenant_workspace_thread",
        "tasks",
        ["tenant_id", "workspace_id", "thread_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "runs",
        _id(),
        _tenant_id("runs"),
        _workspace_id("runs"),
        _user_id("runs", "owner_user_id"),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.threads.id",
                name="fk_runs_thread_id_threads",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_runs_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("official_run_id", sa.String(length=255), nullable=True),
        sa.Column("checkpoint_id", sa.String(length=255), nullable=True),
        sa.Column(
            "input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "output_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            f"status IN ({_sql_values(RUN_STATUSES)})",
            name="ck_runs_status",
        ),
        _primary_key("runs"),
        sa.UniqueConstraint("task_id", "attempt", name="uq_runs_task_attempt"),
        sa.UniqueConstraint("official_run_id", name="uq_runs_official_run_id"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_runs_tenant_workspace_status",
        "runs",
        ["tenant_id", "workspace_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_runs_tenant_workspace_task",
        "runs",
        ["tenant_id", "workspace_id", "task_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "market_snapshots",
        _id(),
        _tenant_id("market_snapshots"),
        _workspace_id("market_snapshots"),
        _user_id("market_snapshots", "owner_user_id"),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_market_snapshots_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.runs.id",
                name="fk_market_snapshots_run_id_runs",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        _primary_key("market_snapshots"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_market_snapshots_tenant_workspace_run",
        "market_snapshots",
        ["tenant_id", "workspace_id", "run_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "web_evidence",
        _id(),
        _tenant_id("web_evidence"),
        _workspace_id("web_evidence"),
        _user_id("web_evidence", "owner_user_id"),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_web_evidence_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.runs.id",
                name="fk_web_evidence_run_id_runs",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _primary_key("web_evidence"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_web_evidence_tenant_workspace_run",
        "web_evidence",
        ["tenant_id", "workspace_id", "run_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "artifacts",
        _id(),
        _tenant_id("artifacts"),
        _workspace_id("artifacts"),
        _user_id("artifacts", "owner_user_id"),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_artifacts_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column(
            "latest_version_number",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        _created_at(),
        _updated_at(),
        _primary_key("artifacts"),
        sa.UniqueConstraint("task_id", "artifact_type", name="uq_artifacts_task_type"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_artifacts_tenant_workspace_task",
        "artifacts",
        ["tenant_id", "workspace_id", "task_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "artifact_versions",
        _id(),
        _tenant_id("artifact_versions"),
        _workspace_id("artifact_versions"),
        _user_id("artifact_versions", "owner_user_id"),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.artifacts.id",
                name="fk_artifact_versions_artifact_id_artifacts",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_artifact_versions_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.runs.id",
                name="fk_artifact_versions_run_id_runs",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created_at(),
        _primary_key("artifact_versions"),
        sa.UniqueConstraint(
            "artifact_id",
            "version_number",
            name="uq_artifact_versions_artifact_version",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_artifact_versions_tenant_workspace_artifact",
        "artifact_versions",
        ["tenant_id", "workspace_id", "artifact_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "decisions",
        _id(),
        _tenant_id("decisions"),
        _workspace_id("decisions"),
        _user_id("decisions", "owner_user_id"),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.artifacts.id",
                name="fk_decisions_artifact_id_artifacts",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "artifact_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.artifact_versions.id",
                name="fk_decisions_artifact_version_id_artifact_versions",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_decisions_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.runs.id",
                name="fk_decisions_run_id_runs",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("decision_version", sa.Integer(), nullable=False),
        sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "evidence_verdict",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "risk_verdict",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        _created_at(),
        _primary_key("decisions"),
        sa.UniqueConstraint(
            "artifact_version_id",
            name="uq_decisions_artifact_version",
        ),
        sa.UniqueConstraint(
            "artifact_id",
            "decision_version",
            name="uq_decisions_artifact_decision_version",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_decisions_tenant_workspace_task",
        "decisions",
        ["tenant_id", "workspace_id", "task_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "task_commands",
        _id(),
        _tenant_id("task_commands"),
        _workspace_id("task_commands"),
        _user_id("task_commands", "actor_user_id"),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_task_commands_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.threads.id",
                name="fk_task_commands_thread_id_threads",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("command_type", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("official_run_id", sa.String(length=255), nullable=True),
        sa.Column("official_command_id", sa.String(length=255), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            f"command_type IN ({_sql_values(TASK_COMMAND_TYPES)})",
            name="ck_task_commands_command_type",
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(TASK_COMMAND_STATUSES)})",
            name="ck_task_commands_status",
        ),
        _primary_key("task_commands"),
        sa.UniqueConstraint(
            "thread_id",
            "sequence",
            name="uq_task_commands_thread_sequence",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_task_commands_workspace_idempotency",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_task_commands_tenant_workspace_status",
        "task_commands",
        ["tenant_id", "workspace_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_task_commands_thread_status_sequence",
        "task_commands",
        ["thread_id", "status", "sequence"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    for table_name in (
        "task_commands",
        "decisions",
        "artifact_versions",
        "artifacts",
        "web_evidence",
        "market_snapshots",
        "runs",
        "tasks",
        "threads",
        "memberships",
        "workspaces",
        "users",
        "tenants",
    ):
        op.drop_table(table_name, schema=PRODUCT_SCHEMA)
