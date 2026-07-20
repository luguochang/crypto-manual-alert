"""Add actor-scoped retention, export and deletion jobs.

The migration owns only Product-side lifecycle state.  It deliberately does not
create tables for LangSmith, Langfuse, checkpoint, object-storage or log
systems: those systems are represented by explicit ``pending_external`` state
until a separately configured adapter can provide an auditable receipt.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_data_lifecycle"
down_revision = "0021_scheduled_monitors"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def _scope_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    )


def _scope_foreign_keys(table: str) -> tuple[sa.ForeignKeyConstraint, ...]:
    return (
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{PRODUCT_SCHEMA}.tenants.id"],
            name=f"fk_{table}_tenant_id_tenants", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name=f"fk_{table}_workspace_id_workspaces", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], [f"{PRODUCT_SCHEMA}.users.id"],
            name=f"fk_{table}_owner_user_id_users", ondelete="RESTRICT",
        ),
    )


def upgrade() -> None:
    op.create_table(
        "data_lifecycle_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("product_retention_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("artifact_retention_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("task_retention_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("run_retention_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("decision_retention_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("usage_retention_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("completed_checkpoint_retention_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("technical_projection_retention_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("log_retention_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("backup_retention_days", sa.Integer(), server_default=sa.text("35"), nullable=False),
        sa.Column("retain_raw_prompt", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("retain_raw_response", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("legal_hold_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("legal_hold_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "product_retention_days > 0 AND artifact_retention_days > 0 AND "
            "task_retention_days > 0 AND run_retention_days > 0 AND "
            "decision_retention_days > 0 AND usage_retention_days > 0 AND "
            "completed_checkpoint_retention_days > 0 AND "
            "technical_projection_retention_days > 0 AND log_retention_days > 0 AND "
            "backup_retention_days > 0",
            name="ck_data_lifecycle_policies_positive_retention",
        ),
        sa.CheckConstraint(
            "(legal_hold_active = false AND legal_hold_reason IS NULL) OR "
            "(legal_hold_active = true AND legal_hold_reason IS NOT NULL AND "
            "length(trim(legal_hold_reason)) > 0)",
            name="ck_data_lifecycle_policies_legal_hold_reason",
        ),
        *_scope_foreign_keys("data_lifecycle_policies"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id",
            name="uq_data_lifecycle_policies_actor_scope",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_data_lifecycle_policies_tenant_workspace_owner",
        "data_lifecycle_policies",
        ["tenant_id", "workspace_id", "owner_user_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "data_export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("scope", sa.String(length=32), server_default=sa.text("'user_data'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifest_version", sa.Integer(), nullable=True),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("manifest_hash", sa.String(length=64), nullable=True),
        sa.Column("bundle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_data_export_jobs_status"),
        sa.CheckConstraint("scope = 'user_data'", name="ck_data_export_jobs_scope"),
        sa.CheckConstraint("attempt >= 0", name="ck_data_export_jobs_attempt"),
        *_scope_foreign_keys("data_export_jobs"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "idempotency_key",
            name="uq_data_export_jobs_actor_idempotency",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_data_export_jobs_dispatch", "data_export_jobs",
        ["status", "available_at", "lease_expires_at"], schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_data_export_jobs_actor_created", "data_export_jobs",
        ["tenant_id", "workspace_id", "owner_user_id", "created_at"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "data_deletion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("scope", sa.String(length=32), server_default=sa.text("'user_data'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("confirmation_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_hold_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("legal_hold_reason", sa.String(length=500), nullable=True),
        sa.Column("system_status", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("external_deletion_reference", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'pending_external', 'succeeded', 'blocked_legal_hold', 'failed')",
            name="ck_data_deletion_jobs_status",
        ),
        sa.CheckConstraint("scope = 'user_data'", name="ck_data_deletion_jobs_scope"),
        sa.CheckConstraint("attempt >= 0", name="ck_data_deletion_jobs_attempt"),
        *_scope_foreign_keys("data_deletion_jobs"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "idempotency_key",
            name="uq_data_deletion_jobs_actor_idempotency",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_data_deletion_jobs_dispatch", "data_deletion_jobs",
        ["status", "lease_expires_at", "requested_at"], schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_data_deletion_jobs_actor_requested", "data_deletion_jobs",
        ["tenant_id", "workspace_id", "owner_user_id", "requested_at"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_deletion_jobs_actor_requested",
        table_name="data_deletion_jobs", schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_data_deletion_jobs_dispatch",
        table_name="data_deletion_jobs", schema=PRODUCT_SCHEMA,
    )
    op.drop_table("data_deletion_jobs", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_data_export_jobs_actor_created",
        table_name="data_export_jobs", schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_data_export_jobs_dispatch",
        table_name="data_export_jobs", schema=PRODUCT_SCHEMA,
    )
    op.drop_table("data_export_jobs", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_data_lifecycle_policies_tenant_workspace_owner",
        table_name="data_lifecycle_policies", schema=PRODUCT_SCHEMA,
    )
    op.drop_table("data_lifecycle_policies", schema=PRODUCT_SCHEMA)
