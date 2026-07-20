from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import importlib.util
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from pydantic import ValidationError
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    DataDeletionJob,
    DataExportJob,
    DataLifecyclePolicy,
    Decision,
    DomainEvent,
    Feedback,
    INTERRUPT_PAUSE_STATUSES,
    INTERRUPT_STATUSES,
    InterruptPause,
    InterruptProjection,
    MarketSnapshot,
    Membership,
    MonitorCronCommand,
    MonitorDefinition,
    MonitorDestination,
    MonitorTrigger,
    NOTIFICATION_ATTEMPT_RESULTS,
    NOTIFICATION_ATTEMPT_TRIGGERS,
    NOTIFICATION_OUTBOX_STATUSES,
    NotificationAttempt,
    NotificationDestination,
    NotificationOutbox,
    OBSERVABILITY_DELIVERY_PROVIDERS,
    OBSERVABILITY_DELIVERY_STATUSES,
    ObservabilityDelivery,
    OBSERVED_TERMINAL_STATUSES,
    REVIEW_POLICIES,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    WatchlistItem,
    WebEvidence,
    Workspace,
    WorkspaceEntitlement,
    UsageLedgerEntry,
)
from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    PendingInterruptMemberView,
    PendingInterruptPauseView,
    TaskView,
)
from crypto_alert_v2.domain.models import (
    Artifact as DomainArtifact,
    EvidenceVerdict,
    MarketAnalysis,
    RiskVerdict,
)
from crypto_alert_v2.graph.request import ArtifactReviewPayload
from crypto_alert_v2.persistence.repositories import (
    ArtifactRepository,
    RunRepository,
    TaskCommandRepository,
    TaskRepository,
)
from tests.fixtures.golden_cases import valid_market_analysis


BACKEND_ROOT = Path(__file__).resolve().parents[2]


INITIAL_TABLES = {
    "tenants",
    "users",
    "workspaces",
    "memberships",
    "threads",
    "tasks",
    "runs",
    "market_snapshots",
    "web_evidence",
    "artifacts",
    "artifact_versions",
    "decisions",
    "task_commands",
}
EXPECTED_TABLES = INITIAL_TABLES | {
    "feedback",
    "interrupt_inbox",
    "interrupt_pauses",
    "notification_outbox",
    "notification_attempts",
    "notification_destinations",
    "watchlist_items",
    "observability_deliveries",
    "domain_events",
    "workspace_entitlements",
    "usage_ledger_entries",
    "monitor_definitions",
    "monitor_destinations",
    "monitor_cron_commands",
    "monitor_triggers",
    "data_lifecycle_policies",
    "data_export_jobs",
    "data_deletion_jobs",
}

TABLE_MODELS = (
    Tenant,
    User,
    Workspace,
    Membership,
    Thread,
    Task,
    Run,
    MarketSnapshot,
    WebEvidence,
    Artifact,
    ArtifactVersion,
    Decision,
    Feedback,
    TaskCommand,
    InterruptPause,
    InterruptProjection,
    NotificationOutbox,
    NotificationAttempt,
    NotificationDestination,
    WatchlistItem,
    ObservabilityDelivery,
    DomainEvent,
    WorkspaceEntitlement,
    UsageLedgerEntry,
    MonitorDefinition,
    MonitorDestination,
    MonitorCronCommand,
    MonitorTrigger,
    DataLifecyclePolicy,
    DataExportJob,
    DataDeletionJob,
)

WORKSPACE_SCOPED_TABLES = EXPECTED_TABLES - {"tenants", "users", "workspaces"}

EXPECTED_JSONB_COLUMNS = {
    ("memberships", "permissions"),
    ("threads", "context"),
    ("tasks", "request_payload"),
    ("runs", "input_payload"),
    ("runs", "output_payload"),
    ("market_snapshots", "snapshot"),
    ("web_evidence", "payload"),
    ("artifact_versions", "content"),
    ("decisions", "decision"),
    ("decisions", "evidence_verdict"),
    ("decisions", "risk_verdict"),
    ("task_commands", "payload"),
    ("interrupt_inbox", "payload"),
    ("interrupt_inbox", "response"),
    ("interrupt_pauses", "root_checkpoint_map"),
    ("notification_outbox", "payload"),
    ("domain_events", "payload"),
    ("usage_ledger_entries", "metadata"),
    ("monitor_definitions", "condition"),
    ("monitor_definitions", "task_template"),
    ("monitor_definitions", "quiet_hours"),
    ("monitor_cron_commands", "payload"),
    ("data_export_jobs", "manifest"),
    ("data_export_jobs", "bundle"),
    ("data_deletion_jobs", "system_status"),
    ("data_deletion_jobs", "external_deletion_reference"),
}

RUN_STATUSES = {
    "queued",
    "running",
    "waiting_human",
    "succeeded",
    "blocked",
    "failed",
    "cancelled",
}


