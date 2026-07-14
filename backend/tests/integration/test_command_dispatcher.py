from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from typing import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.api.agent_server import RemoteRunHandle, RemoteRunState
from crypto_alert_v2.api.schemas import AnalysisSubmission, TerminalGraphOutput
from crypto_alert_v2.api.service import ProductAnalysisService, TaskNotCancellableError
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.commands.dispatcher import CommandDispatcher
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    MarketSnapshot,
    Run,
    Task,
    TaskCommand,
    Thread,
    WebEvidence,
)
from tests.fixtures.golden_cases import complete_market_snapshot, valid_market_analysis


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


@pytest_asyncio.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as migration_connection:
        await migration_connection.run_sync(Base.metadata.create_all)
    database_connection = await engine.connect()
    transaction = await database_connection.begin()
    try:
        yield database_connection
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await database_connection.close()
        await engine.dispose()


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 13, 6, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class InspectingRunner:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.events: list[str] = []
        self.cancelled: list[RemoteRunHandle] = []
        self.task_id: UUID | None = None
        self.registered_handle: tuple[str | None, str | None, str | None] | None = None
        self.remote_status = "success"

    async def start(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("start")
        self.task_id = UUID(str(kwargs["task_id"]))
        return RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id="official-thread",
            run_id="official-run",
        )

    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        self.events.append("join")
        run_filter = (
            Run.task_id == self.task_id
            if self.task_id is not None
            else Run.official_run_id == handle.run_id
        )
        async with self._session_factory() as session:
            registered = (
                await session.execute(
                    select(
                        Run.task_id,
                        Run.official_assistant_id,
                        Thread.official_thread_id,
                        Run.official_run_id,
                    )
                    .join(Thread, Thread.id == Run.thread_id)
                    .where(run_filter)
                )
            ).one()
        self.task_id = registered[0]
        self.registered_handle = tuple(registered[1:])
        return {
            "terminal_status": "failed",
            "errors": [{"code": "provider_unavailable", "retryable": True}],
        }

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState:
        del handle
        self.events.append("get")
        return RemoteRunState(status=self.remote_status)  # type: ignore[arg-type]

    async def cancel(self, handle: RemoteRunHandle) -> None:
        self.cancelled.append(handle)


class LeaseExpiringRunner(InspectingRunner):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: MutableClock,
    ) -> None:
        super().__init__(session_factory)
        self._clock = clock

    async def start(self, **kwargs: object) -> RemoteRunHandle:
        handle = await super().start(**kwargs)
        self._clock.now += timedelta(seconds=31)
        return handle


