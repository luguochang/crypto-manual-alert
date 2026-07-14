from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

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
            "external_subject",
            name="uq_users_tenant_external_subject",
        ),
        Index("ix_users_tenant_subject", "tenant_id", "external_subject"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{PRODUCT_SCHEMA}.tenants.id", ondelete="CASCADE"),
        nullable=False,
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
        UniqueConstraint("workspace_id", "user_id", name="uq_memberships_workspace_user"),
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
        Index("ix_threads_tenant_workspace_created", "tenant_id", "workspace_id", "created_at"),
        Index("ix_threads_tenant_workspace_owner", "tenant_id", "workspace_id", "owner_user_id"),
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
        Index("ix_tasks_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
        Index("ix_tasks_tenant_workspace_thread", "tenant_id", "workspace_id", "thread_id"),
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
        UniqueConstraint("resume_of_run_id", name="uq_runs_resume_of_run"),
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
        CheckConstraint(
            "resume_of_run_id IS NULL OR resume_of_run_id <> id",
            name="ck_runs_resume_not_self",
        ),
        Index("ix_runs_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
        Index("ix_runs_tenant_workspace_task", "tenant_id", "workspace_id", "task_id"),
        Index(
            "ix_runs_tenant_workspace_resume",
            "tenant_id",
            "workspace_id",
            "resume_of_run_id",
        ),
        Index("ix_runs_status_reconcile_deadline", "status", "reconciliation_deadline_at"),
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
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_terminal_status: Mapped[str | None] = mapped_column(String(32))
    resume_of_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True)
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
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "official_interrupt_id",
            "checkpoint_id",
            "response_version",
            name="uq_interrupt_inbox_scope_response",
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
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False
    )
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
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("task_id", "artifact_type", name="uq_artifacts_task_type"),
        Index("ix_artifacts_tenant_workspace_task", "tenant_id", "workspace_id", "task_id"),
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
        Index("ix_decisions_tenant_workspace_task", "tenant_id", "workspace_id", "task_id"),
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
        UniqueConstraint("thread_id", "sequence", name="uq_task_commands_thread_sequence"),
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
        Index("ix_task_commands_thread_status_sequence", "thread_id", "status", "sequence"),
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
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    official_run_id: Mapped[str | None] = mapped_column(String(255))
    official_command_id: Mapped[str | None] = mapped_column(String(255))


__all__ = [
    "Artifact",
    "ArtifactVersion",
    "Decision",
    "INTERRUPT_STATUSES",
    "InterruptProjection",
    "MarketSnapshot",
    "Membership",
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
    "WebEvidence",
    "Workspace",
]