def _unique_column_sets(table_name: str) -> set[frozenset[str]]:
    table = Base.metadata.tables[f"{PRODUCT_SCHEMA}.{table_name}"]
    return {
        frozenset(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _index_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[f"{PRODUCT_SCHEMA}.{table_name}"]
    return {
        tuple(column.name for column in cast(Index, index).columns)
        for index in table.indexes
    }


def test_metadata_contains_only_the_product_core_tables() -> None:
    assert {table.name for table in Base.metadata.sorted_tables} == EXPECTED_TABLES
    assert {table.schema for table in Base.metadata.sorted_tables} == {PRODUCT_SCHEMA}
    assert not any("checkpoint" in table.name for table in Base.metadata.sorted_tables)


@pytest.mark.parametrize("model", TABLE_MODELS)
def test_every_product_entity_has_a_postgresql_uuid_primary_key(model: Any) -> None:
    primary_key_columns = list(model.__table__.primary_key.columns)

    assert [column.name for column in primary_key_columns] == ["id"]
    assert isinstance(primary_key_columns[0].type, UUID)
    assert primary_key_columns[0].type.as_uuid is True


def test_tenant_and_workspace_ownership_is_backed_by_foreign_keys() -> None:
    for table in Base.metadata.sorted_tables:
        if table.name == "tenants":
            continue

        assert "tenant_id" in table.c
        tenant_targets = {
            foreign_key.target_fullname
            for foreign_key in table.c.tenant_id.foreign_keys
        }
        assert f"{PRODUCT_SCHEMA}.tenants.id" in tenant_targets

        if table.name not in WORKSPACE_SCOPED_TABLES:
            continue

        assert "workspace_id" in table.c
        workspace_targets = {
            foreign_key.target_fullname
            for foreign_key in table.c.workspace_id.foreign_keys
        }
        assert f"{PRODUCT_SCHEMA}.workspaces.id" in workspace_targets


def test_actor_external_identifiers_and_lineage_keys_are_unique() -> None:
    assert frozenset({"external_id"}) in _unique_column_sets("tenants")
    assert frozenset({"tenant_id", "external_id"}) in _unique_column_sets("workspaces")
    assert frozenset({"external_id"}) not in _unique_column_sets("workspaces")
    assert frozenset(
        {"tenant_id", "identity_issuer", "external_subject"}
    ) in _unique_column_sets("users")
    assert frozenset({"external_subject"}) not in _unique_column_sets("users")
    assert frozenset({"workspace_id", "user_id"}) in _unique_column_sets("memberships")
    assert frozenset({"task_id", "attempt"}) in _unique_column_sets("runs")
    assert frozenset({"resume_of_run_id"}) in _unique_column_sets("runs")
    assert frozenset(
        {"tenant_id", "workspace_id", "owner_user_id", "task_id", "id"}
    ) in _unique_column_sets("runs")
    assert frozenset(
        {
            "tenant_id",
            "workspace_id",
            "official_interrupt_id",
            "checkpoint_id",
            "response_version",
        }
    ) in _unique_column_sets("interrupt_inbox")
    assert frozenset({"artifact_id", "version_number"}) in _unique_column_sets(
        "artifact_versions"
    )
    assert frozenset({"artifact_version_id"}) in _unique_column_sets("decisions")
    assert frozenset({"thread_id", "sequence"}) in _unique_column_sets("task_commands")
    assert frozenset({"workspace_id", "idempotency_key"}) in _unique_column_sets(
        "task_commands"
    )
    assert frozenset(
        {"workspace_id", "task_id", "channel", "type", "decision_version"}
    ) in _unique_column_sets("notification_outbox")
    assert frozenset({"outbox_id", "attempt_number"}) in _unique_column_sets(
        "notification_attempts"
    )
    assert frozenset({"workspace_id", "idempotency_key"}) in _unique_column_sets(
        "feedback"
    )
    assert frozenset(
        {"tenant_id", "workspace_id", "owner_user_id", "run_id"}
    ) in _unique_column_sets("feedback")


def test_analysis_admission_is_persisted_and_actor_workspace_unique() -> None:
    assert isinstance(Task.__table__.c.idempotency_key.type, String)
    assert Task.__table__.c.idempotency_key.type.length == 255
    assert Task.__table__.c.idempotency_key.nullable is False
    assert isinstance(Task.__table__.c.request_payload_hash.type, String)
    assert Task.__table__.c.request_payload_hash.type.length == 64
    assert Task.__table__.c.request_payload_hash.nullable is False
    assert frozenset(
        {"tenant_id", "workspace_id", "owner_user_id", "idempotency_key"}
    ) in _unique_column_sets("tasks")


def test_run_persists_nullable_official_assistant_id() -> None:
    column = Run.__table__.c.official_assistant_id

    assert isinstance(column.type, String)
    assert column.type.length == 255
    assert column.nullable is True


def test_run_persists_reconciliation_deadline_and_projection_fence() -> None:
    table = Run.__table__

    assert isinstance(table.c.reconciliation_deadline_at.type, DateTime)
    assert table.c.reconciliation_deadline_at.type.timezone is True
    assert table.c.reconciliation_deadline_at.nullable is True
    assert isinstance(table.c.projection_fence.type, Integer)
    assert table.c.projection_fence.nullable is False
    assert table.c.projection_fence.default is not None
    assert table.c.projection_fence.default.arg == 0
    assert table.c.projection_fence.server_default is not None
    assert str(table.c.projection_fence.server_default.arg) == "0"
    assert isinstance(table.c.terminal_output_hash.type, String)
    assert table.c.terminal_output_hash.type.length == 64
    assert table.c.terminal_output_hash.nullable is True
    assert isinstance(table.c.cancel_requested_at.type, DateTime)
    assert table.c.cancel_requested_at.type.timezone is True
    assert table.c.cancel_requested_at.nullable is True
    assert isinstance(table.c.observed_terminal_status.type, String)
    assert table.c.observed_terminal_status.type.length == 32
    assert table.c.observed_terminal_status.nullable is True
    assert isinstance(table.c.resume_of_run_id.type, UUID)
    assert table.c.resume_of_run_id.type.as_uuid is True
    assert table.c.resume_of_run_id.nullable is True

    indexes = {
        cast(Index, index).name: tuple(
            column.name for column in cast(Index, index).columns
        )
        for index in table.indexes
    }
    assert indexes["ix_runs_status_reconcile_deadline"] == (
        "status",
        "reconciliation_deadline_at",
    )
    assert indexes["ix_runs_tenant_workspace_resume"] == (
        "tenant_id",
        "workspace_id",
        "resume_of_run_id",
    )
    assert indexes["ix_runs_tenant_workspace_fork_source"] == (
        "tenant_id",
        "workspace_id",
        "forked_from_run_id",
    )


def test_workspace_review_policy_is_server_owned_and_constrained() -> None:
    column = Workspace.__table__.c.review_policy

    assert isinstance(column.type, String)
    assert column.type.length == 32
    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg == "bypass"
    assert column.server_default is not None
    assert str(column.server_default.arg) == "'bypass'"

    constraint = next(
        constraint
        for constraint in Workspace.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_workspaces_review_policy"
    )
    sql = str(constraint.sqltext)
    assert {value for value in REVIEW_POLICIES if f"'{value}'" in sql} == set(
        REVIEW_POLICIES
    )
    assert "review_policy" not in AnalysisSubmission.model_fields


def test_run_resume_and_fork_lineage_is_actor_task_scoped() -> None:
    table = Run.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    resume_fk = constraints["fk_runs_resume_scope"]
    assert isinstance(resume_fk, ForeignKeyConstraint)
    assert tuple(column.name for column in resume_fk.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "resume_of_run_id",
    )
    assert tuple(element.target_fullname for element in resume_fk.elements) == (
        "app.runs.tenant_id",
        "app.runs.workspace_id",
        "app.runs.owner_user_id",
        "app.runs.task_id",
        "app.runs.id",
    )
    assert resume_fk.ondelete == "CASCADE"

    no_self = constraints["ck_runs_resume_not_self"]
    assert isinstance(no_self, CheckConstraint)
    assert "resume_of_run_id <> id" in str(no_self.sqltext)

    fork_fk = constraints["fk_runs_fork_source_scope"]
    assert isinstance(fork_fk, ForeignKeyConstraint)
    assert tuple(column.name for column in fork_fk.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "forked_from_run_id",
        "forked_from_checkpoint_id",
    )
    assert tuple(element.target_fullname for element in fork_fk.elements) == (
        "app.runs.tenant_id",
        "app.runs.workspace_id",
        "app.runs.owner_user_id",
        "app.runs.task_id",
        "app.runs.id",
        "app.runs.checkpoint_id",
    )
    assert fork_fk.ondelete == "RESTRICT"
    fork_unique = constraints["uq_runs_fork_checkpoint_scope"]
    assert isinstance(fork_unique, UniqueConstraint)
    assert tuple(column.name for column in fork_unique.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "id",
        "checkpoint_id",
    )
    assert table.c.forked_from_run_id.nullable is True
    assert table.c.forked_from_checkpoint_id.nullable is True
    assert table.c.forked_from_checkpoint_id.type.length == 255
    assert "forked_from_run_id <> id" in str(
        constraints["ck_runs_fork_not_self"].sqltext
    )
    complete_lineage_sql = str(constraints["ck_runs_fork_lineage_complete"].sqltext)
    assert "forked_from_run_id IS NULL" in complete_lineage_sql
    assert "forked_from_checkpoint_id IS NULL" in complete_lineage_sql

    observed = constraints["ck_runs_observed_terminal_status"]
    assert isinstance(observed, CheckConstraint)
    observed_sql = str(observed.sqltext)
    assert {
        value for value in OBSERVED_TERMINAL_STATUSES if f"'{value}'" in observed_sql
    } == set(OBSERVED_TERMINAL_STATUSES)
    assert "interrupted" not in observed_sql
    assert "running" not in observed_sql


def test_interrupt_projection_has_formal_state_scope_and_query_contracts() -> None:
    table = InterruptProjection.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert {
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
        "official_interrupt_id",
        "namespace",
        "checkpoint_id",
        "response_version",
        "status",
        "payload",
        "response",
        "expires_at",
        "responded_at",
        "created_at",
        "updated_at",
    } <= set(table.c.keys())
    assert table.c.response_version.default.arg == 1
    assert str(table.c.response_version.server_default.arg) == "1"
    assert table.c.status.default.arg == "pending"
    assert str(table.c.status.server_default.arg) == "'pending'"
    assert isinstance(table.c.namespace.type, Text)
    assert table.c.namespace.nullable is False

    run_scope = constraints["fk_interrupt_inbox_run_scope"]
    assert isinstance(run_scope, ForeignKeyConstraint)
    assert tuple(column.name for column in run_scope.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
    )
    assert tuple(element.target_fullname for element in run_scope.elements) == (
        "app.runs.tenant_id",
        "app.runs.workspace_id",
        "app.runs.owner_user_id",
        "app.runs.task_id",
        "app.runs.id",
    )

    status_constraint = constraints["ck_interrupt_inbox_status"]
    assert isinstance(status_constraint, CheckConstraint)
    status_sql = str(status_constraint.sqltext)
    assert {value for value in INTERRUPT_STATUSES if f"'{value}'" in status_sql} == set(
        INTERRUPT_STATUSES
    )

    indexes = _index_column_sets("interrupt_inbox")
    assert (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "status",
        "expires_at",
    ) in indexes
    assert ("tenant_id", "workspace_id", "task_id", "status") in indexes
    assert ("tenant_id", "workspace_id", "run_id", "status") in indexes
    assert ("checkpoint_id", "official_interrupt_id") in indexes


def test_interrupt_pause_is_the_scope_safe_multi_interrupt_aggregate() -> None:
    table = InterruptPause.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}
    active_index = next(
        index
        for index in table.indexes
        if index.name == "uq_interrupt_pauses_one_active_task"
    )

    assert {
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
        "pause_version",
        "root_thread_id",
        "root_checkpoint_ns",
        "root_checkpoint_id",
        "root_checkpoint_map",
        "member_set_hash",
        "status",
        "expires_at",
        "resume_run_id",
        "accepted_payload_hash",
        "created_at",
        "updated_at",
    } <= set(table.c.keys())
    assert table.c.pause_version.default.arg == 1
    assert str(table.c.pause_version.server_default.arg) == "1"
    assert table.c.status.default.arg == "pending"
    assert str(table.c.status.server_default.arg) == "'pending'"
    assert isinstance(table.c.root_checkpoint_ns.type, Text)
    assert isinstance(table.c.root_checkpoint_map.type, JSONB)
    assert table.c.resume_run_id.nullable is True
    assert table.c.accepted_payload_hash.nullable is True
    assert active_index.unique is True
    assert tuple(column.name for column in active_index.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
    )
    assert str(active_index.dialect_options["postgresql"]["where"]) == (
        "status IN ('pending', 'responding')"
    )

    assert frozenset({"run_id", "pause_version"}) in _unique_column_sets(
        "interrupt_pauses"
    )
    assert frozenset(
        {"run_id", "root_checkpoint_ns", "root_checkpoint_id"}
    ) in _unique_column_sets("interrupt_pauses")
    assert frozenset({"resume_run_id"}) in _unique_column_sets("interrupt_pauses")
    assert frozenset(
        {
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "task_id",
            "run_id",
            "id",
        }
    ) in _unique_column_sets("interrupt_pauses")

    run_scope = constraints["fk_interrupt_pauses_run_scope"]
    assert isinstance(run_scope, ForeignKeyConstraint)
    assert tuple(column.name for column in run_scope.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
    )
    assert tuple(element.target_fullname for element in run_scope.elements) == (
        "app.runs.tenant_id",
        "app.runs.workspace_id",
        "app.runs.owner_user_id",
        "app.runs.task_id",
        "app.runs.id",
    )

    resume_scope = constraints["fk_interrupt_pauses_resume_scope"]
    assert isinstance(resume_scope, ForeignKeyConstraint)
    assert tuple(column.name for column in resume_scope.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "resume_run_id",
    )
    assert tuple(element.target_fullname for element in resume_scope.elements) == (
        "app.runs.tenant_id",
        "app.runs.workspace_id",
        "app.runs.owner_user_id",
        "app.runs.task_id",
        "app.runs.id",
    )

    status_constraint = constraints["ck_interrupt_pauses_status"]
    assert isinstance(status_constraint, CheckConstraint)
    status_sql = str(status_constraint.sqltext)
    assert {
        value for value in INTERRUPT_PAUSE_STATUSES if f"'{value}'" in status_sql
    } == set(INTERRUPT_PAUSE_STATUSES)


def test_interrupt_projection_membership_is_optional_unique_and_bidirectional() -> None:
    table = InterruptProjection.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert table.c.pause_id.nullable is False
    assert frozenset({"pause_id", "official_interrupt_id"}) in _unique_column_sets(
        "interrupt_inbox"
    )

    pause_scope = constraints["fk_interrupt_inbox_pause_scope"]
    assert isinstance(pause_scope, ForeignKeyConstraint)
    assert tuple(column.name for column in pause_scope.columns) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
        "pause_id",
    )
    assert tuple(element.target_fullname for element in pause_scope.elements) == (
        "app.interrupt_pauses.tenant_id",
        "app.interrupt_pauses.workspace_id",
        "app.interrupt_pauses.owner_user_id",
        "app.interrupt_pauses.task_id",
        "app.interrupt_pauses.run_id",
        "app.interrupt_pauses.id",
    )
    assert pause_scope.ondelete == "CASCADE"

    assert InterruptPause.projections.property.back_populates == "pause"
    assert InterruptPause.projections.property.uselist is True
    assert InterruptProjection.pause.property.back_populates == "projections"
    assert InterruptProjection.pause.property.uselist is False


