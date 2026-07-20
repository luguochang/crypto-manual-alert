"""Add the reliable notification outbox and delivery-attempt ledger."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_notification_outbox"
down_revision = "0009_run_fork_lineage"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_tasks_notification_scope",
        "tasks",
        ["tenant_id", "workspace_id", "owner_user_id", "id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_artifacts_notification_scope",
        "artifacts",
        ["tenant_id", "workspace_id", "owner_user_id", "task_id", "id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_artifact_versions_notification_scope",
        "artifact_versions",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "artifact_id",
            "id",
        ],
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_decisions_notification_scope",
        "decisions",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "artifact_id",
            "artifact_version_id",
            "decision_version",
            "id",
        ],
        schema=PRODUCT_SCHEMA,
    )
    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("decision_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fence_token",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "manual_resend_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("manual_resend_requested_by", sa.String(length=255), nullable=True),
        sa.Column("manual_resend_reason", sa.String(length=500), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_notification_outbox"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_notification_outbox_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_notification_outbox_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_notification_outbox_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            [f"{PRODUCT_SCHEMA}.tasks.id"],
            name="fk_notification_outbox_task_id_tasks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{PRODUCT_SCHEMA}.runs.id"],
            name="fk_notification_outbox_run_id_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            [f"{PRODUCT_SCHEMA}.artifacts.id"],
            name="fk_notification_outbox_artifact_id_artifacts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"],
            [f"{PRODUCT_SCHEMA}.artifact_versions.id"],
            name="fk_notification_outbox_artifact_version_id_artifact_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            [f"{PRODUCT_SCHEMA}.decisions.id"],
            name="fk_notification_outbox_decision_id_decisions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id"],
            [
                f"{PRODUCT_SCHEMA}.tasks.tenant_id",
                f"{PRODUCT_SCHEMA}.tasks.workspace_id",
                f"{PRODUCT_SCHEMA}.tasks.owner_user_id",
                f"{PRODUCT_SCHEMA}.tasks.id",
            ],
            name="fk_notification_outbox_task_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_notification_outbox_run_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "artifact_id"],
            [
                f"{PRODUCT_SCHEMA}.artifacts.tenant_id",
                f"{PRODUCT_SCHEMA}.artifacts.workspace_id",
                f"{PRODUCT_SCHEMA}.artifacts.owner_user_id",
                f"{PRODUCT_SCHEMA}.artifacts.task_id",
                f"{PRODUCT_SCHEMA}.artifacts.id",
            ],
            name="fk_notification_outbox_artifact_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "run_id",
                "artifact_id",
                "artifact_version_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.artifact_versions.tenant_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.workspace_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.owner_user_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.task_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.run_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.artifact_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.id",
            ],
            name="fk_notification_outbox_artifact_version_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "run_id",
                "artifact_id",
                "artifact_version_id",
                "decision_version",
                "decision_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.decisions.tenant_id",
                f"{PRODUCT_SCHEMA}.decisions.workspace_id",
                f"{PRODUCT_SCHEMA}.decisions.owner_user_id",
                f"{PRODUCT_SCHEMA}.decisions.task_id",
                f"{PRODUCT_SCHEMA}.decisions.run_id",
                f"{PRODUCT_SCHEMA}.decisions.artifact_id",
                f"{PRODUCT_SCHEMA}.decisions.artifact_version_id",
                f"{PRODUCT_SCHEMA}.decisions.decision_version",
                f"{PRODUCT_SCHEMA}.decisions.id",
            ],
            name="fk_notification_outbox_decision_scope",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "task_id",
            "channel",
            "type",
            "decision_version",
            name="uq_notification_outbox_logical_key",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            name="uq_notification_outbox_attempt_scope",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'leased', 'sending', 'delivered', "
            "'failed_retryable', 'failed_terminal', 'unknown')",
            name="ck_notification_outbox_status",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 5",
            name="ck_notification_outbox_attempt_count",
        ),
        sa.CheckConstraint(
            "fence_token >= 0",
            name="ck_notification_outbox_fence_token",
        ),
        sa.CheckConstraint(
            "(status IN ('leased', 'sending')) = "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_notification_outbox_active_lease",
        ),
        sa.CheckConstraint(
            "(manual_resend_requested_at IS NULL AND "
            "manual_resend_requested_by IS NULL AND manual_resend_reason IS NULL) OR "
            "(manual_resend_requested_at IS NOT NULL AND "
            "manual_resend_requested_by IS NOT NULL)",
            name="ck_notification_outbox_manual_resend_request",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_notification_outbox_status_available",
        "notification_outbox",
        ["status", "available_at", "created_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_notification_outbox_lease_expiry",
        "notification_outbox",
        ["status", "lease_expires_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_notification_outbox_manual_resend",
        "notification_outbox",
        ["manual_resend_requested_at", "created_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_notification_outbox_scope_task",
        "notification_outbox",
        ["tenant_id", "workspace_id", "task_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "notification_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("fence_token", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column(
            "delay_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "cost_units",
            sa.Numeric(precision=18, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "result",
            sa.String(length=32),
            server_default=sa.text("'leased'"),
            nullable=False,
        ),
        sa.Column("provider_receipt", sa.String(length=512), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_notification_attempts"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_notification_attempts_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_notification_attempts_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_notification_attempts_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            [f"{PRODUCT_SCHEMA}.tasks.id"],
            name="fk_notification_attempts_task_id_tasks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"],
            [f"{PRODUCT_SCHEMA}.notification_outbox.id"],
            name="fk_notification_attempts_outbox_id_notification_outbox",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "outbox_id"],
            [
                f"{PRODUCT_SCHEMA}.notification_outbox.tenant_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.workspace_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.owner_user_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.task_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.id",
            ],
            name="fk_notification_attempts_outbox_scope",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "outbox_id",
            "attempt_number",
            name="uq_notification_attempts_outbox_number",
        ),
        sa.CheckConstraint(
            "trigger IN ('automatic', 'manual')",
            name="ck_notification_attempts_trigger",
        ),
        sa.CheckConstraint(
            "result IN ('leased', 'sending', 'delivered', 'failed_retryable', "
            "'failed_terminal', 'unknown', 'released')",
            name="ck_notification_attempts_result",
        ),
        sa.CheckConstraint(
            "attempt_number BETWEEN 1 AND 5",
            name="ck_notification_attempts_attempt_number",
        ),
        sa.CheckConstraint(
            "fence_token >= 1",
            name="ck_notification_attempts_fence_token",
        ),
        sa.CheckConstraint(
            "delay_seconds >= 0 AND "
            "(retry_after_seconds IS NULL OR retry_after_seconds >= 0) AND "
            "cost_units >= 0",
            name="ck_notification_attempts_nonnegative_metrics",
        ),
        sa.CheckConstraint(
            "(trigger = 'automatic' AND requested_by IS NULL) OR "
            "(trigger = 'manual' AND requested_by IS NOT NULL)",
            name="ck_notification_attempts_manual_actor",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_notification_attempts_scope_task",
        "notification_attempts",
        ["tenant_id", "workspace_id", "task_id", "created_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_notification_attempts_outbox_created",
        "notification_attempts",
        ["outbox_id", "created_at"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_attempts_outbox_created",
        table_name="notification_attempts",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_notification_attempts_scope_task",
        table_name="notification_attempts",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("notification_attempts", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_notification_outbox_scope_task",
        table_name="notification_outbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_notification_outbox_manual_resend",
        table_name="notification_outbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_notification_outbox_lease_expiry",
        table_name="notification_outbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_notification_outbox_status_available",
        table_name="notification_outbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("notification_outbox", schema=PRODUCT_SCHEMA)
    op.drop_constraint(
        "uq_decisions_notification_scope",
        "decisions",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "uq_artifact_versions_notification_scope",
        "artifact_versions",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "uq_artifacts_notification_scope",
        "artifacts",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "uq_tasks_notification_scope",
        "tasks",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
