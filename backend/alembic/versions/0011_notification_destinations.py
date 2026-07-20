"""Add encrypted owner-scoped notification destinations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_notification_destinations"
down_revision = "0010_notification_outbox"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "notification_destinations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'disabled'"),
            nullable=False,
        ),
        sa.Column("credential_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("credential_key_version", sa.String(length=64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_notification_destinations"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_notification_destinations_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_notification_destinations_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_notification_destinations_owner_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "channel",
            name="uq_notification_destinations_owner_channel",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_notification_destinations_scope",
        ),
        sa.CheckConstraint(
            "status IN ('enabled', 'disabled')",
            name="ck_notification_destinations_status",
        ),
        sa.CheckConstraint(
            "channel IN ('bark')",
            name="ck_notification_destinations_channel",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_notification_destinations_scope_status",
        "notification_destinations",
        ["tenant_id", "workspace_id", "owner_user_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "notification_outbox",
        sa.Column("destination_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=PRODUCT_SCHEMA,
    )
    op.create_foreign_key(
        "fk_notification_outbox_destination_scope",
        "notification_outbox",
        "notification_destinations",
        ["tenant_id", "workspace_id", "owner_user_id", "destination_id"],
        ["tenant_id", "workspace_id", "owner_user_id", "id"],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_notification_outbox_destination",
        "notification_outbox",
        ["destination_id", "status", "created_at"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_outbox_destination",
        table_name="notification_outbox",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "fk_notification_outbox_destination_scope",
        "notification_outbox",
        schema=PRODUCT_SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("notification_outbox", "destination_id", schema=PRODUCT_SCHEMA)
    op.drop_index(
        "ix_notification_destinations_scope_status",
        table_name="notification_destinations",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("notification_destinations", schema=PRODUCT_SCHEMA)