def test_notification_outbox_has_durable_delivery_and_lease_contracts() -> None:
    table = NotificationOutbox.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert {
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
        "artifact_id",
        "artifact_version_id",
        "decision_id",
        "channel",
        "type",
        "decision_version",
        "payload",
        "payload_hash",
        "status",
        "available_at",
        "attempt_count",
        "lease_owner",
        "lease_expires_at",
        "fence_token",
        "delivered_at",
        "terminal_at",
        "created_at",
        "updated_at",
    } <= set(table.c.keys())
    assert isinstance(table.c.payload.type, JSONB)
    assert isinstance(table.c.payload_hash.type, String)
    assert table.c.payload_hash.type.length == 64
    assert table.c.payload_hash.nullable is False
    assert table.c.status.default.arg == "planned"
    assert str(table.c.status.server_default.arg) == "'planned'"
    assert table.c.attempt_count.default.arg == 0
    assert str(table.c.attempt_count.server_default.arg) == "0"
    assert table.c.fence_token.default.arg == 0
    assert str(table.c.fence_token.server_default.arg) == "0"
    assert table.c.lease_owner.nullable is True
    assert table.c.lease_expires_at.nullable is True
    assert table.c.delivered_at.nullable is True
    assert table.c.terminal_at.nullable is True

    status_constraint = constraints["ck_notification_outbox_status"]
    assert isinstance(status_constraint, CheckConstraint)
    status_sql = str(status_constraint.sqltext)
    assert {
        value for value in NOTIFICATION_OUTBOX_STATUSES if f"'{value}'" in status_sql
    } == set(NOTIFICATION_OUTBOX_STATUSES)
    assert "attempt_count BETWEEN 0 AND 5" in str(
        constraints["ck_notification_outbox_attempt_count"].sqltext
    )
    assert "fence_token >= 0" in str(
        constraints["ck_notification_outbox_fence_token"].sqltext
    )
    active_lease_sql = str(constraints["ck_notification_outbox_active_lease"].sqltext)
    assert "status IN ('leased', 'sending')" in active_lease_sql
    assert "lease_owner IS NOT NULL" in active_lease_sql
    assert "lease_expires_at IS NOT NULL" in active_lease_sql

    indexes = _index_column_sets("notification_outbox")
    assert ("status", "available_at", "created_at") in indexes
    assert ("status", "lease_expires_at") in indexes
    assert ("tenant_id", "workspace_id", "task_id") in indexes


