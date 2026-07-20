"""Add workspace monitor entitlements and immutable usage accounting."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0020_entitlements_usage"
down_revision = "0019_ddgs_provenance"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "workspace_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("active_monitor_limit", sa.Integer(), nullable=False),
        sa.Column("min_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_tasks", sa.Integer(), nullable=False),
        sa.Column("monthly_trigger_limit", sa.Integer(), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
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
            "active_monitor_limit >= 0",
            name="ck_workspace_entitlements_active_monitor_limit",
        ),
        sa.CheckConstraint(
            "min_interval_seconds >= 1",
            name="ck_workspace_entitlements_min_interval_seconds",
        ),
        sa.CheckConstraint(
            "max_concurrent_tasks >= 1",
            name="ck_workspace_entitlements_max_concurrent_tasks",
        ),
        sa.CheckConstraint(
            "monthly_trigger_limit >= 0",
            name="ck_workspace_entitlements_monthly_trigger_limit",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_workspace_entitlements_valid_window",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_workspace_entitlements_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_workspace_entitlements_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_entitlements_workspace"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            name="uq_workspace_entitlements_tenant_workspace",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_workspace_entitlements_tenant_workspace_active",
        "workspace_entitlements",
        ["tenant_id", "workspace_id", "active"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "usage_ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entitlement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "unit", sa.String(length=32), server_default=sa.text("'trigger'"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity >= 1", name="ck_usage_ledger_entries_quantity"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_usage_ledger_entries_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_usage_ledger_entries_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_usage_ledger_entries_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id"],
            [f"{PRODUCT_SCHEMA}.workspace_entitlements.id"],
            name="fk_usage_ledger_entries_entitlement_id_workspace_entitlements",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "idempotency_key",
            name="uq_usage_ledger_entries_workspace_idempotency",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_usage_ledger_entries_tenant_workspace_period",
        "usage_ledger_entries",
        ["tenant_id", "workspace_id", "period_start"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_usage_ledger_entries_tenant_workspace_monitor",
        "usage_ledger_entries",
        ["tenant_id", "workspace_id", "monitor_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app.reject_usage_ledger_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'usage_ledger_entries is append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER usage_ledger_entries_append_only
            BEFORE UPDATE OR DELETE ON app.usage_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION app.reject_usage_ledger_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS usage_ledger_entries_append_only "
            "ON app.usage_ledger_entries"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS app.reject_usage_ledger_mutation()"))
    op.drop_index(
        "ix_usage_ledger_entries_tenant_workspace_monitor",
        table_name="usage_ledger_entries",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_usage_ledger_entries_tenant_workspace_period",
        table_name="usage_ledger_entries",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("usage_ledger_entries", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_workspace_entitlements_tenant_workspace_active",
        table_name="workspace_entitlements",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("workspace_entitlements", schema=PRODUCT_SCHEMA)
