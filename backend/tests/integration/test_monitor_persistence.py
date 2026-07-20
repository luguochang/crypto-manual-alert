from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import os
from uuid import UUID, uuid4

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

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.graph.request import AnalysisRequest
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
from crypto_alert_v2.persistence.monitor_repository import (
    EntitlementDenied,
    MonitorIdempotencyConflict,
    MonitorRepository,
    TriggerAdmissionRejected,
)


PRODUCT_DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
REAL_DATABASE_TESTS = os.getenv("REAL_DATABASE_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not REAL_DATABASE_TESTS or not PRODUCT_DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    separator = url.find("://")
    if url.startswith("postgresql+") and separator != -1:
        return "postgresql+asyncpg" + url[separator:]
    return url


@pytest_asyncio.fixture
async def database_connection() -> AsyncIterator[AsyncConnection]:
    assert PRODUCT_DATABASE_URL is not None
    engine = create_async_engine(_asyncpg_url(PRODUCT_DATABASE_URL))
    async with engine.begin() as migration_connection:
        await migration_connection.execute(
            CreateSchema(PRODUCT_SCHEMA, if_not_exists=True)
        )
        await migration_connection.run_sync(Base.metadata.create_all)

    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield connection
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


async def _seed_lineage_and_entitlement(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
) -> tuple[ActorContext, UUID, UUID]:
    suffix = uuid4().hex
    actor = ActorContext(
        tenant_id=f"monitor-tenant-{suffix}",
        workspace_id=f"monitor-workspace-{suffix}",
        user_id=f"oidc|monitor-{suffix}",
        identity_issuer="legacy",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    tenant_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    thread_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    artifact_id = uuid4()
    artifact_version_id = uuid4()

    async with session_factory() as session, session.begin():
        session.add(
            Tenant(id=tenant_id, external_id=actor.tenant_id, name="Monitor tenant")
        )
        await session.flush()
        session.add_all(
            [
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    identity_issuer=actor.identity_issuer,
                    external_subject=actor.user_id,
                    display_name="Monitor owner",
                ),
                Workspace(
                    id=workspace_id,
                    tenant_id=tenant_id,
                    external_id=actor.workspace_id,
                    name="Monitor workspace",
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
                Thread(
                    id=thread_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=user_id,
                    title="Committed BTC source",
                    context={},
                ),
                WorkspaceEntitlement(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    active=True,
                    active_monitor_limit=1,
                    min_interval_seconds=60,
                    max_concurrent_tasks=5,
                    monthly_trigger_limit=100,
                    valid_from=now - timedelta(days=1),
                    valid_until=now + timedelta(days=30),
                ),
            ]
        )
        await session.flush()
        session.add(
            Task(
                id=task_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                thread_id=thread_id,
                task_type="market_analysis",
                status="succeeded",
                idempotency_key=f"source-{suffix}",
                request_payload_hash="0" * 64,
                request_payload={
                    "symbol": "BTC-USDT-SWAP",
                    "horizon": "4h",
                    "query_text": "Review BTC market structure",
                    "notify": True,
                },
            )
        )
        await session.flush()
        session.add(
            Run(
                id=run_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                thread_id=thread_id,
                task_id=task_id,
                attempt=1,
                status="succeeded",
                input_payload={"symbol": "BTC-USDT-SWAP"},
            )
        )
        await session.flush()
        session.add(
            Artifact(
                id=artifact_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                task_id=task_id,
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
                task_id=task_id,
                run_id=run_id,
                version_number=1,
                schema_version="1.0",
                status="committed",
                content={"status": "committed"},
            )
        )
    return actor, artifact_id, artifact_version_id


async def _create_active_monitor(
    repository: MonitorRepository,
    *,
    artifact_id: UUID,
    artifact_version_id: UUID,
    key: str,
    request_hash: str,
    now: datetime,
    name: str = "BTC scheduled review",
    timezone: str = "UTC",
    quiet_hours: dict[str, str] | None = None,
) -> MonitorDefinition:
    return await repository.create_monitor(
        admission_idempotency_key=key,
        request_payload_hash=request_hash,
        artifact_id=artifact_id,
        artifact_version_id=artifact_version_id,
        name=name,
        run_task_type="market_analysis",
        condition={"kind": "scheduled_review"},
        cron_schedule="0 */4 * * *",
        timezone=timezone,
        quiet_hours=quiet_hours,
        status="active",
        now=now,
    )


@pytest.mark.asyncio
async def test_monitor_create_operations_and_trigger_admission_are_idempotent(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    actor, artifact_id, artifact_version_id = await _seed_lineage_and_entitlement(
        session_factory, now=now
    )

    async with session_factory() as session, session.begin():
        repository = MonitorRepository(session, actor)
        monitor = await _create_active_monitor(
            repository,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            key="create-monitor-1",
            request_hash="a" * 64,
            now=now,
        )
        binding_id = monitor.cron_binding_id
        assert monitor.condition["kind"] == "scheduled_review"
        assert monitor.task_template == {
            "task_type": "market_analysis",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "query_text": "Review BTC market structure",
            "notify": True,
        }

        replay = await _create_active_monitor(
            repository,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            key="create-monitor-1",
            request_hash="a" * 64,
            now=now,
        )
        assert replay.id == monitor.id
        assert replay.cron_binding_id == binding_id
        with pytest.raises(MonitorIdempotencyConflict, match="admission"):
            await _create_active_monitor(
                repository,
                artifact_id=artifact_id,
                artifact_version_id=artifact_version_id,
                key="create-monitor-1",
                request_hash="b" * 64,
                now=now,
            )
        with pytest.raises(EntitlementDenied, match="active monitor limit"):
            await repository.create_monitor(
                admission_idempotency_key="create-draft-over-limit",
                request_payload_hash="d" * 64,
                artifact_id=artifact_id,
                artifact_version_id=artifact_version_id,
                name="Draft over limit",
                run_task_type="market_analysis",
                condition={"kind": "scheduled_review"},
                cron_schedule="0 */6 * * *",
                timezone="UTC",
                now=now,
            )

        paused = await repository.pause_monitor(
            monitor.id,
            expected_version=1,
            operation_idempotency_key="pause-monitor-1",
        )
        assert paused.status == "paused"
        assert paused.version == 2
        assert paused.cron_binding_id == binding_id
        pause_replay = await repository.pause_monitor(
            monitor.id,
            expected_version=1,
            operation_idempotency_key="pause-monitor-1",
        )
        assert pause_replay.version == 2
        with pytest.raises(MonitorIdempotencyConflict, match="operation"):
            await repository.resume_monitor(
                monitor.id,
                expected_version=2,
                operation_idempotency_key="pause-monitor-1",
            )

        resumed = await repository.resume_monitor(
            monitor.id,
            expected_version=2,
            operation_idempotency_key="resume-monitor-1",
        )
        assert resumed.status == "active"
        assert resumed.version == 3
        assert resumed.cron_binding_id == binding_id

        trigger_count_before = int(
            await session.scalar(select(func.count(MonitorTrigger.id))) or 0
        )
        with pytest.raises(TriggerAdmissionRejected, match="cron_binding_id"):
            await repository.admit_trigger(
                monitor.id,
                kind="cron",
                cron_binding_id=uuid4(),
                official_cron_id="cron-1",
                official_run_id="cron-run-1",
                official_thread_id="cron-ingress-thread-1",
                schedule_version=monitor.schedule_version,
                received_at=now,
            )
        assert int(await session.scalar(select(func.count(MonitorTrigger.id))) or 0) == (
            trigger_count_before
        )

        admission = await repository.admit_trigger(
            monitor.id,
            kind="cron",
            cron_binding_id=binding_id,
            official_cron_id="cron-1",
            official_run_id="cron-run-1",
            official_thread_id="cron-ingress-thread-1",
            schedule_version=monitor.schedule_version,
            received_at=now,
        )
        assert admission.created is True
        assert admission.admitted is True
        assert admission.thread is not None
        assert admission.thread.official_thread_id is None
        assert admission.trigger.official_thread_id == "cron-ingress-thread-1"
        assert admission.task is not None
        assert admission.task.task_type == "market_analysis"
        assert admission.task.request_payload == {
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "query_text": "Review BTC market structure",
            "notify": True,
        }
        AnalysisRequest.model_validate(admission.task.request_payload)
        assert admission.task_command is not None
        assert admission.task_command.status == "pending"
        assert admission.task_command.command_type == "submit"
        assert admission.task_command.payload == admission.task.request_payload
        assert admission.usage is not None
        assert admission.usage.quantity == 1
        assert (
            int(
                await session.scalar(
                    select(func.count(Run.id)).where(Run.task_id == admission.task.id)
                )
                or 0
            )
            == 0
        )

        trigger_replay = await repository.admit_trigger(
            monitor.id,
            kind="cron",
            cron_binding_id=binding_id,
            official_cron_id="cron-1",
            official_run_id="cron-run-1",
            official_thread_id="cron-ingress-thread-1",
            schedule_version=monitor.schedule_version,
            received_at=now,
        )
        assert trigger_replay.created is False
        assert trigger_replay.trigger.id == admission.trigger.id
        assert int(
            await session.scalar(
                select(func.count(TaskCommand.id)).where(
                    TaskCommand.task_id == admission.task.id
                )
            )
            or 0
        ) == 1
        assert int(
            await session.scalar(
                select(func.count(UsageLedgerEntry.id)).where(
                    UsageLedgerEntry.trigger_id == admission.trigger.id
                )
            )
            or 0
        ) == 1

        deleted = await repository.delete_monitor(
            monitor.id,
            expected_version=3,
            operation_idempotency_key="delete-monitor-1",
        )
        assert deleted.status == "disabled"
        assert deleted.version == 4
        assert deleted.cron_binding_id == binding_id
        delete_replay = await repository.delete_monitor(
            monitor.id,
            expected_version=3,
            operation_idempotency_key="delete-monitor-1",
        )
        assert delete_replay.version == 4

        commands = list(
            (
                await session.scalars(
                    select(MonitorCronCommand)
                    .where(MonitorCronCommand.monitor_id == monitor.id)
                    .order_by(MonitorCronCommand.desired_revision)
                )
            ).all()
        )
        assert [command.command_type for command in commands] == [
            "create",
            "pause",
            "resume",
            "delete",
        ]
        for command in commands:
            assert command.payload["monitor_id"] == str(monitor.id)
            assert command.payload["cron_binding_id"] == str(binding_id)
            assert "official_cron_id" not in command.payload
            assert "command_id" not in command.payload
            assert "task_template" not in command.payload


@pytest.mark.asyncio
async def test_quiet_hours_append_suppressed_receipt_without_analysis_task(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    now = datetime(2026, 7, 19, 15, 30, tzinfo=UTC)
    actor, artifact_id, artifact_version_id = await _seed_lineage_and_entitlement(
        session_factory, now=now
    )
    async with session_factory() as session, session.begin():
        repository = MonitorRepository(session, actor)
        monitor = await _create_active_monitor(
            repository,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            key="quiet-monitor-1",
            request_hash="c" * 64,
            now=now,
            name="BTC quiet review",
            timezone="Asia/Shanghai",
            quiet_hours={"start": "22:00", "end": "06:00"},
        )
        task_count_before = int(await session.scalar(select(func.count(Task.id))) or 0)
        admission = await repository.admit_trigger(
            monitor.id,
            kind="manual",
            manual_stable_key="quiet-manual-1",
            schedule_version=monitor.schedule_version,
            received_at=now,
        )
        assert admission.created is True
        assert admission.admitted is False
        assert admission.trigger.status == "suppressed"
        assert admission.trigger.reason == "quiet_hours"
        assert admission.task is None
        assert admission.thread is None
        assert admission.task_command is None
        assert admission.usage is None
        assert int(await session.scalar(select(func.count(Task.id))) or 0) == task_count_before
