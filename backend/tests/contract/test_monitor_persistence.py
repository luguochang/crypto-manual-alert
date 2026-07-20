from __future__ import annotations

from datetime import UTC, datetime
import inspect
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from crypto_alert_v2.graph.request import AnalysisRequest, DeepResearchRequest
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    MonitorCronCommand,
    MonitorDefinition,
    MonitorDestination,
    MonitorTrigger,
    UsageLedgerEntry,
    WorkspaceEntitlement,
)
from crypto_alert_v2.persistence.monitor_repository import (
    ACTIVE_MONITOR_STATUSES,
    MonitorRepository,
    _in_quiet_hours,
    _normalize_condition,
    _normalize_quiet_hours,
    _task_payload_from_template,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MONITOR_TABLES = {
    "workspace_entitlements",
    "usage_ledger_entries",
    "monitor_definitions",
    "monitor_destinations",
    "monitor_cron_commands",
    "monitor_triggers",
}


def _constraint_sql(model: type[object], name: str) -> str:
    matches = [
        constraint
        for constraint in model.__table__.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, CheckConstraint) and constraint.name == name
    ]
    assert len(matches) == 1
    return str(matches[0].sqltext)


def _unique_sets(model: type[object]) -> set[frozenset[str]]:
    return {
        frozenset(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, UniqueConstraint)
    }


def _monitor(*, timezone: str, quiet_hours: dict[str, str] | None) -> MonitorDefinition:
    return MonitorDefinition(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
        artifact_id=uuid4(),
        artifact_version_id=uuid4(),
        name="BTC review",
        run_task_type="market_analysis",
        condition={"kind": "scheduled_review"},
        task_template={
            "task_type": "market_analysis",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "query_text": "Review BTC market structure",
            "notify": False,
        },
        admission_idempotency_key="monitor-create-1",
        request_payload_hash="a" * 64,
        cron_schedule="0 */4 * * *",
        timezone=timezone,
        quiet_hours=quiet_hours,
        status="active",
        schedule_version=3,
        desired_revision=3,
        applied_revision=2,
        cron_binding_id=uuid4(),
        version=3,
    )


def test_monitor_metadata_contains_product_owned_tables_and_jsonb() -> None:
    assert MONITOR_TABLES <= {table.name for table in Base.metadata.sorted_tables}
    assert {table.schema for table in Base.metadata.sorted_tables} == {PRODUCT_SCHEMA}
    assert isinstance(MonitorDefinition.__table__.c.condition.type, JSONB)
    assert isinstance(MonitorDefinition.__table__.c.task_template.type, JSONB)
    assert isinstance(MonitorDefinition.__table__.c.cron_binding_id.type, UUID)
    assert MonitorDefinition.__table__.c.cron_binding_id.type.as_uuid is True
    assert isinstance(MonitorCronCommand.__table__.c.payload.type, JSONB)


def test_entitlement_and_create_admission_are_workspace_actor_unique() -> None:
    assert set(ACTIVE_MONITOR_STATUSES) == {"draft", "active", "paused", "degraded"}
    assert frozenset({"workspace_id"}) in _unique_sets(WorkspaceEntitlement)
    assert frozenset({"tenant_id", "workspace_id"}) in _unique_sets(
        WorkspaceEntitlement
    )
    monitor_uniques = _unique_sets(MonitorDefinition)
    assert (
        frozenset(
            {
                "tenant_id",
                "workspace_id",
                "owner_user_id",
                "admission_idempotency_key",
            }
        )
        in monitor_uniques
    )
    assert (
        frozenset({"tenant_id", "workspace_id", "owner_user_id", "cron_binding_id"})
        in monitor_uniques
    )
    assert MonitorDefinition.__table__.c.request_payload_hash.type.length == 64


