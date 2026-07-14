from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from crypto_alert_v2.api.agent_server import RemoteRunHandle
from crypto_alert_v2.api.schemas import AnalysisSubmission, TerminalGraphOutput
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.persistence.models import (
    Artifact,
    MarketSnapshot,
    Membership,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    WebEvidence,
    Workspace,
)
from crypto_alert_v2.persistence.repositories import ArtifactRepository


class RemoteRunner(Protocol):
    async def start(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_thread_id: str,
        product_run_id: str,
        submission: AnalysisSubmission,
    ) -> RemoteRunHandle: ...

    async def join(self, handle: RemoteRunHandle) -> dict[str, Any]: ...

    async def cancel(self, handle: RemoteRunHandle) -> None: ...


@dataclass(frozen=True, slots=True)
class CommandLease:
    command_id: UUID
    task_id: UUID
    product_thread_id: UUID
    product_run_id: UUID
    worker_id: str
    fence_token: int
    actor: ActorContext
    submission: AnalysisSubmission
    remote_handle: RemoteRunHandle | None = None


class CommandDispatcher:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        runner: RemoteRunner,
        worker_id: str,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: int = 30,
        max_attempts: int = 3,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be at least 3")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._session_factory = session_factory
        self._runner = runner
        self._worker_id = worker_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts

    async def dispatch_once(self) -> bool:
        lease = await self.claim_next()
        if lease is None:
            return False
        return await self.execute(lease)

    async def claim_next(self) -> CommandLease | None:
        now = self._clock()
        prior = aliased(TaskCommand)
        prior_unfinished = exists(
            select(1).where(
                prior.thread_id == TaskCommand.thread_id,
                prior.sequence < TaskCommand.sequence,
                prior.status.in_(("pending", "dispatching")),
            )
        )
        async with self._session_factory() as session, session.begin():
            row = (
                await session.execute(
                    select(
                        TaskCommand,
                        Task,
                        Thread,
                        Tenant.external_id,
                        Workspace.external_id,
                        User.external_subject,
                        Membership.role,
                        Membership.permissions,
                    )
                    .join(Task, Task.id == TaskCommand.task_id)
                    .join(Thread, Thread.id == TaskCommand.thread_id)
                    .join(Tenant, Tenant.id == TaskCommand.tenant_id)
                    .join(Workspace, Workspace.id == TaskCommand.workspace_id)
                    .join(User, User.id == TaskCommand.actor_user_id)
                    .join(
                        Membership,
                        and_(
                            Membership.tenant_id == TaskCommand.tenant_id,
                            Membership.workspace_id == TaskCommand.workspace_id,
                            Membership.user_id == TaskCommand.actor_user_id,
                            Membership.is_active.is_(True),
                        ),
                    )
                    .where(
                        TaskCommand.command_type == "submit",
                        Task.status.in_(("queued", "running")),
                        or_(
                            TaskCommand.status == "pending",
                            and_(
                                TaskCommand.status == "dispatching",
                                TaskCommand.lease_expires_at.is_not(None),
                                TaskCommand.lease_expires_at <= now,
                            ),
                        ),
                        ~prior_unfinished,
                    )
                    .order_by(TaskCommand.created_at, TaskCommand.sequence)
                    .limit(1)
                    .with_for_update(of=TaskCommand, skip_locked=True)
                )
            ).one_or_none()
            if row is None:
                return None

            command, task, thread = row[0], row[1], row[2]
            actor = ActorContext(
                tenant_id=row[3],
                workspace_id=row[4],
                user_id=row[5],
                roles=(row[6],),
                permissions=tuple(row[7]),
            )
            if "analysis:write" not in actor.permissions:
                command.status = "rejected"
                command.lease_owner = None
                command.lease_expires_at = None
                task.status = "blocked"
                task.completed_at = now
                return None

            product_run = await session.scalar(
                select(Run)
                .where(
                    Run.task_id == task.id,
                    Run.tenant_id == task.tenant_id,
                    Run.workspace_id == task.workspace_id,
                )
                .order_by(Run.attempt.desc())
                .limit(1)
                .with_for_update()
            )
            if product_run is None:
                previous_attempt = await session.scalar(
                    select(func.coalesce(func.max(Run.attempt), 0)).where(
                        Run.task_id == task.id
                    )
                )
                product_run = Run(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    workspace_id=task.workspace_id,
                    owner_user_id=task.owner_user_id,
                    thread_id=task.thread_id,
                    task_id=task.id,
                    attempt=int(previous_attempt or 0) + 1,
                    status="running",
                    input_payload=task.request_payload,
                    started_at=now,
                    last_heartbeat_at=now,
                )
                session.add(product_run)
                await session.flush()

            command.status = "dispatching"
            command.lease_owner = self._worker_id
            command.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            command.attempt += 1
            task.status = "running"
            product_run.status = "running"
            product_run.last_heartbeat_at = now

            remote_handle = None
            if (
                product_run.official_assistant_id
                and thread.official_thread_id
                and product_run.official_run_id
            ):
                remote_handle = RemoteRunHandle(
                    assistant_id=product_run.official_assistant_id,
                    thread_id=thread.official_thread_id,
                    run_id=product_run.official_run_id,
                )
            return CommandLease(
                command_id=command.id,
                task_id=task.id,
                product_thread_id=thread.id,
                product_run_id=product_run.id,
                worker_id=self._worker_id,
                fence_token=command.attempt,
                actor=actor,
                submission=AnalysisSubmission.model_validate(task.request_payload),
                remote_handle=remote_handle,
            )

    async def execute(self, lease: CommandLease) -> bool:
        if not await self._owns_lease(lease):
            return False

        handle = lease.remote_handle
        if handle is not None:
            authorize = getattr(self._runner, "authorize", None)
            if authorize is not None:
                handle = authorize(handle, lease.actor)
        if handle is None:
            try:
                handle = await self._start_with_heartbeat(
                    lease,
                    actor=lease.actor,
                    task_id=str(lease.task_id),
                    product_thread_id=str(lease.product_thread_id),
                    product_run_id=str(lease.product_run_id),
                    submission=lease.submission,
                )
            except Exception as exc:
                await self._record_remote_error(lease, exc)
                return False
            if handle is None:
                return False
            if not await self._register_remote(lease, handle):
                await self._runner.cancel(handle)
                return False

        try:
            output = await self._join_with_heartbeat(lease, handle)
        except Exception as exc:
            await self._record_remote_error(lease, exc)
            return False
        if output is None:
            return False

        try:
            terminal = TerminalGraphOutput.model_validate(output)
        except ValidationError as exc:
            terminal = TerminalGraphOutput(
                terminal_status="failed",
                errors=[
                    {
                        "code": "invalid_agent_output",
                        "error_type": type(exc).__name__,
                        "retryable": False,
                    }
                ],
            )
        return await self._finalize(lease, terminal)

    async def _owns_lease(self, lease: CommandLease) -> bool:
        now = self._clock()
        async with self._session_factory() as session:
            owned = await session.scalar(
                select(TaskCommand.id).where(
                    TaskCommand.id == lease.command_id,
                    TaskCommand.status == "dispatching",
                    TaskCommand.lease_owner == lease.worker_id,
                    TaskCommand.attempt == lease.fence_token,
                    TaskCommand.lease_expires_at > now,
                )
            )
        return owned is not None

    async def _register_remote(
        self, lease: CommandLease, handle: RemoteRunHandle
    ) -> bool:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(session, lease, now)
            if command is None:
                return False
            task = await session.scalar(
                select(Task).where(Task.id == lease.task_id).with_for_update()
            )
            thread = await session.scalar(
                select(Thread).where(Thread.id == lease.product_thread_id).with_for_update()
            )
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if (
                task is None
                or task.status != "running"
                or thread is None
                or product_run is None
            ):
                return False
            thread.official_thread_id = handle.thread_id
            product_run.official_assistant_id = handle.assistant_id
            product_run.official_run_id = handle.run_id
            product_run.last_heartbeat_at = now
            command.official_run_id = handle.run_id
            command.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            return True

    async def _join_with_heartbeat(
        self, lease: CommandLease, handle: RemoteRunHandle
    ) -> dict[str, Any] | None:
        join_task = asyncio.create_task(self._runner.join(handle))
        interval = max(1.0, self._lease_seconds / 3)
        while True:
            done, _ = await asyncio.wait({join_task}, timeout=interval)
            if join_task in done:
                return await join_task
            if not await self._renew_lease(lease):
                join_task.cancel()
                await asyncio.gather(join_task, return_exceptions=True)
                return None

    async def _start_with_heartbeat(
        self,
        lease: CommandLease,
        **kwargs: object,
    ) -> RemoteRunHandle | None:
        start_task = asyncio.create_task(self._runner.start(**kwargs))
        interval = max(1.0, self._lease_seconds / 3)
        while True:
            done, _ = await asyncio.wait({start_task}, timeout=interval)
            if start_task in done:
                return await start_task
            if not await self._renew_lease(lease):
                start_task.cancel()
                await asyncio.gather(start_task, return_exceptions=True)
                return None

    async def _renew_lease(self, lease: CommandLease) -> bool:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(session, lease, now)
            if command is None:
                return False
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if product_run is None:
                return False
            command.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            product_run.last_heartbeat_at = now
            return True

    async def _record_remote_error(self, lease: CommandLease, exc: Exception) -> None:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(session, lease, now, allow_expired=True)
            if command is None:
                return
            if command.attempt < self._max_attempts:
                command.lease_expires_at = now
                return
            task = await session.scalar(
                select(Task).where(Task.id == lease.task_id).with_for_update()
            )
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if task is None or product_run is None:
                return
            output = {
                "terminal_status": "failed",
                "errors": [
                    {
                        "code": "agent_server_unavailable",
                        "error_type": type(exc).__name__,
                        "retryable": True,
                    }
                ],
            }
            product_run.status = "failed"
            product_run.output_payload = output
            product_run.failure_code = "agent_server_unavailable"
            product_run.failure_message = "Agent Server 暂时不可用，当前分析未完成。"
            product_run.finished_at = now
            task.status = "failed"
            task.completed_at = now
            command.status = "failed"
            command.lease_owner = None
            command.lease_expires_at = None

    async def _finalize(
        self, lease: CommandLease, terminal: TerminalGraphOutput
    ) -> bool:
        now = self._clock()
        output = terminal.model_dump(mode="json", exclude_none=True)
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(session, lease, now, allow_expired=True)
            if command is None:
                return False
            task = await session.scalar(
                select(Task).where(Task.id == lease.task_id).with_for_update()
            )
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if task is None or task.status != "running" or product_run is None:
                return False

            product_run.output_payload = output
            product_run.status = terminal.terminal_status
            product_run.finished_at = now
            task.status = terminal.terminal_status
            task.completed_at = now
            command.status = "dispatched"
            command.lease_owner = None
            command.lease_expires_at = None

            if terminal.errors:
                product_run.failure_code = terminal.errors[0].code

            if terminal.market_snapshot is not None:
                market = terminal.market_snapshot
                session.add(
                    MarketSnapshot(
                        id=uuid4(),
                        tenant_id=task.tenant_id,
                        workspace_id=task.workspace_id,
                        owner_user_id=task.owner_user_id,
                        task_id=task.id,
                        run_id=product_run.id,
                        symbol=market.symbol,
                        snapshot=market.model_dump(mode="json"),
                        fetched_at=market.fetched_at,
                    )
                )
            for evidence in terminal.web_evidence:
                session.add(
                    WebEvidence(
                        id=uuid4(),
                        tenant_id=task.tenant_id,
                        workspace_id=task.workspace_id,
                        owner_user_id=task.owner_user_id,
                        task_id=task.id,
                        run_id=product_run.id,
                        source_url=str(evidence.final_url),
                        title=evidence.title,
                        payload=evidence.model_dump(mode="json"),
                        fetched_at=evidence.fetched_at,
                        published_at=evidence.published_at,
                    )
                )
            if terminal.terminal_status == "succeeded" and terminal.artifact is not None:
                artifact = Artifact(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    workspace_id=task.workspace_id,
                    owner_user_id=task.owner_user_id,
                    task_id=task.id,
                    artifact_type="analysis_report",
                )
                session.add(artifact)
                await session.flush()
                artifact_payload = terminal.artifact.model_dump(mode="json")
                repository = ArtifactRepository(session, lease.actor)
                await repository.commit_version_and_decision(
                    artifact_id=artifact.id,
                    run_id=product_run.id,
                    content=artifact_payload,
                    decision=artifact_payload["analysis"],
                    evidence_verdict=artifact_payload["evidence_verdict"],
                    risk_verdict=artifact_payload["risk_verdict"],
                    schema_version=terminal.artifact.schema_version,
                )
            return True

    async def _locked_command(
        self,
        session: AsyncSession,
        lease: CommandLease,
        now: datetime,
        *,
        allow_expired: bool = False,
    ) -> TaskCommand | None:
        conditions = [
            TaskCommand.id == lease.command_id,
            TaskCommand.status == "dispatching",
            TaskCommand.lease_owner == lease.worker_id,
            TaskCommand.attempt == lease.fence_token,
        ]
        if not allow_expired:
            conditions.append(TaskCommand.lease_expires_at > now)
        return await session.scalar(
            select(TaskCommand).where(*conditions).with_for_update()
        )


__all__ = ["CommandDispatcher", "CommandLease", "RemoteRunner"]
