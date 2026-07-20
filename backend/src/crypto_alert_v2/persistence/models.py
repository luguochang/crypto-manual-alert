from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from crypto_alert_v2.persistence.base import (
    Base,
    PRODUCT_SCHEMA,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


RUN_STATUSES = (
    "queued",
    "running",
    "waiting_human",
    "succeeded",
    "blocked",
    "failed",
    "cancelled",
)

REVIEW_POLICIES = (
    "bypass",
    "required",
)

OBSERVED_TERMINAL_STATUSES = (
    "error",
    "success",
    "timeout",
)

DOMAIN_EVENT_TYPES = (
    "market.snapshot.committed",
    "research.evidence.committed",
    "agent.output.committed",
    "evidence.verdict.committed",
    "risk.verdict.committed",
    "artifact.committed",
    "notification.planned",
    "run.terminal",
)

TASK_COMMAND_TYPES = (
    "submit",
    "respond",
    "cancel_run",
    "cancel_task",
    "retry",
    "fork",
)

TASK_COMMAND_STATUSES = (
    "pending",
    "dispatching",
    "dispatched",
    "rejected",
    "cancelled",
    "failed",
)

INTERRUPT_STATUSES = (
    "pending",
    "responding",
    "resolved",
    "expired",
    "cancelled",
)

INTERRUPT_PAUSE_STATUSES = (
    "pending",
    "responding",
    "resolved",
    "expired",
    "resume_failed",
    "cancelled",
)

NOTIFICATION_OUTBOX_STATUSES = (
    "planned",
    "leased",
    "sending",
    "delivered",
    "failed_retryable",
    "failed_terminal",
    "unknown",
)

NOTIFICATION_ATTEMPT_TRIGGERS = (
    "automatic",
    "manual",
)

NOTIFICATION_ATTEMPT_RESULTS = (
    "leased",
    "sending",
    "delivered",
    "failed_retryable",
    "failed_terminal",
    "unknown",
    "released",
)

NOTIFICATION_DESTINATION_STATUSES = (
    "enabled",
    "disabled",
)

MONITOR_TASK_TYPES = (
    "market_analysis",
    "deep_research",
)

MONITOR_STATUSES = (
    "draft",
    "active",
    "paused",
    "degraded",
    "expired",
    "disabled",
)

MONITOR_CRON_COMMAND_TYPES = (
    "create",
    "update",
    "pause",
    "resume",
    "delete",
)

MONITOR_CRON_COMMAND_STATUSES = (
    "pending",
    "leased",
    "succeeded",
    "failed",
)

MONITOR_TRIGGER_KINDS = (
    "manual",
    "cron",
)

MONITOR_TRIGGER_STATUSES = (
    "received",
    "suppressed",
    "admitted",
    "failed",
)

OBSERVABILITY_DELIVERY_PROVIDERS = (
    "langsmith",
    "langfuse",
)

OBSERVABILITY_DELIVERY_STATUSES = (
    "not_requested",
    "planned",
    "leased",
    "verifying",
    "verified",
    "failed_retryable",
    "failed_terminal",
    "unknown",
)

DATA_LIFECYCLE_EXPORT_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
)

DATA_LIFECYCLE_DELETION_STATUSES = (
    "queued",
    "running",
    "pending_external",
    "succeeded",
    "blocked_legal_hold",
    "failed",
)

