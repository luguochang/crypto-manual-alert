"""Add the durable Product domain event ledger."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_domain_events"
down_revision = "0016_repair_fork_scope"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"
EVENT_TYPES = (
    "market.snapshot.committed",
    "research.evidence.committed",
    "agent.output.committed",
    "evidence.verdict.committed",
    "risk.verdict.committed",
    "artifact.committed",
    "notification.planned",
    "run.terminal",
)


def upgrade() -> None:
    event_types = ", ".join(f"'{value}'" for value in EVENT_TYPES)
    op.create_table(
        "domain_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("official_run_id", sa.String(length=255)),
        sa.Column("checkpoint_id", sa.String(length=255)),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("payload_ref", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"event_type IN ({event_types})",
            name="ck_domain_events_type",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_domain_events_sequence"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{PRODUCT_SCHEMA}.tenants.id"],
            name="fk_domain_events_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{PRODUCT_SCHEMA}.workspaces.id"],
            name="fk_domain_events_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            [f"{PRODUCT_SCHEMA}.users.id"],
            name="fk_domain_events_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            [f"{PRODUCT_SCHEMA}.threads.id"],
            name="fk_domain_events_thread_id_threads",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            [f"{PRODUCT_SCHEMA}.tasks.id"],
            name="fk_domain_events_task_id_tasks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_domain_events_run_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "event_type",
            name="uq_domain_events_run_type",
        ),
        sa.UniqueConstraint(
            "thread_id",
            "sequence",
            name="uq_domain_events_thread_sequence",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_domain_events_scope_run",
        "domain_events",
        ["tenant_id", "workspace_id", "task_id", "run_id"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_domain_events_scope_type_created",
        "domain_events",
        ["tenant_id", "workspace_id", "event_type", "created_at"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_domain_events_scope_type_created",
        table_name="domain_events",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_domain_events_scope_run",
        table_name="domain_events",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("domain_events", schema=PRODUCT_SCHEMA)