class SlowStartRunner(InspectingRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        await asyncio.sleep(1.1)
        return await super().start(**kwargs)


class TerminalJoinFailureRunner(InspectingRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.fail_join = True

    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        if self.fail_join:
            self.events.append("join")
            raise ConnectionError("terminal output temporarily unavailable")
        return await super().join(handle)


class SuccessfulJoinRunner(InspectingRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        await super().join(handle)
        return successful_terminal_output()


class ConflictingSuccessfulJoinRunner(SuccessfulJoinRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        output = await super().join(handle)
        artifact = output["artifact"]
        assert isinstance(artifact, dict)
        analysis = artifact["analysis"]
        assert isinstance(analysis, dict)
        analysis["probability"] = "0.61"
        return output


class RecoveringCancelRunner(InspectingRunner):
    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.events.append("find")
        self.task_id = UUID(str(kwargs["task_id"]))
        return RemoteRunHandle(
            assistant_id="recovered-assistant",
            thread_id=str(kwargs["product_thread_id"]),
            run_id="recovered-run",
        )


class CancelFailureRunner(InspectingRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.fail_cancel = True

    async def cancel(self, handle: RemoteRunHandle) -> None:
        if self.fail_cancel:
            raise ConnectionError("cancel temporarily unavailable")
        await super().cancel(handle)


def actor() -> ActorContext:
    return ActorContext(
        tenant_id="dispatcher-tenant",
        workspace_id="dispatcher-workspace",
        user_id="oidc|dispatcher-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


async def queue_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: str = "dispatcher-analysis-1",
) -> tuple[ProductAnalysisService, dict[str, object]]:
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor())
    queued = await service.create_analysis(
        actor(),
        AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Assess current BTC risk.",
            notify=False,
        ),
        idempotency_key=idempotency_key,
    )
    return service, queued


def successful_terminal_output() -> dict[str, object]:
    source_url = "https://www.reuters.com/markets/currencies/"
    return {
        "terminal_status": "succeeded",
        "market_snapshot": complete_market_snapshot(),
        "web_evidence": [
            {
                "query": "current Bitcoin macro news",
                "final_url": source_url,
                "fetched_at": datetime(2026, 7, 13, 5, 55, tzinfo=UTC),
                "content_hash": "d" * 64,
                "title": "Bitcoin macro update",
                "source": "openai_builtin_web_search",
                "excerpt": "Verified macro evidence for the recovery test.",
                "evidence_relation": "supports",
            }
        ],
        "artifact": {
            "content_version": 1,
            "status": "committed",
            "analysis": valid_market_analysis(),
            "evidence_verdict": {"sufficient": True},
            "risk_verdict": {"allowed": True},
            "source_references": [source_url],
        },
        "errors": [],
    }


async def persisted_output_counts(
    session_factory: async_sessionmaker[AsyncSession],
    task_id: UUID,
) -> dict[str, int]:
    async with session_factory() as session:
        return {
            model.__tablename__: int(
                await session.scalar(
                    select(func.count()).select_from(model).where(model.task_id == task_id)
                )
                or 0
            )
            for model in (
                MarketSnapshot,
                WebEvidence,
                Artifact,
                ArtifactVersion,
                Decision,
            )
        }


@pytest.mark.asyncio
async def test_dispatcher_registers_official_run_before_join(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )

    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert runner.events == ["start", "get", "join"]
    assert runner.registered_handle == (
        "official-assistant",
        "official-thread",
        "official-run",
    )
    async with session_factory() as session:
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == UUID(str(queued["task_id"]))
            )
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == UUID(str(queued["task_id"])))
        )
    assert command is not None
    assert product_run is not None
    assert command.status == "dispatched"
    assert command.official_run_id == "official-run"
    assert command.lease_owner is None
    assert command.lease_expires_at is None
    assert product_run.reconciliation_deadline_at is not None
    assert product_run.projection_fence == command.attempt
    assert product_run.terminal_output_hash is not None
    assert len(product_run.terminal_output_hash) == 64


@pytest.mark.asyncio
async def test_expired_command_lease_is_reclaimed_and_old_owner_is_fenced(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    first_runner = InspectingRunner(session_factory)
    first = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="worker-a",
        clock=clock,
        lease_seconds=30,
    )
    stale_lease = await first.claim_next()
    assert stale_lease is not None

    clock.now += timedelta(seconds=31)
    second_runner = InspectingRunner(session_factory)
    second = CommandDispatcher(
        session_factory=session_factory,
        runner=second_runner,
        worker_id="worker-b",
        clock=clock,
        lease_seconds=30,
    )
    assert await second.dispatch_once() is True
    assert await first.execute(stale_lease) is False

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert first_runner.events == []
    assert second_runner.events == ["start", "get", "join"]


@pytest.mark.asyncio
async def test_remote_run_is_cancelled_when_registration_loses_lease(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, _ = await queue_task(session_factory)
    clock = MutableClock()
    runner = LeaseExpiringRunner(session_factory, clock)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        lease_seconds=30,
    )

    assert await dispatcher.dispatch_once() is False

    assert runner.events == ["start"]
    assert runner.cancelled == [
        RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id="official-thread",
            run_id="official-run",
        )
    ]


@pytest.mark.asyncio
async def test_running_remote_releases_lease_and_is_reclaimed_without_duplicate_start(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    clock = MutableClock()
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        reconciliation_interval_seconds=2,
    )

    assert await dispatcher.dispatch_once() is True
    assert runner.events == ["start", "get"]
    assert runner.cancelled == []
    assert await dispatcher.claim_next() is None

    runner.remote_status = "success"
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    assert runner.events == ["start", "get", "get", "join"]


