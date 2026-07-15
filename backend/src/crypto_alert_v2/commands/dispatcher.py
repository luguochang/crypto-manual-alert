from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from crypto_alert_v2.api.agent_server import (
    RemoteCancelResult,
    RemoteInterrupt,
    RemoteRunHandle,
    RemoteRunState,
)
from crypto_alert_v2.api.schemas import AnalysisSubmission, TerminalGraphOutput
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.graph.request import ReviewResponse
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    InterruptProjection,
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


class RemoteRunner(Protocol):
    async def start(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_thread_id: str,
        product_run_id: str,
        submission: AnalysisSubmission,
        review_policy: Literal["bypass", "required"] = "bypass",
    ) -> RemoteRunHandle: ...

    async def join(self, handle: RemoteRunHandle) -> dict[str, Any]: ...

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState: ...

    async def find(
        self,
        *,
        actor: ActorContext,
        task_id: str,
        product_thread_id: str,
        product_run_id: str,
    ) -> RemoteRunHandle | None: ...

    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult: ...

    async def get_interrupts(
        self,
        handle: RemoteRunHandle,
    ) -> tuple[RemoteInterrupt, ...]: ...

    async def resume(
        self,
        *,
        actor: ActorContext,
        handle: RemoteRunHandle,
        task_id: str,
        product_run_id: str,
        response: dict[str, Any],
        checkpoint_id: str,
    ) -> RemoteRunHandle: ...


ObservedTerminalStatus = Literal["error", "success", "timeout"]
ReviewPolicy = Literal["bypass", "required"]


class RespondCommandPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    projection_id: UUID
    interrupt_id: str = Field(min_length=1, max_length=255)
    checkpoint_id: str = Field(min_length=1, max_length=255)
    response_version: int = Field(ge=1)
    response: ReviewResponse
    expired: bool = False


