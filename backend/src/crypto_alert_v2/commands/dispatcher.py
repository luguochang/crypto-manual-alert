from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from crypto_alert_v2.api.agent_server import (
    RemoteCancelResult,
    RemoteCheckpoint,
    RemoteForkIndeterminateError,
    RemoteInterruptSet,
    RemoteResumeIndeterminateError,
    RemoteRunHandle,
    RemoteRunState,
)
from crypto_alert_v2.api.schemas import AnalysisSubmission, TerminalGraphOutput
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.graph.request import ArtifactReviewPayload, ReviewResponse
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    InterruptPause,
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

    async def fork(
        self,
        *,
        actor: ActorContext,
        handle: RemoteRunHandle,
        task_id: str,
        product_run_id: str,
        checkpoint_id: str,
    ) -> RemoteRunHandle: ...

    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult: ...

    async def get_interrupts(
        self,
        handle: RemoteRunHandle,
    ) -> RemoteInterruptSet: ...

    async def resume(
        self,
        *,
        actor: ActorContext,
        handle: RemoteRunHandle,
        task_id: str,
        product_run_id: str,
        responses: Mapping[str, dict[str, Any]],
        checkpoint: RemoteCheckpoint,
    ) -> RemoteRunHandle: ...


ObservedTerminalStatus = Literal["error", "success", "timeout"]
ReviewPolicy = Literal["bypass", "required"]


class ResumeCheckpointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=255)
    checkpoint_ns: str = Field(max_length=1024)
    checkpoint_id: str = Field(min_length=1, max_length=255)
    checkpoint_map: dict[str, str] = Field(default_factory=dict)


