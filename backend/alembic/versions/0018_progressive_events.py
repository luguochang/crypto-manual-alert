"""Make Product domain events resumable and progressively appendable."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_progressive_events"
down_revision = "0017_domain_events"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column(
            "next_domain_event_sequence",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column("official_stream_last_event_id", sa.String(length=255)),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column("official_stream_last_event_at", sa.DateTime(timezone=True)),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "domain_events",
        sa.Column("source_event_key", sa.String(length=255)),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "domain_events",
        sa.Column("source_event_id", sa.String(length=255)),
        schema=PRODUCT_SCHEMA,
    )
    op.add_column(
        "domain_events",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text())),
        schema=PRODUCT_SCHEMA,
    )

    op.execute(
        sa.text(
            """
            UPDATE app.domain_events AS event
            SET payload = CASE event.event_type
                WHEN 'market.snapshot.committed'
                    THEN run.output_payload -> 'market_snapshot'
                WHEN 'research.evidence.committed'
                    THEN run.output_payload -> 'web_evidence'
                WHEN 'agent.output.committed'
                    THEN run.output_payload #> '{artifact,analysis}'
                WHEN 'evidence.verdict.committed'
                    THEN run.output_payload #> '{artifact,evidence_verdict}'
                WHEN 'risk.verdict.committed'
                    THEN run.output_payload #> '{artifact,risk_verdict}'
                WHEN 'artifact.committed'
                    THEN run.output_payload -> 'artifact'
                WHEN 'notification.planned'
                    THEN COALESCE(
                        (
                            SELECT outbox.payload
                            FROM app.notification_outbox AS outbox
                            WHERE outbox.run_id = event.run_id
                            ORDER BY outbox.created_at DESC, outbox.id DESC
                            LIMIT 1
                        ),
                        '{}'::jsonb
                    )
                WHEN 'run.terminal' THEN run.output_payload
                ELSE '{}'::jsonb
            END,
            source_event_key = 'legacy-terminal:' || event.event_type,
            payload_ref = 'domain-event://' || event.id::text || '/payload'
            FROM app.runs AS run
            WHERE run.id = event.run_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE app.threads AS thread
            SET next_domain_event_sequence = COALESCE(
                (
                    SELECT MAX(event.sequence) + 1
                    FROM app.domain_events AS event
                    WHERE event.thread_id = thread.id
                ),
                1
            )
            """
        )
    )
    op.alter_column(
        "domain_events",
        "source_event_key",
        nullable=False,
        schema=PRODUCT_SCHEMA,
    )
    op.alter_column(
        "domain_events",
        "payload",
        nullable=False,
        schema=PRODUCT_SCHEMA,
    )

    op.drop_constraint(
        "uq_domain_events_run_type",
        "domain_events",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_domain_events_run_source_key",
        "domain_events",
        ["run_id", "source_event_key"],
        schema=PRODUCT_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_runs_domain_event_scope",
        "runs",
        ["tenant_id", "workspace_id", "owner_user_id", "thread_id", "task_id", "id"],
        schema=PRODUCT_SCHEMA,
    )
    op.drop_constraint(
        "fk_domain_events_run_scope",
        "domain_events",
        schema=PRODUCT_SCHEMA,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_domain_events_run_scope",
        "domain_events",
        "runs",
        [
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "thread_id",
            "task_id",
            "run_id",
        ],
        ["tenant_id", "workspace_id", "owner_user_id", "thread_id", "task_id", "id"],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_domain_events_run_scope",
        "domain_events",
        schema=PRODUCT_SCHEMA,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_domain_events_run_scope",
        "domain_events",
        "runs",
        ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
        ["tenant_id", "workspace_id", "owner_user_id", "task_id", "id"],
        source_schema=PRODUCT_SCHEMA,
        referent_schema=PRODUCT_SCHEMA,
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_runs_domain_event_scope",
        "runs",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "uq_domain_events_run_source_key",
        "domain_events",
        schema=PRODUCT_SCHEMA,
        type_="unique",
    )
    op.execute(
        sa.text(
            """
            DELETE FROM app.domain_events AS candidate
            USING app.domain_events AS retained
            WHERE candidate.run_id = retained.run_id
              AND candidate.event_type = retained.event_type
              AND (
                  candidate.sequence > retained.sequence
                  OR (
                      candidate.sequence = retained.sequence
                      AND candidate.id::text > retained.id::text
                  )
              )
            """
        )
    )
    op.create_unique_constraint(
        "uq_domain_events_run_type",
        "domain_events",
        ["run_id", "event_type"],
        schema=PRODUCT_SCHEMA,
    )
    op.drop_column("domain_events", "payload", schema=PRODUCT_SCHEMA)
    op.drop_column("domain_events", "source_event_id", schema=PRODUCT_SCHEMA)
    op.drop_column("domain_events", "source_event_key", schema=PRODUCT_SCHEMA)
    op.drop_column("runs", "official_stream_last_event_at", schema=PRODUCT_SCHEMA)
    op.drop_column("runs", "official_stream_last_event_id", schema=PRODUCT_SCHEMA)
    op.drop_column("threads", "next_domain_event_sequence", schema=PRODUCT_SCHEMA)