DATA_LIFECYCLE_SCOPE = "user_data"


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "identity_issuer",
            "external_subject",
            name="uq_users_tenant_issuer_subject",
        ),
        Index(
            "ix_users_tenant_issuer_subject",
            "tenant_id",
            "identity_issuer",
            "external_subject",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_issuer: Mapped[str] = mapped_column(
        String(512), nullable=False, default="legacy", server_default=text("'legacy'")
    )
    external_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint(
            f"review_policy IN ({_sql_values(REVIEW_POLICIES)})",
            name="ck_workspaces_review_policy",
        ),
        UniqueConstraint(
            "tenant_id",
            "external_id",
            name="uq_workspaces_tenant_external_id",
        ),
        Index("ix_workspaces_tenant_external", "tenant_id", "external_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    review_policy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="bypass",
        server_default=text("'bypass'"),
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_memberships_workspace_user"
        ),
        Index(
            "ix_memberships_tenant_workspace_user",
            "tenant_id",
            "workspace_id",
            "user_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )


class Thread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "threads"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "official_thread_id",
            name="uq_threads_workspace_official_thread",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_threads_monitor_scope",
        ),
        Index(
            "ix_threads_tenant_workspace_created",
            "tenant_id",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_threads_tenant_workspace_owner",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    official_thread_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(500))
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    next_domain_event_sequence: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_tasks_actor_workspace_idempotency",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_tasks_notification_scope",
        ),
        Index(
            "ix_tasks_tenant_workspace_status", "tenant_id", "workspace_id", "status"
        ),
        Index(
            "ix_tasks_tenant_workspace_thread", "tenant_id", "workspace_id", "thread_id"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    thread_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(RUN_STATUSES)})",
            name="ck_runs_status",
        ),
        CheckConstraint(
            "observed_terminal_status IS NULL OR "
            f"observed_terminal_status IN ({_sql_values(OBSERVED_TERMINAL_STATUSES)})",
            name="ck_runs_observed_terminal_status",
        ),
        UniqueConstraint("task_id", "attempt", name="uq_runs_task_attempt"),
        UniqueConstraint("official_run_id", name="uq_runs_official_run_id"),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            name="uq_runs_projection_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "thread_id",
            "task_id",
            "id",
            name="uq_runs_domain_event_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            "checkpoint_id",
            name="uq_runs_fork_checkpoint_scope",
        ),
        UniqueConstraint("resume_of_run_id", name="uq_runs_resume_of_run"),
        UniqueConstraint("retry_of_run_id", name="uq_runs_retry_of_run"),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "resume_of_run_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_runs_resume_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "retry_of_run_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_runs_retry_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "forked_from_run_id",
                "forked_from_checkpoint_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
                f"{PRODUCT_SCHEMA}.runs.checkpoint_id",
            ],
            name="fk_runs_fork_source_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "resume_of_run_id IS NULL OR resume_of_run_id <> id",
            name="ck_runs_resume_not_self",
        ),
        CheckConstraint(
            "retry_of_run_id IS NULL OR retry_of_run_id <> id",
            name="ck_runs_retry_not_self",
        ),
        CheckConstraint(
            "forked_from_run_id IS NULL OR forked_from_run_id <> id",
            name="ck_runs_fork_not_self",
        ),
        CheckConstraint(
            "(forked_from_run_id IS NULL) = (forked_from_checkpoint_id IS NULL)",
            name="ck_runs_fork_lineage_complete",
        ),
        Index("ix_runs_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
        Index("ix_runs_tenant_workspace_task", "tenant_id", "workspace_id", "task_id"),
        Index(
            "ix_runs_tenant_workspace_resume",
            "tenant_id",
            "workspace_id",
            "resume_of_run_id",
        ),
        Index(
            "ix_runs_tenant_workspace_retry",
            "tenant_id",
            "workspace_id",
            "retry_of_run_id",
        ),
        Index(
            "ix_runs_tenant_workspace_fork_source",
            "tenant_id",
            "workspace_id",
            "forked_from_run_id",
        ),
        Index(
            "ix_runs_status_reconcile_deadline", "status", "reconciliation_deadline_at"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    thread_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    official_assistant_id: Mapped[str | None] = mapped_column(String(255))
    official_run_id: Mapped[str | None] = mapped_column(String(255))
    checkpoint_id: Mapped[str | None] = mapped_column(String(255))
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciliation_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    projection_fence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    terminal_output_hash: Mapped[str | None] = mapped_column(String(64))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    observed_terminal_status: Mapped[str | None] = mapped_column(String(32))
    official_stream_last_event_id: Mapped[str | None] = mapped_column(String(255))
    official_stream_last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    resume_of_run_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    retry_of_run_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    forked_from_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True)
    )
    forked_from_checkpoint_id: Mapped[str | None] = mapped_column(String(255))


class DomainEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "domain_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({_sql_values(DOMAIN_EVENT_TYPES)})",
            name="ck_domain_events_type",
        ),
        CheckConstraint("sequence >= 1", name="ck_domain_events_sequence"),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "thread_id",
                "task_id",
                "run_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.thread_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_domain_events_run_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "run_id",
            "source_event_key",
            name="uq_domain_events_run_source_key",
        ),
        UniqueConstraint(
            "thread_id",
            "sequence",
            name="uq_domain_events_thread_sequence",
        ),
        Index(
            "ix_domain_events_scope_run",
            "tenant_id",
            "workspace_id",
            "task_id",
            "run_id",
        ),
        Index(
            "ix_domain_events_scope_type_created",
            "tenant_id",
            "workspace_id",
            "event_type",
            "created_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    thread_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    official_run_id: Mapped[str | None] = mapped_column(String(255))
    checkpoint_id: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(255))
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_ref: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InterruptPause(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interrupt_pauses"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(INTERRUPT_PAUSE_STATUSES)})",
            name="ck_interrupt_pauses_status",
        ),
        CheckConstraint(
            "pause_version >= 1",
            name="ck_interrupt_pauses_pause_version",
        ),
        CheckConstraint(
            "resume_run_id IS NULL OR resume_run_id <> run_id",
            name="ck_interrupt_pauses_resume_not_source",
        ),
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "run_id",
            "pause_version",
            name="uq_interrupt_pauses_run_version",
        ),
        UniqueConstraint(
            "run_id",
            "root_checkpoint_ns",
            "root_checkpoint_id",
            name="uq_interrupt_pauses_root_checkpoint",
        ),
        UniqueConstraint(
            "resume_run_id",
            name="uq_interrupt_pauses_resume_run",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "id",
            name="uq_interrupt_pauses_projection_scope",
        ),
        Index(
            "ix_interrupt_pauses_scope_status_expiry",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "status",
            "expires_at",
        ),
        Index(
            "ix_interrupt_pauses_scope_task_status",
            "tenant_id",
            "workspace_id",
            "task_id",
            "status",
        ),
        Index(
            "uq_interrupt_pauses_one_active_task",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'responding')"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    pause_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    root_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    root_checkpoint_ns: Mapped[str] = mapped_column(Text, nullable=False)
    root_checkpoint_id: Mapped[str] = mapped_column(String(255), nullable=False)
    root_checkpoint_map: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    member_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_run_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    accepted_payload_hash: Mapped[str | None] = mapped_column(String(64))

    projections: Mapped[list["InterruptProjection"]] = relationship(
        back_populates="pause",
        passive_deletes=True,
    )