@pytest.mark.asyncio
async def test_terminal_join_transport_error_keeps_product_run_reconcilable(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = TerminalJoinFailureRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        reconciliation_interval_seconds=2,
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "running"

    runner.fail_join = False
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"


@pytest.mark.asyncio
async def test_terminal_join_replay_does_not_duplicate_persisted_output(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, queued = await queue_task(session_factory)
    first_runner = SuccessfulJoinRunner(session_factory)
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="worker-a",
    )

    assert await first_dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    expected_counts = {
        "market_snapshots": 1,
        "web_evidence": 1,
        "artifacts": 1,
        "artifact_versions": 1,
        "decisions": 1,
    }
    assert await persisted_output_counts(session_factory, task_id) == expected_counts

    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        command = await session.scalar(
            select(TaskCommand)
            .where(TaskCommand.task_id == task_id, TaskCommand.command_type == "submit")
            .with_for_update()
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).with_for_update()
        )
        assert task is not None
        assert command is not None
        assert product_run is not None
        terminal_output_hash = product_run.terminal_output_hash
        projection_fence = product_run.projection_fence
        assert terminal_output_hash is not None

        task.status = "running"
        task.completed_at = None
        product_run.status = "running"
        product_run.finished_at = None
        command.status = "pending"
        command.lease_owner = None
        command.lease_expires_at = None

    replay_runner = SuccessfulJoinRunner(session_factory)
    restarted_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=replay_runner,
        worker_id="worker-after-restart",
    )

    assert await restarted_dispatcher.dispatch_once() is True
    assert replay_runner.events == ["get", "join"]
    assert await persisted_output_counts(session_factory, task_id) == expected_counts
    async with session_factory() as session:
        replayed_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert replayed_run is not None
    assert replayed_run.projection_fence == projection_fence
    assert replayed_run.terminal_output_hash == terminal_output_hash
    async with session_factory() as session:
        replayed_task = await session.scalar(select(Task).where(Task.id == task_id))
        replayed_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
    assert replayed_task is not None
    assert replayed_task.status == "succeeded"
    assert replayed_task.completed_at is not None
    assert replayed_run.status == "succeeded"
    assert replayed_run.finished_at is not None
    assert replayed_command is not None
    assert replayed_command.status == "dispatched"
    assert replayed_command.lease_owner is None
    assert replayed_command.lease_expires_at is None


@pytest.mark.asyncio
async def test_conflicting_terminal_replay_is_failed_without_duplicate_output(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, queued = await queue_task(session_factory)
    first = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="first-worker",
    )
    assert await first.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    expected_counts = await persisted_output_counts(session_factory, task_id)
    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        command = await session.scalar(
            select(TaskCommand)
            .where(TaskCommand.task_id == task_id, TaskCommand.command_type == "submit")
            .with_for_update()
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).with_for_update()
        )
        assert task is not None
        assert command is not None
        assert product_run is not None
        task.status = "running"
        task.completed_at = None
        product_run.status = "running"
        product_run.finished_at = None
        command.status = "pending"
        command.lease_owner = None
        command.lease_expires_at = None

    conflicting = CommandDispatcher(
        session_factory=session_factory,
        runner=ConflictingSuccessfulJoinRunner(session_factory),
        worker_id="conflicting-worker",
    )
    assert await conflicting.dispatch_once() is False

    async with session_factory() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id))
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert task is not None
    assert task.status == "failed"
    assert command is not None
    assert command.status == "failed"
    assert product_run is not None
    assert product_run.status == "failed"
    assert product_run.failure_code == "terminal_projection_conflict"
    assert await persisted_output_counts(session_factory, task_id) == expected_counts


