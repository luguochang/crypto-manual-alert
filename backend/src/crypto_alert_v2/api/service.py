from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from crypto_alert_v2.api.schemas import AnalysisSubmission, InterruptResponseSubmission
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.graph.request import ReviewResponse
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    InterruptProjection,
    Membership,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    Workspace,
)
from crypto_alert_v2.persistence.repositories import (
    ResolvedActor,
    TaskRunProjectionRepository,
    resolve_actor,
)
from crypto_alert_v2.projections.task import project_task_run_sources


class IdempotencyConflictError(RuntimeError):
    pass


class TaskNotCancellableError(RuntimeError):
    pass


class InterruptResponseConflictError(RuntimeError):
    pass


_MAIN_ACTIONS = frozenset(
    {
        "open_long",
        "open_short",
        "hold_long",
        "hold_short",
        "close_long",
        "close_short",
        "flip_long_to_short",
        "flip_short_to_long",
        "trigger_long",
        "trigger_short",
        "no_trade",
    }
)


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _require_analysis_write(actor: ActorContext, resolved: ResolvedActor) -> None:
    if (
        "analysis:write" not in actor.permissions
        or "analysis:write" not in resolved.permissions
    ):
        raise PermissionError("analysis:write permission is required")


def _require_analysis_read(actor: ActorContext, resolved: ResolvedActor) -> None:
    if (
        "analysis:read" not in actor.permissions
        or "analysis:read" not in resolved.permissions
    ):
        raise PermissionError("analysis:read permission is required")


def _run_main_action(run: Run) -> str | None:
    output = run.output_payload
    if not isinstance(output, dict):
        return None
    artifact = output.get("artifact")
    if not isinstance(artifact, dict):
        return None
    analysis = artifact.get("analysis")
    if not isinstance(analysis, dict):
        return None
    action = analysis.get("main_action")
    return action if isinstance(action, str) and action in _MAIN_ACTIONS else None


def _require_same_payload(task: Task, payload_hash: str) -> None:
    if task.request_payload_hash != payload_hash:
        raise IdempotencyConflictError(
            "Idempotency-Key was already used with a different analysis payload."
        )


def _admission_task_view(task: Task, payload_hash: str) -> dict[str, Any]:
    _require_same_payload(task, payload_hash)
    request_payload = task.request_payload
    return {
        "task_id": str(task.id),
        "status": task.status,
        "symbol": request_payload["symbol"],
        "horizon": request_payload["horizon"],
        "query_text": request_payload.get("query_text"),
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "market_snapshot": None,
        "web_evidence": [],
        "artifact": None,
        "errors": [],
        "agent_stream": None,
    }


async def _find_admission_task(
    session: AsyncSession,
    resolved: ResolvedActor,
    idempotency_key: str,
) -> Task | None:
    return await session.scalar(
        select(Task).where(
            Task.tenant_id == resolved.tenant_id,
            Task.workspace_id == resolved.workspace_id,
            Task.owner_user_id == resolved.user_id,
            Task.idempotency_key == idempotency_key,
        )
    )