class InterruptProjection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interrupt_inbox"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(INTERRUPT_STATUSES)})",
            name="ck_interrupt_inbox_status",
        ),
        CheckConstraint(
            "response_version >= 1",
            name="ck_interrupt_inbox_response_version",
        ),
        CheckConstraint(
            "responded_at IS NULL OR response IS NOT NULL",
            name="ck_interrupt_inbox_response_timestamp",
        ),
        CheckConstraint(
            "status <> 'pending' OR (response IS NULL AND responded_at IS NULL)",
            name="ck_interrupt_inbox_pending_empty",
        ),
        CheckConstraint(
            "status NOT IN ('responding', 'resolved') OR response IS NOT NULL",
            name="ck_interrupt_inbox_active_response",
        ),
        CheckConstraint(
            "status <> 'resolved' OR responded_at IS NOT NULL",
            name="ck_interrupt_inbox_resolved_timestamp",
        ),
        CheckConstraint(
            "status <> 'expired' OR expires_at IS NOT NULL",
            name="ck_interrupt_inbox_expired_timestamp",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_interrupt_inbox_run_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "run_id",
                "pause_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.interrupt_pauses.tenant_id",
                f"{PRODUCT_SCHEMA}.interrupt_pauses.workspace_id",
                f"{PRODUCT_SCHEMA}.interrupt_pauses.owner_user_id",
                f"{PRODUCT_SCHEMA}.interrupt_pauses.task_id",
                f"{PRODUCT_SCHEMA}.interrupt_pauses.run_id",
                f"{PRODUCT_SCHEMA}.interrupt_pauses.id",
            ],
            name="fk_interrupt_inbox_pause_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "official_interrupt_id",
            "checkpoint_id",
            "response_version",
            name="uq_interrupt_inbox_scope_response",
        ),
        UniqueConstraint(
            "pause_id",
            "official_interrupt_id",
            name="uq_interrupt_inbox_pause_member",
        ),
        Index(
            "ix_interrupt_inbox_scope_status_expiry",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "status",
            "expires_at",
        ),
        Index(
            "ix_interrupt_inbox_scope_task_status",
            "tenant_id",
            "workspace_id",
            "task_id",
            "status",
        ),
        Index(
            "ix_interrupt_inbox_scope_run_status",
            "tenant_id",
            "workspace_id",
            "run_id",
            "status",
        ),
        Index(
            "ix_interrupt_inbox_checkpoint_interrupt",
            "checkpoint_id",
            "official_interrupt_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    pause_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    official_interrupt_id: Mapped[str] = mapped_column(String(255), nullable=False)
    namespace: Mapped[str] = mapped_column(Text, nullable=False)
    checkpoint_id: Mapped[str] = mapped_column(String(255), nullable=False)
    response_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pause: Mapped[InterruptPause] = relationship(back_populates="projections")


class MarketSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        Index(
            "ix_market_snapshots_tenant_workspace_run",
            "tenant_id",
            "workspace_id",
            "run_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WebEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "web_evidence"
    __table_args__ = (
        Index(
            "ix_web_evidence_tenant_workspace_run",
            "tenant_id",
            "workspace_id",
            "run_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("task_id", "artifact_type", name="uq_artifacts_task_type"),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            name="uq_artifacts_notification_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_artifacts_monitor_scope",
        ),
        Index(
            "ix_artifacts_tenant_workspace_task", "tenant_id", "workspace_id", "task_id"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    latest_version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )


class ArtifactVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "version_number",
            name="uq_artifact_versions_artifact_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "artifact_id",
            "id",
            name="uq_artifact_versions_notification_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "artifact_id",
            "id",
            name="uq_artifact_versions_monitor_scope",
        ),
        Index(
            "ix_artifact_versions_tenant_workspace_artifact",
            "tenant_id",
            "workspace_id",
            "artifact_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Decision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("artifact_version_id", name="uq_decisions_artifact_version"),
        UniqueConstraint(
            "artifact_id",
            "decision_version",
            name="uq_decisions_artifact_decision_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "artifact_id",
            "artifact_version_id",
            "decision_version",
            "id",
            name="uq_decisions_notification_scope",
        ),
        Index(
            "ix_decisions_tenant_workspace_task", "tenant_id", "workspace_id", "task_id"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evidence_verdict: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    risk_verdict: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "rating IN ('positive', 'negative')",
            name="ck_feedback_rating",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_feedback_workspace_idempotency",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "run_id",
            name="uq_feedback_owner_run",
        ),
        Index(
            "ix_feedback_tenant_workspace_run",
            "tenant_id",
            "workspace_id",
            "run_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifact_versions.id", ondelete="SET NULL"),
    )
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)


class WatchlistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "symbol",
            name="uq_watchlist_owner_symbol",
        ),
        Index(
            "ix_watchlist_tenant_workspace_owner",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)


