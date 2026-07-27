"""Add the durable controlled-improvement governance workflow."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0026_improvement_governance"
down_revision = "0025_improvement_cases"
branch_labels = None
depends_on = None


def _actor_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    )


def _actor_foreign_keys() -> tuple[sa.ForeignKeyConstraint, ...]:
    return (
        sa.ForeignKeyConstraint(["tenant_id"], ["app.tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["app.workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app.users.id"], ondelete="RESTRICT"),
    )


def _id_and_timestamps() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
    )


def upgrade() -> None:
    op.create_table(
        "improvement_datasets",
        *_actor_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        *_id_and_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','frozen')",
            name="ck_improvement_datasets_status",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64",
            name="ck_improvement_datasets_source_hash",
        ),
        *_actor_foreign_keys(),
        sa.PrimaryKeyConstraint("id", name="pk_improvement_datasets"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_improvement_datasets_actor_idempotency",
        ),
        schema="app",
    )
    op.create_index(
        "ix_improvement_datasets_actor_status",
        "improvement_datasets",
        ["tenant_id", "workspace_id", "owner_user_id", "status"],
        schema="app",
    )

    op.create_table(
        "improvement_candidates",
        *_actor_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_version", sa.String(255), nullable=False),
        sa.Column("candidate_version", sa.String(255), nullable=False),
        sa.Column("rollback_target_version", sa.String(255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        *_id_and_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','evaluated','pending_review','approved','rejected',"
            "'shadow','active','rolled_back')",
            name="ck_improvement_candidates_status",
        ),
        sa.CheckConstraint(
            "length(version_hash) = 64",
            name="ck_improvement_candidates_version_hash",
        ),
        *_actor_foreign_keys(),
        sa.PrimaryKeyConstraint("id", name="pk_improvement_candidates"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "version_hash",
            name="uq_improvement_candidates_actor_hash",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_improvement_candidates_actor_idempotency",
        ),
        schema="app",
    )
    op.create_index(
        "ix_improvement_candidates_actor_status",
        "improvement_candidates",
        ["tenant_id", "workspace_id", "owner_user_id", "status"],
        schema="app",
    )

    op.create_table(
        "improvement_dataset_members",
        *_actor_columns(),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("replay_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_name", sa.String(255), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64",
            name="ck_improvement_dataset_members_source_hash",
        ),
        *_actor_foreign_keys(),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["app.improvement_datasets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replay_id"],
            ["app.frozen_replay_records.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_improvement_dataset_members"),
        sa.UniqueConstraint(
            "dataset_id",
            "replay_id",
            name="uq_improvement_dataset_members_replay",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "case_name",
            name="uq_improvement_dataset_members_case",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "ordinal",
            name="uq_improvement_dataset_members_ordinal",
        ),
        schema="app",
    )
    op.create_index(
        "ix_improvement_dataset_members_actor_dataset",
        "improvement_dataset_members",
        ["tenant_id", "workspace_id", "owner_user_id", "dataset_id"],
        schema="app",
    )

    op.create_table(
        "improvement_experiments",
        *_actor_columns(),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(255), nullable=False),
        sa.Column("git_revision", sa.String(255), nullable=False),
        sa.Column("case_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gate_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        *_id_and_timestamps(),
        sa.CheckConstraint(
            "status IN ('succeeded','failed')",
            name="ck_improvement_experiments_status",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64",
            name="ck_improvement_experiments_source_hash",
        ),
        *_actor_foreign_keys(),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["app.improvement_datasets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["app.improvement_candidates.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_improvement_experiments"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_improvement_experiments_actor_idempotency",
        ),
        schema="app",
    )
    op.create_index(
        "ix_improvement_experiments_actor_candidate",
        "improvement_experiments",
        ["tenant_id", "workspace_id", "owner_user_id", "candidate_id", "created_at"],
        schema="app",
    )

    op.create_table(
        "improvement_reviews",
        *_actor_columns(),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("interrupt_pause_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_id_and_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_improvement_reviews_status",
        ),
        *_actor_foreign_keys(),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["app.improvement_candidates.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["app.tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["app.runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["interrupt_pause_id"],
            ["app.interrupt_pauses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["app.users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_improvement_reviews"),
        sa.UniqueConstraint(
            "candidate_id",
            name="uq_improvement_reviews_candidate",
        ),
        schema="app",
    )
    op.create_index(
        "ix_improvement_reviews_actor_status",
        "improvement_reviews",
        ["tenant_id", "workspace_id", "owner_user_id", "status"],
        schema="app",
    )

    op.create_table(
        "improvement_shadow_runs",
        *_actor_columns(),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_version", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("minimum_runs", sa.Integer(), nullable=False),
        sa.Column("observed_runs", sa.Integer(), nullable=False),
        sa.Column("comparison", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_id_and_timestamps(),
        sa.CheckConstraint(
            "status IN ('running','passed','failed')",
            name="ck_improvement_shadow_runs_status",
        ),
        sa.CheckConstraint(
            "minimum_runs > 0 AND observed_runs >= 0 AND observed_runs <= minimum_runs",
            name="ck_improvement_shadow_runs_counts",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64",
            name="ck_improvement_shadow_runs_source_hash",
        ),
        *_actor_foreign_keys(),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["app.improvement_candidates.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_improvement_shadow_runs"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_improvement_shadow_runs_actor_idempotency",
        ),
        schema="app",
    )
    op.create_index(
        "ix_improvement_shadow_runs_actor_candidate",
        "improvement_shadow_runs",
        ["tenant_id", "workspace_id", "owner_user_id", "candidate_id", "created_at"],
        schema="app",
    )

    op.create_table(
        "improvement_release_events",
        *_actor_columns(),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_version", sa.String(255), nullable=False),
        sa.Column("to_version", sa.String(255), nullable=False),
        sa.Column("rollback_target_version", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('promoted','rolled_back')",
            name="ck_improvement_release_events_action",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64",
            name="ck_improvement_release_events_source_hash",
        ),
        *_actor_foreign_keys(),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["app.improvement_candidates.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["app.improvement_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shadow_run_id"],
            ["app.improvement_shadow_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_improvement_release_events"),
        sa.UniqueConstraint(
            "candidate_id",
            "action",
            name="uq_improvement_release_events_candidate_action",
        ),
        schema="app",
    )
    op.create_index(
        "ix_improvement_release_events_actor_created",
        "improvement_release_events",
        ["tenant_id", "workspace_id", "owner_user_id", "created_at"],
        schema="app",
    )
    op.execute(
        """
        CREATE FUNCTION app.reject_improvement_release_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'improvement_release_events are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_improvement_release_events_append_only
        BEFORE UPDATE OR DELETE ON app.improvement_release_events
        FOR EACH ROW
        EXECUTE FUNCTION app.reject_improvement_release_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_improvement_release_events_append_only "
        "ON app.improvement_release_events"
    )
    op.execute("DROP FUNCTION app.reject_improvement_release_event_mutation()")
    for table_name, index_name in (
        ("improvement_release_events", "ix_improvement_release_events_actor_created"),
        ("improvement_shadow_runs", "ix_improvement_shadow_runs_actor_candidate"),
        ("improvement_reviews", "ix_improvement_reviews_actor_status"),
        ("improvement_experiments", "ix_improvement_experiments_actor_candidate"),
        ("improvement_dataset_members", "ix_improvement_dataset_members_actor_dataset"),
        ("improvement_candidates", "ix_improvement_candidates_actor_status"),
        ("improvement_datasets", "ix_improvement_datasets_actor_status"),
    ):
        op.drop_index(index_name, table_name=table_name, schema="app")
        op.drop_table(table_name, schema="app")
