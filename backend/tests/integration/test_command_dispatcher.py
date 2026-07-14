from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from typing import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.api.agent_server import RemoteRunHandle
from crypto_alert_v2.api.schemas import AnalysisSubmission
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.commands.dispatcher import CommandDispatcher
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import Run, TaskCommand, Thread


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
        assert self.task_id is not None
        async with self._session_factory() as session:
            registered = (
                await session.execute(
                    select(
                        Run.official_assistant_id,
                        Thread.official_thread_id,
                        Run.official_run_id,
                    )
                    .join(Thread, Thread.id == Run.thread_id)
                    .where(Run.task_id == self.task_id)
                )
            ).one()
        self.registered_handle = tuple(registered)
        return {
            "terminal_status": "failed",
            "errors": [{"code": "provider_unavailable", "retryable": True}],
        }

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
        idempotency_key="dispatcher-analysis-1",
    )
    return service, queued


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
    assert runner.events == ["start", "join"]
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
    assert command is not None
    assert command.status == "dispatched"
    assert command.official_run_id == "official-run"
    assert command.lease_owner is None
    assert command.lease_expires_at is None


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
    assert second_runner.events == ["start", "join"]


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
async def test_lost_join_lease_detaches_without_cancelling_the_registered_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )
    lease = await dispatcher.claim_next()
    assert lease is not None

    async def lose_lease_after_registration(
        _: object,
        __: object,
        ___: RemoteRunHandle,
    ) -> None:
        return None

    dispatcher._join_with_heartbeat = lose_lease_after_registration.__get__(  # type: ignore[method-assign]
        dispatcher,
        CommandDispatcher,
    )

    assert await dispatcher.execute(lease) is False
    assert runner.events == ["start"]
    assert runner.cancelled == []


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
