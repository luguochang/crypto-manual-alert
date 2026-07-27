"""Add durable Postmortem and Frozen Replay records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0025_improvement_cases"
down_revision = "0024_memory_outcome_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_memory_deletion_jobs_actor_status",
        "memory_deletion_jobs",
        ["tenant_id", "workspace_id", "owner_user_id", "status"],
        schema="app",
    )
    op.create_table(
        "postmortem_cases",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), server_default=sa.text("'open'"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("expected_behavior", sa.Text(), nullable=True),
        sa.Column("actual_behavior", sa.Text(), nullable=True),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "category IN ('negative_feedback','operator_postmortem','evaluation_badcase')",
            name="ck_postmortem_cases_category",
        ),
        sa.CheckConstraint(
            "status IN ('open','frozen','closed')",
            name="ck_postmortem_cases_status",
        ),
        sa.CheckConstraint("length(source_hash) = 64", name="ck_postmortem_cases_source_hash"),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["app.workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["feedback_id"], ["app.feedback.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["app.tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["app.runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["artifact_version_id"], ["app.artifact_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_postmortem_cases"),
        sa.UniqueConstraint("feedback_id", name="uq_postmortem_cases_feedback"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_postmortem_cases_owner_idempotency",
        ),
        schema="app",
    )
    op.create_index(
        "ix_postmortem_cases_actor_status",
        "postmortem_cases",
        ["tenant_id", "workspace_id", "owner_user_id", "status"],
        schema="app",
    )

    op.create_table(
        "frozen_replay_records",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("postmortem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("packet", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("rule_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("length(source_hash) = 64", name="ck_frozen_replay_records_source_hash"),
        sa.CheckConstraint(
            "jsonb_typeof(packet) = 'object' AND packet->>'allow_live_fetch' = 'false' "
            "AND packet->>'allow_live_side_effects' = 'false'",
            name="ck_frozen_replay_records_no_live_effects",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["app.workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["postmortem_id"], ["app.postmortem_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["app.tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["app.runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["artifact_version_id"], ["app.artifact_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_frozen_replay_records"),
        sa.UniqueConstraint("postmortem_id", name="uq_frozen_replay_records_postmortem"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "source_hash",
            name="uq_frozen_replay_records_actor_hash",
        ),
        schema="app",
    )
    op.create_index(
        "ix_frozen_replay_records_actor_created",
        "frozen_replay_records",
        ["tenant_id", "workspace_id", "owner_user_id", "created_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_frozen_replay_records_actor_created",
        table_name="frozen_replay_records",
        schema="app",
    )
    op.drop_table("frozen_replay_records", schema="app")
    op.drop_index(
        "ix_postmortem_cases_actor_status",
        table_name="postmortem_cases",
        schema="app",
    )
    op.drop_table("postmortem_cases", schema="app")
    op.drop_index(
        "ix_memory_deletion_jobs_actor_status",
        table_name="memory_deletion_jobs",
        schema="app",
    )