def test_notification_attempts_form_an_append_only_delivery_audit_ledger() -> None:
    table = NotificationAttempt.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert {
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "outbox_id",
        "attempt_number",
        "owner",
        "fence_token",
        "trigger",
        "requested_by",
        "reason",
        "delay_seconds",
        "retry_after_seconds",
        "cost_units",
        "result",
        "provider_receipt",
        "error_code",
        "created_at",
        "finished_at",
    } <= set(table.c.keys())
    assert table.c.delay_seconds.default.arg == 0
    assert str(table.c.delay_seconds.server_default.arg) == "0"
    assert isinstance(table.c.cost_units.type, Numeric)
    assert table.c.cost_units.type.precision == 18
    assert table.c.cost_units.type.scale == 6
    assert str(table.c.cost_units.server_default.arg) == "0"
    assert table.c.result.default.arg == "leased"
    assert str(table.c.result.server_default.arg) == "'leased'"
    assert table.c.requested_by.nullable is True
    assert table.c.retry_after_seconds.nullable is True
    assert table.c.finished_at.nullable is True

    outbox_fk = next(iter(table.c.outbox_id.foreign_keys))
    assert outbox_fk.target_fullname == f"{PRODUCT_SCHEMA}.notification_outbox.id"
    assert outbox_fk.ondelete == "CASCADE"

    trigger_sql = str(constraints["ck_notification_attempts_trigger"].sqltext)
    assert {
        value for value in NOTIFICATION_ATTEMPT_TRIGGERS if f"'{value}'" in trigger_sql
    } == set(NOTIFICATION_ATTEMPT_TRIGGERS)
    result_sql = str(constraints["ck_notification_attempts_result"].sqltext)
    assert {
        value for value in NOTIFICATION_ATTEMPT_RESULTS if f"'{value}'" in result_sql
    } == set(NOTIFICATION_ATTEMPT_RESULTS)
    assert "attempt_number BETWEEN 1 AND 5" in str(
        constraints["ck_notification_attempts_attempt_number"].sqltext
    )
    assert "fence_token >= 1" in str(
        constraints["ck_notification_attempts_fence_token"].sqltext
    )
    metrics_sql = str(
        constraints["ck_notification_attempts_nonnegative_metrics"].sqltext
    )
    assert "delay_seconds >= 0" in metrics_sql
    assert "retry_after_seconds IS NULL OR retry_after_seconds >= 0" in metrics_sql
    assert "cost_units >= 0" in metrics_sql
    manual_actor_sql = str(constraints["ck_notification_attempts_manual_actor"].sqltext)
    assert "trigger = 'automatic' AND requested_by IS NULL" in manual_actor_sql
    assert "trigger = 'manual' AND requested_by IS NOT NULL" in manual_actor_sql

    indexes = _index_column_sets("notification_attempts")
    assert ("tenant_id", "workspace_id", "task_id", "created_at") in indexes
    assert ("outbox_id", "created_at") in indexes


def test_observability_deliveries_have_scoped_idempotency_and_fenced_state() -> None:
    table = ObservabilityDelivery.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert {
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
        "provider",
        "event_type",
        "event_version",
        "delivery_key",
        "correlation_id",
        "status",
        "sampled",
        "skip_reason",
        "attempt_count",
        "fence_token",
        "lease_owner",
        "lease_expires_at",
        "next_attempt_at",
        "verification_deadline",
        "provider_trace_id",
        "last_stage",
        "last_retry_state",
        "last_error_code",
        "last_error_type",
        "last_error_summary",
        "last_error_at",
        "verified_at",
        "terminal_at",
        "created_at",
        "updated_at",
    } <= set(table.c.keys())
    assert table.c.status.default.arg == "planned"
    assert str(table.c.status.server_default.arg) == "'planned'"
    assert table.c.sampled.default.arg is True
    assert str(table.c.sampled.server_default.arg) == "true"
    assert table.c.attempt_count.default.arg == 0
    assert table.c.fence_token.default.arg == 0

    provider_sql = str(constraints["ck_observability_deliveries_provider"].sqltext)
    assert {
        value
        for value in OBSERVABILITY_DELIVERY_PROVIDERS
        if f"'{value}'" in provider_sql
    } == set(OBSERVABILITY_DELIVERY_PROVIDERS)
    status_sql = str(constraints["ck_observability_deliveries_status"].sqltext)
    assert {
        value for value in OBSERVABILITY_DELIVERY_STATUSES if f"'{value}'" in status_sql
    } == set(OBSERVABILITY_DELIVERY_STATUSES)
    assert "event_version >= 1" in str(
        constraints["ck_observability_deliveries_event_version"].sqltext
    )
    assert "attempt_count >= 0" in str(
        constraints["ck_observability_deliveries_attempt_count"].sqltext
    )
    assert "fence_token >= 0" in str(
        constraints["ck_observability_deliveries_fence_token"].sqltext
    )
    active_lease_sql = str(
        constraints["ck_observability_deliveries_active_lease"].sqltext
    )
    assert "status IN ('leased', 'verifying')" in active_lease_sql
    assert "lease_owner IS NOT NULL" in active_lease_sql
    assert "lease_expires_at IS NOT NULL" in active_lease_sql
    assert "status = 'not_requested'" in str(
        constraints["ck_observability_deliveries_skip_reason"].sqltext
    )
    assert "provider_trace_id IS NOT NULL" in str(
        constraints["ck_observability_deliveries_verified_receipt"].sqltext
    )

    unique_sets = _unique_column_sets("observability_deliveries")
    assert (
        frozenset(
            {
                "tenant_id",
                "workspace_id",
                "task_id",
                "run_id",
                "provider",
                "event_type",
                "event_version",
            }
        )
        in unique_sets
    )
    assert frozenset({"tenant_id", "workspace_id", "delivery_key"}) in unique_sets
    indexes = _index_column_sets("observability_deliveries")
    assert ("tenant_id", "workspace_id", "task_id", "run_id") in indexes
    assert ("status", "next_attempt_at", "created_at") in indexes
    assert ("status", "lease_expires_at") in indexes

    task_scope = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "fk_observability_deliveries_task_scope"
    )
    run_scope = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "fk_observability_deliveries_run_scope"
    )
    assert tuple(element.parent.name for element in task_scope.elements) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
    )
    assert tuple(element.parent.name for element in run_scope.elements) == (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "task_id",
        "run_id",
    )


