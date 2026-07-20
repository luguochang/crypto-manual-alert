from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.api.agent_server import (
    RemoteRunHandle,
    RemoteRunState,
)
from crypto_alert_v2.auth.context import ActorContext
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


ACTIVE_PRODUCT_STATUSES = frozenset({"running", "waiting_human"})
RECONCILABLE_COMMAND_TYPES = frozenset({"submit", "respond", "retry", "fork"})
TERMINAL_REMOTE_STATUSES = frozenset({"error", "success", "timeout"})


class ProjectionConflictError(RuntimeError):
    """The official state conflicts with an already fenced Product projection."""


@dataclass(frozen=True, slots=True)
class ProjectionReconciliationLease:
    command_id: UUID
    command_attempt: int
    command_sequence: int
    product_run_id: UUID
    product_thread_id: UUID
    task_id: UUID
    projection_fence: int
    worker_id: str
    actor: ActorContext
    remote_thread_id: str
    remote_handle: RemoteRunHandle | None


class ProjectionRunReader(Protocol):
    async def find(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_thread_id: str,
        product_run_id: str,
    ) -> RemoteRunHandle | None: ...

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState: ...


class ProjectionReconciliationStore(Protocol):
    async def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        stale_before: datetime,
        lease_expires_at: datetime,
    ) -> ProjectionReconciliationLease | None: ...

    async def register_remote_handle(
        self,
        lease: ProjectionReconciliationLease,
        handle: RemoteRunHandle,
        *,
        now: datetime,
    ) -> bool: ...

    async def observe_remote_absence(
        self,
        lease: ProjectionReconciliationLease,
        *,
        now: datetime,
    ) -> bool: ...

    async def observe_remote_state(
        self,
        lease: ProjectionReconciliationLease,
        handle: RemoteRunHandle,
        state: RemoteRunState,
        *,
        now: datetime,
    ) -> bool: ...

    async def release(
        self,
        lease: ProjectionReconciliationLease,
        *,
        now: datetime,
    ) -> bool: ...

    async def release_owned(self, *, worker_id: str, now: datetime) -> None: ...