@pytest.mark.asyncio
async def test_higher_command_sequence_fences_stale_terminal_projection(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
    )
    stale_submit_lease = await dispatcher.claim_next()
    assert stale_submit_lease is not None
    assert stale_submit_lease.command_sequence == 1
    assert await dispatcher.execute(stale_submit_lease) is True

    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-fences-stale-terminal",
    )
    assert await dispatcher.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        stale_command = await session.scalar(
            select(TaskCommand)
            .where(TaskCommand.id == stale_submit_lease.command_id)
            .with_for_update()
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).with_for_update()
        )
        assert task is not None
        assert stale_command is not None
        assert product_run is not None
        assert product_run.status == "cancelled"
        assert product_run.projection_fence == 2
        cancelled_output = product_run.output_payload
        cancelled_output_hash = product_run.terminal_output_hash

        task.status = "running"
        task.completed_at = None
        stale_command.status = "dispatching"
        stale_command.lease_owner = stale_submit_lease.worker_id
        stale_command.lease_expires_at = clock.now + timedelta(seconds=30)
        stale_command.attempt = stale_submit_lease.fence_token

    stale_terminal = TerminalGraphOutput.model_validate(successful_terminal_output())
    assert await dispatcher._finalize(stale_submit_lease, stale_terminal) is False

    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    assert product_run.status == "cancelled"
    assert product_run.projection_fence == 2
    assert product_run.output_payload == cancelled_output
    assert product_run.terminal_output_hash == cancelled_output_hash
    assert await persisted_output_counts(session_factory, task_id) == {
        "market_snapshots": 0,
        "web_evidence": 0,
        "artifacts": 0,
        "artifact_versions": 0,
        "decisions": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("persisted_winner", ("terminal_success", "cancel_intent"))
async def test_cancel_and_terminal_success_race_has_deterministic_owner(
    connection: AsyncConnection,
    persisted_winner: str,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key=f"race-{persisted_winner}",
    )
    runner: InspectingRunner
    if persisted_winner == "terminal_success":
        runner = SuccessfulJoinRunner(session_factory)
    else:
        runner = InspectingRunner(session_factory)
        runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="race-worker",
    )
    submit_lease = await dispatcher.claim_next()
    assert submit_lease is not None
    assert await dispatcher.execute(submit_lease) is True

    if persisted_winner == "terminal_success":
        with pytest.raises(TaskNotCancellableError):
            await service.cancel_task(
                actor(),
                str(queued["task_id"]),
                "cancel-after-terminal-success",
            )
        expected_status = "succeeded"
        expected_fence = 1
        expected_artifacts = 1
    else:
        await service.cancel_task(
            actor(),
            str(queued["task_id"]),
            "cancel-before-terminal-success",
        )
        late_success = TerminalGraphOutput.model_validate(successful_terminal_output())
        assert await dispatcher._finalize(submit_lease, late_success) is False
        runner.remote_status = "success"
        assert await dispatcher.dispatch_once() is True
        expected_status = "cancelled"
        expected_fence = 2
        expected_artifacts = 0

    task_id = UUID(str(queued["task_id"]))
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == expected_status
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    assert product_run.status == expected_status
    assert product_run.projection_fence == expected_fence
    counts = await persisted_output_counts(session_factory, task_id)
    assert counts["artifacts"] == expected_artifacts
    assert counts["artifact_versions"] == expected_artifacts


@pytest.mark.asyncio
async def test_worker_restart_uses_persisted_reconciliation_deadline(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    first_runner = InspectingRunner(session_factory)
    first_runner.remote_status = "running"
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="worker-before-restart",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_run_seconds=2,
    )

    assert await first_dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    persisted_deadline = product_run.reconciliation_deadline_at
    assert persisted_deadline == clock.now + timedelta(seconds=2)

    clock.now += timedelta(seconds=3)
    restarted_runner = InspectingRunner(session_factory)
    restarted_runner.remote_status = "running"
    restarted_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=restarted_runner,
        worker_id="worker-after-restart",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_run_seconds=3_600,
    )

    assert await restarted_dispatcher.dispatch_once() is True
    assert restarted_runner.events == ["get"]
    assert len(restarted_runner.cancelled) == 1
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_run_timeout"
    async with session_factory() as session:
        timed_out_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert timed_out_run is not None
    assert timed_out_run.reconciliation_deadline_at == persisted_deadline
    assert timed_out_run.output_payload is not None
    assert timed_out_run.output_payload["errors"][0]["error_type"] == (
        "OrphanDeadlineExceeded"
    )


