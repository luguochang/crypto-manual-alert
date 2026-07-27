"""Add signed webhook integrations, nonce replay protection and audit."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0029_webhook_security"
down_revision = "0028_usage_governance"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "webhook_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("active_key_id", sa.String(length=64), nullable=False),
        sa.Column(
            "accepted_key_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
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
            "jsonb_typeof(accepted_key_ids) = 'array'",
            name="ck_webhook_integrations_key_ids_array",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_webhook_integrations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_webhook_integrations_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_webhook_integrations_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "name",
            name="uq_webhook_integrations_actor_name",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_webhook_integrations_actor_id",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_webhook_integrations_tenant_workspace_active",
        "webhook_integrations",
        ["tenant_id", "workspace_id", "active"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "webhook_replay_nonces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_webhook_replay_nonces_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_webhook_replay_nonces_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_webhook_replay_nonces_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "integration_id"],
            [
                f"{PRODUCT_SCHEMA}.webhook_integrations.tenant_id",
                f"{PRODUCT_SCHEMA}.webhook_integrations.workspace_id",
                f"{PRODUCT_SCHEMA}.webhook_integrations.owner_user_id",
                f"{PRODUCT_SCHEMA}.webhook_integrations.id",
            ],
            name="fk_webhook_replay_nonces_integration_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_id",
            "nonce_hash",
            name="uq_webhook_replay_nonces_integration_nonce",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_webhook_replay_nonces_actor_expiry",
        "webhook_replay_nonces",
        ["tenant_id", "workspace_id", "expires_at"],
        schema=PRODUCT_SCHEMA,
    )

    op.create_table(
        "webhook_delivery_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'rejected', 'replayed')",
            name="ck_webhook_delivery_audits_status",
        ),
        sa.CheckConstraint(
            "length(nonce_hash) = 64 AND length(payload_hash) = 64",
            name="ck_webhook_delivery_audits_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_webhook_delivery_audits_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_webhook_delivery_audits_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_webhook_delivery_audits_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            [f"{PRODUCT_SCHEMA}.webhook_integrations.id"],
            name="fk_webhook_delivery_audits_integration_id_webhook_integrations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_webhook_delivery_audits_integration_received",
        "webhook_delivery_audits",
        ["integration_id", "received_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_webhook_delivery_audits_actor_status",
        "webhook_delivery_audits",
        ["tenant_id", "workspace_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app.reject_webhook_audit_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'webhook_delivery_audits is append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER webhook_delivery_audits_append_only
            BEFORE UPDATE OR DELETE ON app.webhook_delivery_audits
            FOR EACH ROW EXECUTE FUNCTION app.reject_webhook_audit_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS webhook_delivery_audits_append_only "
            "ON app.webhook_delivery_audits"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS app.reject_webhook_audit_mutation()"))
    op.drop_index(
        "ix_webhook_delivery_audits_actor_status",
        table_name="webhook_delivery_audits",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_webhook_delivery_audits_integration_received",
        table_name="webhook_delivery_audits",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("webhook_delivery_audits", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_webhook_replay_nonces_actor_expiry",
        table_name="webhook_replay_nonces",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("webhook_replay_nonces", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_webhook_integrations_tenant_workspace_active",
        table_name="webhook_integrations",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("webhook_integrations", schema=PRODUCT_SCHEMA)