class SqlAlchemyProjectionReconciliationStore:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        stale_before: datetime,
        lease_expires_at: datetime,
    ) -> ProjectionReconciliationLease | None:
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.execute(
                    select(
                        TaskCommand,
                        Task,
                        Thread,
                        Tenant.external_id,
                        Workspace.external_id,
                        User.external_subject,
                        User.identity_issuer,
                        Membership.id,
                        Membership.role,
                        Membership.permissions,
                    )
                    .join(Task, Task.id == TaskCommand.task_id)
                    .join(Thread, Thread.id == TaskCommand.thread_id)
                    .join(Tenant, Tenant.id == TaskCommand.tenant_id)
                    .join(Workspace, Workspace.id == TaskCommand.workspace_id)
                    .join(User, User.id == TaskCommand.actor_user_id)
                    .outerjoin(
                        Membership,
                        (Membership.tenant_id == TaskCommand.tenant_id)
                        & (Membership.workspace_id == TaskCommand.workspace_id)
                        & (Membership.user_id == TaskCommand.actor_user_id),
                    )
                    .where(
                        TaskCommand.command_type.in_(RECONCILABLE_COMMAND_TYPES),
                        TaskCommand.status == "dispatching",
                        TaskCommand.attempt > 0,
                        TaskCommand.lease_expires_at.is_not(None),
                        TaskCommand.lease_expires_at <= now,
                        Task.status.in_(ACTIVE_PRODUCT_STATUSES),
                    )
                    .order_by(
                        TaskCommand.lease_expires_at,
                        TaskCommand.created_at,
                        TaskCommand.sequence,
                    )
                    .limit(32)
                    .with_for_update(of=TaskCommand, skip_locked=True)
                )
            ).all()
            for row in rows:
                command, task, thread = row[0], row[1], row[2]
                product_run = await self._target_run(session, command, task)
                if not self._is_reconcilable_run(
                    product_run,
                    command=command,
                    stale_before=stale_before,
                ):
                    continue
                assert product_run is not None
                admitted_permissions = tuple(row[9] or ())
                actor = ActorContext(
                    tenant_id=row[3],
                    workspace_id=row[4],
                    user_id=row[5],
                    identity_issuer=row[6],
                    context_id=row[7],
                    roles=(row[8] or "member",),
                    permissions=tuple(
                        dict.fromkeys(
                            (*admitted_permissions, "analysis:read", "analysis:write")
                        )
                    ),
                )
                remote_thread_id = thread.official_thread_id or str(thread.id)
                remote_handle = None
                if product_run.official_assistant_id and product_run.official_run_id:
                    remote_handle = RemoteRunHandle(
                        assistant_id=product_run.official_assistant_id,
                        thread_id=remote_thread_id,
                        run_id=product_run.official_run_id,
                    )
                command.lease_owner = worker_id
                command.lease_expires_at = lease_expires_at
                return ProjectionReconciliationLease(
                    command_id=command.id,
                    command_attempt=command.attempt,
                    command_sequence=command.sequence,
                    product_run_id=product_run.id,
                    product_thread_id=thread.id,
                    task_id=task.id,
                    projection_fence=product_run.projection_fence,
                    worker_id=worker_id,
                    actor=actor,
                    remote_thread_id=remote_thread_id,
                    remote_handle=remote_handle,
                )
        return None

    async def register_remote_handle(
        self,
        lease: ProjectionReconciliationLease,
        handle: RemoteRunHandle,
        *,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            locked = await self._locked_projection(session, lease, now=now)
            if locked is None:
                return False
            command, product_run, thread = locked
            self._validate_handle(lease, product_run, thread, command, handle)
            thread.official_thread_id = handle.thread_id
            product_run.official_assistant_id = handle.assistant_id
            product_run.official_run_id = handle.run_id
            command.official_run_id = handle.run_id
            product_run.last_heartbeat_at = now
            return True

    async def observe_remote_absence(
        self,
        lease: ProjectionReconciliationLease,
        *,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            locked = await self._locked_projection(session, lease, now=now)
            if locked is None:
                return False
            _, product_run, _ = locked
            product_run.last_heartbeat_at = now
            return True

    async def observe_remote_state(
        self,
        lease: ProjectionReconciliationLease,
        handle: RemoteRunHandle,
        state: RemoteRunState,
        *,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            locked = await self._locked_projection(session, lease, now=now)
            if locked is None:
                return False
            command, product_run, thread = locked
            self._validate_handle(lease, product_run, thread, command, handle)
            if state.status in TERMINAL_REMOTE_STATUSES:
                if (
                    product_run.observed_terminal_status is not None
                    and product_run.observed_terminal_status != state.status
                ):
                    raise ProjectionConflictError(
                        "Official Run terminal status changed after observation"
                    )
                product_run.observed_terminal_status = state.status
            elif product_run.observed_terminal_status is not None:
                raise ProjectionConflictError(
                    "Official Run became non-terminal after terminal observation"
                )
            product_run.last_heartbeat_at = now
            self._release_command(command, now=now)
            return True

    async def release(
        self,
        lease: ProjectionReconciliationLease,
        *,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            command = await session.scalar(
                select(TaskCommand)
                .where(TaskCommand.id == lease.command_id)
                .with_for_update()
            )
            if not self._owns_command(command, lease, require_unexpired=False, now=now):
                return False
            assert command is not None
            self._release_command(command, now=now)
            return True

    async def release_owned(self, *, worker_id: str, now: datetime) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(TaskCommand)
                .where(
                    TaskCommand.status == "dispatching",
                    TaskCommand.lease_owner == worker_id,
                )
                .values(lease_owner=None, lease_expires_at=now)
            )

    async def _target_run(
        self,
        session: AsyncSession,
        command: TaskCommand,
        task: Task,
    ) -> Run | None:
        target_id = _command_target_run_id(command)
        if command.command_type in {"retry", "fork"} and target_id is None:
            return None
        query = select(Run).where(
            Run.task_id == task.id,
            Run.thread_id == task.thread_id,
            Run.tenant_id == task.tenant_id,
            Run.workspace_id == task.workspace_id,
            Run.owner_user_id == task.owner_user_id,
        )
        if command.official_run_id:
            query = query.where(Run.official_run_id == command.official_run_id)
        elif target_id is not None:
            query = query.where(Run.id == target_id)
        else:
            query = query.order_by(Run.attempt.desc(), Run.id.desc()).limit(1)
        return await session.scalar(query.with_for_update())

    @staticmethod
    def _is_reconcilable_run(
        product_run: Run | None,
        *,
        command: TaskCommand,
        stale_before: datetime,
    ) -> bool:
        if product_run is None:
            return False
        if product_run.status not in ACTIVE_PRODUCT_STATUSES:
            return False
        if product_run.observed_terminal_status is not None:
            return False
        if product_run.terminal_output_hash is not None:
            return False
        if product_run.projection_fence >= command.sequence:
            return False
        if (
            product_run.last_heartbeat_at is not None
            and product_run.last_heartbeat_at > stale_before
        ):
            return False
        if (
            command.official_run_id is not None
            and product_run.official_run_id != command.official_run_id
        ):
            return False
        if command.command_type == "respond" and product_run.resume_of_run_id is None:
            return False
        if command.command_type == "retry" and product_run.retry_of_run_id is None:
            return False
        if command.command_type == "fork" and product_run.forked_from_run_id is None:
            return False
        return True

    async def _locked_projection(
        self,
        session: AsyncSession,
        lease: ProjectionReconciliationLease,
        *,
        now: datetime,
    ) -> tuple[TaskCommand, Run, Thread] | None:
        command = await session.scalar(
            select(TaskCommand)
            .where(TaskCommand.id == lease.command_id)
            .with_for_update()
        )
        if not self._owns_command(command, lease, require_unexpired=True, now=now):
            return None
        product_run = await session.scalar(
            select(Run).where(Run.id == lease.product_run_id).with_for_update()
        )
        task = await session.scalar(
            select(Task).where(Task.id == lease.task_id).with_for_update()
        )
        thread = await session.scalar(
            select(Thread).where(Thread.id == lease.product_thread_id).with_for_update()
        )
        if product_run is None or task is None or thread is None:
            return None
        if task.status not in ACTIVE_PRODUCT_STATUSES:
            return None
        if product_run.status not in ACTIVE_PRODUCT_STATUSES:
            return None
        if product_run.projection_fence != lease.projection_fence:
            return None
        if product_run.terminal_output_hash is not None:
            return None
        return command, product_run, thread

    @staticmethod
    def _owns_command(
        command: TaskCommand | None,
        lease: ProjectionReconciliationLease,
        *,
        require_unexpired: bool,
        now: datetime,
    ) -> bool:
        if command is None:
            return False
        if (
            command.status != "dispatching"
            or command.lease_owner != lease.worker_id
            or command.attempt != lease.command_attempt
            or command.sequence != lease.command_sequence
        ):
            return False
        if require_unexpired and (
            command.lease_expires_at is None or command.lease_expires_at <= now
        ):
            return False
        return True

    @staticmethod
    def _validate_handle(
        lease: ProjectionReconciliationLease,
        product_run: Run,
        thread: Thread,
        command: TaskCommand,
        handle: RemoteRunHandle,
    ) -> None:
        if handle.thread_id != lease.remote_thread_id:
            raise ProjectionConflictError(
                "Agent Server returned a different Thread during reconciliation"
            )
        if thread.official_thread_id not in {None, handle.thread_id}:
            raise ProjectionConflictError(
                "Product Thread points to another official Thread"
            )
        if product_run.official_run_id not in {None, handle.run_id}:
            raise ProjectionConflictError("Product Run points to another official Run")
        if product_run.official_assistant_id not in {None, handle.assistant_id}:
            raise ProjectionConflictError(
                "Product Run points to another official Assistant"
            )
        if command.official_run_id not in {None, handle.run_id}:
            raise ProjectionConflictError("Command points to another official Run")

    @staticmethod
    def _release_command(command: TaskCommand, *, now: datetime) -> None:
        command.lease_owner = None
        command.lease_expires_at = now


class ProductProjectionReconciler:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession] | None = None,
        store: ProjectionReconciliationStore | None = None,
        runner: ProjectionRunReader,
        worker_id: str,
        clock: Callable[[], datetime] | None = None,
        stale_after_seconds: int = 30,
        lease_seconds: int = 30,
        remote_timeout_seconds: float = 8.0,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be at least 3")
        if remote_timeout_seconds <= 0:
            raise ValueError("remote_timeout_seconds must be positive")
        if lease_seconds <= remote_timeout_seconds * 2:
            raise ValueError("lease must cover bounded find and get operations")
        if store is None:
            if session_factory is None:
                raise ValueError("session_factory or store is required")
            store = SqlAlchemyProjectionReconciliationStore(session_factory)
        self._store = store
        self._runner = runner
        self._worker_id = worker_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._stale_after_seconds = stale_after_seconds
        self._lease_seconds = lease_seconds
        self._remote_timeout_seconds = remote_timeout_seconds

    async def dispatch_once(self) -> bool:
        now = self._clock()
        lease = await self._store.claim_next(
            worker_id=self._worker_id,
            now=now,
            stale_before=now - timedelta(seconds=self._stale_after_seconds),
            lease_expires_at=now + timedelta(seconds=self._lease_seconds),
        )
        if lease is None:
            return False
        try:
            handle = lease.remote_handle
            if handle is None:
                async with asyncio.timeout(self._remote_timeout_seconds):
                    handle = await self._runner.find(
                        actor=lease.actor,
                        task_id=str(lease.task_id),
                        product_thread_id=lease.remote_thread_id,
                        product_run_id=str(lease.product_run_id),
                    )
                if handle is None:
                    return await self._store.observe_remote_absence(
                        lease,
                        now=self._clock(),
                    )
            if not await self._store.register_remote_handle(
                lease,
                handle,
                now=self._clock(),
            ):
                return False
            handle = _authorize_handle(self._runner, handle, lease.actor)
            async with asyncio.timeout(self._remote_timeout_seconds):
                state = await self._runner.get(handle)
            return await self._store.observe_remote_state(
                lease,
                handle,
                state,
                now=self._clock(),
            )
        finally:
            await self._store.release(lease, now=self._clock())

    async def release_owned_leases(self) -> None:
        await self._store.release_owned(worker_id=self._worker_id, now=self._clock())


def _authorize_handle(
    runner: ProjectionRunReader,
    handle: RemoteRunHandle,
    actor: ActorContext,
) -> RemoteRunHandle:
    authorize = getattr(runner, "authorize", None)
    return authorize(handle, actor) if callable(authorize) else handle


def _command_target_run_id(command: TaskCommand) -> UUID | None:
    field_name = {
        "retry": "retry_run_id",
        "fork": "fork_run_id",
    }.get(command.command_type)
    if field_name is None:
        return None
    value: Any = command.payload.get(field_name)
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


__all__ = [
    "ProductProjectionReconciler",
    "ProjectionConflictError",
    "ProjectionReconciliationLease",
    "ProjectionReconciliationStore",
    "ProjectionRunReader",
    "SqlAlchemyProjectionReconciliationStore",
]