def test_task_view_exposes_only_typed_pending_interrupts() -> None:
    now = datetime(2026, 7, 15, 9, 30, tzinfo=UTC)
    payload = ArtifactReviewPayload(
        review_iteration=1,
        artifact=DomainArtifact(
            content_version=1,
            status="draft",
            analysis=MarketAnalysis.model_validate(valid_market_analysis()),
            evidence_verdict=EvidenceVerdict(sufficient=True),
            risk_verdict=RiskVerdict(allowed=True),
            source_references=["https://example.com/review-source"],
        ),
    ).model_dump(mode="json")
    interrupt = {
        "interrupt_id": "interrupt-1",
        "response_version": 1,
        "status": "pending",
        "payload": payload,
    }
    pause = {
        "pause_id": "11111111-1111-4111-8111-111111111111",
        "pause_version": 1,
        "status": "pending",
        "expires_at": now,
        "members": [interrupt],
    }
    view = TaskView.model_validate(
        {
            "task_id": "task-1",
            "status": "waiting_human",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "query_text": "Review this analysis.",
            "created_at": now,
            "pending_interrupts": pause,
        }
    )

    assert view.pending_interrupts == PendingInterruptPauseView.model_validate(pause)
    serialized = view.model_dump(mode="json")
    for internal_field in ("run_id", "namespace", "checkpoint_id"):
        assert internal_field not in serialized["pending_interrupts"]["members"][0]
        with pytest.raises(ValidationError):
            PendingInterruptMemberView.model_validate(
                {**interrupt, internal_field: "must-not-leak"}
            )
    assert (
        TaskView.model_validate(
            {
                "task_id": "task-2",
                "status": "queued",
                "symbol": "ETH-USDT-SWAP",
                "horizon": "4h",
                "created_at": now,
            }
        ).pending_interrupts
        is None
    )
    with pytest.raises(ValidationError):
        PendingInterruptMemberView.model_validate({**interrupt, "status": "resolved"})
    with pytest.raises(ValidationError):
        PendingInterruptMemberView.model_validate({**interrupt, "response_version": 0})


def test_workspace_access_paths_have_composite_indexes() -> None:
    for table_name in WORKSPACE_SCOPED_TABLES:
        assert any(
            columns[:2] == ("tenant_id", "workspace_id")
            for columns in _index_column_sets(table_name)
        ), table_name


def test_structured_payloads_use_jsonb_and_timestamps_are_timezone_aware() -> None:
    actual_jsonb_columns: set[tuple[str, str]] = set()

    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                actual_jsonb_columns.add((table.name, column.name))
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True, f"{table.name}.{column.name}"

    assert actual_jsonb_columns == EXPECTED_JSONB_COLUMNS


def test_run_status_check_constraint_contains_exactly_the_supported_states() -> None:
    constraints = [
        constraint
        for constraint in Run.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_runs_status"
    ]

    assert len(constraints) == 1
    sql = str(constraints[0].sqltext)
    assert {status for status in RUN_STATUSES if f"'{status}'" in sql} == RUN_STATUSES
    assert "degraded" not in sql


@dataclass(frozen=True, slots=True)
class _Actor:
    tenant_id: str = "tenant-external"
    workspace_id: str = "workspace-external"
    user_id: str = "oidc|subject"
    identity_issuer: str = "https://identity.example.com"
    context_id: UUID | None = None


class _RecordingSession:
    def __init__(self) -> None:
        self.statement: Any | None = None

    async def scalar(self, statement: Any) -> None:
        self.statement = statement
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repository_type",
    (TaskRepository, RunRepository, ArtifactRepository, TaskCommandRepository),
)
async def test_repository_reads_resolve_actor_scope_inside_the_resource_query(
    repository_type: type[Any],
) -> None:
    recording_session = _RecordingSession()
    repository = repository_type(cast(AsyncSession, recording_session), _Actor())

    assert await repository.get(uuid4()) is None
    assert recording_session.statement is not None
    sql = str(
        recording_session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "tenants.external_id = 'tenant-external'" in sql
    assert "workspaces.external_id = 'workspace-external'" in sql
    assert "users.external_subject = 'oidc|subject'" in sql
    assert "users.identity_issuer = 'https://identity.example.com'" in sql
    assert "memberships.is_active IS true" in sql
    assert "app.memberships.tenant_id = app.tenants.id" in sql
    assert "app.memberships.workspace_id = app.workspaces.id" in sql
    assert "app.memberships.user_id = app.users.id" in sql
    actor_column = (
        "actor_user_id" if repository_type is TaskCommandRepository else "owner_user_id"
    )
    assert (
        f"app.{repository_type.model.__tablename__}.{actor_column} = app.users.id"
        in sql
    )


class _MigrationOperations:
    def __init__(self) -> None:
        self.created_tables: list[tuple[str, str | None]] = []
        self.dropped_tables: list[tuple[str, str | None]] = []
        self.added_columns: list[tuple[str, str, str | None]] = []
        self.altered_columns: list[tuple[str, str, bool | None, str | None]] = []
        self.created_constraints: list[
            tuple[str, str, tuple[str, ...], str | None]
        ] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], str | None]] = []
        self.dropped_indexes: list[tuple[str, str | None, str | None]] = []
        self.dropped_columns: list[tuple[str, str, str | None]] = []
        self.executed: list[str] = []

    def execute(self, statement: Any) -> None:
        self.executed.append(str(statement))

    def create_table(
        self, name: str, *elements: Any, schema: str | None = None
    ) -> None:
        self.created_tables.append((name, schema))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        *,
        schema: str | None = None,
        **_: Any,
    ) -> None:
        self.created_indexes.append((name, table_name, tuple(columns), schema))

    def drop_index(
        self,
        name: str,
        *,
        table_name: str | None = None,
        schema: str | None = None,
        **_: Any,
    ) -> None:
        self.dropped_indexes.append((name, table_name, schema))

    def drop_table(self, name: str, *, schema: str | None = None) -> None:
        self.dropped_tables.append((name, schema))

    def add_column(
        self,
        table_name: str,
        column: Any,
        *,
        schema: str | None = None,
    ) -> None:
        self.added_columns.append((table_name, column.name, schema))

    def alter_column(
        self,
        table_name: str,
        column_name: str,
        *,
        nullable: bool | None = None,
        schema: str | None = None,
        **_: Any,
    ) -> None:
        self.altered_columns.append((table_name, column_name, nullable, schema))

    def create_unique_constraint(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        *,
        schema: str | None = None,
    ) -> None:
        self.created_constraints.append((name, table_name, tuple(columns), schema))

    def drop_constraint(
        self,
        name: str,
        table_name: str,
        *,
        schema: str | None = None,
        **_: Any,
    ) -> None:
        self.dropped_constraints.append((name, table_name, schema))

    def drop_column(
        self,
        table_name: str,
        column_name: str,
        *,
        schema: str | None = None,
    ) -> None:
        self.dropped_columns.append((table_name, column_name, schema))