class RespondCommandMember(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    projection_id: UUID
    interrupt_id: str = Field(min_length=1, max_length=255)
    namespace: str = Field(max_length=1024)
    checkpoint_id: str = Field(min_length=1, max_length=255)
    response_version: int = Field(ge=1)
    response: ReviewResponse


class RespondCommandPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pause_id: UUID
    pause_version: int = Field(ge=1)
    root_checkpoint: ResumeCheckpointPayload
    responses: list[RespondCommandMember] = Field(min_length=1, max_length=64)
    expired: bool = False

    @model_validator(mode="after")
    def require_unique_members(self) -> "RespondCommandPayload":
        interrupt_ids = [item.interrupt_id for item in self.responses]
        projection_ids = [item.projection_id for item in self.responses]
        if len(interrupt_ids) != len(set(interrupt_ids)):
            raise ValueError("respond command interrupt IDs must be unique")
        if len(projection_ids) != len(set(projection_ids)):
            raise ValueError("respond command projection IDs must be unique")
        return self


class ForkCommandPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_run_id: UUID
    fork_run_id: UUID
    checkpoint_id: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_distinct_runs(self) -> "ForkCommandPayload":
        if self.source_run_id == self.fork_run_id:
            raise ValueError("fork source and destination Runs must differ")
        return self


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
    fork_source_handle: RemoteRunHandle | None = None
    fork_payload: ForkCommandPayload | None = None
    review_policy: ReviewPolicy = "bypass"
    observed_terminal_status: ObservedTerminalStatus | None = None
    resume_reconcile_only: bool = False
    fork_reconcile_only: bool = False


def _task_accepts_active_run(task: Task, lease: CommandLease) -> bool:
    if task.status == "running":
        return True
    return (
        task.status == "waiting_human"
        and lease.command_type == "respond"
        and lease.respond_payload is not None
        and not lease.respond_payload.expired
    )


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
                    select(InterruptPause, Task)
                    .join(Task, Task.id == InterruptPause.task_id)
                    .where(
                        InterruptPause.status == "pending",
                        InterruptPause.expires_at.is_not(None),
                        InterruptPause.expires_at <= now,
                        Task.status == "waiting_human",
                    )
                    .order_by(InterruptPause.expires_at, InterruptPause.id)
                    .limit(1)
                    .with_for_update(of=Task, skip_locked=True)
                )
            ).one_or_none()
            if row is None:
                return False
            pause, task = row
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
                    Run.id == pause.run_id,
                    Run.task_id == task.id,
                    Run.status == "waiting_human",
                )
                .with_for_update()
            )
            pause = await session.scalar(
                select(InterruptPause)
                .where(
                    InterruptPause.id == pause.id,
                    InterruptPause.task_id == task.id,
                )
                .with_for_update()
            )
            if (
                parent_run is None
                or pause is None
                or pause.status != "pending"
                or pause.expires_at is None
                or pause.expires_at > now
            ):
                return False
            projections = list(
                (
                    await session.scalars(
                        select(InterruptProjection)
                        .where(
                            InterruptProjection.pause_id == pause.id,
                            InterruptProjection.task_id == task.id,
                        )
                        .order_by(InterruptProjection.id)
                        .with_for_update()
                    )
                ).all()
            )
            if not projections or any(
                projection.status != "pending" for projection in projections
            ):
                raise RuntimeError("Expiring interrupt pause has inconsistent members")

            response = {
                "action": "reject",
                "comment": "The review window expired before a decision was submitted.",
            }
            command_payload = {
                "pause_id": str(pause.id),
                "pause_version": pause.pause_version,
                "root_checkpoint": {
                    "thread_id": pause.root_thread_id,
                    "checkpoint_ns": pause.root_checkpoint_ns,
                    "checkpoint_id": pause.root_checkpoint_id,
                    "checkpoint_map": pause.root_checkpoint_map,
                },
                "responses": [
                    {
                        "projection_id": str(projection.id),
                        "interrupt_id": projection.official_interrupt_id,
                        "namespace": projection.namespace,
                        "checkpoint_id": projection.checkpoint_id,
                        "response_version": projection.response_version,
                        "response": response,
                    }
                    for projection in sorted(
                        projections,
                        key=lambda item: item.official_interrupt_id,
                    )
                ],
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
            await session.flush()
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
                    idempotency_key=f"expire:{pause.id}:{pause.pause_version}",
                )
            )
            pause.status = "expired"
            pause.resume_run_id = resumed_run.id
            pause.accepted_payload_hash = command_hash
            for projection in projections:
                projection.status = "expired"
                projection.response = response
                projection.responded_at = now
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
                        and_(
                            Membership.tenant_id == TaskCommand.tenant_id,
                            Membership.workspace_id == TaskCommand.workspace_id,
                            Membership.user_id == TaskCommand.actor_user_id,
                        ),
                    )
                    .where(
                        TaskCommand.command_type.in_(
                            ("submit", "respond", "fork", "cancel_task")
                        ),
                        Task.status.in_(("queued", "running", "waiting_human")),
                        or_(
                            and_(
                                TaskCommand.status == "pending",
                                or_(
                                    TaskCommand.lease_expires_at.is_(None),
                                    TaskCommand.lease_expires_at <= now,
                                ),
                            ),
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
            admitted_permissions = tuple(row[10] or ())
            actor = ActorContext(
                tenant_id=row[3],
                workspace_id=row[4],
                user_id=row[6],
                identity_issuer=row[7],
                context_id=row[8],
                roles=(row[9] or "member",),
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
            fork_payload = None
            if command.command_type == "respond":
                try:
                    respond_payload = RespondCommandPayload.model_validate(
                        command.payload
                    )
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
            if command.command_type == "fork":
                try:
                    fork_payload = ForkCommandPayload.model_validate(command.payload)
                except ValidationError as exc:
                    command.status = "failed"
                    command.lease_owner = None
                    command.lease_expires_at = None
                    task.status = "failed"
                    task.completed_at = now
                    if product_run is not None:
                        product_run.status = "failed"
                        product_run.failure_code = "invalid_fork_command"
                        product_run.failure_message = str(exc)
                        product_run.finished_at = now
                    return None

                product_run = await session.scalar(
                    select(Run)
                    .where(
                        Run.id == fork_payload.fork_run_id,
                        Run.task_id == task.id,
                        Run.thread_id == task.thread_id,
                        Run.tenant_id == task.tenant_id,
                        Run.workspace_id == task.workspace_id,
                        Run.owner_user_id == task.owner_user_id,
                    )
                    .with_for_update()
                )
                fork_source_run = await session.scalar(
                    select(Run)
                    .where(
                        Run.id == fork_payload.source_run_id,
                        Run.task_id == task.id,
                        Run.thread_id == task.thread_id,
                        Run.tenant_id == task.tenant_id,
                        Run.workspace_id == task.workspace_id,
                        Run.owner_user_id == task.owner_user_id,
                        Run.checkpoint_id == fork_payload.checkpoint_id,
                    )
                    .with_for_update()
                )
                if (
                    product_run is None
                    or product_run.checkpoint_id != fork_payload.checkpoint_id
                    or product_run.forked_from_run_id != fork_payload.source_run_id
                    or product_run.forked_from_checkpoint_id
                    != fork_payload.checkpoint_id
                    or fork_source_run is None
                ):
                    command.status = "failed"
                    command.lease_owner = None
                    command.lease_expires_at = None
                    task.status = "failed"
                    task.completed_at = now
                    if product_run is not None:
                        product_run.status = "failed"
                        product_run.failure_code = "invalid_fork_lineage"
                        product_run.failure_message = (
                            "Fork command does not match its Product Run lineage."
                        )
                        product_run.finished_at = now
                    return None
            else:
                fork_source_run = None
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
            if command.command_type in {"submit", "respond", "fork"}:
                if command.command_type in {"submit", "fork"} or (
                    respond_payload is not None and respond_payload.expired
                ):
                    task.status = "running"
                else:
                    task.status = "waiting_human"
                assert product_run is not None
                product_run.status = "running"
                if product_run.started_at is None:
                    product_run.started_at = now
                product_run.last_heartbeat_at = now
                if product_run.reconciliation_deadline_at is None:
                    product_run.reconciliation_deadline_at = now + timedelta(
                        seconds=self._max_run_seconds
                    )

            resume_reconcile_only = False
            if (
                command.command_type == "respond"
                and product_run is not None
                and product_run.official_run_id is None
            ):
                resume_reconcile_only = product_run.failure_code in {
                    "agent_resume_create_intent",
                    "agent_resume_indeterminate",
                }
                if not resume_reconcile_only:
                    product_run.failure_code = "agent_resume_create_intent"
                    product_run.failure_message = (
                        "Official resume create intent is durable; a replacement "
                        "worker must reconcile metadata before any second create."
                    )

            fork_reconcile_only = False
            if (
                command.command_type == "fork"
                and product_run is not None
                and product_run.official_run_id is None
            ):
                fork_reconcile_only = product_run.failure_code in {
                    "agent_fork_create_intent",
                    "agent_fork_indeterminate",
                }
                if not fork_reconcile_only:
                    product_run.failure_code = "agent_fork_create_intent"
                    product_run.failure_message = (
                        "Official checkpoint fork create intent is durable; a "
                        "replacement worker must reconcile metadata before any "
                        "second create."
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
            if (
                command.command_type == "cancel_task"
                and remote_handle is None
                and product_run is not None
                and product_run.resume_of_run_id is not None
                and thread.official_thread_id
            ):
                source_run = await session.scalar(
                    select(Run)
                    .where(Run.id == product_run.resume_of_run_id)
                    .with_for_update()
                )
                if (
                    source_run is not None
                    and source_run.official_assistant_id
                    and source_run.official_run_id
                ):
                    remote_handle = RemoteRunHandle(
                        assistant_id=source_run.official_assistant_id,
                        thread_id=thread.official_thread_id,
                        run_id=source_run.official_run_id,
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
            fork_source_handle = None
            if (
                command.command_type == "fork"
                and fork_source_run is not None
                and fork_source_run.official_assistant_id
                and thread.official_thread_id
                and fork_source_run.official_run_id
            ):
                fork_source_handle = RemoteRunHandle(
                    assistant_id=fork_source_run.official_assistant_id,
                    thread_id=thread.official_thread_id,
                    run_id=fork_source_run.official_run_id,
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
                fork_source_handle=fork_source_handle,
                fork_payload=fork_payload,
                review_policy=cast(ReviewPolicy, row[5]),
                observed_terminal_status=(
                    cast(
                        ObservedTerminalStatus | None,
                        product_run.observed_terminal_status,
                    )
                    if product_run is not None
                    else None
                ),
                resume_reconcile_only=resume_reconcile_only,
                fork_reconcile_only=fork_reconcile_only,
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
        if lease.command_type == "fork" and lease.fork_payload is None:
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
                    if lease.resume_reconcile_only:
                        handle = await self._runner.find(
                            actor=lease.actor,
                            task_id=str(lease.task_id),
                            product_thread_id=lease.resume_handle.thread_id,
                            product_run_id=str(lease.product_run_id),
                        )
                        if handle is None:
                            raise RemoteResumeIndeterminateError(
                                "Durable resume create intent has no visible official "
                                "Run; refusing a duplicate create"
                            )
                    else:
                        handle = await self._resume_with_heartbeat(
                            lease,
                            actor=lease.actor,
                            handle=lease.resume_handle,
                            task_id=str(lease.task_id),
                            product_run_id=str(lease.product_run_id),
                            responses={
                                member.interrupt_id: member.response.model_dump(
                                    mode="json",
                                    exclude_none=True,
                                )
                                for member in lease.respond_payload.responses
                            },
                            checkpoint=RemoteCheckpoint(
                                thread_id=(
                                    lease.respond_payload.root_checkpoint.thread_id
                                ),
                                checkpoint_ns=(
                                    lease.respond_payload.root_checkpoint.checkpoint_ns
                                ),
                                checkpoint_id=(
                                    lease.respond_payload.root_checkpoint.checkpoint_id
                                ),
                                checkpoint_map=(
                                    lease.respond_payload.root_checkpoint.checkpoint_map
                                ),
                            ),
                        )
                elif lease.command_type == "fork":
                    if lease.fork_source_handle is None or lease.fork_payload is None:
                        raise RuntimeError(
                            "Fork command has no registered source Run lineage"
                        )
                    source_handle = lease.fork_source_handle
                    authorize = getattr(self._runner, "authorize", None)
                    if authorize is not None:
                        source_handle = authorize(source_handle, lease.actor)
                    if lease.fork_reconcile_only:
                        handle = await self._runner.find(
                            actor=lease.actor,
                            task_id=str(lease.task_id),
                            product_thread_id=source_handle.thread_id,
                            product_run_id=str(lease.product_run_id),
                        )
                        if handle is None:
                            raise RemoteForkIndeterminateError(
                                "Durable checkpoint fork create intent has no visible "
                                "official Run; refusing a duplicate create"
                            )
                    else:
                        handle = await self._fork_with_heartbeat(
                            lease,
                            actor=lease.actor,
                            handle=source_handle,
                            task_id=str(lease.task_id),
                            product_run_id=str(lease.product_run_id),
                            checkpoint_id=lease.fork_payload.checkpoint_id,
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
                    interrupt_set = await self._runner.get_interrupts(handle)
            except Exception as exc:
                return await self._schedule_interrupt_projection_retry(lease, exc)
            return await self._mark_waiting_human(lease, interrupt_set)
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
                raise RuntimeError(
                    "Official Run terminal status changed after observation"
                )
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
                select(Thread)
                .where(Thread.id == lease.product_thread_id)
                .with_for_update()
            )
            if (
                task is None
                or not _task_accepts_active_run(task, lease)
                or thread is None
                or product_run is None
            ):
                return "lost"
            thread.official_thread_id = handle.thread_id
            product_run.official_assistant_id = handle.assistant_id
            product_run.official_run_id = handle.run_id
            product_run.last_heartbeat_at = now
            product_run.failure_code = None
            product_run.failure_message = None
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
                select(Run).where(Run.id == lease.product_run_id).with_for_update()
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

    async def _close_active_interrupt_lineage(
        self,
        session: AsyncSession,
        lease: CommandLease,
        *,
        pause_status: Literal["resolved", "cancelled"],
        member_status: Literal["resolved", "cancelled"],
    ) -> None:
        if lease.product_run_id is None:
            return
        pauses = list(
            (
                await session.scalars(
                    select(InterruptPause)
                    .where(
                        InterruptPause.task_id == lease.task_id,
                        InterruptPause.status.in_(("pending", "responding")),
                        or_(
                            InterruptPause.run_id == lease.product_run_id,
                            InterruptPause.resume_run_id == lease.product_run_id,
                        ),
                    )
                    .order_by(InterruptPause.id)
                    .with_for_update()
                )
            ).all()
        )
        if not pauses:
            return
        pause_ids = [pause.id for pause in pauses]
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection)
                    .where(
                        InterruptProjection.task_id == lease.task_id,
                        InterruptProjection.pause_id.in_(pause_ids),
                    )
                    .order_by(InterruptProjection.id)
                    .with_for_update()
                )
            ).all()
        )
        members_by_pause: dict[UUID, list[InterruptProjection]] = {
            pause_id: [] for pause_id in pause_ids
        }
        for projection in projections:
            members_by_pause[projection.pause_id].append(projection)
        for pause in pauses:
            members = members_by_pause[pause.id]
            if not members or any(member.status != pause.status for member in members):
                raise RuntimeError("Active interrupt lineage is inconsistent")
            resolved_with_accepted_responses = (
                pause_status == "resolved"
                and pause.status == "responding"
                and all(member.response is not None for member in members)
            )
            effective_pause_status = (
                "resolved" if resolved_with_accepted_responses else pause_status
            )
            effective_member_status = (
                "resolved" if resolved_with_accepted_responses else member_status
            )
            if pause_status == "resolved" and not resolved_with_accepted_responses:
                effective_pause_status = "cancelled"
                effective_member_status = "cancelled"
            pause.status = effective_pause_status
            for member in members:
                member.status = effective_member_status

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
                    "error_type": type(exc).__name__
                    if exc is not None
                    else "RunDiscoveryTimeout",
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
                    select(Run).where(Run.id == lease.product_run_id).with_for_update()
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
            await self._close_active_interrupt_lineage(
                session,
                lease,
                pause_status="cancelled",
                member_status="cancelled",
            )
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
                    select(Run).where(Run.id == lease.product_run_id).with_for_update()
                )

            if product_run is not None:
                if product_run.projection_fence > lease.command_sequence:
                    command.status = "cancelled"
                    command.lease_owner = None
                    command.lease_expires_at = None
                    return False
            await self._close_active_interrupt_lineage(
                session,
                lease,
                pause_status="cancelled",
                member_status="cancelled",
            )
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

    async def _fork_with_heartbeat(
        self,
        lease: CommandLease,
        **kwargs: object,
    ) -> RemoteRunHandle | None:
        fork_task = asyncio.create_task(self._runner.fork(**kwargs))
        interval = max(1.0, self._lease_seconds / 3)
        try:
            async with asyncio.timeout(self._remote_operation_timeout_seconds):
                while True:
                    done, _ = await asyncio.wait({fork_task}, timeout=interval)
                    if fork_task in done:
                        return await fork_task
                    if not await self._renew_lease(lease):
                        return None
        except TimeoutError as exc:
            raise RemoteForkIndeterminateError(
                "Official checkpoint fork exceeded the remote operation deadline; "
                "only metadata reconciliation is allowed"
            ) from exc
        finally:
            if not fork_task.done():
                fork_task.cancel()
                await asyncio.gather(fork_task, return_exceptions=True)

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
        return bool(deadline is not None and self._clock() >= deadline)

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
        interrupt_set: RemoteInterruptSet,
    ) -> bool:
        if lease.product_run_id is None:
            return False
        interrupts = interrupt_set.interrupts
        if not interrupts:
            return False
        if len(interrupts) > 64:
            return await self._finalize(
                lease,
                TerminalGraphOutput(
                    terminal_status="failed",
                    errors=[
                        {
                            "code": "interrupt_member_limit_exceeded",
                            "error_type": "OfficialInterruptSet",
                            "retryable": False,
                        }
                    ],
                ),
            )
        root_checkpoint = interrupt_set.checkpoint
        canonical_member_coordinates = [
            {
                "interrupt_id": item.interrupt_id,
                "namespace": item.namespace,
                "checkpoint_id": item.checkpoint_id,
            }
            for item in sorted(interrupts, key=lambda item: item.interrupt_id)
        ]
        member_set_hash = sha256(
            json.dumps(
                {
                    "root_checkpoint": {
                        "thread_id": root_checkpoint.thread_id,
                        "checkpoint_ns": root_checkpoint.checkpoint_ns,
                        "checkpoint_id": root_checkpoint.checkpoint_id,
                        "checkpoint_map": root_checkpoint.checkpoint_map,
                    },
                    "members": canonical_member_coordinates,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
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
            if (
                task is None
                or not _task_accepts_active_run(task, lease)
                or product_run is None
            ):
                return False
            await self._resolve_responding_interrupt(session, lease, now)
            pause = await session.scalar(
                select(InterruptPause)
                .where(
                    InterruptPause.run_id == product_run.id,
                    InterruptPause.root_checkpoint_ns == root_checkpoint.checkpoint_ns,
                    InterruptPause.root_checkpoint_id == root_checkpoint.checkpoint_id,
                )
                .with_for_update()
            )
            if pause is None:
                latest_pause_version = await session.scalar(
                    select(
                        func.coalesce(func.max(InterruptPause.pause_version), 0)
                    ).where(
                        InterruptPause.task_id == task.id,
                        InterruptPause.tenant_id == task.tenant_id,
                        InterruptPause.workspace_id == task.workspace_id,
                        InterruptPause.owner_user_id == task.owner_user_id,
                    )
                )
                pause = InterruptPause(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    workspace_id=task.workspace_id,
                    owner_user_id=task.owner_user_id,
                    task_id=task.id,
                    run_id=product_run.id,
                    pause_version=int(latest_pause_version or 0) + 1,
                    root_thread_id=root_checkpoint.thread_id,
                    root_checkpoint_ns=root_checkpoint.checkpoint_ns,
                    root_checkpoint_id=root_checkpoint.checkpoint_id,
                    root_checkpoint_map=root_checkpoint.checkpoint_map,
                    member_set_hash=member_set_hash,
                    status="pending",
                    expires_at=now + timedelta(seconds=self._interrupt_ttl_seconds),
                )
                session.add(pause)
                await session.flush()
            elif (
                pause.member_set_hash != member_set_hash
                or pause.root_thread_id != root_checkpoint.thread_id
                or pause.root_checkpoint_map != root_checkpoint.checkpoint_map
            ):
                raise RuntimeError(
                    "Official Runtime changed an existing interrupt pause member set"
                )
            for remote_interrupt in interrupts:
                public_payload = ArtifactReviewPayload.model_validate(
                    remote_interrupt.value
                ).model_dump(mode="json")
                projection = await session.scalar(
                    select(InterruptProjection)
                    .where(
                        InterruptProjection.tenant_id == task.tenant_id,
                        InterruptProjection.workspace_id == task.workspace_id,
                        InterruptProjection.owner_user_id == task.owner_user_id,
                        InterruptProjection.task_id == task.id,
                        InterruptProjection.pause_id == pause.id,
                        InterruptProjection.official_interrupt_id
                        == remote_interrupt.interrupt_id,
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
                            pause_id=pause.id,
                            official_interrupt_id=remote_interrupt.interrupt_id,
                            namespace=remote_interrupt.namespace,
                            checkpoint_id=remote_interrupt.checkpoint_id,
                            response_version=1,
                            status="pending",
                            payload=public_payload,
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
                    if (
                        projection.checkpoint_id != remote_interrupt.checkpoint_id
                        or projection.namespace != remote_interrupt.namespace
                    ):
                        raise RuntimeError(
                            "Official Runtime changed an existing interrupt member"
                        )
                    projection.namespace = remote_interrupt.namespace
                    projection.payload = public_payload
            persisted_members = list(
                (
                    await session.scalars(
                        select(InterruptProjection)
                        .where(InterruptProjection.pause_id == pause.id)
                        .order_by(InterruptProjection.id)
                    )
                ).all()
            )
            if len(persisted_members) != len(interrupts):
                raise RuntimeError(
                    "Persisted interrupt pause member count is inconsistent"
                )
            task.status = "waiting_human"
            product_run.status = "waiting_human"
            product_run.checkpoint_id = root_checkpoint.checkpoint_id
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
        pause = await session.scalar(
            select(InterruptPause)
            .where(
                InterruptPause.id == payload.pause_id,
                InterruptPause.task_id == lease.task_id,
            )
            .with_for_update()
        )
        if pause is None:
            raise RuntimeError("Respond command interrupt pause is missing")
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection)
                    .where(
                        InterruptProjection.pause_id == pause.id,
                        InterruptProjection.task_id == lease.task_id,
                    )
                    .order_by(InterruptProjection.id)
                    .with_for_update()
                )
            ).all()
        )
        expected_projection_ids = {member.projection_id for member in payload.responses}
        if {projection.id for projection in projections} != expected_projection_ids:
            raise RuntimeError("Respond command interrupt member set is inconsistent")
        if pause.status == "responding":
            pause.status = "resolved"
            for projection in projections:
                if projection.status != "responding":
                    raise RuntimeError(
                        "Respond command interrupt member state is inconsistent"
                    )
                projection.status = "resolved"
                projection.responded_at = projection.responded_at or now

    async def _record_remote_error(self, lease: CommandLease, exc: Exception) -> None:
        if lease.product_run_id is None:
            return
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            command = await self._locked_command(
                session, lease, now, allow_expired=True
            )
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
            if lease.command_type == "respond" and lease.respond_payload is not None:
                task = await session.scalar(
                    select(Task).where(Task.id == lease.task_id).with_for_update()
                )
                pause = await session.scalar(
                    select(InterruptPause)
                    .where(
                        InterruptPause.id == lease.respond_payload.pause_id,
                        InterruptPause.task_id == lease.task_id,
                    )
                    .with_for_update()
                )
                if task is None or pause is None:
                    raise RuntimeError(
                        "Failed resume command has no interrupt pause authority"
                    )
                projections = list(
                    (
                        await session.scalars(
                            select(InterruptProjection)
                            .where(
                                InterruptProjection.pause_id == pause.id,
                                InterruptProjection.task_id == lease.task_id,
                            )
                            .order_by(InterruptProjection.id)
                            .with_for_update()
                        )
                    ).all()
                )
                expected_projection_ids = {
                    member.projection_id for member in lease.respond_payload.responses
                }
                expected_pause_status = (
                    "expired" if lease.respond_payload.expired else "responding"
                )
                if (
                    pause.status != expected_pause_status
                    or {projection.id for projection in projections}
                    != expected_projection_ids
                    or any(
                        projection.status != expected_pause_status
                        for projection in projections
                    )
                ):
                    raise RuntimeError(
                        "Failed resume command interrupt lineage is inconsistent"
                    )
                if (
                    isinstance(exc, RemoteResumeIndeterminateError)
                    and product_run.reconciliation_deadline_at is not None
                    and product_run.reconciliation_deadline_at > now
                ):
                    task.status = (
                        "running" if lease.respond_payload.expired else "waiting_human"
                    )
                    product_run.status = "queued"
                    product_run.failure_code = "agent_resume_indeterminate"
                    product_run.failure_message = (
                        "Official resume create may have succeeded; only metadata "
                        "reconciliation is allowed until the recovery deadline."
                    )
                    command.status = "pending"
                    command.lease_owner = None
                    command.lease_expires_at = now + timedelta(
                        seconds=self._reconciliation_interval_seconds
                    )
                    return
                attempt_limit = (
                    self._max_cancel_attempts
                    if lease.respond_payload.expired
                    else self._max_attempts
                )
                if command.attempt < attempt_limit:
                    # The accepted response map is immutable. Automatic expiry gets
                    # the larger cancellation retry budget, but must still converge.
                    task.status = (
                        "running" if lease.respond_payload.expired else "waiting_human"
                    )
                    product_run.status = "queued"
                    product_run.failure_code = "agent_server_unavailable"
                    product_run.failure_message = (
                        "Agent Server is temporarily unavailable; the accepted "
                        "review batch is still awaiting resume."
                    )
                    command.status = "pending"
                    command.lease_owner = None
                    command.lease_expires_at = now + timedelta(
                        seconds=self._reconciliation_interval_seconds
                    )
                    return

                output = {
                    "terminal_status": "failed",
                    "errors": [
                        {
                            "code": "agent_resume_failed",
                            "error_type": type(exc).__name__,
                            "retryable": False,
                            "attempt": max(1, min(command.attempt, 100)),
                        }
                    ],
                }
                output_hash = sha256(
                    json.dumps(
                        output,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                pause.status = "resume_failed"
                product_run.status = "failed"
                product_run.output_payload = output
                product_run.failure_code = "agent_resume_failed"
                product_run.failure_message = (
                    "Official Run resume failed after the configured attempt limit."
                )
                product_run.finished_at = now
                product_run.projection_fence = lease.command_sequence
                product_run.terminal_output_hash = output_hash
                task.status = "failed"
                task.completed_at = now
                command.status = "failed"
                command.lease_owner = None
                command.lease_expires_at = None
                return
            if lease.command_type == "fork" and lease.fork_payload is not None:
                task = await session.scalar(
                    select(Task).where(Task.id == lease.task_id).with_for_update()
                )
                if task is None:
                    raise RuntimeError("Failed fork command has no Task authority")
                if (
                    isinstance(exc, RemoteForkIndeterminateError)
                    and product_run.reconciliation_deadline_at is not None
                    and product_run.reconciliation_deadline_at > now
                ):
                    task.status = "queued"
                    product_run.status = "queued"
                    product_run.failure_code = "agent_fork_indeterminate"
                    product_run.failure_message = (
                        "Official checkpoint fork may have succeeded; only metadata "
                        "reconciliation is allowed until the recovery deadline."
                    )
                    command.status = "pending"
                    command.lease_owner = None
                    command.lease_expires_at = now + timedelta(
                        seconds=self._reconciliation_interval_seconds
                    )
                    return
                if command.attempt < self._max_attempts:
                    task.status = "queued"
                    product_run.status = "queued"
                    product_run.failure_code = "agent_server_unavailable"
                    product_run.failure_message = (
                        "Agent Server is temporarily unavailable; the admitted "
                        "checkpoint fork is awaiting dispatch."
                    )
                    command.status = "pending"
                    command.lease_owner = None
                    command.lease_expires_at = now + timedelta(
                        seconds=self._reconciliation_interval_seconds
                    )
                    return

                output = {
                    "terminal_status": "failed",
                    "errors": [
                        {
                            "code": "agent_fork_failed",
                            "error_type": type(exc).__name__,
                            "retryable": False,
                            "attempt": max(1, min(command.attempt, 100)),
                        }
                    ],
                }
                output_hash = sha256(
                    json.dumps(
                        output,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                product_run.status = "failed"
                product_run.output_payload = output
                product_run.failure_code = "agent_fork_failed"
                product_run.failure_message = "Official checkpoint fork failed after the configured attempt limit."
                product_run.finished_at = now
                product_run.projection_fence = lease.command_sequence
                product_run.terminal_output_hash = output_hash
                task.status = "failed"
                task.completed_at = now
                command.status = "failed"
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
            command = await self._locked_command(
                session, lease, now, allow_expired=True
            )
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
            task_accepts_projection = _task_accepts_active_run(task, lease) or (
                lease.command_type == "cancel_task" and task.status == "waiting_human"
            )
            if not task_accepts_projection:
                command.status = "cancelled"
                command.lease_owner = None
                command.lease_expires_at = None
                return False
            if lease.command_type == "cancel_task":
                await self._close_active_interrupt_lineage(
                    session,
                    lease,
                    pause_status="resolved",
                    member_status="resolved",
                )
            else:
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
            if (
                terminal.terminal_status == "succeeded"
                and terminal.artifact is not None
            ):
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
