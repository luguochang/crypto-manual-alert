from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.api.agent_server import RemoteRunHandle, RemoteRunState
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    Membership,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    Workspace,
)
from crypto_alert_v2.projections.reconciler import ProductProjectionReconciler


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)
NOW = datetime(2026, 7, 17, 9, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as migration_connection:
        await migration_connection.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
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


@dataclass(frozen=True)
class SeededProjection:
    task_id: UUID
    run_id: UUID
    command_id: UUID
    remote_thread_id: str
    remote_run_id: str


async def seed_stale_projection(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    registered: bool,
    lease_expires_at: datetime | None = None,
) -> SeededProjection:
    suffix = uuid4().hex
    tenant_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    thread_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    command_id = uuid4()
    remote_thread_id = f"official-thread-{suffix}"
    remote_run_id = f"official-run-{suffix}"
    async with session_factory() as session, session.begin():
        session.add(
            Tenant(
                id=tenant_id,
                external_id=f"tenant-{suffix}",
                name="Projection Test Tenant",
            )
        )
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                identity_issuer="projection-test",
                external_subject=f"user-{suffix}",
                display_name="Projection Test User",
            )
        )
        session.add(
            Workspace(
                id=workspace_id,
                tenant_id=tenant_id,
                external_id=f"workspace-{suffix}",
                name="Projection Test Workspace",
                review_policy="bypass",
            )
        )
        await session.flush()
        session.add(
            Membership(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role="member",
                permissions=["analysis:read", "analysis:write"],
            )
        )
        session.add(
            Thread(
                id=thread_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                official_thread_id=remote_thread_id,
                title="Projection reconciliation",
                context={},
            )
        )
        await session.flush()
        session.add(
            Task(
                id=task_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                thread_id=thread_id,
                task_type="analysis",
                status="running",
                idempotency_key=f"task-{suffix}",
                request_payload_hash="a" * 64,
                request_payload={"symbol": "BTC-USDT-SWAP"},
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
                status="running",
                official_assistant_id=("official-assistant" if registered else None),
                official_run_id=remote_run_id if registered else None,
                input_payload={"symbol": "BTC-USDT-SWAP"},
                started_at=NOW - timedelta(minutes=5),
                last_heartbeat_at=NOW - timedelta(seconds=31),
                reconciliation_deadline_at=NOW + timedelta(minutes=5),
                projection_fence=0,
            )
        )
        session.add(
            TaskCommand(
                id=command_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_user_id=user_id,
                task_id=task_id,
                thread_id=thread_id,
                command_type="submit",
                payload={},
                payload_hash="b" * 64,
                sequence=1,
                status="dispatching",
                lease_owner="stopped-command-worker",
                lease_expires_at=lease_expires_at or NOW - timedelta(seconds=1),
                attempt=2,
                idempotency_key=f"command-{suffix}",
                official_run_id=remote_run_id if registered else None,
            )
        )
    return SeededProjection(
        task_id=task_id,
        run_id=run_id,
        command_id=command_id,
        remote_thread_id=remote_thread_id,
        remote_run_id=remote_run_id,
    )


class ReadOnlyPostgresRunner:
    def __init__(
        self,
        *,
        handle: RemoteRunHandle,
        status: str,
        found: RemoteRunHandle | None = None,
        return_found: bool = True,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        fenced: SeededProjection | None = None,
    ) -> None:
        self.handle = handle
        self.status = status
        self.found = handle if return_found else found
        self.session_factory = session_factory
        self.fenced = fenced
        self.calls: list[str] = []

    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.calls.append("find")
        assert kwargs["task_id"]
        assert kwargs["product_run_id"]
        assert kwargs["product_thread_id"] == self.handle.thread_id
        return self.found

    def authorize(
        self,
        handle: RemoteRunHandle,
        actor: ActorContext,
    ) -> RemoteRunHandle:
        assert actor.permissions == ("analysis:read", "analysis:write")
        self.calls.append("authorize")
        return handle

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState:
        assert handle == self.handle
        self.calls.append("get")
        if self.session_factory is not None and self.fenced is not None:
            async with self.session_factory() as session, session.begin():
                product_run = await session.scalar(
                    select(Run).where(Run.id == self.fenced.run_id).with_for_update()
                )
                task = await session.scalar(
                    select(Task).where(Task.id == self.fenced.task_id).with_for_update()
                )
                assert product_run is not None and task is not None
                product_run.status = "cancelled"
                product_run.projection_fence = 2
                product_run.terminal_output_hash = "f" * 64
                task.status = "cancelled"
        return RemoteRunState(status=self.status)  # type: ignore[arg-type]


def build_reconciler(
    session_factory: async_sessionmaker[AsyncSession],
    runner: ReadOnlyPostgresRunner,
) -> ProductProjectionReconciler:
    return ProductProjectionReconciler(
        session_factory=session_factory,
        runner=runner,
        worker_id="projection-reconciler",
        clock=lambda: NOW,
        remote_timeout_seconds=1,
    )