def _load_initial_revision() -> Any:
    revision_path = BACKEND_ROOT / "alembic" / "versions" / "0001_initial.py"
    spec = importlib.util.spec_from_file_location(
        "product_initial_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_admission_revision() -> Any:
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0002_analysis_admission_idempotency.py"
    )
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_analysis_admission_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_tenant_actor_revision() -> Any:
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0003_tenant_scoped_actor_ids.py"
    )
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_tenant_actor_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_official_assistant_revision() -> Any:
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0004_official_assistant_id.py"
    )
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_official_assistant_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_run_recovery_revision() -> Any:
    revision_path = BACKEND_ROOT / "alembic" / "versions" / "0005_run_recovery_state.py"
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_run_recovery_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_interrupt_projection_revision() -> Any:
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0006_interrupt_projection.py"
    )
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_interrupt_projection_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_run_fork_revision() -> Any:
    revision_path = BACKEND_ROOT / "alembic" / "versions" / "0009_run_fork_lineage.py"
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_run_fork_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_notification_outbox_revision() -> Any:
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0010_notification_outbox.py"
    )
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_notification_outbox_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_retry_lineage_revision() -> Any:
    revision_path = BACKEND_ROOT / "alembic" / "versions" / "0012_run_retry_lineage.py"
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_retry_lineage_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_feedback_revision() -> Any:
    revision_path = BACKEND_ROOT / "alembic" / "versions" / "0013_feedback.py"
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_feedback_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_watchlist_revision() -> Any:
    revision_path = BACKEND_ROOT / "alembic" / "versions" / "0014_watchlist.py"
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_watchlist_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _load_observability_delivery_revision() -> Any:
    revision_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0015_observability_delivery.py"
    )
    assert revision_path.is_file()
    spec = importlib.util.spec_from_file_location(
        "product_observability_delivery_revision", revision_path
    )
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def test_initial_revision_explicitly_creates_and_drops_the_product_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _load_initial_revision()
    operations = _MigrationOperations()
    monkeypatch.setattr(revision, "op", operations)

    assert revision.revision == "0001_initial"
    assert revision.down_revision is None
    revision.upgrade()
    revision.downgrade()

    assert set(operations.created_tables) == {
        (table_name, PRODUCT_SCHEMA) for table_name in INITIAL_TABLES
    }
    assert set(operations.dropped_tables) == {
        (table_name, PRODUCT_SCHEMA) for table_name in INITIAL_TABLES
    }


def test_analysis_admission_revision_backfills_and_constrains_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _load_admission_revision()
    operations = _MigrationOperations()
    monkeypatch.setattr(revision, "op", operations)

    assert revision.revision == "0002_analysis_idempotency"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0001_initial"
    revision.upgrade()
    revision.downgrade()

    assert set(operations.added_columns) == {
        ("tasks", "idempotency_key", PRODUCT_SCHEMA),
        ("tasks", "request_payload_hash", PRODUCT_SCHEMA),
    }
    assert set(operations.altered_columns) == {
        ("tasks", "idempotency_key", False, PRODUCT_SCHEMA),
        ("tasks", "request_payload_hash", False, PRODUCT_SCHEMA),
    }
    assert operations.created_constraints == [
        (
            "uq_tasks_actor_workspace_idempotency",
            "tasks",
            ("tenant_id", "workspace_id", "owner_user_id", "idempotency_key"),
            PRODUCT_SCHEMA,
        )
    ]
    assert any("UPDATE app.tasks" in statement for statement in operations.executed)
    assert operations.dropped_constraints == [
        ("uq_tasks_actor_workspace_idempotency", "tasks", PRODUCT_SCHEMA)
    ]
    assert operations.dropped_columns == [
        ("tasks", "request_payload_hash", PRODUCT_SCHEMA),
        ("tasks", "idempotency_key", PRODUCT_SCHEMA),
    ]


def test_tenant_actor_revision_replaces_global_external_id_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _load_tenant_actor_revision()
    operations = _MigrationOperations()
    monkeypatch.setattr(revision, "op", operations)

    assert revision.revision == "0003_tenant_actor_ids"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0002_analysis_idempotency"
    revision.upgrade()
    revision.downgrade()

    assert operations.dropped_constraints == [
        ("uq_users_external_subject", "users", PRODUCT_SCHEMA),
        ("uq_workspaces_external_id", "workspaces", PRODUCT_SCHEMA),
        ("uq_workspaces_tenant_external_id", "workspaces", PRODUCT_SCHEMA),
        ("uq_users_tenant_external_subject", "users", PRODUCT_SCHEMA),
    ]
    assert operations.created_constraints == [
        (
            "uq_users_tenant_external_subject",
            "users",
            ("tenant_id", "external_subject"),
            PRODUCT_SCHEMA,
        ),
        (
            "uq_workspaces_tenant_external_id",
            "workspaces",
            ("tenant_id", "external_id"),
            PRODUCT_SCHEMA,
        ),
        (
            "uq_workspaces_external_id",
            "workspaces",
            ("external_id",),
            PRODUCT_SCHEMA,
        ),
        (
            "uq_users_external_subject",
            "users",
            ("external_subject",),
            PRODUCT_SCHEMA,
        ),
    ]


def test_official_assistant_revision_adds_and_drops_nullable_run_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _load_official_assistant_revision()
    operations = _MigrationOperations()
    monkeypatch.setattr(revision, "op", operations)

    assert revision.revision == "0004_official_assistant_id"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0003_tenant_actor_ids"
    revision.upgrade()
    revision.downgrade()

    assert operations.added_columns == [
        ("runs", "official_assistant_id", PRODUCT_SCHEMA)
    ]
    assert operations.dropped_columns == [
        ("runs", "official_assistant_id", PRODUCT_SCHEMA)
    ]


def test_run_recovery_revision_adds_durable_reconciliation_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _load_run_recovery_revision()
    operations = _MigrationOperations()
    monkeypatch.setattr(revision, "op", operations)

    assert revision.revision == "0005_run_recovery_state"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0004_official_assistant_id"
    revision.upgrade()
    revision.downgrade()

    assert set(operations.added_columns) == {
        ("runs", "reconciliation_deadline_at", PRODUCT_SCHEMA),
        ("runs", "projection_fence", PRODUCT_SCHEMA),
        ("runs", "terminal_output_hash", PRODUCT_SCHEMA),
        ("runs", "cancel_requested_at", PRODUCT_SCHEMA),
    }
    assert set(operations.dropped_columns) == {
        ("runs", "cancel_requested_at", PRODUCT_SCHEMA),
        ("runs", "terminal_output_hash", PRODUCT_SCHEMA),
        ("runs", "projection_fence", PRODUCT_SCHEMA),
        ("runs", "reconciliation_deadline_at", PRODUCT_SCHEMA),
    }
    assert operations.created_indexes == [
        (
            "ix_runs_status_reconcile_deadline",
            "runs",
            ("status", "reconciliation_deadline_at"),
            PRODUCT_SCHEMA,
        )
    ]
    assert operations.dropped_indexes == [
        ("ix_runs_status_reconcile_deadline", "runs", PRODUCT_SCHEMA)
    ]
    assert any(
        "SET reconciliation_deadline_at = started_at + interval '15 minutes'"
        in statement
        for statement in operations.executed
    )


