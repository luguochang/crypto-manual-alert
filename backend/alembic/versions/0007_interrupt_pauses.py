"""Persist authoritative multi-interrupt pauses.

Revision ID: 0007_interrupt_pauses
Revises: 0006_interrupt_projection
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_interrupt_pauses"
down_revision: str | None = "0006_interrupt_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_SCHEMA = "app"
INTERRUPT_PAUSE_STATUSES = (
    "pending",
    "responding",
    "resolved",
    "expired",
    "resume_failed",
    "cancelled",
)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _assert_legacy_data_is_safe() -> None:
    # Hold both legacy write authorities stable from validation through backfill.
    op.execute(
        sa.text(
            "LOCK TABLE app.task_commands, app.interrupt_inbox "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    op.execute(
        sa.text(
            """
            DO $migration$
            DECLARE
                blocked_records text;
            BEGIN
                SELECT string_agg(
                    command.id::text || ' (' || command.status || ')',
                    ', ' ORDER BY command.id
                )
                INTO blocked_records
                FROM (
                    SELECT id, status
                    FROM app.task_commands
                    WHERE command_type = 'respond'
                      AND status IN ('pending', 'dispatching')
                    ORDER BY id
                    LIMIT 20
                ) AS command;

                IF blocked_records IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'legacy interrupt pause migration blocked: '
                            'active legacy respond command(s) still use the '
                            '0006 payload contract',
                        DETAIL = 'Affected task_command IDs/statuses (up to 20): '
                            || blocked_records,
                        HINT = 'Resolve or cancel the listed work before retrying '
                            'revision 0007; do not manually rewrite command payloads.';
                END IF;

                SELECT string_agg(
                    active_task.task_id::text || ' ('
                        || active_task.active_run_count::text || ' active Runs)',
                    ', ' ORDER BY active_task.task_id
                )
                INTO blocked_records
                FROM (
                    SELECT
                        tenant_id,
                        workspace_id,
                        owner_user_id,
                        task_id,
                        count(DISTINCT run_id) AS active_run_count
                    FROM app.interrupt_inbox
                    WHERE status IN ('pending', 'responding')
                    GROUP BY tenant_id, workspace_id, owner_user_id, task_id
                    HAVING count(DISTINCT run_id) > 1
                    ORDER BY task_id
                    LIMIT 20
                ) AS active_task;

                IF blocked_records IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'legacy interrupt pause migration blocked: '
                            'one or more Tasks have multiple active legacy pauses',
                        DETAIL = 'Affected task IDs/active Run counts (up to 20): '
                            || blocked_records,
                        HINT = 'Resolve or cancel the listed work before retrying '
                            'revision 0007; each Task may have only one pending or '
                            'responding pause.';
                END IF;

                SELECT string_agg(
                    legacy_run.run_id::text || ' ('
                        || legacy_run.checkpoint_pair_count::text || ' pairs)',
                    ', ' ORDER BY legacy_run.run_id
                )
                INTO blocked_records
                FROM (
                    SELECT
                        run_id,
                        count(DISTINCT (namespace, checkpoint_id))
                            AS checkpoint_pair_count
                    FROM app.interrupt_inbox
                    GROUP BY run_id
                    HAVING count(DISTINCT (namespace, checkpoint_id)) > 1
                    ORDER BY run_id
                    LIMIT 20
                ) AS legacy_run;

                IF blocked_records IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'legacy interrupt pause migration blocked: '
                            'one or more Product Runs contain multiple '
                            'namespace/checkpoint pairs',
                        DETAIL = 'Affected run IDs/pair counts (up to 20): '
                            || blocked_records,
                        HINT = 'Resolve or cancel the listed work before retrying '
                            'revision 0007; the official root checkpoint cannot be '
                            'reconstructed safely from these legacy rows.';
                END IF;

                SELECT string_agg(
                    legacy_member.run_id::text || ' ['
                        || legacy_member.namespace || ' @ '
                        || legacy_member.checkpoint_id || ']',
                    ', ' ORDER BY
                        legacy_member.run_id,
                        legacy_member.namespace,
                        legacy_member.checkpoint_id
                )
                INTO blocked_records
                FROM (
                    SELECT DISTINCT run_id, namespace, checkpoint_id
                    FROM app.interrupt_inbox
                    WHERE namespace <> ''
                    ORDER BY run_id, namespace, checkpoint_id
                    LIMIT 20
                ) AS legacy_member;

                IF blocked_records IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'legacy interrupt pause migration blocked: '
                            'a legacy Run contains only a non-root checkpoint namespace',
                        DETAIL = 'Affected run/checkpoint coordinates (up to 20): '
                            || blocked_records,
                        HINT = 'Resolve or cancel the listed work before retrying '
                            'revision 0007; a root checkpoint cannot be inferred '
                            'from a nested-only legacy projection.';
                END IF;

                SELECT string_agg(
                    legacy_run.run_id::text,
                    ', ' ORDER BY legacy_run.run_id
                )
                INTO blocked_records
                FROM (
                    SELECT DISTINCT inbox.run_id
                    FROM app.interrupt_inbox AS inbox
                    JOIN app.runs AS run ON run.id = inbox.run_id
                    JOIN app.threads AS thread ON thread.id = run.thread_id
                    WHERE thread.official_thread_id IS NULL
                    ORDER BY inbox.run_id
                    LIMIT 20
                ) AS legacy_run;

                IF blocked_records IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'legacy interrupt pause migration blocked: '
                            'a legacy Run has no official thread identity',
                        DETAIL = 'Affected run IDs (up to 20): ' || blocked_records,
                        HINT = 'Resolve or cancel the listed work before retrying '
                            'revision 0007; do not fabricate an official thread ID.';
                END IF;

                SELECT string_agg(
                    legacy_group.run_id::text || ' ['
                        || legacy_group.namespace || ' @ '
                        || legacy_group.checkpoint_id || ': '
                        || legacy_group.member_statuses || ']',
                    ', ' ORDER BY
                        legacy_group.run_id,
                        legacy_group.namespace,
                        legacy_group.checkpoint_id
                )
                INTO blocked_records
                FROM (
                    SELECT
                        run_id,
                        namespace,
                        checkpoint_id,
                        string_agg(DISTINCT status, '/' ORDER BY status)
                            AS member_statuses
                    FROM app.interrupt_inbox
                    GROUP BY run_id, namespace, checkpoint_id
                    HAVING count(DISTINCT status) > 1
                    ORDER BY run_id, namespace, checkpoint_id
                    LIMIT 20
                ) AS legacy_group;

                IF blocked_records IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'legacy interrupt pause migration blocked: '
                            'one or more legacy pauses contain mixed member statuses',
                        DETAIL = 'Affected pause coordinates/statuses (up to 20): '
                            || blocked_records,
                        HINT = 'Resolve or cancel the listed work before retrying '
                            'revision 0007; all members of a legacy pause must have '
                            'one provably consistent status.';
                END IF;

                SELECT string_agg(
                    duplicate_member.run_id::text || ' ['
                        || duplicate_member.namespace || ' @ '
                        || duplicate_member.checkpoint_id || ': '
                        || duplicate_member.official_interrupt_id || ']',
                    ', ' ORDER BY
                        duplicate_member.run_id,
                        duplicate_member.namespace,
                        duplicate_member.checkpoint_id,
                        duplicate_member.official_interrupt_id
                )
                INTO blocked_records
                FROM (
                    SELECT
                        run_id,
                        namespace,
                        checkpoint_id,
                        official_interrupt_id
                    FROM app.interrupt_inbox
                    GROUP BY
                        run_id,
                        namespace,
                        checkpoint_id,
                        official_interrupt_id
                    HAVING count(*) > 1
                    ORDER BY
                        run_id,
                        namespace,
                        checkpoint_id,
                        official_interrupt_id
                    LIMIT 20
                ) AS duplicate_member;

                IF blocked_records IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'legacy interrupt pause migration blocked: '
                            'duplicate legacy interrupt membership was found',
                        DETAIL = 'Affected pause members (up to 20): '
                            || blocked_records,
                        HINT = 'Resolve or cancel the listed work before retrying '
                            'revision 0007; deduplicate only after reconciling the '
                            'official Runtime state.';
                END IF;
            END
            $migration$
            """
        )
    )


def upgrade() -> None:
    _assert_legacy_data_is_safe()

    op.create_table(
        "interrupt_pauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tenants.id",
                name="fk_interrupt_pauses_tenant_id_tenants",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.workspaces.id",
                name="fk_interrupt_pauses_workspace_id_workspaces",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.users.id",
                name="fk_interrupt_pauses_owner_user_id_users",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{PRODUCT_SCHEMA}.tasks.id",
                name="fk_interrupt_pauses_task_id_tasks",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "pause_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("root_thread_id", sa.String(length=255), nullable=False),
        sa.Column("root_checkpoint_ns", sa.Text(), nullable=False),
        sa.Column("root_checkpoint_id", sa.String(length=255), nullable=False),
        sa.Column(
            "root_checkpoint_map",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("member_set_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_payload_hash", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_interrupt_pauses"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_interrupt_pauses_run_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "resume_run_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_interrupt_pauses_resume_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "run_id",
            "pause_version",
            name="uq_interrupt_pauses_run_version",
        ),
        sa.UniqueConstraint(
            "run_id",
            "root_checkpoint_ns",
            "root_checkpoint_id",
            name="uq_interrupt_pauses_root_checkpoint",
        ),
        sa.UniqueConstraint(
            "resume_run_id",
            name="uq_interrupt_pauses_resume_run",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "id",
            name="uq_interrupt_pauses_projection_scope",
        ),
        sa.CheckConstraint(
            f"status IN ({_sql_values(INTERRUPT_PAUSE_STATUSES)})",
            name="ck_interrupt_pauses_status",
        ),
        sa.CheckConstraint(
            "pause_version >= 1",
            name="ck_interrupt_pauses_pause_version",
        ),
        sa.CheckConstraint(
            "resume_run_id IS NULL OR resume_run_id <> run_id",
            name="ck_interrupt_pauses_resume_not_source",
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_interrupt_pauses_scope_status_expiry",
        "interrupt_pauses",
        ["tenant_id", "workspace_id", "owner_user_id", "status", "expires_at"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "ix_interrupt_pauses_scope_task_status",
        "interrupt_pauses",
        ["tenant_id", "workspace_id", "task_id", "status"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_index(
        "uq_interrupt_pauses_one_active_task",
        "interrupt_pauses",
        ["tenant_id", "workspace_id", "owner_user_id", "task_id"],
        unique=True,
        schema=PRODUCT_SCHEMA,
        postgresql_where=sa.text("status IN ('pending', 'responding')"),
    )

    op.add_column(
        "interrupt_inbox",
        sa.Column("pause_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=PRODUCT_SCHEMA,
    )

    # Preflight proves one root coordinate and one member status per legacy Run.
    op.execute(
        sa.text(
            """
            WITH legacy_groups AS (
                SELECT
                    (array_agg(i.id ORDER BY i.created_at, i.id))[1] AS id,
                    i.tenant_id,
                    i.workspace_id,
                    i.owner_user_id,
                    i.task_id,
                    i.run_id,
                    t.official_thread_id AS root_thread_id,
                    i.namespace AS root_checkpoint_ns,
                    i.checkpoint_id AS root_checkpoint_id,
                    '{}'::jsonb AS root_checkpoint_map,
                    encode(
                        sha256(
                            convert_to(
                                '{"members":['
                                || string_agg(
                                    '{"checkpoint_id":'
                                    || to_json(i.checkpoint_id)::text
                                    || ',"interrupt_id":'
                                    || to_json(i.official_interrupt_id)::text
                                    || ',"namespace":'
                                    || to_json(i.namespace)::text
                                    || '}',
                                    ',' ORDER BY i.official_interrupt_id
                                )
                                || '],"root_checkpoint":{"checkpoint_id":'
                                || to_json(i.checkpoint_id)::text
                                || ',"checkpoint_map":{},"checkpoint_ns":'
                                || to_json(i.namespace)::text
                                || ',"thread_id":'
                                || to_json(t.official_thread_id)::text
                                || '}}',
                                'UTF8'
                            )
                        ),
                        'hex'
                    ) AS member_set_hash,
                    CASE
                        WHEN bool_or(i.status = 'pending') THEN 'pending'
                        WHEN bool_or(i.status = 'responding') THEN 'responding'
                        WHEN bool_and(i.status = 'resolved') THEN 'resolved'
                        WHEN bool_and(i.status = 'expired') THEN 'expired'
                        WHEN bool_and(i.status = 'cancelled') THEN 'cancelled'
                        ELSE 'cancelled'
                    END AS status,
                    max(i.expires_at) AS expires_at,
                    (
                        array_agg(resumed.id ORDER BY resumed.created_at, resumed.id)
                            FILTER (WHERE resumed.id IS NOT NULL)
                    )[1] AS resume_run_id,
                    min(i.created_at) AS created_at,
                    max(i.updated_at) AS updated_at
                FROM app.interrupt_inbox AS i
                JOIN app.runs AS r
                  ON r.tenant_id = i.tenant_id
                 AND r.workspace_id = i.workspace_id
                 AND r.owner_user_id = i.owner_user_id
                 AND r.task_id = i.task_id
                 AND r.id = i.run_id
                JOIN app.threads AS t ON t.id = r.thread_id
                LEFT JOIN app.runs AS resumed ON resumed.resume_of_run_id = i.run_id
                GROUP BY
                    i.tenant_id,
                    i.workspace_id,
                    i.owner_user_id,
                    i.task_id,
                    i.run_id,
                    t.official_thread_id,
                    r.thread_id,
                    i.namespace,
                    i.checkpoint_id
            ),
            versioned_groups AS (
                SELECT
                    legacy_groups.*,
                    row_number() OVER (
                        PARTITION BY run_id
                        ORDER BY
                            created_at,
                            root_checkpoint_ns,
                            root_checkpoint_id,
                            id
                    )::integer AS pause_version,
                    count(*) OVER (PARTITION BY run_id)::integer AS pause_count
                FROM legacy_groups
            )
            INSERT INTO app.interrupt_pauses (
                id,
                tenant_id,
                workspace_id,
                owner_user_id,
                task_id,
                run_id,
                pause_version,
                root_thread_id,
                root_checkpoint_ns,
                root_checkpoint_id,
                root_checkpoint_map,
                member_set_hash,
                status,
                expires_at,
                resume_run_id,
                accepted_payload_hash,
                created_at,
                updated_at
            )
            SELECT
                id,
                tenant_id,
                workspace_id,
                owner_user_id,
                task_id,
                run_id,
                pause_version,
                root_thread_id,
                root_checkpoint_ns,
                root_checkpoint_id,
                root_checkpoint_map,
                member_set_hash,
                status,
                expires_at,
                CASE
                    WHEN pause_version = pause_count THEN resume_run_id
                    ELSE NULL
                END,
                NULL,
                created_at,
                updated_at
            FROM versioned_groups
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE app.interrupt_inbox AS inbox
            SET pause_id = pause.id
            FROM app.interrupt_pauses AS pause
            WHERE pause.run_id = inbox.run_id
              AND pause.root_checkpoint_ns = inbox.namespace
              AND pause.root_checkpoint_id = inbox.checkpoint_id
            """
        )
    )
    op.alter_column(
        "interrupt_inbox",
        "pause_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        schema=PRODUCT_SCHEMA,
    )

    op.create_foreign_key(
        "fk_interrupt_inbox_pause_scope",
        "interrupt_inbox",
        "interrupt_pauses",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "pause_id",
        ],
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "id",
        ],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_interrupt_inbox_pause_member",
        "interrupt_inbox",
        ["pause_id", "official_interrupt_id"],
        schema=PRODUCT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_interrupt_inbox_pause_member",
        "interrupt_inbox",
        type_="unique",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "fk_interrupt_inbox_pause_scope",
        "interrupt_inbox",
        type_="foreignkey",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_column("interrupt_inbox", "pause_id", schema=PRODUCT_SCHEMA)

    op.drop_index(
        "uq_interrupt_pauses_one_active_task",
        table_name="interrupt_pauses",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_interrupt_pauses_scope_task_status",
        table_name="interrupt_pauses",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_index(
        "ix_interrupt_pauses_scope_status_expiry",
        table_name="interrupt_pauses",
        schema=PRODUCT_SCHEMA,
    )
    op.drop_table("interrupt_pauses", schema=PRODUCT_SCHEMA)
