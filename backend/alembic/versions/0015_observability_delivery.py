"""Add the Product observability delivery ledger."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015_observability_delivery"
down_revision = "0014_watchlist"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "observability_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "event_type",
            sa.String(length=64),
            server_default=sa.text("'root_trace'"),
            nullable=False,
        ),
        sa.Column(
            "event_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("delivery_key", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column(
            "sampled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("skip_reason", sa.String(length=128)),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "fence_token",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=255)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("verification_deadline", sa.DateTime(timezone=True)),
        sa.Column("provider_trace_id", sa.String(length=255)),
        sa.Column("last_stage", sa.String(length=32)),
        sa.Column("last_retry_state", sa.String(length=32)),
        sa.Column("last_error_code", sa.String(length=128)),
        sa.Column("last_error_type", sa.String(length=128)),
        sa.Column("last_error_summary", sa.String(length=500)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
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
            "provider IN ('langsmith', 'langfuse')",
            name="ck_observability_deliveries_provider",
        ),
        sa.CheckConstraint(
            "status IN ('not_requested', 'planned', 'leased', 'verifying', "
            "'verified', 'failed_retryable', 'failed_terminal', 'unknown')",
            name="ck_observability_deliveries_status",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_observability_deliveries_event_version",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_observability_deliveries_attempt_count",
        ),
        sa.CheckConstraint(
            "fence_token >= 0",
            name="ck_observability_deliveries_fence_token",
        ),
        sa.CheckConstraint(
            "(status IN ('leased', 'verifying')) = "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_observability_deliveries_active_lease",
        ),
        sa.CheckConstraint(
            "(status = 'not_requested') = (skip_reason IS NOT NULL)",
            name="ck_observability_deliveries_skip_reason",
        ),
        sa.CheckConstraint(
            "(status = 'verified') = "
            "(provider_trace_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_observability_deliveries_verified_receipt",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id"],
            [
                f"{PRODUCT_SCHEMA}.tasks.tenant_id",
                f"{PRODUCT_SCHEMA}.tasks.workspace_id",
                f"{PRODUCT_SCHEMA}.tasks.owner_user_id",
                f"{PRODUCT_SCHEMA}.tasks.id",
            ],
            name="fk_observability_deliveries_task_scope",
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
            name="fk_observability_deliveries_run_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "task_id",
            "run_id",
            "provider",
            "event_type",
            "event_version",
            name="uq_observability_deliveries_logical_key",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "delivery_key",
            name="uq_observability_deliveries_delivery_key",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_observability_deliveries_scope_run",
        "observability_deliveries",
        ["tenant_id", "workspace_id", "task_id", "run_id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_observability_deliveries_due",
        "observability_deliveries",
        ["status", "next_attempt_at", "created_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_observability_deliveries_lease",
        "observability_deliveries",
        ["status", "lease_expires_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_observability_deliveries_provider_status",
        "observability_deliveries",
        ["tenant_id", "workspace_id", "provider", "status"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_observability_deliveries_provider_status",
        table_name="observability_deliveries",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_observability_deliveries_lease",
        table_name="observability_deliveries",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_observability_deliveries_due",
        table_name="observability_deliveries",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_observability_deliveries_scope_run",
        table_name="observability_deliveries",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("observability_deliveries", schema=PRODUCT_SCHEMA)