def _render_run_recovery_sql(method_name: str) -> str:
    revision = _load_run_recovery_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def test_run_recovery_revision_upgrade_and_downgrade_compile_for_postgresql() -> None:
    upgrade_sql = _render_run_recovery_sql("upgrade")
    downgrade_sql = _render_run_recovery_sql("downgrade")

    assert (
        "ALTER TABLE app.runs ADD COLUMN reconciliation_deadline_at "
        "TIMESTAMP WITH TIME ZONE;"
    ) in upgrade_sql
    assert (
        "ALTER TABLE app.runs ADD COLUMN projection_fence INTEGER DEFAULT 0 NOT NULL;"
    ) in upgrade_sql
    assert (
        "ALTER TABLE app.runs ADD COLUMN terminal_output_hash VARCHAR(64);"
    ) in upgrade_sql
    assert (
        "ALTER TABLE app.runs ADD COLUMN cancel_requested_at TIMESTAMP WITH TIME ZONE;"
    ) in upgrade_sql
    assert (
        "CREATE INDEX ix_runs_status_reconcile_deadline "
        "ON app.runs (status, reconciliation_deadline_at);"
    ) in upgrade_sql

    downgrade_statements = [
        "DROP INDEX app.ix_runs_status_reconcile_deadline;",
        "ALTER TABLE app.runs DROP COLUMN cancel_requested_at;",
        "ALTER TABLE app.runs DROP COLUMN terminal_output_hash;",
        "ALTER TABLE app.runs DROP COLUMN projection_fence;",
        "ALTER TABLE app.runs DROP COLUMN reconciliation_deadline_at;",
    ]
    positions = [downgrade_sql.index(statement) for statement in downgrade_statements]
    assert positions == sorted(positions)


def _render_run_fork_sql(method_name: str) -> str:
    revision = _load_run_fork_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def test_run_fork_revision_compiles_auditable_scoped_lineage() -> None:
    revision = _load_run_fork_revision()
    assert revision.revision == "0009_run_fork_lineage"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0008_oidc_identity_issuer"

    upgrade_sql = _render_run_fork_sql("upgrade")
    downgrade_sql = _render_run_fork_sql("downgrade")
    assert "ALTER TABLE app.runs ADD COLUMN forked_from_run_id UUID;" in upgrade_sql
    assert (
        "ALTER TABLE app.runs ADD COLUMN forked_from_checkpoint_id VARCHAR(255);"
        in upgrade_sql
    )
    assert "CONSTRAINT fk_runs_fork_source_scope" in upgrade_sql
    assert "CONSTRAINT uq_runs_fork_checkpoint_scope UNIQUE" in upgrade_sql
    assert (
        "FOREIGN KEY(tenant_id, workspace_id, owner_user_id, task_id, " in upgrade_sql
    )
    assert "forked_from_run_id, forked_from_checkpoint_id)" in upgrade_sql
    assert (
        "REFERENCES app.runs (tenant_id, workspace_id, owner_user_id, task_id, "
        "id, checkpoint_id)" in upgrade_sql
    )
    assert "ON DELETE RESTRICT" in upgrade_sql
    assert "ck_runs_fork_lineage_complete" in upgrade_sql
    assert "ix_runs_tenant_workspace_fork_source" in upgrade_sql
    assert "DROP COLUMN forked_from_checkpoint_id" in downgrade_sql
    assert "DROP COLUMN forked_from_run_id" in downgrade_sql


def _render_notification_outbox_sql(method_name: str) -> str:
    revision = _load_notification_outbox_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def test_notification_outbox_revision_compiles_complete_delivery_schema() -> None:
    revision = _load_notification_outbox_revision()

    assert revision.revision == "0010_notification_outbox"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0009_run_fork_lineage"

    upgrade_sql = _render_notification_outbox_sql("upgrade")
    downgrade_sql = _render_notification_outbox_sql("downgrade")

    required_upgrade_statements = (
        "CREATE TABLE app.notification_outbox (",
        "payload JSONB NOT NULL",
        "CONSTRAINT uq_notification_outbox_logical_key UNIQUE "
        "(workspace_id, task_id, channel, type, decision_version)",
        "CONSTRAINT ck_notification_outbox_active_lease CHECK "
        "((status IN ('leased', 'sending')) = "
        "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL))",
        "CREATE INDEX ix_notification_outbox_status_available ON "
        "app.notification_outbox (status, available_at, created_at);",
        "CREATE TABLE app.notification_attempts (",
        "cost_units NUMERIC(18, 6) DEFAULT 0 NOT NULL",
        "CONSTRAINT fk_notification_attempts_outbox_id_notification_outbox "
        "FOREIGN KEY(outbox_id) REFERENCES app.notification_outbox (id) "
        "ON DELETE CASCADE",
        "CONSTRAINT uq_notification_attempts_outbox_number UNIQUE "
        "(outbox_id, attempt_number)",
        "CONSTRAINT ck_notification_attempts_manual_actor CHECK "
        "((trigger = 'automatic' AND requested_by IS NULL) OR "
        "(trigger = 'manual' AND requested_by IS NOT NULL))",
        "CREATE INDEX ix_notification_attempts_outbox_created ON "
        "app.notification_attempts (outbox_id, created_at);",
    )
    for statement in required_upgrade_statements:
        assert statement in upgrade_sql

    downgrade_statements = (
        "DROP INDEX app.ix_notification_attempts_outbox_created;",
        "DROP INDEX app.ix_notification_attempts_scope_task;",
        "DROP TABLE app.notification_attempts;",
        "DROP INDEX app.ix_notification_outbox_scope_task;",
        "DROP INDEX app.ix_notification_outbox_lease_expiry;",
        "DROP INDEX app.ix_notification_outbox_status_available;",
        "DROP TABLE app.notification_outbox;",
    )
    positions = [downgrade_sql.index(statement) for statement in downgrade_statements]
    assert positions == sorted(positions)


def _render_retry_lineage_sql(method_name: str) -> str:
    revision = _load_retry_lineage_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def test_retry_lineage_revision_compiles_scoped_retry_constraints() -> None:
    revision = _load_retry_lineage_revision()

    assert revision.revision == "0012_run_retry_lineage"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0011_notification_destinations"

    upgrade_sql = _render_retry_lineage_sql("upgrade")
    downgrade_sql = _render_retry_lineage_sql("downgrade")

    required_upgrade_statements = (
        "ALTER TABLE app.runs ADD COLUMN retry_of_run_id UUID;",
        "CONSTRAINT uq_runs_retry_of_run UNIQUE (retry_of_run_id)",
        "CONSTRAINT fk_runs_retry_scope FOREIGN KEY(tenant_id, workspace_id, "
        "owner_user_id, task_id, retry_of_run_id) REFERENCES app.runs",
        "ON DELETE RESTRICT",
        "CONSTRAINT ck_runs_retry_not_self CHECK (retry_of_run_id IS NULL OR "
        "retry_of_run_id <> id)",
        "CREATE INDEX ix_runs_tenant_workspace_retry ON app.runs "
        "(tenant_id, workspace_id, retry_of_run_id);",
    )
    for statement in required_upgrade_statements:
        assert statement in upgrade_sql

    downgrade_statements = (
        "DROP INDEX app.ix_runs_tenant_workspace_retry;",
        "ALTER TABLE app.runs DROP CONSTRAINT ck_runs_retry_not_self;",
        "ALTER TABLE app.runs DROP CONSTRAINT fk_runs_retry_scope;",
        "ALTER TABLE app.runs DROP CONSTRAINT uq_runs_retry_of_run;",
        "ALTER TABLE app.runs DROP COLUMN retry_of_run_id;",
    )
    positions = [downgrade_sql.index(statement) for statement in downgrade_statements]
    assert positions == sorted(positions)