@pytest.mark.asyncio
async def test_registered_terminal_run_is_observed_once_without_projecting_output(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    seeded = await seed_stale_projection(session_factory, registered=True)
    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id=seeded.remote_thread_id,
        run_id=seeded.remote_run_id,
    )
    runner = ReadOnlyPostgresRunner(handle=handle, status="success")
    reconciler = build_reconciler(session_factory, runner)

    assert await reconciler.dispatch_once() is True
    assert await reconciler.dispatch_once() is False

    async with session_factory() as session:
        product_run = await session.get(Run, seeded.run_id)
        command = await session.get(TaskCommand, seeded.command_id)
    assert product_run is not None and command is not None
    assert product_run.status == "running"
    assert product_run.observed_terminal_status == "success"
    assert product_run.output_payload is None
    assert product_run.terminal_output_hash is None
    assert product_run.projection_fence == 0
    assert product_run.last_heartbeat_at == NOW
    assert command.status == "dispatching"
    assert command.attempt == 2
    assert command.lease_owner is None
    assert command.lease_expires_at == NOW
    assert runner.calls == ["authorize", "get"]


@pytest.mark.asyncio
async def test_find_registers_lost_handle_and_observes_error_idempotently(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    seeded = await seed_stale_projection(session_factory, registered=False)
    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id=seeded.remote_thread_id,
        run_id=seeded.remote_run_id,
    )
    runner = ReadOnlyPostgresRunner(handle=handle, status="error")
    reconciler = build_reconciler(session_factory, runner)

    assert await reconciler.dispatch_once() is True

    async with session_factory() as session:
        product_run = await session.get(Run, seeded.run_id)
        command = await session.get(TaskCommand, seeded.command_id)
    assert product_run is not None and command is not None
    assert product_run.official_assistant_id == "official-assistant"
    assert product_run.official_run_id == seeded.remote_run_id
    assert product_run.observed_terminal_status == "error"
    assert command.official_run_id == seeded.remote_run_id
    assert command.attempt == 2
    assert runner.calls == ["find", "authorize", "get"]


@pytest.mark.asyncio
async def test_missing_official_run_updates_heartbeat_before_retrying(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    seeded = await seed_stale_projection(session_factory, registered=False)
    runner = ReadOnlyPostgresRunner(
        handle=RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id=seeded.remote_thread_id,
            run_id=seeded.remote_run_id,
        ),
        status="running",
        return_found=False,
    )
    reconciler = build_reconciler(session_factory, runner)

    assert await reconciler.dispatch_once() is True
    assert await reconciler.dispatch_once() is False

    async with session_factory() as session:
        product_run = await session.get(Run, seeded.run_id)
        command = await session.get(TaskCommand, seeded.command_id)
    assert product_run is not None and command is not None
    assert product_run.last_heartbeat_at == NOW
    assert command.lease_owner is None
    assert command.lease_expires_at == NOW
    assert runner.calls == ["find"]


@pytest.mark.asyncio
async def test_concurrent_projection_fence_rejects_stale_terminal_observation(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    seeded = await seed_stale_projection(session_factory, registered=True)
    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id=seeded.remote_thread_id,
        run_id=seeded.remote_run_id,
    )
    runner = ReadOnlyPostgresRunner(
        handle=handle,
        status="success",
        session_factory=session_factory,
        fenced=seeded,
    )

    assert await build_reconciler(session_factory, runner).dispatch_once() is False

    async with session_factory() as session:
        product_run = await session.get(Run, seeded.run_id)
        command = await session.get(TaskCommand, seeded.command_id)
    assert product_run is not None and command is not None
    assert product_run.status == "cancelled"
    assert product_run.projection_fence == 2
    assert product_run.terminal_output_hash == "f" * 64
    assert product_run.observed_terminal_status is None
    assert command.lease_owner is None
    assert command.lease_expires_at == NOW


@pytest.mark.asyncio
async def test_live_command_lease_is_never_stolen(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    seeded = await seed_stale_projection(
        session_factory,
        registered=True,
        lease_expires_at=NOW + timedelta(seconds=1),
    )
    runner = ReadOnlyPostgresRunner(
        handle=RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id=seeded.remote_thread_id,
            run_id=seeded.remote_run_id,
        ),
        status="success",
    )

    assert await build_reconciler(session_factory, runner).dispatch_once() is False

    async with session_factory() as session:
        command = await session.get(TaskCommand, seeded.command_id)
        product_run = await session.get(Run, seeded.run_id)
    assert command is not None and product_run is not None
    assert command.lease_owner == "stopped-command-worker"
    assert command.lease_expires_at == NOW + timedelta(seconds=1)
    assert product_run.observed_terminal_status is None
    assert runner.calls == []