def _public_error(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    errors = payload.get("errors") or []
    if not errors:
        if payload.get("terminal_status") != "blocked":
            return []
        artifact = payload.get("artifact") or {}
        risk = artifact.get("risk_verdict") or {}
        evidence = artifact.get("evidence_verdict") or {}
        reasons = list(risk.get("blocked_reasons") or [])
        reasons.extend(evidence.get("missing_required") or [])
        suffix = f" 原因：{'；'.join(str(item) for item in reasons)}" if reasons else ""
        return [
            {
                "code": "risk_gate_blocked",
                "message": f"证据或风险门禁阻止了本次分析。{suffix}".strip(),
                "retryable": False,
            }
        ]
    first = errors[0] if isinstance(errors[0], dict) else {}
    code = str(first.get("code") or "analysis_failed")
    messages = {
        "provider_unavailable": "无法连接市场数据提供方，当前未生成分析结果。",
        "research_unavailable": "检索服务没有返回可验证来源，当前未生成分析结果。",
        "model_unavailable": "分析模型暂时不可用，当前未生成分析结果。",
        "agent_cancel_failed": "无法确认官方执行已停止，请联系运维检查该运行。",
        "orphan_cancel_unconfirmed": "任务超时后无法确认官方执行已停止，请联系运维处理。",
        "agent_run_timeout": "官方执行超过允许时限，当前未生成分析结果。",
        "terminal_projection_unavailable": "官方执行已结束，但暂时无法读取最终结果。",
        "terminal_projection_conflict": "终态投影发生一致性冲突，当前结果未被采用。",
    }
    diagnostics: dict[str, Any] = {}
    provider = first.get("provider")
    error_type = first.get("error_type")
    attempt = first.get("attempt")
    if _safe_diagnostic_identifier(provider, max_length=64):
        diagnostics["provider"] = provider
    if _safe_diagnostic_identifier(error_type, max_length=128):
        diagnostics["error_type"] = error_type
    if isinstance(attempt, int) and not isinstance(attempt, bool) and 1 <= attempt <= 100:
        diagnostics["attempt"] = attempt
    return [
        {
            "code": code,
            "message": messages.get(code, "分析未能完成，请检查错误码后重试。"),
            "retryable": bool(first.get("retryable", code != "analysis_failed")),
            **diagnostics,
        }
    ]


def _safe_diagnostic_identifier(value: object, *, max_length: int) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= max_length:
        return False
    return all(character.isascii() and (character.isalnum() or character in "._-") for character in value)


async def _task_view(
    session: AsyncSession,
    resolved: ResolvedActor,
    task: Task,
    *,
    selected_run_id: UUID | None = None,
) -> dict[str, Any]:
    run_filters = [
        Run.task_id == task.id,
        Run.tenant_id == resolved.tenant_id,
        Run.workspace_id == resolved.workspace_id,
        Run.owner_user_id == resolved.user_id,
    ]
    if selected_run_id is not None:
        run_filters.append(Run.id == selected_run_id)
    latest_run_subquery = (
        select(Run)
        .where(*run_filters)
        .order_by(Run.attempt.desc())
        .limit(1)
        .subquery()
    )
    latest_run_alias = aliased(Run, latest_run_subquery)
    run_thread = (
        await session.execute(
            select(latest_run_alias, Thread.official_thread_id)
            .join(
                Thread,
                and_(
                    latest_run_alias.thread_id == Thread.id,
                    latest_run_alias.tenant_id == Thread.tenant_id,
                    latest_run_alias.workspace_id == Thread.workspace_id,
                    latest_run_alias.owner_user_id == Thread.owner_user_id,
                ),
            )
            .where(
                Thread.id == task.thread_id,
                Thread.tenant_id == resolved.tenant_id,
                Thread.workspace_id == resolved.workspace_id,
                Thread.owner_user_id == resolved.user_id,
            )
        )
    ).one_or_none()
    latest_run = run_thread[0] if run_thread is not None else None
    official_thread_id = run_thread[1] if run_thread is not None else None
    effective_status = latest_run.status if latest_run is not None else task.status
    if (
        task.status == "waiting_human"
        and latest_run is not None
        and latest_run.status == "queued"
        and latest_run.resume_of_run_id is not None
    ):
        effective_status = task.status
    cancel_requested_at = await session.scalar(
        select(TaskCommand.created_at)
        .where(
            TaskCommand.task_id == task.id,
            TaskCommand.tenant_id == resolved.tenant_id,
            TaskCommand.workspace_id == resolved.workspace_id,
            TaskCommand.actor_user_id == resolved.user_id,
            TaskCommand.command_type == "cancel_task",
            TaskCommand.status.in_(("pending", "dispatching")),
        )
        .order_by(TaskCommand.sequence.desc())
        .limit(1)
    )
    market_snapshot = None
    web_evidence = []
    if latest_run is not None:
        records = await TaskRunProjectionRepository(session, resolved).get_sources(
            task_id=task.id,
            run_id=latest_run.id,
        )
        run_sources = project_task_run_sources(records)
        market_snapshot = run_sources.market_snapshot
        web_evidence = run_sources.web_evidence
    artifact_statement = (
        select(ArtifactVersion.content)
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(
            Artifact.task_id == task.id,
            Artifact.tenant_id == resolved.tenant_id,
            Artifact.workspace_id == resolved.workspace_id,
            Artifact.owner_user_id == resolved.user_id,
        )
        .order_by(ArtifactVersion.version_number.desc())
        .limit(1)
    )
    if latest_run is not None:
        artifact_statement = artifact_statement.where(
            ArtifactVersion.run_id == latest_run.id
        )
    artifact_content = await session.scalar(artifact_statement)
    if (
        artifact_content is None
        and latest_run is not None
        and latest_run.status == "blocked"
        and latest_run.output_payload
    ):
        artifact_content = latest_run.output_payload.get("artifact")
    agent_stream = None
    if (
        latest_run is not None
        and latest_run.official_assistant_id
        and official_thread_id
        and latest_run.official_run_id
    ):
        agent_stream = {
            "protocol": "langgraph-v2",
            "assistant_id": latest_run.official_assistant_id,
            "thread_id": official_thread_id,
            "run_id": latest_run.official_run_id,
        }
    pending_interrupts: list[dict[str, Any]] = []
    projections = (
        await session.scalars(
            select(InterruptProjection)
            .where(
                InterruptProjection.task_id == task.id,
                InterruptProjection.tenant_id == resolved.tenant_id,
                InterruptProjection.workspace_id == resolved.workspace_id,
                InterruptProjection.owner_user_id == resolved.user_id,
                InterruptProjection.status.in_(("pending", "responding")),
            )
            .order_by(
                InterruptProjection.created_at,
                InterruptProjection.id,
            )
        )
    ).all()
    pending_interrupts = [
        {
            "task_id": str(projection.task_id),
            "run_id": str(projection.run_id),
            "interrupt_id": projection.official_interrupt_id,
            "namespace": projection.namespace,
            "checkpoint_id": projection.checkpoint_id,
            "response_version": projection.response_version,
            "status": projection.status,
            "payload": projection.payload,
            "response": projection.response,
            "expires_at": projection.expires_at,
            "responded_at": projection.responded_at,
        }
        for projection in projections
    ]
    request_payload = task.request_payload
    return {
        "task_id": str(task.id),
        "status": effective_status,
        "symbol": request_payload["symbol"],
        "horizon": request_payload["horizon"],
        "query_text": request_payload.get("query_text"),
        "created_at": task.created_at,
        "completed_at": (
            latest_run.finished_at if latest_run is not None else task.completed_at
        ),
        "cancel_requested_at": cancel_requested_at,
        "market_snapshot": market_snapshot,
        "web_evidence": web_evidence,
        "artifact": artifact_content,
        "errors": _public_error(
            latest_run.output_payload if latest_run is not None else None
        ),
        "agent_stream": agent_stream,
        "pending_interrupts": pending_interrupts,
    }


class ProductAnalysisService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def bootstrap_actor(self, actor: ActorContext) -> None:
        await self.provision_actor(
            actor,
            tenant_name="Development Tenant",
            workspace_name="Development Workspace",
            user_display_name="Development User",
        )

    async def provision_actor(
        self,
        actor: ActorContext,
        *,
        tenant_name: str,
        workspace_name: str,
        user_display_name: str,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            tenant = await session.scalar(
                select(Tenant).where(Tenant.external_id == actor.tenant_id)
            )
            if tenant is None:
                tenant = Tenant(
                    id=uuid4(), external_id=actor.tenant_id, name=tenant_name
                )
                session.add(tenant)
                await session.flush()
            else:
                tenant.name = tenant_name

            user = await session.scalar(
                select(User).where(
                    User.tenant_id == tenant.id,
                    User.external_subject == actor.user_id,
                )
            )
            if user is None:
                user = User(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    external_subject=actor.user_id,
                    display_name=user_display_name,
                )
                session.add(user)
            else:
                user.display_name = user_display_name

            workspace = await session.scalar(
                select(Workspace).where(
                    Workspace.tenant_id == tenant.id,
                    Workspace.external_id == actor.workspace_id,
                )
            )
            if workspace is None:
                workspace = Workspace(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    external_id=actor.workspace_id,
                    name=workspace_name,
                )
                session.add(workspace)
            else:
                workspace.name = workspace_name
            await session.flush()

            membership = await session.scalar(
                select(Membership).where(
                    Membership.tenant_id == tenant.id,
                    Membership.workspace_id == workspace.id,
                    Membership.user_id == user.id,
                )
            )
            if membership is None:
                session.add(
                    Membership(
                        id=uuid4(),
                        tenant_id=tenant.id,
                        workspace_id=workspace.id,
                        user_id=user.id,
                        role=actor.roles[0] if actor.roles else "member",
                        permissions=list(actor.permissions),
                        is_active=True,
                    )
                )
            else:
                membership.role = actor.roles[0] if actor.roles else "member"
                membership.permissions = list(actor.permissions)
                membership.is_active = True

    async def create_analysis(
        self,
        actor: ActorContext,
        submission: AnalysisSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request_payload = submission.model_dump(mode="json")
        payload_hash = _payload_hash(request_payload)
        try:
            async with self._session_factory() as session, session.begin():
                resolved = await resolve_actor(session, actor)
                _require_analysis_write(actor, resolved)
                existing = await _find_admission_task(
                    session, resolved, idempotency_key
                )
                if existing is not None:
                    _require_same_payload(existing, payload_hash)
                    return await _task_view(session, resolved, existing)

                thread = Thread(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    owner_user_id=resolved.user_id,
                    title=f"{submission.symbol} {submission.horizon} analysis",
                    context={},
                )
                session.add(thread)
                await session.flush()
                task = Task(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    owner_user_id=resolved.user_id,
                    thread_id=thread.id,
                    task_type="market_analysis",
                    status="queued",
                    idempotency_key=idempotency_key,
                    request_payload_hash=payload_hash,
                    request_payload=request_payload,
                )
                session.add(task)
                await session.flush()
                command = TaskCommand(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    actor_user_id=resolved.user_id,
                    task_id=task.id,
                    thread_id=thread.id,
                    command_type="submit",
                    payload=request_payload,
                    payload_hash=payload_hash,
                    sequence=1,
                    status="pending",
                    attempt=0,
                    idempotency_key=f"submit:{task.id}",
                )
                session.add(command)
                await session.flush()
                return _admission_task_view(task, payload_hash)
        except IntegrityError as error:
            async with self._session_factory() as session:
                resolved = await resolve_actor(session, actor)
                _require_analysis_write(actor, resolved)
                existing = await _find_admission_task(
                    session, resolved, idempotency_key
                )
                if existing is None:
                    raise error
                _require_same_payload(existing, payload_hash)
                return await _task_view(session, resolved, existing)

    async def get_task(
        self,
        actor: ActorContext,
        task_id: str,
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(actor, resolved)
            task = await session.scalar(
                select(Task).where(
                    Task.id == task_uuid,
                    Task.tenant_id == resolved.tenant_id,
                    Task.workspace_id == resolved.workspace_id,
                    Task.owner_user_id == resolved.user_id,
                )
            )
            if task is None:
                return None
            return await _task_view(
                session,
                resolved,
                task,
                selected_run_id=run_id,
            )

    async def cancel_task(
        self,
        actor: ActorContext,
        task_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        command_idempotency_key = (
            f"cancel:{task_uuid}:{sha256(idempotency_key.encode()).hexdigest()}"
        )
        payload = {"task_id": str(task_uuid)}
        payload_hash = _payload_hash(payload)
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(actor, resolved)
            task = await session.scalar(
                select(Task)
                .where(
                    Task.id == task_uuid,
                    Task.tenant_id == resolved.tenant_id,
                    Task.workspace_id == resolved.workspace_id,
                    Task.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if task is None:
                return None
            if task.status == "cancelled":
                return await _task_view(session, resolved, task)
            if task.status in {"succeeded", "blocked", "failed"}:
                raise TaskNotCancellableError(
                    "Only queued, running, or waiting tasks can be cancelled."
                )

            commands = list(
                (
                    await session.scalars(
                        select(TaskCommand)
                        .where(
                            TaskCommand.task_id == task.id,
                            TaskCommand.tenant_id == resolved.tenant_id,
                            TaskCommand.workspace_id == resolved.workspace_id,
                        )
                        .order_by(TaskCommand.sequence)
                        .with_for_update()
                    )
                ).all()
            )
            if any(
                command.idempotency_key == command_idempotency_key
                for command in commands
            ):
                return await _task_view(session, resolved, task)
            if any(
                command.command_type == "cancel_task"
                and command.status in {"pending", "dispatching"}
                for command in commands
            ):
                return await _task_view(session, resolved, task)

            for command in commands:
                if command.status == "pending" or (
                    command.status == "dispatching"
                    and not (
                        command.command_type == "submit"
                        and command.official_run_id is None
                    )
                ):
                    command.status = "cancelled"
                    command.lease_owner = None
                    command.lease_expires_at = None

            latest_run = await session.scalar(
                select(Run)
                .where(
                    Run.task_id == task.id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
                .order_by(Run.attempt.desc())
                .limit(1)
                .with_for_update()
            )
            if latest_run is not None:
                latest_run.cancel_requested_at = datetime.now(UTC)

            session.add(
                TaskCommand(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    actor_user_id=resolved.user_id,
                    task_id=task.id,
                    thread_id=task.thread_id,
                    command_type="cancel_task",
                    payload=payload,
                    payload_hash=payload_hash,
                    sequence=max(
                        (command.sequence for command in commands),
                        default=0,
                    )
                    + 1,
                    status="pending",
                    attempt=0,
                    idempotency_key=command_idempotency_key,
                )
            )
            await session.flush()
            return await _task_view(session, resolved, task)

    async def respond_interrupt(
        self,
        actor: ActorContext,
        task_id: str,
        interrupt_id: str,
        submission: InterruptResponseSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None

        review_response = ReviewResponse.model_validate(
            submission.model_dump(exclude={"response_version"})
        )
        response = review_response.model_dump(mode="json", exclude_none=True)
        request_identity = {
            "task_id": str(task_uuid),
            "interrupt_id": interrupt_id,
            "response_version": submission.response_version,
            "response": response,
        }
        request_hash = _payload_hash(request_identity)
        command_idempotency_key = (
            "respond:"
            + sha256(
                f"{task_uuid}:{interrupt_id}:{idempotency_key}".encode()
            ).hexdigest()
        )

        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(actor, resolved)
            task = await session.scalar(
                select(Task)
                .where(
                    Task.id == task_uuid,
                    Task.tenant_id == resolved.tenant_id,
                    Task.workspace_id == resolved.workspace_id,
                    Task.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if task is None:
                return None

            commands = list(
                (
                    await session.scalars(
                        select(TaskCommand)
                        .where(
                            TaskCommand.task_id == task.id,
                            TaskCommand.tenant_id == resolved.tenant_id,
                            TaskCommand.workspace_id == resolved.workspace_id,
                        )
                        .order_by(TaskCommand.sequence)
                        .with_for_update()
                    )
                ).all()
            )
            replay = next(
                (
                    command
                    for command in commands
                    if command.idempotency_key == command_idempotency_key
                ),
                None,
            )
            if replay is not None:
                if replay.payload_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency-Key was already used with a different "
                        "interrupt response payload."
                    )
                return await _task_view(session, resolved, task)

            waiting_run = await session.scalar(
                select(Run)
                .where(
                    Run.task_id == task.id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                    Run.status == "waiting_human",
                )
                .order_by(Run.attempt.desc())
                .limit(1)
                .with_for_update()
            )
            if waiting_run is None or task.status != "waiting_human":
                raise InterruptResponseConflictError(
                    "Task is not waiting for this interrupt."
                )

            projections = list(
                (
                    await session.scalars(
                        select(InterruptProjection)
                        .where(
                            InterruptProjection.task_id == task.id,
                            InterruptProjection.tenant_id == resolved.tenant_id,
                            InterruptProjection.workspace_id == resolved.workspace_id,
                            InterruptProjection.owner_user_id == resolved.user_id,
                            InterruptProjection.official_interrupt_id == interrupt_id,
                        )
                        .order_by(
                            InterruptProjection.response_version.desc(),
                            InterruptProjection.created_at.desc(),
                            InterruptProjection.id.desc(),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            if not projections:
                return None
            projection = next(
                (
                    candidate
                    for candidate in projections
                    if candidate.run_id == waiting_run.id
                ),
                None,
            )
            if projection is None:
                raise InterruptResponseConflictError(
                    "Interrupt is stale for the latest waiting run."
                )
            if projection.response_version != submission.response_version:
                raise InterruptResponseConflictError(
                    "Interrupt response_version is stale."
                )
            now = datetime.now(UTC)
            if projection.status == "expired" or (
                projection.status == "pending"
                and projection.expires_at is not None
                and projection.expires_at <= now
            ):
                raise InterruptResponseConflictError(
                    "Interrupt response window has expired."
                )
            if projection.status != "pending":
                raise InterruptResponseConflictError(
                    "Interrupt has already been responded to."
                )

            resume_run = Run(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                attempt=waiting_run.attempt + 1,
                status="queued",
                input_payload=waiting_run.input_payload,
                resume_of_run_id=waiting_run.id,
            )
            command_payload = {
                "projection_id": str(projection.id),
                "interrupt_id": projection.official_interrupt_id,
                "checkpoint_id": projection.checkpoint_id,
                "response_version": projection.response_version,
                "response": response,
                "expired": False,
            }
            projection.status = "responding"
            projection.response = response
            projection.responded_at = now
            session.add(resume_run)
            session.add(
                TaskCommand(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    actor_user_id=resolved.user_id,
                    task_id=task.id,
                    thread_id=task.thread_id,
                    command_type="respond",
                    payload=command_payload,
                    payload_hash=request_hash,
                    sequence=max(
                        (command.sequence for command in commands),
                        default=0,
                    )
                    + 1,
                    status="pending",
                    attempt=0,
                    idempotency_key=command_idempotency_key,
                )
            )
            await session.flush()
            return await _task_view(session, resolved, task)

    async def list_runs(
        self,
        actor: ActorContext,
        *,
        limit: int,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(actor, resolved)
            rows = (
                await session.execute(
                    select(Run, Task)
                    .join(
                        Task,
                        and_(
                            Run.task_id == Task.id,
                            Run.tenant_id == Task.tenant_id,
                            Run.workspace_id == Task.workspace_id,
                            Run.owner_user_id == Task.owner_user_id,
                        ),
                    )
                    .where(
                        Run.tenant_id == resolved.tenant_id,
                        Run.workspace_id == resolved.workspace_id,
                        Run.owner_user_id == resolved.user_id,
                        Task.tenant_id == resolved.tenant_id,
                        Task.workspace_id == resolved.workspace_id,
                        Task.owner_user_id == resolved.user_id,
                    )
                    .order_by(Run.created_at.desc(), Run.id.desc())
                    .limit(limit)
                )
            ).all()
            return {
                "items": [
                    {
                        "run_id": str(run.id),
                        "task_id": str(task.id),
                        "attempt": run.attempt,
                        "status": run.status,
                        "symbol": task.request_payload["symbol"],
                        "horizon": task.request_payload["horizon"],
                        "created_at": run.created_at,
                        "finished_at": run.finished_at,
                        "main_action": _run_main_action(run),
                    }
                    for run, task in rows
                ],
                "limit": limit,
            }
