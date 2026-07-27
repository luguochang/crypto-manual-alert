"""Retain append-only lifecycle receipts after parent data deletion."""

from alembic import op


revision = "0031_lifecycle_receipt_retention"
down_revision = "0030_lifecycle_receipts"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"
TABLE_NAME = "data_deletion_receipts"

_PARENT_FOREIGN_KEYS = (
    (
        "fk_data_deletion_receipts_deletion_job_id_data_deletion_jobs",
        "deletion_job_id",
        "data_deletion_jobs",
    ),
    ("fk_data_deletion_receipts_tenant_id_tenants", "tenant_id", "tenants"),
    (
        "fk_data_deletion_receipts_workspace_id_workspaces",
        "workspace_id",
        "workspaces",
    ),
    ("fk_data_deletion_receipts_owner_user_id_users", "owner_user_id", "users"),
)


def upgrade() -> None:
    for constraint_name, _column_name, _parent_table in _PARENT_FOREIGN_KEYS:
        op.drop_constraint(
            constraint_name,
            TABLE_NAME,
            schema=PRODUCT_SCHEMA,
            type_="foreignkey",
        )


def downgrade() -> None:
    for constraint_name, column_name, parent_table in _PARENT_FOREIGN_KEYS:
        op.create_foreign_key(
            constraint_name,
            TABLE_NAME,
            parent_table,
            [column_name],
            ["id"],
            source_schema=PRODUCT_SCHEMA,
            referent_schema=PRODUCT_SCHEMA,
            ondelete="RESTRICT",
        )