class NotificationDestination(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_destinations"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(NOTIFICATION_DESTINATION_STATUSES)})",
            name="ck_notification_destinations_status",
        ),
        CheckConstraint(
            "channel IN ('bark')",
            name="ck_notification_destinations_channel",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "channel",
            name="uq_notification_destinations_owner_channel",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_notification_destinations_scope",
        ),
        Index(
            "ix_notification_destinations_scope_status",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "status",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="disabled",
        server_default=text("'disabled'"),
    )
    credential_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credential_key_version: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ObservabilityDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "observability_deliveries"
    __table_args__ = (
        CheckConstraint(
            f"provider IN ({_sql_values(OBSERVABILITY_DELIVERY_PROVIDERS)})",
            name="ck_observability_deliveries_provider",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(OBSERVABILITY_DELIVERY_STATUSES)})",
            name="ck_observability_deliveries_status",
        ),
        CheckConstraint(
            "event_version >= 1",
            name="ck_observability_deliveries_event_version",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_observability_deliveries_attempt_count",
        ),
        CheckConstraint(
            "fence_token >= 0",
            name="ck_observability_deliveries_fence_token",
        ),
        CheckConstraint(
            "(status IN ('leased', 'verifying')) = "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_observability_deliveries_active_lease",
        ),
        CheckConstraint(
            "(status = 'not_requested') = (skip_reason IS NOT NULL)",
            name="ck_observability_deliveries_skip_reason",
        ),
        CheckConstraint(
            "(status = 'verified') = "
            "(provider_trace_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_observability_deliveries_verified_receipt",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "task_id",
            "run_id",
            "provider",
            "event_type",
            "event_version",
            name="uq_observability_deliveries_logical_key",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "delivery_key",
            name="uq_observability_deliveries_delivery_key",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id"],
            [
                f"{PRODUCT_SCHEMA}.tasks.tenant_id",
                f"{PRODUCT_SCHEMA}.tasks.workspace_id",
                f"{PRODUCT_SCHEMA}.tasks.owner_user_id",
                f"{PRODUCT_SCHEMA}.tasks.id",
            ],
            name="fk_observability_deliveries_task_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_observability_deliveries_run_scope",
            ondelete="CASCADE",
        ),
        Index(
            "ix_observability_deliveries_scope_run",
            "tenant_id",
            "workspace_id",
            "task_id",
            "run_id",
        ),
        Index(
            "ix_observability_deliveries_due",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_observability_deliveries_lease",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_observability_deliveries_provider_status",
            "tenant_id",
            "workspace_id",
            "provider",
            "status",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="root_trace",
        server_default=text("'root_trace'"),
    )
    event_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    delivery_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="planned", server_default=text("'planned'")
    )
    sampled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    skip_reason: Mapped[str | None] = mapped_column(String(128))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    fence_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    provider_trace_id: Mapped[str | None] = mapped_column(String(255))
    last_stage: Mapped[str | None] = mapped_column(String(32))
    last_retry_state: Mapped[str | None] = mapped_column(String(32))
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_type: Mapped[str | None] = mapped_column(String(128))
    last_error_summary: Mapped[str | None] = mapped_column(String(500))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(NOTIFICATION_OUTBOX_STATUSES)})",
            name="ck_notification_outbox_status",
        ),
        CheckConstraint(
            "attempt_count BETWEEN 0 AND 5",
            name="ck_notification_outbox_attempt_count",
        ),
        CheckConstraint(
            "fence_token >= 0",
            name="ck_notification_outbox_fence_token",
        ),
        CheckConstraint(
            "(status IN ('leased', 'sending')) = "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_notification_outbox_active_lease",
        ),
        CheckConstraint(
            "(manual_resend_requested_at IS NULL AND "
            "manual_resend_requested_by IS NULL AND manual_resend_reason IS NULL) OR "
            "(manual_resend_requested_at IS NOT NULL AND "
            "manual_resend_requested_by IS NOT NULL)",
            name="ck_notification_outbox_manual_resend_request",
        ),
        UniqueConstraint(
            "workspace_id",
            "task_id",
            "channel",
            "type",
            "decision_version",
            name="uq_notification_outbox_logical_key",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "id",
            name="uq_notification_outbox_attempt_scope",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id"],
            [
                f"{PRODUCT_SCHEMA}.tasks.tenant_id",
                f"{PRODUCT_SCHEMA}.tasks.workspace_id",
                f"{PRODUCT_SCHEMA}.tasks.owner_user_id",
                f"{PRODUCT_SCHEMA}.tasks.id",
            ],
            name="fk_notification_outbox_task_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "destination_id"],
            [
                f"{PRODUCT_SCHEMA}.notification_destinations.tenant_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.workspace_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.owner_user_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.id",
            ],
            name="fk_notification_outbox_destination_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "run_id"],
            [
                f"{PRODUCT_SCHEMA}.runs.tenant_id",
                f"{PRODUCT_SCHEMA}.runs.workspace_id",
                f"{PRODUCT_SCHEMA}.runs.owner_user_id",
                f"{PRODUCT_SCHEMA}.runs.task_id",
                f"{PRODUCT_SCHEMA}.runs.id",
            ],
            name="fk_notification_outbox_run_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "artifact_id"],
            [
                f"{PRODUCT_SCHEMA}.artifacts.tenant_id",
                f"{PRODUCT_SCHEMA}.artifacts.workspace_id",
                f"{PRODUCT_SCHEMA}.artifacts.owner_user_id",
                f"{PRODUCT_SCHEMA}.artifacts.task_id",
                f"{PRODUCT_SCHEMA}.artifacts.id",
            ],
            name="fk_notification_outbox_artifact_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "run_id",
                "artifact_id",
                "artifact_version_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.artifact_versions.tenant_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.workspace_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.owner_user_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.task_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.run_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.artifact_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.id",
            ],
            name="fk_notification_outbox_artifact_version_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "task_id",
                "run_id",
                "artifact_id",
                "artifact_version_id",
                "decision_version",
                "decision_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.decisions.tenant_id",
                f"{PRODUCT_SCHEMA}.decisions.workspace_id",
                f"{PRODUCT_SCHEMA}.decisions.owner_user_id",
                f"{PRODUCT_SCHEMA}.decisions.task_id",
                f"{PRODUCT_SCHEMA}.decisions.run_id",
                f"{PRODUCT_SCHEMA}.decisions.artifact_id",
                f"{PRODUCT_SCHEMA}.decisions.artifact_version_id",
                f"{PRODUCT_SCHEMA}.decisions.decision_version",
                f"{PRODUCT_SCHEMA}.decisions.id",
            ],
            name="fk_notification_outbox_decision_scope",
            ondelete="CASCADE",
        ),
        Index(
            "ix_notification_outbox_status_available",
            "status",
            "available_at",
            "created_at",
        ),
        Index(
            "ix_notification_outbox_lease_expiry",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_notification_outbox_destination",
            "destination_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_notification_outbox_manual_resend",
            "manual_resend_requested_at",
            "created_at",
        ),
        Index(
            "ix_notification_outbox_scope_task",
            "tenant_id",
            "workspace_id",
            "task_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="planned",
        server_default=text("'planned'"),
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fence_token: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manual_resend_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    manual_resend_requested_by: Mapped[str | None] = mapped_column(String(255))
    manual_resend_reason: Mapped[str | None] = mapped_column(String(500))


class NotificationAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notification_attempts"
    __table_args__ = (
        CheckConstraint(
            f"trigger IN ({_sql_values(NOTIFICATION_ATTEMPT_TRIGGERS)})",
            name="ck_notification_attempts_trigger",
        ),
        CheckConstraint(
            f"result IN ({_sql_values(NOTIFICATION_ATTEMPT_RESULTS)})",
            name="ck_notification_attempts_result",
        ),
        CheckConstraint(
            "attempt_number BETWEEN 1 AND 5",
            name="ck_notification_attempts_attempt_number",
        ),
        CheckConstraint(
            "fence_token >= 1",
            name="ck_notification_attempts_fence_token",
        ),
        CheckConstraint(
            "delay_seconds >= 0 AND "
            "(retry_after_seconds IS NULL OR retry_after_seconds >= 0) AND "
            "cost_units >= 0",
            name="ck_notification_attempts_nonnegative_metrics",
        ),
        CheckConstraint(
            "(trigger = 'automatic' AND requested_by IS NULL) OR "
            "(trigger = 'manual' AND requested_by IS NOT NULL)",
            name="ck_notification_attempts_manual_actor",
        ),
        UniqueConstraint(
            "outbox_id",
            "attempt_number",
            name="uq_notification_attempts_outbox_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id", "outbox_id"],
            [
                f"{PRODUCT_SCHEMA}.notification_outbox.tenant_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.workspace_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.owner_user_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.task_id",
                f"{PRODUCT_SCHEMA}.notification_outbox.id",
            ],
            name="fk_notification_attempts_outbox_scope",
            ondelete="CASCADE",
        ),
        Index(
            "ix_notification_attempts_scope_task",
            "tenant_id",
            "workspace_id",
            "task_id",
            "created_at",
        ),
        Index(
            "ix_notification_attempts_outbox_created",
            "outbox_id",
            "created_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    outbox_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.notification_outbox.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    fence_token: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(String(128))
    delay_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    cost_units: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    result: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="leased",
        server_default=text("'leased'"),
    )
    provider_receipt: Mapped[str | None] = mapped_column(String(512))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_commands"
    __table_args__ = (
        CheckConstraint(
            f"command_type IN ({_sql_values(TASK_COMMAND_TYPES)})",
            name="ck_task_commands_command_type",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(TASK_COMMAND_STATUSES)})",
            name="ck_task_commands_status",
        ),
        UniqueConstraint(
            "thread_id", "sequence", name="uq_task_commands_thread_sequence"
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_task_commands_workspace_idempotency",
        ),
        Index(
            "ix_task_commands_tenant_workspace_status",
            "tenant_id",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_task_commands_thread_status_sequence", "thread_id", "status", "sequence"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    command_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    official_run_id: Mapped[str | None] = mapped_column(String(255))
    official_command_id: Mapped[str | None] = mapped_column(String(255))


class WorkspaceEntitlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_entitlements"
    __table_args__ = (
        CheckConstraint(
            "active_monitor_limit >= 0",
            name="ck_workspace_entitlements_active_monitor_limit",
        ),
        CheckConstraint(
            "min_interval_seconds >= 1",
            name="ck_workspace_entitlements_min_interval_seconds",
        ),
        CheckConstraint(
            "max_concurrent_tasks >= 1",
            name="ck_workspace_entitlements_max_concurrent_tasks",
        ),
        CheckConstraint(
            "monthly_trigger_limit >= 0",
            name="ck_workspace_entitlements_monthly_trigger_limit",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_workspace_entitlements_valid_window",
        ),
        UniqueConstraint("workspace_id", name="uq_workspace_entitlements_workspace"),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            name="uq_workspace_entitlements_tenant_workspace",
        ),
        Index(
            "ix_workspace_entitlements_tenant_workspace_active",
            "tenant_id",
            "workspace_id",
            "active",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    active_monitor_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    min_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_trigger_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageLedgerEntry(UUIDPrimaryKeyMixin, Base):
    """Immutable Product usage accounting; one row represents one admitted trigger."""

    __tablename__ = "usage_ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_definitions.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.id",
            ],
            name="fk_usage_ledger_entries_monitor_id_monitor_definitions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "trigger_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_triggers.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_triggers.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_triggers.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_triggers.id",
            ],
            name="fk_usage_ledger_entries_trigger_id_monitor_triggers",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity >= 1", name="ck_usage_ledger_entries_quantity"),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "idempotency_key",
            name="uq_usage_ledger_entries_workspace_idempotency",
        ),
        Index(
            "ix_usage_ledger_entries_tenant_workspace_period",
            "tenant_id",
            "workspace_id",
            "period_start",
        ),
        Index(
            "ix_usage_ledger_entries_tenant_workspace_monitor",
            "tenant_id",
            "workspace_id",
            "monitor_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entitlement_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspace_entitlements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monitor_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    trigger_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    unit: Mapped[str] = mapped_column(
        String(32), nullable=False, default="trigger", server_default=text("'trigger'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    ledger_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MonitorDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "monitor_definitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "artifact_id"],
            [
                f"{PRODUCT_SCHEMA}.artifacts.tenant_id",
                f"{PRODUCT_SCHEMA}.artifacts.workspace_id",
                f"{PRODUCT_SCHEMA}.artifacts.owner_user_id",
                f"{PRODUCT_SCHEMA}.artifacts.id",
            ],
            name="fk_monitor_definitions_artifact_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "artifact_id",
                "artifact_version_id",
            ],
            [
                f"{PRODUCT_SCHEMA}.artifact_versions.tenant_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.workspace_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.owner_user_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.artifact_id",
                f"{PRODUCT_SCHEMA}.artifact_versions.id",
            ],
            name="fk_monitor_definitions_artifact_version_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"run_task_type IN ({_sql_values(MONITOR_TASK_TYPES)})",
            name="ck_monitor_definitions_run_task_type",
        ),
        CheckConstraint(
            "jsonb_typeof(condition) = 'object' AND condition ? 'kind' AND "
            "jsonb_typeof(condition->'kind') = 'string' AND "
            "length(condition->>'kind') > 0",
            name="ck_monitor_definitions_condition_object",
        ),
        CheckConstraint(
            "jsonb_typeof(task_template) = 'object' AND "
            "task_template ? 'task_type' AND "
            "task_template ? 'symbol' AND "
            "task_template ? 'horizon' AND "
            "task_template ? 'query_text' AND "
            "jsonb_typeof(task_template->'task_type') = 'string' AND "
            "jsonb_typeof(task_template->'symbol') = 'string' AND "
            "jsonb_typeof(task_template->'horizon') = 'string' AND "
            "jsonb_typeof(task_template->'query_text') = 'string' AND "
            "NOT (task_template ? 'source_artifact_version_id') AND "
            "task_template->>'task_type' = run_task_type AND "
            "((task_template->>'task_type' = 'market_analysis' AND "
            "task_template ? 'notify' AND "
            "jsonb_typeof(task_template->'notify') = 'boolean') OR "
            "(task_template->>'task_type' = 'deep_research' AND "
            "NOT (task_template ? 'notify')))",
            name="ck_monitor_definitions_task_template",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(MONITOR_STATUSES)})",
            name="ck_monitor_definitions_status",
        ),
        CheckConstraint(
            "schedule_version >= 1 AND desired_revision >= 1 "
            "AND applied_revision >= 0 AND version >= 1",
            name="ck_monitor_definitions_revisions",
        ),
        CheckConstraint(
            "quiet_hours IS NULL OR (jsonb_typeof(quiet_hours) = 'object' AND "
            "quiet_hours ? 'start' AND quiet_hours ? 'end' AND "
            "jsonb_typeof(quiet_hours->'start') = 'string' AND "
            "jsonb_typeof(quiet_hours->'end') = 'string')",
            name="ck_monitor_definitions_quiet_hours_object",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_monitor_definitions_actor_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "name",
            name="uq_monitor_definitions_owner_name",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "admission_idempotency_key",
            name="uq_monitor_definitions_admission_idempotency",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "cron_binding_id",
            name="uq_monitor_definitions_cron_binding_scope",
        ),
        Index(
            "ix_monitor_definitions_tenant_workspace_status",
            "tenant_id",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_monitor_definitions_actor_next_run",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "status",
            "next_run_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    run_task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    task_template: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    admission_idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cron_schedule: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quiet_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", server_default=text("'draft'")
    )
    schedule_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    desired_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    applied_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cron_binding_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, default=uuid4
    )
    official_cron_id: Mapped[str | None] = mapped_column(String(255))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class MonitorDestination(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "monitor_destinations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_definitions.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.id",
            ],
            name="fk_monitor_destinations_monitor_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "destination_id"],
            [
                f"{PRODUCT_SCHEMA}.notification_destinations.tenant_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.workspace_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.owner_user_id",
                f"{PRODUCT_SCHEMA}.notification_destinations.id",
            ],
            name="fk_monitor_destinations_destination_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "monitor_id",
            "destination_id",
            name="uq_monitor_destinations_binding",
        ),
        Index(
            "ix_monitor_destinations_tenant_workspace_monitor",
            "tenant_id",
            "workspace_id",
            "monitor_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monitor_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    destination_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )


class MonitorCronCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "monitor_cron_commands"
    __table_args__ = (
        CheckConstraint(
            f"command_type IN ({_sql_values(MONITOR_CRON_COMMAND_TYPES)})",
            name="ck_monitor_cron_commands_command_type",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(MONITOR_CRON_COMMAND_STATUSES)})",
            name="ck_monitor_cron_commands_status",
        ),
        CheckConstraint(
            "attempt >= 0 AND fence_token >= 0 AND desired_revision >= 1",
            name="ck_monitor_cron_commands_lease_counters",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ? 'monitor_id' AND "
            "payload ? 'schedule_version' AND payload ? 'cron_binding_id' AND "
            "NOT (payload ?| ARRAY['task_template', 'condition', 'query_text', "
            "'symbol', 'horizon', 'request_payload', 'command_id', "
            "'official_cron_id', 'official_run_id', 'official_thread_id'])",
            name="ck_monitor_cron_commands_control_payload_only",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_definitions.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.id",
            ],
            name="fk_monitor_cron_commands_monitor_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_monitor_cron_commands_owner_idempotency",
        ),
        Index(
            "ix_monitor_cron_commands_dispatch",
            "status",
            "available_at",
            "lease_expires_at",
        ),
        Index(
            "ix_monitor_cron_commands_tenant_workspace_monitor",
            "tenant_id",
            "workspace_id",
            "monitor_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monitor_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(32), nullable=False)
    desired_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    request_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default=text("'pending'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fence_token: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(String(500))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonitorTrigger(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "monitor_triggers"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ({_sql_values(MONITOR_TRIGGER_KINDS)})",
            name="ck_monitor_triggers_kind",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(MONITOR_TRIGGER_STATUSES)})",
            name="ck_monitor_triggers_status",
        ),
        CheckConstraint(
            "schedule_version >= 1",
            name="ck_monitor_triggers_schedule_version",
        ),
        CheckConstraint(
            "(kind = 'cron' AND official_run_id IS NOT NULL AND "
            "manual_stable_key IS NULL) OR "
            "(kind = 'manual' AND manual_stable_key IS NOT NULL AND "
            "official_run_id IS NULL)",
            name="ck_monitor_triggers_identity_by_kind",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "monitor_id"],
            [
                f"{PRODUCT_SCHEMA}.monitor_definitions.tenant_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.workspace_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.owner_user_id",
                f"{PRODUCT_SCHEMA}.monitor_definitions.id",
            ],
            name="fk_monitor_triggers_monitor_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "task_id"],
            [
                f"{PRODUCT_SCHEMA}.tasks.tenant_id",
                f"{PRODUCT_SCHEMA}.tasks.workspace_id",
                f"{PRODUCT_SCHEMA}.tasks.owner_user_id",
                f"{PRODUCT_SCHEMA}.tasks.id",
            ],
            name="fk_monitor_triggers_task_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id", "owner_user_id", "thread_id"],
            [
                f"{PRODUCT_SCHEMA}.threads.tenant_id",
                f"{PRODUCT_SCHEMA}.threads.workspace_id",
                f"{PRODUCT_SCHEMA}.threads.owner_user_id",
                f"{PRODUCT_SCHEMA}.threads.id",
            ],
            name="fk_monitor_triggers_thread_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "id",
            name="uq_monitor_triggers_actor_scope",
        ),
        Index(
            "ix_monitor_triggers_tenant_workspace_monitor_received",
            "tenant_id",
            "workspace_id",
            "monitor_id",
            "received_at",
        ),
        Index(
            "ix_monitor_triggers_tenant_workspace_task",
            "tenant_id",
            "workspace_id",
            "task_id",
        ),
        Index(
            "uq_monitor_triggers_official_run",
            "tenant_id",
            "workspace_id",
            "monitor_id",
            "official_run_id",
            unique=True,
            postgresql_where=text("official_run_id IS NOT NULL"),
        ),
        Index(
            "uq_monitor_triggers_manual_stable_key",
            "tenant_id",
            "workspace_id",
            "monitor_id",
            "manual_stable_key",
            unique=True,
            postgresql_where=text("manual_stable_key IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monitor_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
    official_cron_id: Mapped[str | None] = mapped_column(String(255))
    official_run_id: Mapped[str | None] = mapped_column(String(255))
    official_thread_id: Mapped[str | None] = mapped_column(String(255))
    manual_stable_key: Mapped[str | None] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    schedule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    thread_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataLifecyclePolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Actor-owned retention policy used by export and deletion workflows."""

    __tablename__ = "data_lifecycle_policies"
    __table_args__ = (
        CheckConstraint(
            "product_retention_days > 0 AND artifact_retention_days > 0 AND "
            "task_retention_days > 0 AND run_retention_days > 0 AND "
            "decision_retention_days > 0 AND usage_retention_days > 0 AND "
            "completed_checkpoint_retention_days > 0 AND "
            "technical_projection_retention_days > 0 AND "
            "log_retention_days > 0 AND backup_retention_days > 0",
            name="ck_data_lifecycle_policies_positive_retention",
        ),
        CheckConstraint(
            "(legal_hold_active = false AND legal_hold_reason IS NULL) OR "
            "(legal_hold_active = true AND legal_hold_reason IS NOT NULL AND "
            "length(trim(legal_hold_reason)) > 0)",
            name="ck_data_lifecycle_policies_legal_hold_reason",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            name="uq_data_lifecycle_policies_actor_scope",
        ),
        Index(
            "ix_data_lifecycle_policies_tenant_workspace_owner",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default=text("365")
    )
    artifact_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default=text("365")
    )
    task_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default=text("365")
    )
    run_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default=text("365")
    )
    decision_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default=text("365")
    )
    usage_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default=text("365")
    )
    completed_checkpoint_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )
    technical_projection_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )
    log_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )
    backup_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=35, server_default=text("35")
    )
    retain_raw_prompt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    retain_raw_response: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    legal_hold_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    legal_hold_reason: Mapped[str | None] = mapped_column(String(500))


class DataExportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_export_jobs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(DATA_LIFECYCLE_EXPORT_STATUSES)})",
            name="ck_data_export_jobs_status",
        ),
        CheckConstraint(
            "scope = 'user_data'",
            name="ck_data_export_jobs_scope",
        ),
        CheckConstraint(
            "attempt >= 0",
            name="ck_data_export_jobs_attempt",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_data_export_jobs_actor_idempotency",
        ),
        Index(
            "ix_data_export_jobs_dispatch",
            "status",
            "available_at",
            "lease_expires_at",
        ),
        Index(
            "ix_data_export_jobs_actor_created",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "created_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DATA_LIFECYCLE_SCOPE,
        server_default=text("'user_data'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default=text("'queued'")
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_version: Mapped[int | None] = mapped_column(Integer)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    manifest_hash: Mapped[str | None] = mapped_column(String(64))
    bundle: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    last_error: Mapped[str | None] = mapped_column(String(500))


class DataDeletionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_deletion_jobs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(DATA_LIFECYCLE_DELETION_STATUSES)})",
            name="ck_data_deletion_jobs_status",
        ),
        CheckConstraint(
            "scope = 'user_data'",
            name="ck_data_deletion_jobs_scope",
        ),
        CheckConstraint(
            "attempt >= 0",
            name="ck_data_deletion_jobs_attempt",
        ),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_data_deletion_jobs_actor_idempotency",
        ),
        Index(
            "ix_data_deletion_jobs_dispatch",
            "status",
            "lease_expires_at",
            "requested_at",
        ),
        Index(
            "ix_data_deletion_jobs_actor_requested",
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "requested_at",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DATA_LIFECYCLE_SCOPE,
        server_default=text("'user_data'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default=text("'queued'")
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_hold_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    legal_hold_reason: Mapped[str | None] = mapped_column(String(500))
    system_status: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    external_deletion_reference: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    last_error: Mapped[str | None] = mapped_column(String(500))


__all__ = [
    "Artifact",
    "ArtifactVersion",
    "Decision",
    "DATA_LIFECYCLE_DELETION_STATUSES",
    "DATA_LIFECYCLE_EXPORT_STATUSES",
    "DATA_LIFECYCLE_SCOPE",
    "DataDeletionJob",
    "DataExportJob",
    "DataLifecyclePolicy",
    "Feedback",
    "INTERRUPT_PAUSE_STATUSES",
    "INTERRUPT_STATUSES",
    "InterruptPause",
    "InterruptProjection",
    "MarketSnapshot",
    "Membership",
    "MONITOR_CRON_COMMAND_STATUSES",
    "MONITOR_CRON_COMMAND_TYPES",
    "MONITOR_STATUSES",
    "MONITOR_TASK_TYPES",
    "MONITOR_TRIGGER_KINDS",
    "MONITOR_TRIGGER_STATUSES",
    "MonitorCronCommand",
    "MonitorDefinition",
    "MonitorDestination",
    "MonitorTrigger",
    "OBSERVED_TERMINAL_STATUSES",
    "REVIEW_POLICIES",
    "RUN_STATUSES",
    "Run",
    "TASK_COMMAND_STATUSES",
    "TASK_COMMAND_TYPES",
    "Task",
    "TaskCommand",
    "Tenant",
    "Thread",
    "User",
    "UsageLedgerEntry",
    "WatchlistItem",
    "WebEvidence",
    "Workspace",
    "WorkspaceEntitlement",
]
