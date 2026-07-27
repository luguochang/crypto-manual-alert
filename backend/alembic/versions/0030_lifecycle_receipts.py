"""Add append-only per-system lifecycle receipts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0030_lifecycle_receipts"
down_revision = "0029_webhook_security"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "data_deletion_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deletion_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("system", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("survivor_count", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reference",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("receipt_hash", sa.String(length=64), nullable=False),
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
            "system IN ('product_db', 'checkpoint', 'store', 'object_storage', "
            "'search', 'langsmith', 'langfuse', 'logs', 'backups')",
            name="ck_data_deletion_receipts_system",
        ),
        sa.CheckConstraint(
            "phase IN ('delete', 'survivor_scan', 'retention_queue')",
            name="ck_data_deletion_receipts_phase",
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'not_applicable', 'pending_external', "
            "'pending_expiry', 'failed')",
            name="ck_data_deletion_receipts_outcome",
        ),
        sa.CheckConstraint(
            "attempt >= 1 AND affected_count >= 0 AND survivor_count >= 0",
            name="ck_data_deletion_receipts_counts",
        ),
        sa.CheckConstraint(
            "length(receipt_hash) = 64",
            name="ck_data_deletion_receipts_hash",
        ),
        sa.ForeignKeyConstraint(
            ["deletion_job_id"],
            [f"{PRODUCT_SCHEMA}.data_deletion_jobs.id"],
            name="fk_data_deletion_receipts_deletion_job_id_data_deletion_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_data_deletion_receipts_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_data_deletion_receipts_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_data_deletion_receipts_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "deletion_job_id",
            "system",
            "phase",
            "attempt",
            name="uq_data_deletion_receipts_job_system_phase_attempt",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_data_deletion_receipts_job_created",
        "data_deletion_receipts",
        ["deletion_job_id", "created_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_data_deletion_receipts_actor_system",
        "data_deletion_receipts",
        ["tenant_id", "workspace_id", "owner_user_id", "system", "phase"],
        schema=PRODUCT_SCHEMA,
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app.reject_data_deletion_receipt_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'data_deletion_receipts is append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER data_deletion_receipts_append_only
            BEFORE UPDATE OR DELETE ON app.data_deletion_receipts
            FOR EACH ROW EXECUTE FUNCTION app.reject_data_deletion_receipt_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS data_deletion_receipts_append_only "
            "ON app.data_deletion_receipts"
        )
    )
    op.execute(
        sa.text("DROP FUNCTION IF EXISTS app.reject_data_deletion_receipt_mutation()")
    )
    op.drop_index(
        "ix_data_deletion_receipts_actor_system",
        table_name="data_deletion_receipts",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_data_deletion_receipts_job_created",
        table_name="data_deletion_receipts",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("data_deletion_receipts", schema=PRODUCT_SCHEMA)
