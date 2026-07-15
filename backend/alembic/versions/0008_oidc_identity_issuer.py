"""Bind Product users to a stable OIDC issuer and subject pair."""

from alembic import op
import sqlalchemy as sa


revision = "0008_oidc_identity_issuer"
down_revision = "0007_interrupt_pauses"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "identity_issuer",
            sa.String(length=512),
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index("ix_users_tenant_subject", table_name="users", schema=PRODUCT_SCHEMA)
    op.drop_constraint(
        "uq_users_tenant_external_subject",
        "users",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_users_tenant_issuer_subject",
        "users",
        ["tenant_id", "identity_issuer", "external_subject"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_users_tenant_issuer_subject",
        "users",
        ["tenant_id", "identity_issuer", "external_subject"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_users_tenant_issuer_subject",
        table_name="users",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "uq_users_tenant_issuer_subject",
        "users",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_users_tenant_external_subject",
        "users",
        ["tenant_id", "external_subject"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_users_tenant_subject",
        "users",
        ["tenant_id", "external_subject"],
        schema=PRODUCT_SCHEMA,
    )
    op.drop_column("users", "identity_issuer", schema=PRODUCT_SCHEMA)