def test_condition_and_task_template_checks_match_api_contracts() -> None:
    condition_sql = _constraint_sql(
        MonitorDefinition, "ck_monitor_definitions_condition_object"
    )
    assert "condition ? 'kind'" in condition_sql
    assert "condition->'kind'" in condition_sql
    assert "condition ? 'type'" not in condition_sql

    template_sql = _constraint_sql(
        MonitorDefinition, "ck_monitor_definitions_task_template"
    )
    assert "task_template->>'task_type' = run_task_type" in template_sql
    assert "source_artifact_version_id" in template_sql
    assert "deep_research" in template_sql
    assert "NOT (task_template ? 'notify')" in template_sql
    assert "jsonb_typeof(task_template->'notify') = 'boolean'" in template_sql


def test_server_template_builds_exact_graph_request_payloads() -> None:
    market_template = {
        "task_type": "market_analysis",
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "query_text": "Review BTC market structure",
        "notify": True,
    }
    market_payload = _task_payload_from_template(market_template)
    assert set(market_payload) == {"symbol", "horizon", "query_text", "notify"}
    assert AnalysisRequest.model_validate(market_payload).notify is True

    deep_template = {
        "task_type": "deep_research",
        "symbol": "ETH-USDT-SWAP",
        "horizon": "1d",
        "query_text": "Research ETH catalysts",
    }
    deep_payload = _task_payload_from_template(deep_template)
    assert set(deep_payload) == {"task_type", "symbol", "horizon", "query_text"}
    assert DeepResearchRequest.model_validate(deep_payload).task_type == "deep_research"
    assert "notify" not in deep_payload
    assert "source_artifact_version_id" not in market_payload | deep_payload


def test_condition_and_quiet_hours_validation_are_fail_closed() -> None:
    assert _normalize_condition({"kind": "price", "operator": "gte"}) == {
        "kind": "price",
        "operator": "gte",
    }
    for invalid in ({"type": "price"}, {"kind": ""}, {}):
        with pytest.raises(ValueError, match="kind"):
            _normalize_condition(invalid)

    assert _normalize_quiet_hours({"start": "22:30", "end": "06:15"}) == {
        "start": "22:30",
        "end": "06:15",
    }
    for invalid in (
        {"start": "24:00", "end": "06:00"},
        {"start": "22:00", "end": "6:00"},
        {"start": "22:00"},
        {"start": "22:00", "end": "22:00"},
    ):
        with pytest.raises(ValueError, match="quiet_hours"):
            _normalize_quiet_hours(invalid)