@dataclass(frozen=True, slots=True)
class CommandLease:
    command_id: UUID
    task_id: UUID
    product_thread_id: UUID
    product_run_id: UUID | None
    command_type: str
    command_sequence: int
    worker_id: str
    fence_token: int
    actor: ActorContext
    submission: AnalysisSubmission | None
    remote_handle: RemoteRunHandle | None = None
    resume_handle: RemoteRunHandle | None = None
    respond_payload: RespondCommandPayload | None = None
    review_policy: ReviewPolicy = "bypass"
    observed_terminal_status: ObservedTerminalStatus | None = None


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
        max_cancel_attempts: int = 30,
        max_cancel_seconds: int = 120,
        remote_operation_timeout_seconds: float = 20.0,
        reconciliation_interval_seconds: float = 2.0,
        max_run_seconds: int = 900,
        interrupt_ttl_seconds: int = 3_600,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be at least 3")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if max_cancel_attempts < 1:
            raise ValueError("max_cancel_attempts must be positive")
        if max_cancel_seconds < 1:
            raise ValueError("max_cancel_seconds must be positive")
        if remote_operation_timeout_seconds <= 0:
            raise ValueError("remote_operation_timeout_seconds must be positive")
        if reconciliation_interval_seconds <= 0:
            raise ValueError("reconciliation_interval_seconds must be positive")
        if max_run_seconds < 1:
            raise ValueError("max_run_seconds must be positive")
        if interrupt_ttl_seconds < 1:
            raise ValueError("interrupt_ttl_seconds must be positive")
        self._session_factory = session_factory
        self._runner = runner
        self._worker_id = worker_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._max_cancel_attempts = max_cancel_attempts
        self._max_cancel_seconds = max_cancel_seconds
        self._remote_operation_timeout_seconds = remote_operation_timeout_seconds
        self._reconciliation_interval_seconds = reconciliation_interval_seconds
        self._max_run_seconds = max_run_seconds
        self._interrupt_ttl_seconds = interrupt_ttl_seconds

    async def dispatch_once(self) -> bool:
        if await self._expire_due_interrupt_once():
            return True
        lease = await self.claim_next()
        if lease is None:
            return False
        return await self.execute(lease)

    async def _expire_due_interrupt_once(self) -> bool:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            row = (
                await session.execute(
                    select(InterruptProjection, Task)
                    .join(Task, Task.id == InterruptProjection.task_id)
                    .where(
                        InterruptProjection.status == "pending",
                        InterruptProjection.expires_at.is_not(None),
                        InterruptProjection.expires_at <= now,
                        Task.status == "waiting_human",
                    )
                    .order_by(InterruptProjection.expires_at, InterruptProjection.id)
                    .limit(1)
                    .with_for_update(of=Task, skip_locked=True)
                )
            ).one_or_none()
            if row is None:
                return False
            interrupt, task = row
            commands = list(
                (
                    await session.scalars(
                        select(TaskCommand)
                        .where(TaskCommand.task_id == task.id)
                        .order_by(TaskCommand.sequence)
                        .with_for_update()
                    )
                ).all()
            )
            if any(
                command.command_type == "respond"
                and command.status in {"pending", "dispatching"}
                for command in commands
            ):
                return False
            parent_run = await session.scalar(
                select(Run)
                .where(
                    Run.id == interrupt.run_id,
                    Run.task_id == task.id,
                    Run.status == "waiting_human",
                )
                .with_for_update()
            )
            interrupt = await session.scalar(
                select(InterruptProjection)
                .where(
                    InterruptProjection.id == interrupt.id,
                    InterruptProjection.task_id == task.id,
                )
                .with_for_update()
            )
            if (
                parent_run is None
                or interrupt is None
                or interrupt.status != "pending"
                or interrupt.expires_at is None
                or interrupt.expires_at > now
            ):
                return False

            response = {
                "action": "reject",
                "comment": "The review window expired before a decision was submitted.",
            }
            command_payload = {
                "projection_id": str(interrupt.id),
                "interrupt_id": interrupt.official_interrupt_id,
                "checkpoint_id": interrupt.checkpoint_id,
                "response_version": interrupt.response_version,
                "response": response,
                "expired": True,
            }
            command_hash = sha256(
                json.dumps(
                    command_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            resumed_run = Run(
                id=uuid4(),
                tenant_id=task.tenant_id,
                workspace_id=task.workspace_id,
                owner_user_id=task.owner_user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                attempt=parent_run.attempt + 1,
                status="queued",
                input_payload=task.request_payload,
                resume_of_run_id=parent_run.id,
            )
            session.add(resumed_run)
            session.add(
                TaskCommand(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    workspace_id=task.workspace_id,
                    actor_user_id=task.owner_user_id,
                    task_id=task.id,
                    thread_id=task.thread_id,
                    command_type="respond",
                    payload=command_payload,
                    payload_hash=command_hash,
                    sequence=max(
                        (command.sequence for command in commands),
                        default=0,
                    )
                    + 1,
                    status="pending",
                    attempt=0,
                    idempotency_key=(
                        f"expire:{interrupt.id}:{interrupt.response_version}"
                    ),
                )
            )
            interrupt.status = "expired"
            interrupt.response = response
            interrupt.responded_at = now
            await session.flush()
            return True

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
                        Workspace.review_policy,
                        User.external_subject,
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
                        and_(
                            Membership.tenant_id == TaskCommand.tenant_id,
                            Membership.workspace_id == TaskCommand.workspace_id,
                            Membership.user_id == TaskCommand.actor_user_id,
                        ),
                    )
                    .where(
                        TaskCommand.command_type.in_(("submit", "respond", "cancel_task")),
                        Task.status.in_(("queued", "running", "waiting_human")),
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
                    .with_for_update(of=Task, skip_locked=True)
                )
            ).one_or_none()
            if row is None:
                return None

            command, task, thread = row[0], row[1], row[2]
            command = await session.scalar(
                select(TaskCommand)
                .where(TaskCommand.id == command.id)
                .with_for_update()
            )
            if command is None:
                return None
            admitted_permissions = tuple(row[8] or ())
            actor = ActorContext(
                tenant_id=row[3],
                workspace_id=row[4],
                user_id=row[6],
                roles=(row[7] or "member",),
                permissions=tuple(
                    dict.fromkeys(
                        (*admitted_permissions, "analysis:read", "analysis:write")
                    )
                ),
            )

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
            respond_payload = None
            if command.command_type == "respond":
                try:
                    respond_payload = RespondCommandPayload.model_validate(command.payload)
                except ValidationError as exc:
                    command.status = "failed"
                    command.lease_owner = None
                    command.lease_expires_at = None
                    task.status = "failed"
                    task.completed_at = now
                    if product_run is not None:
                        product_run.status = "failed"
                        product_run.failure_code = "invalid_respond_command"
                        product_run.failure_message = str(exc)
                        product_run.finished_at = now
                    return None
            if command.command_type == "submit" and product_run is None:
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
                    reconciliation_deadline_at=now
                    + timedelta(seconds=self._max_run_seconds),
                )
                session.add(product_run)
                await session.flush()

            if (
                command.command_type == "submit"
                and product_run is not None
                and product_run.cancel_requested_at is not None
            ):
                has_cancel_command = await session.scalar(
                    select(
                        exists().where(
                            TaskCommand.task_id == task.id,
                            TaskCommand.command_type == "cancel_task",
                            TaskCommand.status.in_(("pending", "dispatching")),
                        )
                    )
                )
                if has_cancel_command:
                    command.status = "cancelled"
                    command.lease_owner = None
                    command.lease_expires_at = None
                    return None

            command.status = "dispatching"
            command.lease_owner = self._worker_id
            command.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            command.attempt += 1
            if command.command_type in {"submit", "respond"}:
                task.status = "running"
                assert product_run is not None
                product_run.status = "running"
                product_run.last_heartbeat_at = now
                if product_run.reconciliation_deadline_at is None:
                    product_run.reconciliation_deadline_at = now + timedelta(
                        seconds=self._max_run_seconds
                    )

            remote_handle = None
            if (
                product_run is not None
                and product_run.official_assistant_id
                and thread.official_thread_id
                and product_run.official_run_id
            ):
                remote_handle = RemoteRunHandle(
                    assistant_id=product_run.official_assistant_id,
                    thread_id=thread.official_thread_id,
                    run_id=product_run.official_run_id,
                )
            resume_handle = None
            if (
                command.command_type == "respond"
                and product_run is not None
                and product_run.resume_of_run_id is not None
                and thread.official_thread_id
            ):
                resume_run = await session.scalar(
                    select(Run)
                    .where(Run.id == product_run.resume_of_run_id)
                    .with_for_update()
                )
                if (
                    resume_run is not None
                    and resume_run.official_assistant_id
                    and resume_run.official_run_id
                ):
                    resume_handle = RemoteRunHandle(
                        assistant_id=resume_run.official_assistant_id,
                        thread_id=thread.official_thread_id,
                        run_id=resume_run.official_run_id,
                    )
            return CommandLease(
                command_id=command.id,
                task_id=task.id,
                product_thread_id=thread.id,
                product_run_id=(product_run.id if product_run is not None else None),
                command_type=command.command_type,
                command_sequence=command.sequence,
                worker_id=self._worker_id,
                fence_token=command.attempt,
                actor=actor,
                submission=(
                    AnalysisSubmission.model_validate(task.request_payload)
                    if command.command_type == "submit"
                    else None
                ),
                remote_handle=remote_handle,
                resume_handle=resume_handle,
                respond_payload=respond_payload,
                review_policy=cast(ReviewPolicy, row[5]),
                observed_terminal_status=(
                    cast(
                        ObservedTerminalStatus | None,
                        product_run.observed_terminal_status,
                    )
                    if product_run is not None
                    else None
                ),
            )

    async def execute(self, lease: CommandLease) -> bool:
        if not await self._owns_lease(lease):
            return False

        if lease.command_type == "cancel_task":
            return await self._execute_cancel(lease)
        if lease.product_run_id is None:
            return False
        if lease.command_type == "submit" and lease.submission is None:
            return False
        if lease.command_type == "respond" and lease.respond_payload is None:
            return False

        handle = lease.remote_handle
        if handle is not None:
            authorize = getattr(self._runner, "authorize", None)
            if authorize is not None:
                handle = authorize(handle, lease.actor)
        if handle is None:
            try:
                if lease.command_type == "respond":
                    if lease.resume_handle is None or lease.respond_payload is None:
                        raise RuntimeError(
                            "Respond command has no registered interrupted Run"
                        )
                    handle = await self._resume_with_heartbeat(
                        lease,
                        actor=lease.actor,
                        handle=lease.resume_handle,
                        task_id=str(lease.task_id),
                        product_run_id=str(lease.product_run_id),
                        response=lease.respond_payload.response.model_dump(
                            mode="json",
                            exclude_none=True,
                        ),
                        checkpoint_id=lease.respond_payload.checkpoint_id,
                    )
                else:
                    assert lease.submission is not None
                    handle = await self._start_with_heartbeat(
                        lease,
                        actor=lease.actor,
                        task_id=str(lease.task_id),
                        product_thread_id=str(lease.product_thread_id),
                        product_run_id=str(lease.product_run_id),
                        submission=lease.submission,
                        review_policy=lease.review_policy,
                    )
            except Exception as exc:
                await self._record_remote_error(lease, exc)
                return False
            if handle is None:
                return False
            registration = await self._register_remote(lease, handle)
            if registration == "cancel_requested":
                return True
            if registration == "lost":
                return False

        if lease.observed_terminal_status is not None:
            return await self._project_remote_terminal(
                lease,
                handle,
                RemoteRunState(status=lease.observed_terminal_status),
            )

        try:
            remote_state = await self._runner.get(handle)
        except Exception:
            return await self._reconcile_or_timeout(lease, handle)

        if remote_state.status in {"pending", "running"}:
            return await self._reconcile_or_timeout(lease, handle)
        if remote_state.status == "interrupted":
            try:
                async with asyncio.timeout(self._remote_operation_timeout_seconds):
                    interrupts = await self._runner.get_interrupts(handle)
            except Exception as exc:
                return await self._schedule_interrupt_projection_retry(lease, exc)
            return await self._mark_waiting_human(lease, interrupts)
        return await self._project_remote_terminal(
            lease,
            handle,
            remote_state,
        )

    async def _execute_cancel(self, lease: CommandLease) -> bool:
        handle = lease.remote_handle
        if lease.observed_terminal_status is not None:
            if handle is None:
                return await self._schedule_terminal_retry(
                    lease,
                    RuntimeError("Observed terminal Run has no registered handle"),
                )
            authorize = getattr(self._runner, "authorize", None)
            if authorize is not None:
                handle = authorize(handle, lease.actor)
            return await self._project_remote_terminal(
                lease,
                handle,
                RemoteRunState(status=lease.observed_terminal_status),
            )
        if handle is None and lease.product_run_id is not None:
            try:
                async with asyncio.timeout(self._remote_operation_timeout_seconds):
                    handle = await self._runner.find(
                        actor=lease.actor,
                        task_id=str(lease.task_id),
                        product_thread_id=str(lease.product_thread_id),
                        product_run_id=str(lease.product_run_id),
                    )
            except Exception as exc:
                return await self._schedule_cancel_retry(lease, exc)
            if handle is None:
                return await self._schedule_cancel_retry(lease)
            if not await self._register_cancel_target(lease, handle):
                return False
        if handle is not None:
            authorize = getattr(self._runner, "authorize", None)
            if authorize is not None:
                handle = authorize(handle, lease.actor)
            try:
                cancel_result = await self._cancel_remote(handle)
            except Exception as exc:
                return await self._schedule_cancel_retry(lease, exc)
            if cancel_result.outcome == "unconfirmed":
                return await self._schedule_cancel_retry(lease)
            if cancel_result.outcome == "terminal":
                if cancel_result.state is None:
                    return await self._schedule_cancel_retry(lease)
                return await self._project_remote_terminal(
                    lease,
                    handle,
                    cancel_result.state,
                )
        return await self._finalize_cancel(lease)

    async def _project_remote_terminal(
        self,
        lease: CommandLease,
        handle: RemoteRunHandle,
        remote_state: RemoteRunState,
    ) -> bool:
        if not await self._remember_remote_terminal(lease, remote_state):
            return False
        if remote_state.status in {"error", "timeout"}:
            return await self._finalize(
                lease,
                TerminalGraphOutput(
                    terminal_status="failed",
                    errors=[
                        {
                            "code": (
                                "agent_run_timeout"
                                if remote_state.status == "timeout"
                                else "agent_run_error"
                            ),
                            "error_type": "OfficialRunStatus",
                            "retryable": remote_state.status == "timeout",
                        }
                    ],
                ),
            )
        if remote_state.status != "success":
            raise RuntimeError("Remote Run is not terminal")

        try:
            async with asyncio.timeout(self._remote_operation_timeout_seconds):
                output = await self._runner.join(handle)
        except Exception as exc:
            return await self._schedule_terminal_retry(lease, exc)

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

    async def _remember_remote_terminal(
        self,
        lease: CommandLease,
        remote_state: RemoteRunState,
    ) -> bool:
        if remote_state.status not in {"error", "success", "timeout"}:
            raise RuntimeError("Remote Run is not terminal")
        if lease.product_run_id is None:
            return False
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
            if command is None:
                return False
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if product_run is None:
                return False
            if (
                product_run.observed_terminal_status is not None
                and product_run.observed_terminal_status != remote_state.status
            ):
                raise RuntimeError("Official Run terminal status changed after observation")
            product_run.observed_terminal_status = remote_state.status
            product_run.last_heartbeat_at = now
            return True

    async def _schedule_terminal_retry(
        self,
        lease: CommandLease,
        exc: Exception,
    ) -> bool:
        attempt_limit = (
            self._max_cancel_attempts
            if lease.command_type == "cancel_task"
            else self._max_attempts
        )
        if lease.fence_token >= attempt_limit:
            return await self._finalize(
                lease,
                TerminalGraphOutput(
                    terminal_status="failed",
                    errors=[
                        {
                            "code": "terminal_projection_unavailable",
                            "error_type": type(exc).__name__,
                            "retryable": False,
                            "attempt": max(1, min(lease.fence_token, 100)),
                        }
                    ],
                ),
            )
        return await self._schedule_reconciliation(lease)

    async def _cancel_remote(
        self,
        handle: RemoteRunHandle,
    ) -> RemoteCancelResult:
        async with asyncio.timeout(self._remote_operation_timeout_seconds):
            return await self._runner.cancel(handle)

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
    ) -> str:
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(session, lease, now)
            if command is None:
                return "lost"
            task = await session.scalar(
                select(Task).where(Task.id == lease.task_id).with_for_update()
            )
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            thread = await session.scalar(
                select(Thread).where(Thread.id == lease.product_thread_id).with_for_update()
            )
            if (
                task is None
                or task.status != "running"
                or thread is None
                or product_run is None
            ):
                return "lost"
            thread.official_thread_id = handle.thread_id
            product_run.official_assistant_id = handle.assistant_id
            product_run.official_run_id = handle.run_id
            product_run.last_heartbeat_at = now
            command.official_run_id = handle.run_id
            if product_run.cancel_requested_at is not None:
                command.status = "cancelled"
                command.lease_owner = None
                command.lease_expires_at = None
                return "cancel_requested"
            command.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            return "registered"

    async def _register_cancel_target(
        self,
        lease: CommandLease,
        handle: RemoteRunHandle,
    ) -> bool:
        if lease.product_run_id is None:
            return False
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
            if command is None:
                return False
            product_run = await session.scalar(
                select(Run)
                .where(Run.id == lease.product_run_id)
                .with_for_update()
            )
            thread = await session.scalar(
                select(Thread)
                .where(Thread.id == lease.product_thread_id)
                .with_for_update()
            )
            if thread is None or product_run is None:
                return False
            thread.official_thread_id = handle.thread_id
            product_run.official_assistant_id = handle.assistant_id
            product_run.official_run_id = handle.run_id
            product_run.last_heartbeat_at = now
            command.official_run_id = handle.run_id
            return True

    async def _schedule_cancel_retry(
        self,
        lease: CommandLease,
        exc: Exception | None = None,
    ) -> bool:
        if lease.fence_token >= self._max_cancel_attempts:
            return await self._finalize_cancel_failure(lease, exc)
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
            if command is None:
                return False
            command.lease_owner = None
            command.lease_expires_at = now + timedelta(
                seconds=self._reconciliation_interval_seconds
            )
            return True

    async def _finalize_cancel_failure(
        self,
        lease: CommandLease,
        exc: Exception | None,
        *,
        failure_code: str = "agent_cancel_failed",
        failure_message: str = "Official Run cancellation could not be confirmed.",
    ) -> bool:
        now = self._clock()
        output = {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": failure_code,
                    "error_type": type(exc).__name__ if exc is not None else "RunDiscoveryTimeout",
                    "retryable": False,
                    "attempt": max(1, min(lease.fence_token, 100)),
                }
            ],
        }
        output_hash = sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
            if command is None:
                return False
            task = await session.scalar(
                select(Task).where(Task.id == lease.task_id).with_for_update()
            )
            product_run = None
            if lease.product_run_id is not None:
                product_run = await session.scalar(
                    select(Run)
                    .where(Run.id == lease.product_run_id)
                    .with_for_update()
                )
            if task is None or task.status in {
                "succeeded",
                "blocked",
                "failed",
                "cancelled",
            }:
                command.status = "cancelled"
                command.lease_owner = None
                command.lease_expires_at = None
                return False
            task.status = "failed"
            task.completed_at = now
            command.status = "failed"
            command.lease_owner = None
            command.lease_expires_at = None
            if product_run is not None:
                product_run.status = "failed"
                product_run.output_payload = output
                product_run.failure_code = failure_code
                product_run.failure_message = failure_message
                product_run.finished_at = now
                product_run.projection_fence = lease.command_sequence
                product_run.terminal_output_hash = output_hash
            return True

    async def _finalize_cancel(self, lease: CommandLease) -> bool:
        now = self._clock()
        output = {"terminal_status": "cancelled", "errors": []}
        output_hash = sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
            if command is None:
                return False
            task = await session.scalar(
                select(Task).where(Task.id == lease.task_id).with_for_update()
            )
            if task is None or task.status in {
                "succeeded",
                "blocked",
                "failed",
                "cancelled",
            }:
                command.status = "cancelled"
                command.lease_owner = None
                command.lease_expires_at = None
                return False
            product_run = None
            if lease.product_run_id is not None:
                product_run = await session.scalar(
                    select(Run)
                    .where(Run.id == lease.product_run_id)
                    .with_for_update()
                )

            if product_run is not None:
                if product_run.projection_fence > lease.command_sequence:
                    command.status = "cancelled"
                    command.lease_owner = None
                    command.lease_expires_at = None
                    return False
            active_interrupts = list(
                (
                    await session.scalars(
                        select(InterruptProjection)
                        .where(
                            InterruptProjection.task_id == lease.task_id,
                            InterruptProjection.status.in_(("pending", "responding")),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            for interrupt in active_interrupts:
                interrupt.status = "cancelled"
            task.status = "cancelled"
            task.completed_at = now
            command.status = "dispatched"
            command.lease_owner = None
            command.lease_expires_at = None
            if product_run is not None:
                product_run.status = "cancelled"
                product_run.output_payload = output
                product_run.finished_at = now
                product_run.projection_fence = lease.command_sequence
                product_run.terminal_output_hash = output_hash
            return True

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

    async def _resume_with_heartbeat(
        self,
        lease: CommandLease,
        **kwargs: object,
    ) -> RemoteRunHandle | None:
        resume_task = asyncio.create_task(self._runner.resume(**kwargs))
        interval = max(1.0, self._lease_seconds / 3)
        while True:
            done, _ = await asyncio.wait({resume_task}, timeout=interval)
            if resume_task in done:
                return await resume_task
            if not await self._renew_lease(lease):
                resume_task.cancel()
                await asyncio.gather(resume_task, return_exceptions=True)
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

    async def _reconcile_or_timeout(
        self,
        lease: CommandLease,
        handle: RemoteRunHandle,
    ) -> bool:
        if await self._run_deadline_exceeded(lease):
            try:
                cancel_result = await self._cancel_remote(handle)
            except Exception as exc:
                return await self._schedule_or_finalize_orphan_cancel(lease, exc)
            if cancel_result.outcome == "unconfirmed":
                return await self._schedule_or_finalize_orphan_cancel(
                    lease,
                    RuntimeError("Official Run cancellation is unconfirmed"),
                )
            if cancel_result.outcome == "terminal":
                if cancel_result.state is None:
                    return await self._schedule_or_finalize_orphan_cancel(
                        lease,
                        RuntimeError("Official Run terminal state is unavailable"),
                    )
                return await self._project_remote_terminal(
                    lease,
                    handle,
                    cancel_result.state,
                )
            return await self._finalize(
                lease,
                TerminalGraphOutput(
                    terminal_status="failed",
                    errors=[
                        {
                            "code": "agent_run_timeout",
                            "error_type": "OrphanDeadlineExceeded",
                            "retryable": True,
                        }
                    ],
                ),
            )
        return await self._schedule_reconciliation(lease)

    async def _schedule_or_finalize_orphan_cancel(
        self,
        lease: CommandLease,
        exc: Exception,
    ) -> bool:
        if lease.product_run_id is None:
            return False
        now = self._clock()
        cleanup_exhausted = False
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
            if command is None:
                return False
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if product_run is None or product_run.status != "running":
                return False
            cleanup_started_at = product_run.cancel_requested_at
            if cleanup_started_at is None:
                product_run.cancel_requested_at = now
            elif now >= cleanup_started_at + timedelta(
                seconds=self._max_cancel_seconds
            ):
                cleanup_exhausted = True

            if not cleanup_exhausted:
                product_run.last_heartbeat_at = now
                command.lease_owner = None
                command.lease_expires_at = now + timedelta(
                    seconds=self._reconciliation_interval_seconds
                )

        if cleanup_exhausted:
            return await self._finalize_cancel_failure(
                lease,
                exc,
                failure_code="orphan_cancel_unconfirmed",
                failure_message=(
                    "Official Run cleanup after the orphan deadline could not be confirmed."
                ),
            )
        return True

    async def _run_deadline_exceeded(self, lease: CommandLease) -> bool:
        if lease.product_run_id is None:
            return True
        async with self._session_factory() as session:
            timing = (
                await session.execute(
                    select(
                        Run.reconciliation_deadline_at,
                        Run.started_at,
                    ).where(Run.id == lease.product_run_id)
                )
            ).one_or_none()
        if timing is None:
            return True
        deadline, started_at = timing
        if deadline is None and started_at is not None:
            deadline = started_at + timedelta(seconds=self._max_run_seconds)
        return bool(
            deadline is not None and self._clock() >= deadline
        )

    async def _schedule_reconciliation(self, lease: CommandLease) -> bool:
        if lease.product_run_id is None:
            return False
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
            if command is None:
                return False
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if product_run is None or product_run.status != "running":
                return False
            product_run.last_heartbeat_at = now
            command.lease_owner = None
            command.lease_expires_at = now + timedelta(
                seconds=self._reconciliation_interval_seconds
            )
            return True

    async def _schedule_interrupt_projection_retry(
        self,
        lease: CommandLease,
        exc: Exception,
    ) -> bool:
        if lease.fence_token >= self._max_attempts:
            return await self._finalize(
                lease,
                TerminalGraphOutput(
                    terminal_status="failed",
                    errors=[
                        {
                            "code": "interrupt_projection_unavailable",
                            "error_type": type(exc).__name__,
                            "retryable": False,
                            "attempt": max(1, min(lease.fence_token, 100)),
                        }
                    ],
                ),
            )
        return await self._schedule_reconciliation(lease)

    async def _mark_waiting_human(
        self,
        lease: CommandLease,
        interrupts: tuple[RemoteInterrupt, ...],
    ) -> bool:
        if lease.product_run_id is None:
            return False
        if not interrupts:
            return False
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session,
                lease,
                now,
                allow_expired=True,
            )
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
            await self._resolve_responding_interrupt(session, lease, now)
            for remote_interrupt in interrupts:
                projection = await session.scalar(
                    select(InterruptProjection)
                    .where(
                        InterruptProjection.tenant_id == task.tenant_id,
                        InterruptProjection.workspace_id == task.workspace_id,
                        InterruptProjection.owner_user_id == task.owner_user_id,
                        InterruptProjection.task_id == task.id,
                        InterruptProjection.official_interrupt_id
                        == remote_interrupt.interrupt_id,
                        InterruptProjection.checkpoint_id
                        == remote_interrupt.checkpoint_id,
                        InterruptProjection.response_version == 1,
                    )
                    .with_for_update()
                )
                if projection is None:
                    session.add(
                        InterruptProjection(
                            id=uuid4(),
                            tenant_id=task.tenant_id,
                            workspace_id=task.workspace_id,
                            owner_user_id=task.owner_user_id,
                            task_id=task.id,
                            run_id=product_run.id,
                            official_interrupt_id=remote_interrupt.interrupt_id,
                            namespace=remote_interrupt.namespace,
                            checkpoint_id=remote_interrupt.checkpoint_id,
                            response_version=1,
                            status="pending",
                            payload=remote_interrupt.value,
                            expires_at=now
                            + timedelta(seconds=self._interrupt_ttl_seconds),
                        )
                    )
                    continue
                if projection.run_id != product_run.id:
                    raise RuntimeError(
                        "Official interrupt identity was reused by another Product Run"
                    )
                if projection.status == "pending":
                    projection.namespace = remote_interrupt.namespace
                    projection.payload = remote_interrupt.value
            task.status = "waiting_human"
            product_run.status = "waiting_human"
            product_run.last_heartbeat_at = now
            command.status = "dispatched"
            command.lease_owner = None
            command.lease_expires_at = None
            return True

    async def _resolve_responding_interrupt(
        self,
        session: AsyncSession,
        lease: CommandLease,
        now: datetime,
    ) -> None:
        payload = lease.respond_payload
        if payload is None:
            return
        projection = await session.scalar(
            select(InterruptProjection)
            .where(
                InterruptProjection.id == payload.projection_id,
                InterruptProjection.task_id == lease.task_id,
            )
            .with_for_update()
        )
        if projection is None:
            raise RuntimeError("Respond command interrupt projection is missing")
        if projection.status == "responding":
            projection.status = "resolved"
            projection.responded_at = projection.responded_at or now

    async def _record_remote_error(self, lease: CommandLease, exc: Exception) -> None:
        if lease.product_run_id is None:
            return
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(session, lease, now, allow_expired=True)
            if command is None:
                return
            product_run = await session.scalar(
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
            )
            if product_run is None:
                return
            if product_run.cancel_requested_at is not None:
                command.status = "cancelled"
                command.lease_owner = None
                command.lease_expires_at = None
                return
            if command.attempt < self._max_attempts:
                command.lease_expires_at = now
                return
            task = await session.scalar(
                select(Task).where(Task.id == lease.task_id).with_for_update()
            )
            if task is None:
                return
            await self._resolve_responding_interrupt(session, lease, now)
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
        if lease.product_run_id is None:
            return False
        now = self._clock()
        output = terminal.model_dump(mode="json", exclude_none=True)
        output_hash = sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
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
            if task is None or product_run is None:
                return False
            if task.status != "running":
                command.status = "cancelled"
                command.lease_owner = None
                command.lease_expires_at = None
                return False
            await self._resolve_responding_interrupt(session, lease, now)
            if product_run.projection_fence > lease.command_sequence:
                command.status = "cancelled"
                command.lease_owner = None
                command.lease_expires_at = None
                return False
            if (
                product_run.projection_fence == lease.command_sequence
                and product_run.terminal_output_hash is not None
            ):
                if product_run.terminal_output_hash == output_hash:
                    product_run.status = terminal.terminal_status
                    product_run.finished_at = product_run.finished_at or now
                    task.status = terminal.terminal_status
                    task.completed_at = task.completed_at or now
                    command.status = "dispatched"
                    command.lease_owner = None
                    command.lease_expires_at = None
                    return True
                product_run.status = "failed"
                product_run.failure_code = "terminal_projection_conflict"
                product_run.failure_message = (
                    "A terminal replay did not match the persisted output hash."
                )
                product_run.finished_at = now
                task.status = "failed"
                task.completed_at = now
                command.status = "failed"
                command.lease_owner = None
                command.lease_expires_at = None
                return False

            product_run.output_payload = output
            product_run.projection_fence = lease.command_sequence
            product_run.terminal_output_hash = output_hash
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
                artifact_version = ArtifactVersion(
                    id=uuid4(),
                    tenant_id=artifact.tenant_id,
                    workspace_id=artifact.workspace_id,
                    owner_user_id=artifact.owner_user_id,
                    artifact_id=artifact.id,
                    task_id=artifact.task_id,
                    run_id=product_run.id,
                    version_number=1,
                    schema_version=terminal.artifact.schema_version,
                    status="committed",
                    content=artifact_payload,
                )
                artifact.latest_version_number = 1
                session.add(artifact_version)
                session.add(
                    Decision(
                        id=uuid4(),
                        tenant_id=artifact.tenant_id,
                        workspace_id=artifact.workspace_id,
                        owner_user_id=artifact.owner_user_id,
                        artifact_id=artifact.id,
                        artifact_version_id=artifact_version.id,
                        task_id=artifact.task_id,
                        run_id=product_run.id,
                        decision_version=1,
                        decision=artifact_payload["analysis"],
                        evidence_verdict=artifact_payload["evidence_verdict"],
                        risk_verdict=artifact_payload["risk_verdict"],
                    )
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
        task_id = await session.scalar(
            select(Task.id).where(Task.id == lease.task_id).with_for_update()
        )
        if task_id is None:
            return None
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