def _render_feedback_sql(method_name: str) -> str:
    revision = _load_feedback_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def test_feedback_revision_compiles_owner_scoped_idempotent_schema() -> None:
    revision = _load_feedback_revision()

    assert revision.revision == "0013_feedback"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0012_run_retry_lineage"

    upgrade_sql = _render_feedback_sql("upgrade")
    downgrade_sql = _render_feedback_sql("downgrade")
    for statement in (
        "CREATE TABLE app.feedback (",
        "rating VARCHAR(16) NOT NULL",
        "CONSTRAINT ck_feedback_rating CHECK (rating IN ('positive', 'negative'))",
        "CONSTRAINT uq_feedback_workspace_idempotency UNIQUE "
        "(workspace_id, idempotency_key)",
        "CONSTRAINT uq_feedback_owner_run UNIQUE "
        "(tenant_id, workspace_id, owner_user_id, run_id)",
        "CREATE INDEX ix_feedback_tenant_workspace_run ON app.feedback "
        "(tenant_id, workspace_id, run_id);",
    ):
        assert statement in upgrade_sql
    assert "DROP INDEX app.ix_feedback_tenant_workspace_run;" in downgrade_sql
    assert "DROP TABLE app.feedback;" in downgrade_sql


def test_watchlist_revision_compiles_owner_scoped_symbol_schema() -> None:
    revision = _load_watchlist_revision()

    assert revision.revision == "0014_watchlist"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0013_feedback"

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    revision.upgrade()
    upgrade_sql = output.getvalue()

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    revision.downgrade()
    downgrade_sql = output.getvalue()

    for statement in (
        "CREATE TABLE app.watchlist_items (",
        "symbol VARCHAR(64) NOT NULL",
        "CONSTRAINT uq_watchlist_owner_symbol UNIQUE "
        "(tenant_id, workspace_id, owner_user_id, symbol)",
        "CREATE INDEX ix_watchlist_tenant_workspace_owner ON app.watchlist_items "
        "(tenant_id, workspace_id, owner_user_id);",
    ):
        assert statement in upgrade_sql
    assert "DROP INDEX app.ix_watchlist_tenant_workspace_owner;" in downgrade_sql
    assert "DROP TABLE app.watchlist_items;" in downgrade_sql


def test_observability_delivery_revision_compiles_durable_scoped_ledger() -> None:
    revision = _load_observability_delivery_revision()

    assert revision.revision == "0015_observability_delivery"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0014_watchlist"

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    revision.upgrade()
    upgrade_sql = output.getvalue()

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    revision.downgrade()
    downgrade_sql = output.getvalue()

    for statement in (
        "CREATE TABLE app.observability_deliveries (",
        "correlation_id VARCHAR(255) NOT NULL",
        "verification_deadline TIMESTAMP WITH TIME ZONE",
        "CONSTRAINT uq_observability_deliveries_logical_key UNIQUE "
        "(tenant_id, workspace_id, task_id, run_id, provider, event_type, "
        "event_version)",
        "CONSTRAINT fk_observability_deliveries_task_scope FOREIGN KEY(tenant_id, "
        "workspace_id, owner_user_id, task_id) REFERENCES app.tasks",
        "CONSTRAINT fk_observability_deliveries_run_scope FOREIGN KEY(tenant_id, "
        "workspace_id, owner_user_id, task_id, run_id) REFERENCES app.runs",
        "CREATE INDEX ix_observability_deliveries_due ON "
        "app.observability_deliveries (status, next_attempt_at, created_at);",
    ):
        assert statement in upgrade_sql
    assert (
        "DROP INDEX app.ix_observability_deliveries_provider_status;" in downgrade_sql
    )
    assert "DROP TABLE app.observability_deliveries;" in downgrade_sql


def _render_interrupt_projection_sql(method_name: str) -> str:
    revision = _load_interrupt_projection_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    revision.op = Operations(context)
    getattr(revision, method_name)()
    return output.getvalue()


def test_interrupt_projection_revision_compiles_complete_upgrade_and_downgrade() -> (
    None
):
    revision = _load_interrupt_projection_revision()

    assert revision.revision == "0006_interrupt_projection"
    assert len(revision.revision) <= 32
    assert revision.down_revision == "0005_run_recovery_state"

    upgrade_sql = _render_interrupt_projection_sql("upgrade")
    downgrade_sql = _render_interrupt_projection_sql("downgrade")

    required_upgrade_statements = (
        "ALTER TABLE app.workspaces ADD COLUMN review_policy "
        "VARCHAR(32) DEFAULT 'bypass' NOT NULL;",
        "ALTER TABLE app.workspaces ADD CONSTRAINT ck_workspaces_review_policy "
        "CHECK (review_policy IN ('bypass', 'required'));",
        "ALTER TABLE app.runs ADD COLUMN resume_of_run_id UUID;",
        "ALTER TABLE app.runs ADD COLUMN observed_terminal_status VARCHAR(32);",
        "ALTER TABLE app.runs ADD CONSTRAINT ck_runs_observed_terminal_status "
        "CHECK (observed_terminal_status IS NULL OR observed_terminal_status "
        "IN ('error', 'success', 'timeout'));",
        "ALTER TABLE app.runs ADD CONSTRAINT fk_runs_resume_scope "
        "FOREIGN KEY(tenant_id, workspace_id, owner_user_id, task_id, "
        "resume_of_run_id) REFERENCES app.runs (tenant_id, workspace_id, "
        "owner_user_id, task_id, id) ON DELETE CASCADE;",
        "CREATE TABLE app.interrupt_inbox (",
        "namespace TEXT NOT NULL",
        "CONSTRAINT fk_interrupt_inbox_run_scope FOREIGN KEY(tenant_id, "
        "workspace_id, owner_user_id, task_id, run_id) REFERENCES app.runs "
        "(tenant_id, workspace_id, owner_user_id, task_id, id) ON DELETE CASCADE",
        "CONSTRAINT ck_interrupt_inbox_status CHECK (status IN "
        "('pending', 'responding', 'resolved', 'expired', 'cancelled'))",
        "CREATE INDEX ix_interrupt_inbox_scope_status_expiry ON "
        "app.interrupt_inbox (tenant_id, workspace_id, owner_user_id, status, "
        "expires_at);",
    )
    for statement in required_upgrade_statements:
        assert statement in upgrade_sql

    downgrade_statements = (
        "DROP TABLE app.interrupt_inbox;",
        "ALTER TABLE app.runs DROP CONSTRAINT fk_runs_resume_scope;",
        "ALTER TABLE app.runs DROP CONSTRAINT ck_runs_observed_terminal_status;",
        "ALTER TABLE app.runs DROP COLUMN observed_terminal_status;",
        "ALTER TABLE app.runs DROP COLUMN resume_of_run_id;",
        "ALTER TABLE app.workspaces DROP CONSTRAINT ck_workspaces_review_policy;",
        "ALTER TABLE app.workspaces DROP COLUMN review_policy;",
    )
    positions = [downgrade_sql.index(statement) for statement in downgrade_statements]
    assert positions == sorted(positions)


def test_alembic_uses_asyncpg_and_keeps_its_version_table_in_product_schema() -> None:
    ini = (BACKEND_ROOT / "alembic.ini").read_text(encoding="utf-8")
    env = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")

    assert "script_location = %(here)s/alembic" in ini
    assert "sqlalchemy.url = postgresql+asyncpg://" in ini
    assert "async_engine_from_config" in env
    assert "PRODUCT_DATABASE_URL" in env
    assert "version_table_schema=PRODUCT_SCHEMA" in env
    assert "include_schemas=True" in env
