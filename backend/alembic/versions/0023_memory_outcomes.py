"""Add product Memory controls and exchange-native Outcome observations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023_memory_outcomes"
down_revision = "0022_data_lifecycle"
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
        "memory_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("session_id", sa.String(255), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("memory_key", sa.String(128), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("scope IN ('session', 'workspace')", name="ck_memory_entries_scope"),
        sa.CheckConstraint(
            "purpose IN ('session_clarification', 'profile', 'strategy_config', 'process_lesson', 'event', 'badcase')",
            name="ck_memory_entries_purpose",
        ),
        sa.ForeignKeyConstraint(["source_artifact_id"], [f"{PRODUCT_SCHEMA}.artifacts.id"], ondelete="SET NULL"),
        *_scope_foreign_keys("memory_entries"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "owner_user_id", "session_id", "purpose", "memory_key",
            name="uq_memory_entries_actor_session_purpose_key",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_memory_entries_actor_enabled_expiry", "memory_entries",
        ["tenant_id", "workspace_id", "owner_user_id", "enabled", "expires_at"], schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_memory_entries_workspace_purpose", "memory_entries",
        ["tenant_id", "workspace_id", "purpose"], schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "memory_deletion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_memory_deletion_jobs_status"),
        sa.ForeignKeyConstraint(["memory_id"], [f"{PRODUCT_SCHEMA}.memory_entries.id"], ondelete="CASCADE"),
        *_scope_foreign_keys("memory_deletion_jobs"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "owner_user_id", "idempotency_key", name="uq_memory_deletion_jobs_actor_idempotency"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_memory_deletion_jobs_dispatch", "memory_deletion_jobs",
        ["status", "requested_at"], schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "outcome_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_scope_columns(),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("baseline", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'scheduled'"), nullable=False),
        sa.Column("predicted_probability", sa.Numeric(12, 10), nullable=True),
        sa.Column("realized_label", sa.Numeric(12, 10), nullable=True),
        sa.Column("horizon", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), server_default=sa.text("'exchange_native'"), nullable=False),
        sa.Column("maturation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("close_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("high_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("low_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("fees", sa.Numeric(30, 12), server_default=sa.text("0"), nullable=False),
        sa.Column("slippage", sa.Numeric(30, 12), server_default=sa.text("0"), nullable=False),
        sa.Column("funding", sa.Numeric(30, 12), server_default=sa.text("0"), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('scheduled', 'pending', 'matured', 'insufficient', 'failed')", name="ck_outcome_observations_status"),
        sa.CheckConstraint("baseline IN ('decision', 'hold', 'no_trade')", name="ck_outcome_observations_baseline"),
        sa.CheckConstraint("source = 'exchange_native'", name="ck_outcome_observations_source"),
        sa.ForeignKeyConstraint(["artifact_version_id"], [f"{PRODUCT_SCHEMA}.artifact_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], [f"{PRODUCT_SCHEMA}.tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], [f"{PRODUCT_SCHEMA}.runs.id"], ondelete="RESTRICT"),
        *_scope_foreign_keys("outcome_observations"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "owner_user_id", "artifact_version_id", "horizon", name="uq_outcome_observations_artifact_horizon"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index("ix_outcome_observations_maturation", "outcome_observations", ["status", "maturation_at"], schema=PRODUCT_SCHEMA)
    op.create_index("ix_outcome_observations_actor_status", "outcome_observations", ["tenant_id", "workspace_id", "owner_user_id", "status"], schema=PRODUCT_SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_outcome_observations_actor_status", table_name="outcome_observations", schema=PRODUCT_SCHEMA)
    op.drop_index("ix_outcome_observations_maturation", table_name="outcome_observations", schema=PRODUCT_SCHEMA)
    op.drop_table("outcome_observations", schema=PRODUCT_SCHEMA)
    op.drop_index("ix_memory_deletion_jobs_dispatch", table_name="memory_deletion_jobs", schema=PRODUCT_SCHEMA)
    op.drop_table("memory_deletion_jobs", schema=PRODUCT_SCHEMA)
    op.drop_index("ix_memory_entries_workspace_purpose", table_name="memory_entries", schema=PRODUCT_SCHEMA)
    op.drop_index("ix_memory_entries_actor_enabled_expiry", table_name="memory_entries", schema=PRODUCT_SCHEMA)
    op.drop_table("memory_entries", schema=PRODUCT_SCHEMA)
