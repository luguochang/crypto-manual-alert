from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema

from crypto_alert_v2.api.schemas import MonitorCreateSubmission, MonitorMutationSubmission
from crypto_alert_v2.api.service import (
    MonitorConditionEvaluatorUnavailableError,
    ProductAnalysisService,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Membership,
    MonitorCronCommand,
    MonitorDefinition,
    MonitorTrigger,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    UsageLedgerEntry,
    User,
    Workspace,
    WorkspaceEntitlement,
)


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
REAL_DATABASE_TESTS = os.getenv("REAL_DATABASE_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not REAL_DATABASE_TESTS or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


def _asyncpg_url(url: str) -> str:
    return (
        url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://")
        else url
    )


@pytest_asyncio.fixture
async def database_connection() -> AsyncIterator[AsyncConnection]:
    assert DATABASE_URL is not None
    engine = create_async_engine(_asyncpg_url(DATABASE_URL))
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(PRODUCT_SCHEMA, if_not_exists=True))
        await connection.run_sync(Base.metadata.create_all)
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield connection
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime,
) -> tuple[ActorContext, object, object]:
    suffix = uuid4().hex
    actor = ActorContext(
        tenant_id=f"service-monitor-tenant-{suffix}",
        workspace_id=f"service-monitor-workspace-{suffix}",
        user_id=f"oidc|service-monitor-{suffix}",
        identity_issuer="legacy",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    tenant_id, workspace_id, user_id = uuid4(), uuid4(), uuid4()
    source_thread_id, source_task_id, source_run_id = uuid4(), uuid4(), uuid4()
    artifact_id, artifact_version_id = uuid4(), uuid4()
    async with session_factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, external_id=actor.tenant_id, name="Tenant"))
        await session.flush()
        session.add_all(
            [
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    identity_issuer=actor.identity_issuer,
                    external_subject=actor.user_id,
                    display_name="Owner",
                ),
                Workspace(
                    id=workspace_id,
                    tenant_id=tenant_id,
                    external_id=actor.workspace_id,
                    name="Workspace",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Membership(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role="member",
                    permissions=["analysis:read", "analysis:write"],
                ),
                WorkspaceEntitlement(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    active=True,
                    active_monitor_limit=3,
                    min_interval_seconds=300,
                    max_concurrent_tasks=3,
                    monthly_trigger_limit=100,
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                ),
                Thread(
                    id=source_thread_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=user_id,
                    title="Source",
                    context={},
                ),
            ]
        )
        await session.flush()
        session.add(
            Task(
                id=source_task_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                thread_id=source_thread_id,
                task_type="market_analysis",
                status="succeeded",
                idempotency_key=f"source-{suffix}",
                request_payload_hash="0" * 64,
                request_payload={
                    "symbol": "BTC-USDT-SWAP",
                    "horizon": "4h",
                    "query_text": "Review BTC market structure",
                    "notify": False,
                },
            )
        )
        await session.flush()
        session.add(
            Run(
                id=source_run_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                thread_id=source_thread_id,
                task_id=source_task_id,
                attempt=1,
                status="succeeded",
                input_payload={},
            )
        )
        session.add(
            Artifact(
                id=artifact_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                task_id=source_task_id,
                artifact_type="analysis_report",
                latest_version_number=1,
            )
        )
        await session.flush()
        session.add(
            ArtifactVersion(
                id=artifact_version_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                artifact_id=artifact_id,
                task_id=source_task_id,
                run_id=source_run_id,
                version_number=1,
                schema_version="1.0",
                status="committed",
                content={"status": "committed"},
            )
        )
    return actor, artifact_id, artifact_version_id