@pytest.mark.asyncio
async def test_interrupted_remote_projects_waiting_human_without_join(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "waiting_human"
    assert runner.events == ["start", "get"]


@pytest.mark.asyncio
async def test_running_remote_is_cancelled_only_after_orphan_deadline(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        max_run_seconds=2,
    )
    lease = await dispatcher.claim_next()
    assert lease is not None
    clock.now += timedelta(seconds=3)

    assert await dispatcher.execute(lease) is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert runner.cancelled


@pytest.mark.asyncio
async def test_orphan_deadline_cancel_failure_keeps_cleanup_reconcilable(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = CancelFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="orphan-cleanup-worker",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_run_seconds=2,
    )

    assert await dispatcher.dispatch_once() is True
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "running"

    runner.fail_cancel = False
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_run_timeout"


@pytest.mark.asyncio
async def test_queued_task_cancel_is_durable_without_creating_remote_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )

    requested = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-queued-1",
    )
    assert requested is not None
    assert requested["cancel_requested_at"] is not None
    replayed = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-queued-with-a-different-key",
    )
    assert replayed is not None
    assert replayed["cancel_requested_at"] == requested["cancel_requested_at"]
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.events == []
    async with session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(Run).where(
                        Run.task_id == UUID(str(queued["task_id"]))
                    )
                )
            ).all()
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand)
                    .where(
                        TaskCommand.task_id == UUID(str(queued["task_id"]))
                    )
                    .order_by(TaskCommand.sequence)
                )
            ).all()
        )
    assert runs == []
    assert [(item.command_type, item.status) for item in commands] == [
        ("submit", "cancelled"),
        ("cancel_task", "dispatched"),
    ]


@pytest.mark.asyncio
async def test_running_task_cancel_stops_registered_official_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )
    assert await dispatcher.dispatch_once() is True

    requested = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-running-1",
    )
    assert requested is not None
    assert requested["cancel_requested_at"] is not None
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.events == ["start", "get"]
    assert len(runner.cancelled) == 1


@pytest.mark.asyncio
async def test_cancel_requested_during_start_registers_then_cancels_remote_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="start-cancel-race-worker",
    )
    submit_lease = await dispatcher.claim_next()
    assert submit_lease is not None

    requested = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-during-start",
    )
    assert requested is not None
    assert requested["cancel_requested_at"] is not None
    async with session_factory() as session:
        submit = await session.scalar(
            select(TaskCommand).where(TaskCommand.id == submit_lease.command_id)
        )
    assert submit is not None
    assert submit.status == "dispatching"

    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id="official-thread",
        run_id="official-run",
    )
    assert await dispatcher._register_remote(submit_lease, handle) == (
        "cancel_requested"
    )
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.cancelled == [handle]


@pytest.mark.asyncio
async def test_cancel_recovers_unregistered_remote_run_after_worker_restart(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = RecoveringCancelRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="recovery-worker",
        clock=clock,
        cancel_discovery_seconds=0,
    )
    submit_lease = await dispatcher.claim_next()
    assert submit_lease is not None
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-after-ambiguous-start",
    )

    clock.now += timedelta(seconds=31)
    assert await dispatcher.claim_next() is None
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.events == ["find"]
    assert runner.cancelled == [
        RemoteRunHandle(
            assistant_id="recovered-assistant",
            thread_id=str(submit_lease.product_thread_id),
            run_id="recovered-run",
        )
    ]
    async with session_factory() as session:
        product_run = await session.scalar(
            select(Run).where(Run.id == submit_lease.product_run_id)
        )
    assert product_run is not None
    assert product_run.official_run_id == "recovered-run"
    assert product_run.official_assistant_id == "recovered-assistant"


@pytest.mark.asyncio
async def test_cancel_transport_error_is_retried_without_losing_intent(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = CancelFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        reconciliation_interval_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-retry-1",
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "running"

    runner.fail_cancel = False
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"


@pytest.mark.asyncio
async def test_permanent_cancel_failure_becomes_an_explicit_product_failure(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = CancelFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="permanent-cancel-failure-worker",
        max_cancel_attempts=1,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-permanent-failure",
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_cancel_failed"
    assert view["errors"][0]["retryable"] is False


@pytest.mark.asyncio
async def test_remote_start_renews_the_command_lease_before_join(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    await queue_task(session_factory)
    runner = SlowStartRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        lease_seconds=3,
    )
    renew_calls = 0
    renew_lease = dispatcher._renew_lease

    async def recording_renewal(lease: object) -> bool:
        nonlocal renew_calls
        renew_calls += 1
        return await renew_lease(lease)  # type: ignore[arg-type]

    dispatcher._renew_lease = recording_renewal  # type: ignore[method-assign]

    assert await dispatcher.dispatch_once() is True
    assert renew_calls >= 1
