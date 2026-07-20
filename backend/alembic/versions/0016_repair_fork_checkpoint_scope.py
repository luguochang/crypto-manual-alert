"""Repair fork lineage scope to include the source checkpoint."""

from alembic import op
import sqlalchemy as sa


revision = "0016_repair_fork_scope"
down_revision = "0015_observability_delivery"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"
CONSTRAINT_NAME = "fk_runs_fork_source_scope"
UNIQUE_CONSTRAINT_NAME = "uq_runs_fork_checkpoint_scope"


def _has_constraint(name: str, *, kind: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if kind == "foreignkey":
        return any(
            item["name"] == name
            for item in inspector.get_foreign_keys("runs", schema=PRODUCT_SCHEMA)
        )
    if kind == "unique":
        return any(
            item["name"] == name
            for item in inspector.get_unique_constraints("runs", schema=PRODUCT_SCHEMA)
        )
    raise ValueError(f"unsupported constraint kind: {kind}")


def upgrade() -> None:
    if not _has_constraint(UNIQUE_CONSTRAINT_NAME, kind="unique"):
        op.create_unique_constraint(
            UNIQUE_CONSTRAINT_NAME,
            "runs",
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "id",
                "checkpoint_id",
            ],
            schema=PRODUCT_SCHEMA,
        )
    if _has_constraint(CONSTRAINT_NAME, kind="foreignkey"):
        op.drop_constraint(
            CONSTRAINT_NAME,
            "runs",
            schema=PRODUCT_SCHEMA,
            type_="foreignkey",
        )
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "runs",
        "runs",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "forked_from_run_id",
            "forked_from_checkpoint_id",
        ],
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            "checkpoint_id",
        ],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    if _has_constraint(CONSTRAINT_NAME, kind="foreignkey"):
        op.drop_constraint(
            CONSTRAINT_NAME,
            "runs",
            schema=PRODUCT_SCHEMA,
            type_="foreignkey",
        )
    if not _has_constraint(UNIQUE_CONSTRAINT_NAME, kind="unique"):
        op.create_unique_constraint(
            UNIQUE_CONSTRAINT_NAME,
            "runs",
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "id",
                "checkpoint_id",
            ],
            schema=PRODUCT_SCHEMA,
        )
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "runs",
        "runs",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "forked_from_run_id",
            "forked_from_checkpoint_id",
        ],
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            "checkpoint_id",
        ],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="RESTRICT",
    )
