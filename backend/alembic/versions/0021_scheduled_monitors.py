"""Add scheduled monitor definitions, cron outbox and trigger history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0021_scheduled_monitors"
down_revision = "0020_entitlements_usage"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "monitor_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("run_task_type", sa.String(length=64), nullable=False),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("task_template", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("admission_idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("cron_schedule", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quiet_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("schedule_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("desired_revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("applied_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cron_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("official_cron_id", sa.String(length=255), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "run_task_type IN ('market_analysis', 'deep_research')",
            name="ck_monitor_definitions_run_task_type",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(condition) = 'object' AND condition ? 'kind' AND "
            "jsonb_typeof(condition->'kind') = 'string' AND "
            "length(condition->>'kind') > 0",
            name="ck_monitor_definitions_condition_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(task_template) = 'object' AND "
            "task_template ? 'task_type' AND task_template ? 'symbol' AND "
            "task_template ? 'horizon' AND task_template ? 'query_text' AND "
            "jsonb_typeof(task_template->'task_type') = 'string' AND "
            "jsonb_typeof(task_template->'symbol') = 'string' AND "
            "jsonb_typeof(task_template->'horizon') = 'string' AND "
            "jsonb_typeof(task_template->'query_text') = 'string' AND "
            "NOT (task_template ? 'source_artifact_version_id') AND "
            "task_template->>'task_type' = run_task_type AND "
            "((task_template->>'task_type' = 'market_analysis' AND "
            "task_template ? 'notify' AND "
            "jsonb_typeof(task_template->'notify') = 'boolean') OR "
            "(task_template->>'task_type' = 'deep_research' AND "
            "NOT (task_template ? 'notify')))" ,
            name="ck_monitor_definitions_task_template",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'degraded', 'expired', 'disabled')",
            name="ck_monitor_definitions_status",
        ),
        sa.CheckConstraint(
            "schedule_version >= 1 AND desired_revision >= 1 AND "
            "applied_revision >= 0 AND version >= 1",
            name="ck_monitor_definitions_revisions",
        ),
        sa.CheckConstraint(
            "quiet_hours IS NULL OR (jsonb_typeof(quiet_hours) = 'object' AND "
            "quiet_hours ? 'start' AND quiet_hours ? 'end' AND "
            "jsonb_typeof(quiet_hours->'start') = 'string' AND "
            "jsonb_typeof(quiet_hours->'end') = 'string')",
            name="ck_monitor_definitions_quiet_hours_object",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_monitor_definitions_tenant_id_tenants", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_monitor_definitions_workspace_id_workspaces", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_monitor_definitions_owner_user_id_users", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], [f"{PRODUCT_SCHEMA}.artifacts.id"],
            name="fk_monitor_definitions_artifact_id_artifacts", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], [f"{PRODUCT_SCHEMA}.artifact_versions.id"],
            name="fk_monitor_definitions_artifact_version_id_artifact_versions", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "id",
            name="uq_monitor_definitions_actor_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "name",
            name="uq_monitor_definitions_owner_name",
        ),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "admission_idempotency_key",
            name="uq_monitor_definitions_admission_idempotency",
        ),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "cron_binding_id",
            name="uq_monitor_definitions_cron_binding_scope",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_monitor_definitions_tenant_workspace_status", "monitor_definitions",
        ["tenant_id", "workspace_id", "status"], schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_monitor_definitions_actor_next_run", "monitor_definitions",
        ["tenant_id", "workspace_id", "owner_user_id", "status", "next_run_at"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "monitor_destinations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_monitor_destinations_tenant_id_tenants", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_monitor_destinations_workspace_id_workspaces", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_monitor_destinations_owner_user_id_users", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_definitions.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.id",
            ], name="fk_monitor_destinations_monitor_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "destination_id"],
            [
                f"{PRODUCT_SCHEMA}.notification_destinations.tenant_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.workspace_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.owner_user_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.id",
            ], name="fk_monitor_destinations_destination_scope", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "monitor_id", "destination_id",
            name="uq_monitor_destinations_binding",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_monitor_destinations_tenant_workspace_monitor", "monitor_destinations",
        ["tenant_id", "workspace_id", "monitor_id"], schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "monitor_cron_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_type", sa.String(length=32), nullable=False),
        sa.Column("desired_revision", sa.Integer(), nullable=False),
        sa.Column("request_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fence_token", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "command_type IN ('create', 'update', 'pause', 'resume', 'delete')",
            name="ck_monitor_cron_commands_command_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'leased', 'succeeded', 'failed')",
            name="ck_monitor_cron_commands_status",
        ),
        sa.CheckConstraint(
            "attempt >= 0 AND fence_token >= 0 AND desired_revision >= 1",
            name="ck_monitor_cron_commands_lease_counters",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ? 'monitor_id' AND "
            "payload ? 'schedule_version' AND payload ? 'cron_binding_id' AND "
            "NOT (payload ?| ARRAY['task_template', 'condition', 'query_text', "
            "'symbol', 'horizon', 'request_payload', 'command_id', "
            "'official_cron_id', 'official_run_id', 'official_thread_id'])",
            name="ck_monitor_cron_commands_control_payload_only",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_monitor_cron_commands_tenant_id_tenants", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_monitor_cron_commands_workspace_id_workspaces", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_monitor_cron_commands_owner_user_id_users", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_definitions.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.id",
            ], name="fk_monitor_cron_commands_monitor_scope", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "idempotency_key",
            name="uq_monitor_cron_commands_owner_idempotency",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_monitor_cron_commands_dispatch", "monitor_cron_commands",
        ["status", "available_at", "lease_expires_at"], schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_monitor_cron_commands_tenant_workspace_monitor", "monitor_cron_commands",
        ["tenant_id", "workspace_id", "monitor_id"], schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "monitor_triggers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("official_cron_id", sa.String(length=255), nullable=True),
        sa.Column("official_run_id", sa.String(length=255), nullable=True),
        sa.Column("official_thread_id", sa.String(length=255), nullable=True),
        sa.Column("manual_stable_key", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('manual', 'cron')", name="ck_monitor_triggers_kind"
        ),
        sa.CheckConstraint(
            "status IN ('received', 'suppressed', 'admitted', 'failed')",
            name="ck_monitor_triggers_status",
        ),
        sa.CheckConstraint(
            "schedule_version >= 1", name="ck_monitor_triggers_schedule_version"
        ),
        sa.CheckConstraint(
            "(kind = 'cron' AND official_run_id IS NOT NULL AND manual_stable_key IS NULL) OR "
            "(kind = 'manual' AND manual_stable_key IS NOT NULL AND official_run_id IS NULL)",
            name="ck_monitor_triggers_identity_by_kind",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_monitor_triggers_tenant_id_tenants", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_monitor_triggers_workspace_id_workspaces", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_monitor_triggers_owner_user_id_users", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_definitions.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.id",
            ], name="fk_monitor_triggers_monitor_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id"],
            [
                f"{PRODUCT_SCHEMA}.tasks.tenant_id",
                f"{PRODUCT_SCHEMA}.tasks.workspace_id",
                f"{PRODUCT_SCHEMA}.tasks.owner_user_id",
                f"{PRODUCT_SCHEMA}.tasks.id",
            ], name="fk_monitor_triggers_task_scope", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], [f"{PRODUCT_SCHEMA}.threads.id"],
            name="fk_monitor_triggers_thread_id_threads", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "id",
            name="uq_monitor_triggers_actor_scope",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_monitor_triggers_tenant_workspace_monitor_received", "monitor_triggers",
        ["tenant_id", "workspace_id", "monitor_id", "received_at"], schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_monitor_triggers_tenant_workspace_task", "monitor_triggers",
        ["tenant_id", "workspace_id", "task_id"], schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "uq_monitor_triggers_official_run", "monitor_triggers",
        ["tenant_id", "workspace_id", "monitor_id", "official_run_id"],
        unique=True, schema=PRODUCT_SCHEMA,
        postgresql_where=sa.text("official_run_id IS NOT NULL"),
    )
    op.create_index(
        "uq_monitor_triggers_manual_stable_key", "monitor_triggers",
        ["tenant_id", "workspace_id", "monitor_id", "manual_stable_key"],
        unique=True, schema=PRODUCT_SCHEMA,
        postgresql_where=sa.text("manual_stable_key IS NOT NULL"),
    )

    op.create_foreign_key(
        "fk_usage_ledger_entries_monitor_id_monitor_definitions",
        "usage_ledger_entries", "monitor_definitions", ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
        ["tenant_id", "workspace_id", "owner_user_id", "id"], source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA, ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_usage_ledger_entries_trigger_id_monitor_triggers",
        "usage_ledger_entries", "monitor_triggers", ["tenant_id", "workspace_id", "owner_user_id", "trigger_id"],
        ["tenant_id", "workspace_id", "owner_user_id", "id"], source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA, ondelete="RESTRICT",
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app.reject_monitor_trigger_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'monitor_triggers is append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER monitor_triggers_append_only
            BEFORE UPDATE OR DELETE ON app.monitor_triggers
            FOR EACH ROW EXECUTE FUNCTION app.reject_monitor_trigger_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS monitor_triggers_append_only ON app.monitor_triggers"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS app.reject_monitor_trigger_mutation()"))
    op.drop_constraint(
        "fk_usage_ledger_entries_trigger_id_monitor_triggers",
        "usage_ledger_entries", type_="foreignkey", schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "fk_usage_ledger_entries_monitor_id_monitor_definitions",
        "usage_ledger_entries", type_="foreignkey", schema=PRODUCT_SCHEMA,
    )
    op.drop_table("monitor_triggers", schema=PRODUCT_SCHEMA)
    op.drop_table("monitor_cron_commands", schema=PRODUCT_SCHEMA)
    op.drop_table("monitor_destinations", schema=PRODUCT_SCHEMA)
    op.drop_table("monitor_definitions", schema=PRODUCT_SCHEMA)