@pytest.mark.asyncio
async def test_product_service_monitor_lifecycle_and_manual_admission(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    actor, artifact_id, artifact_version_id = await _seed(session_factory, now)
    service = ProductAnalysisService(session_factory=session_factory, clock=lambda: now)
    submission = MonitorCreateSubmission(
        name="BTC hourly review",
        artifact_id=artifact_id,
        artifact_version_id=artifact_version_id,
        run_task_type="market_analysis",
        condition={"kind": "scheduled_review"},
        schedule="0 * * * *",
        timezone="UTC",
        expires_at=now + timedelta(days=7),
        quiet_hours=None,
        destination_ids=[],
    )

    created = await service.create_monitor(actor, submission, "monitor-create-1")
    replay = await service.create_monitor(actor, submission, "monitor-create-1")
    assert created["id"] == replay["id"]
    assert created["status"] == "draft"
    assert created["cron_configured"] is False

    paused = await service.pause_monitor(
        actor,
        str(created["id"]),
        MonitorMutationSubmission(expected_version=1),
        "monitor-pause-1",
    )
    assert paused is not None
    assert paused["status"] == "paused"

    resumed = await service.resume_monitor(
        actor,
        str(created["id"]),
        MonitorMutationSubmission(expected_version=2),
        "monitor-resume-1",
    )
    assert resumed is not None
    assert resumed["status"] == "active"

    triggered = await service.trigger_monitor(actor, str(created["id"]), "manual-1")
    assert triggered is not None
    assert triggered["latest_trigger"]["trigger_kind"] == "manual"

    async with session_factory() as session:
        tasks = list((await session.scalars(select(Task))).all())
        commands = list((await session.scalars(select(TaskCommand))).all())
        assert sum(item.task_type == "market_analysis" for item in tasks) == 2
        assert sum(item.command_type == "submit" for item in commands) == 1


async def _monitor_side_effect_counts(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[int, ...]:
    models = (
        Thread,
        Task,
        TaskCommand,
        UsageLedgerEntry,
        MonitorDefinition,
        MonitorTrigger,
        MonitorCronCommand,
    )
    async with session_factory() as session:
        counts: list[int] = []
        for model in models:
            counts.append(int(await session.scalar(select(func.count(model.id))) or 0))
        return tuple(counts)


@pytest.mark.asyncio
async def test_unsupported_monitor_conditions_fail_before_database_admission(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    actor, artifact_id, artifact_version_id = await _seed(session_factory, now)
    before = await _monitor_side_effect_counts(session_factory)
    session_factory_calls = 0

    def guarded_session_factory() -> object:
        nonlocal session_factory_calls
        session_factory_calls += 1
        raise AssertionError("unsupported monitor admission must not open a session")

    service = ProductAnalysisService(
        session_factory=guarded_session_factory,  # type: ignore[arg-type]
        clock=lambda: now,
    )
    unsupported_conditions = (
        {"kind": "price", "operator": "gte", "threshold": 70_000},
        {"kind": "thesis", "statement": "BTC remains resilient"},
        {
            "kind": "provider_health",
            "provider": "okx",
            "consecutive_failures": 2,
        },
    )

    for index, condition in enumerate(unsupported_conditions):
        submission = MonitorCreateSubmission(
            name=f"unsupported monitor {index}",
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            run_task_type="market_analysis",
            condition=condition,
            schedule="0 * * * *",
            timezone="UTC",
            expires_at=now + timedelta(days=7),
            quiet_hours=None,
            destination_ids=[],
        )
        with pytest.raises(MonitorConditionEvaluatorUnavailableError) as raised:
            await service.create_monitor(actor, submission, f"unsupported-{index}")
        assert raised.value.code == "monitor_condition_evaluator_unavailable"
        assert raised.value.condition_kind == condition["kind"]

    assert session_factory_calls == 0
    assert await _monitor_side_effect_counts(session_factory) == before


@pytest.mark.asyncio
async def test_historical_unsupported_monitor_cannot_create_trigger_side_effects(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    actor, artifact_id, artifact_version_id = await _seed(session_factory, now)
    service = ProductAnalysisService(session_factory=session_factory, clock=lambda: now)
    scheduled_submission = MonitorCreateSubmission(
        name="Legacy condition monitor",
        artifact_id=artifact_id,
        artifact_version_id=artifact_version_id,
        run_task_type="market_analysis",
        condition={"kind": "scheduled_review"},
        schedule="0 * * * *",
        timezone="UTC",
        expires_at=now + timedelta(days=7),
        quiet_hours=None,
        destination_ids=[],
    )
    created = await service.create_monitor(
        actor, scheduled_submission, "legacy-condition-monitor"
    )

    async with session_factory() as session, session.begin():
        monitor = await session.get(MonitorDefinition, created["id"])
        assert monitor is not None
        monitor.condition = {
            "kind": "price",
            "operator": "gte",
            "threshold": 70_000,
        }
        monitor.status = "active"
        await session.flush()

    before = await _monitor_side_effect_counts(session_factory)
    with pytest.raises(MonitorConditionEvaluatorUnavailableError) as raised:
        await service.trigger_monitor(actor, str(created["id"]), "legacy-price-trigger")

    assert raised.value.code == "monitor_condition_evaluator_unavailable"
    assert raised.value.condition_kind == "price"
    assert await _monitor_side_effect_counts(session_factory) == before