def test_quiet_hours_are_cross_midnight_and_dst_aware() -> None:
    shanghai = _monitor(
        timezone="Asia/Shanghai", quiet_hours={"start": "22:00", "end": "06:00"}
    )
    assert _in_quiet_hours(shanghai, datetime(2026, 1, 1, 15, 30, tzinfo=UTC))
    assert _in_quiet_hours(shanghai, datetime(2026, 1, 1, 21, 30, tzinfo=UTC))
    assert not _in_quiet_hours(shanghai, datetime(2026, 1, 1, 22, 30, tzinfo=UTC))

    new_york = _monitor(
        timezone="America/New_York",
        quiet_hours={"start": "01:00", "end": "03:00"},
    )
    assert _in_quiet_hours(new_york, datetime(2026, 3, 8, 6, 30, tzinfo=UTC))
    assert not _in_quiet_hours(new_york, datetime(2026, 3, 8, 7, 30, tzinfo=UTC))
    assert _in_quiet_hours(new_york, datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
    assert _in_quiet_hours(new_york, datetime(2026, 11, 1, 6, 30, tzinfo=UTC))


def test_cron_outbox_contains_only_stable_control_references() -> None:
    monitor = _monitor(timezone="UTC", quiet_hours=None)
    payload = MonitorRepository._cron_control_payload(monitor)
    assert payload["monitor_id"] == str(monitor.id)
    assert payload["schedule_version"] == monitor.schedule_version
    assert payload["cron_binding_id"] == str(monitor.cron_binding_id)
    assert (
        not {
            "command_id",
            "official_cron_id",
            "official_run_id",
            "official_thread_id",
            "task_template",
            "condition",
            "query_text",
            "symbol",
            "horizon",
        }
        & payload.keys()
    )
    payload_check = _constraint_sql(
        MonitorCronCommand, "ck_monitor_cron_commands_control_payload_only"
    )
    for key in ("monitor_id", "schedule_version", "cron_binding_id"):
        assert f"payload ? '{key}'" in payload_check
    for forbidden in ("command_id", "official_cron_id", "task_template"):
        assert forbidden in payload_check


def test_trigger_idempotency_and_destination_scope_are_database_enforced() -> None:
    indexes = {index.name: index for index in MonitorTrigger.__table__.indexes}
    assert indexes["uq_monitor_triggers_official_run"].unique is True
    assert indexes["uq_monitor_triggers_manual_stable_key"].unique is True
    assert (
        indexes["uq_monitor_triggers_official_run"].dialect_options["postgresql"][
            "where"
        ]
        is not None
    )
    assert (
        indexes["uq_monitor_triggers_manual_stable_key"].dialect_options["postgresql"][
            "where"
        ]
        is not None
    )

    composite_foreign_keys = {
        tuple(column.name for column in constraint.columns)
        for constraint in MonitorDestination.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint) and len(constraint.columns) > 1
    }
    assert (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "monitor_id",
    ) in composite_foreign_keys
    assert (
        "tenant_id",
        "workspace_id",
        "owner_user_id",
        "destination_id",
    ) in composite_foreign_keys


def test_usage_and_trigger_history_are_append_only_and_not_cascaded() -> None:
    assert "updated_at" not in UsageLedgerEntry.__table__.c
    assert "updated_at" not in MonitorTrigger.__table__.c
    assert frozenset({"tenant_id", "workspace_id", "idempotency_key"}) in _unique_sets(
        UsageLedgerEntry
    )
    for model in (UsageLedgerEntry, MonitorTrigger, MonitorCronCommand):
        for foreign_key in model.__table__.foreign_keys:
            assert foreign_key.ondelete != "CASCADE"

    entitlement_migration = (
        BACKEND_ROOT / "alembic" / "versions" / "0020_entitlements_usage.py"
    ).read_text()
    monitor_migration = (
        BACKEND_ROOT / "alembic" / "versions" / "0021_scheduled_monitors.py"
    ).read_text()
    assert "usage_ledger_entries_append_only" in entitlement_migration
    assert "BEFORE UPDATE OR DELETE" in entitlement_migration
    assert "monitor_triggers_append_only" in monitor_migration
    assert "BEFORE UPDATE OR DELETE" in monitor_migration
    assert 'down_revision = "0019_ddgs_provenance"' in entitlement_migration
    assert 'down_revision = "0020_entitlements_usage"' in monitor_migration


def test_repository_orders_idempotency_and_binding_checks_before_mutation() -> None:
    create_signature = inspect.signature(MonitorRepository.create_monitor)
    assert "admission_idempotency_key" in create_signature.parameters
    assert "request_payload_hash" in create_signature.parameters
    assert "task_template" not in create_signature.parameters

    entitlement_source = inspect.getsource(MonitorRepository.require_entitlement)
    assert "admission_key" not in entitlement_source
    assert "admission_hash" not in entitlement_source

    update_source = inspect.getsource(MonitorRepository.update_monitor)
    assert update_source.index("existing_command") < update_source.index(
        "monitor.version != expected_version"
    )
    assert 'status == "paused"' in update_source
    assert 'status == "pause"' not in update_source

    admission_source = inspect.getsource(MonitorRepository.admit_trigger)
    assert admission_source.index("cron_binding_id != monitor.cron_binding_id") < (
        admission_source.index("existing = await self._find_existing_trigger")
    )
    assert "official_thread_id=None" in admission_source
