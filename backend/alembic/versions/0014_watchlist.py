"""Add owner-scoped Product watchlist items."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_watchlist"
down_revision = "0013_feedback"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{PRODUCT_SCHEMA}.tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], [f"{PRODUCT_SCHEMA}.workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], [f"{PRODUCT_SCHEMA}.users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "symbol",
            name="uq_watchlist_owner_symbol",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_watchlist_tenant_workspace_owner",
        "watchlist_items",
        ["tenant_id", "workspace_id", "owner_user_id"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_watchlist_tenant_workspace_owner",
        table_name="watchlist_items",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("watchlist_items", schema=PRODUCT_SCHEMA)
