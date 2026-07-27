"""Extend entitlements and add immutable usage reconciliation receipts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0028_usage_governance"
down_revision = "0027_improvement_review_runtime"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "workspace_entitlements",
        sa.Column(
            "allowed_task_types",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                "'[\"market_analysis\",\"deep_research\",\"candidate_review\"]'::jsonb"
            ),
            nullable=False,
        ),
        schema=PRODUCT_SCHEMA,
    )
    entitlement_columns = (
        ("monthly_agent_admission_limit", sa.Integer(), "10000"),
        ("monthly_model_token_limit", sa.BigInteger(), "50000000"),
        ("monthly_search_request_limit", sa.Integer(), "100000"),
        ("monthly_runtime_millisecond_limit", sa.BigInteger(), "3600000000"),
        ("storage_byte_limit", sa.BigInteger(), "10737418240"),
        ("max_retention_days", sa.Integer(), "3650"),
    )
    for name, column_type, default in entitlement_columns:
        op.add_column(
            "workspace_entitlements",
            sa.Column(
                name,
                column_type,
                server_default=sa.text(default),
                nullable=False,
            ),
            schema=PRODUCT_SCHEMA,
        )
        op.create_check_constraint(
            f"ck_workspace_entitlements_{name}",
            "workspace_entitlements",
            f"{name} >= {1 if name == 'max_retention_days' else 0}",
            schema=PRODUCT_SCHEMA,
        )

    for name, length, default in (
        ("operation_type", 64, "monitor_trigger"),
        ("resource_type", 64, "monitor_trigger"),
    ):
        op.add_column(
            "usage_ledger_entries",
            sa.Column(
                name,
                sa.String(length=length),
                server_default=sa.text(f"'{default}'"),
                nullable=False,
            ),
            schema=PRODUCT_SCHEMA,
        )
    op.add_column(
        "usage_ledger_entries",
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "usage_ledger_entries",
        sa.Column("source_receipt_hash", sa.String(length=64), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.create_check_constraint(
        "ck_usage_ledger_entries_source_receipt_hash",
        "usage_ledger_entries",
        "source_receipt_hash IS NULL OR length(source_receipt_hash) = 64",
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_usage_ledger_entries_tenant_workspace_resource",
        "usage_ledger_entries",
        ["tenant_id", "workspace_id", "resource_type", "resource_id"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "usage_reconciliations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "source_totals", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "ledger_totals", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "discrepancies", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("ledger_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "repair_applied",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('reconciled', 'discrepant')",
            name="ck_usage_reconciliations_status",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64 AND length(ledger_hash) = 64",
            name="ck_usage_reconciliations_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_usage_reconciliations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_usage_reconciliations_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_usage_reconciliations_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "period_start",
            "source_hash",
            "ledger_hash",
            name="uq_usage_reconciliations_snapshot",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_usage_reconciliations_tenant_workspace_period",
        "usage_reconciliations",
        ["tenant_id", "workspace_id", "period_start", "created_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app.reject_usage_reconciliation_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'usage_reconciliations is append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER usage_reconciliations_append_only
            BEFORE UPDATE OR DELETE ON app.usage_reconciliations
            FOR EACH ROW EXECUTE FUNCTION app.reject_usage_reconciliation_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS usage_reconciliations_append_only "
            "ON app.usage_reconciliations"
        )
    )
    op.execute(
        sa.text("DROP FUNCTION IF EXISTS app.reject_usage_reconciliation_mutation()")
    )
    op.drop_index(
        "ix_usage_reconciliations_tenant_workspace_period",
        table_name="usage_reconciliations",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("usage_reconciliations", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_usage_ledger_entries_tenant_workspace_resource",
        table_name="usage_ledger_entries",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "ck_usage_ledger_entries_source_receipt_hash",
        "usage_ledger_entries",
        type_="check",
        schema=PRODUCT_SCHEMA,
    )
    for name in (
        "source_receipt_hash",
        "resource_id",
        "resource_type",
        "operation_type",
    ):
        op.drop_column("usage_ledger_entries", name, schema=PRODUCT_SCHEMA)
    for name in (
        "max_retention_days",
        "storage_byte_limit",
        "monthly_runtime_millisecond_limit",
        "monthly_search_request_limit",
        "monthly_model_token_limit",
        "monthly_agent_admission_limit",
    ):
        op.drop_constraint(
            f"ck_workspace_entitlements_{name}",
            "workspace_entitlements",
            type_="check",
            schema=PRODUCT_SCHEMA,
        )
        op.drop_column("workspace_entitlements", name, schema=PRODUCT_SCHEMA)
    op.drop_column(
        "workspace_entitlements", "allowed_task_types", schema=PRODUCT_SCHEMA
    )
