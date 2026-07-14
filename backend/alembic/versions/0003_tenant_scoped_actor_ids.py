"""Scope user and workspace external identifiers to a tenant.

Revision ID: 0003_tenant_actor_ids
Revises: 0002_analysis_idempotency
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0003_tenant_actor_ids"
down_revision: str | None = "0002_analysis_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.drop_constraint(
        "uq_users_external_subject",
        "users",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "uq_workspaces_external_id",
        "workspaces",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_users_tenant_external_subject",
        "users",
        ["tenant_id", "external_subject"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_workspaces_tenant_external_id",
        "workspaces",
        ["tenant_id", "external_id"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_workspaces_tenant_external_id",
        "workspaces",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "uq_users_tenant_external_subject",
        "users",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_workspaces_external_id",
        "workspaces",
        ["external_id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_users_external_subject",
        "users",
        ["external_subject"],
        schema=PRODUCT_SCHEMA,
    )
