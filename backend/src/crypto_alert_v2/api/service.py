from base64 import b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import hmac
import json
from secrets import token_bytes
from typing import Any, Callable
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    ForkSubmission,
    InboxQueryStatus,
    InterruptResponseSubmission,
    InterruptResponsesSubmission,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.graph.request import ArtifactReviewPayload, ReviewResponse
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    InterruptPause,
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


class ForkConflictError(RuntimeError):
    pass


class InterruptResponseConflictError(RuntimeError):
    pass


class InterruptBatchRequiredError(InterruptResponseConflictError):
    pass


class InvalidInboxCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _InboxCursor:
    created_at: datetime
    pause_id: UUID
    scope: str
    status: str


_INBOX_CURSOR_VERSION = 3
_INBOX_CURSOR_MAX_LENGTH = 2048
_INBOX_CURSOR_NONCE_LENGTH = 12
_INBOX_CURSOR_AAD = b"crypto-alert-v2:product-inbox-cursor:v2"
_INBOX_QUERY_STATUSES = frozenset(
    {
        "active",
        "pending",
        "responding",
        "resolved",
        "expired",
        "resume_failed",
        "all",
    }
)
_INBOX_STATUS_FILTERS: dict[str, tuple[str, ...]] = {
    "active": ("pending", "responding"),
    "pending": ("pending",),
    "responding": ("responding",),
    "resolved": ("resolved",),
    "expired": ("expired",),
    "resume_failed": ("resume_failed",),
}


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


def _encode_inbox_cursor(cursor: _InboxCursor, *, key: bytes) -> str:
    created_at = cursor.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    payload = {
        "created_at": created_at,
        "id": str(cursor.pause_id),
        "scope": cursor.scope,
        "status": cursor.status,
        "v": _INBOX_CURSOR_VERSION,
    }
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    nonce = token_bytes(_INBOX_CURSOR_NONCE_LENGTH)
    encrypted = AESGCM(key).encrypt(nonce, plaintext, _INBOX_CURSOR_AAD)
    return urlsafe_b64encode(nonce + encrypted).decode("ascii").rstrip("=")


def _parse_inbox_cursor(
    cursor: str,
    *,
    key: bytes,
    scope: str,
    status: str,
) -> _InboxCursor:
    try:
        if (
            not cursor
            or len(cursor) > _INBOX_CURSOR_MAX_LENGTH
            or not cursor.isascii()
            or any(
                not (character.isalnum() or character in "-_")
                for character in cursor
            )
        ):
            raise ValueError
        encoded = cursor.encode("ascii")
        envelope = b64decode(
            encoded + (b"=" * (-len(encoded) % 4)),
            altchars=b"-_",
            validate=True,
        )
        if len(envelope) <= _INBOX_CURSOR_NONCE_LENGTH + 16:
            raise ValueError
        nonce = envelope[:_INBOX_CURSOR_NONCE_LENGTH]
        ciphertext = envelope[_INBOX_CURSOR_NONCE_LENGTH:]
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, _INBOX_CURSOR_AAD)
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {
            "created_at",
            "id",
            "scope",
            "status",
            "v",
        }:
            raise ValueError
        if type(payload["v"]) is not int or payload["v"] != _INBOX_CURSOR_VERSION:
            raise ValueError
        if payload["status"] != status:
            raise ValueError
        if not isinstance(payload["scope"], str) or not hmac.compare_digest(
            payload["scope"], scope
        ):
            raise ValueError
        if not isinstance(payload["created_at"], str) or not isinstance(
            payload["id"], str
        ):
            raise ValueError
        created_at = datetime.fromisoformat(
            payload["created_at"].replace("Z", "+00:00")
        )
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        parsed = _InboxCursor(
            created_at=created_at.astimezone(UTC),
            pause_id=UUID(payload["id"]),
            scope=scope,
            status=status,
        )
        return parsed
    except (
        BinasciiError,
        InvalidTag,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ):
        raise InvalidInboxCursorError("Invalid inbox cursor.") from None


def _inbox_scope(resolved: ResolvedActor) -> str:
    identity = (
        f"{resolved.tenant_id}\0{resolved.workspace_id}\0{resolved.user_id}"
    ).encode("utf-8")
    return sha256(identity).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _require_analysis_write(resolved: ResolvedActor) -> None:
    if "analysis:write" not in resolved.permissions:
        raise PermissionError("analysis:write permission is required")


def _require_analysis_read(resolved: ResolvedActor) -> None:
    if "analysis:read" not in resolved.permissions:
        raise PermissionError("analysis:read permission is required")


async def _cancel_pending_pause_for_fork(
    session: AsyncSession,
    resolved: ResolvedActor,
    task: Task,
) -> None:
    pauses = list(
        (
            await session.scalars(
                select(InterruptPause)
                .where(
                    InterruptPause.task_id == task.id,
                    InterruptPause.tenant_id == resolved.tenant_id,
                    InterruptPause.workspace_id == resolved.workspace_id,
                    InterruptPause.owner_user_id == resolved.user_id,
                    InterruptPause.status.in_(("pending", "responding")),
                )
                .order_by(InterruptPause.pause_version)
                .with_for_update()
            )
        ).all()
    )
    if not pauses:
        return
    if len(pauses) != 1:
        raise RuntimeError("Task has more than one active interrupt pause")
    pause = pauses[0]
    if pause.status == "responding":
        raise ForkConflictError(
            "Task has an accepted review decision that is still resuming."
        )
    projections = list(
        (
            await session.scalars(
                select(InterruptProjection)
                .where(
                    InterruptProjection.pause_id == pause.id,
                    InterruptProjection.task_id == task.id,
                    InterruptProjection.tenant_id == resolved.tenant_id,
                    InterruptProjection.workspace_id == resolved.workspace_id,
                    InterruptProjection.owner_user_id == resolved.user_id,
                )
                .order_by(InterruptProjection.id)
                .with_for_update()
            )
        ).all()
    )
    if not projections or any(item.status != "pending" for item in projections):
        raise RuntimeError("Pending interrupt pause member state is inconsistent")
    paused_run = await session.scalar(
        select(Run)
        .where(
            Run.id == pause.run_id,
            Run.task_id == task.id,
            Run.tenant_id == resolved.tenant_id,
            Run.workspace_id == resolved.workspace_id,
            Run.owner_user_id == resolved.user_id,
        )
        .with_for_update()
    )
    if paused_run is None or paused_run.status != "waiting_human":
        raise RuntimeError("Pending interrupt pause Run state is inconsistent")
    pause.status = "cancelled"
    for projection in projections:
        projection.status = "cancelled"
    paused_run.status = "cancelled"
    paused_run.finished_at = paused_run.finished_at or datetime.now(UTC)


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
        "agent_resume_failed": (
            "人工审核决定已保存，但官方 Agent 未能在恢复期限内继续运行。"
        ),
        "agent_fork_failed": "无法从所选历史节点创建新的分析运行。",
        "interrupt_member_limit_exceeded": (
            "官方执行返回的并行审核项超过产品上限，当前任务已安全终止。"
        ),
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
    active_pauses = list(
        (
            await session.scalars(
                select(InterruptPause)
                .where(
                    InterruptPause.task_id == task.id,
                    InterruptPause.tenant_id == resolved.tenant_id,
                    InterruptPause.workspace_id == resolved.workspace_id,
                    InterruptPause.owner_user_id == resolved.user_id,
                    InterruptPause.status.in_(("pending", "responding")),
                    *(
                        (
                            or_(
                                InterruptPause.run_id == selected_run_id,
                                InterruptPause.resume_run_id == selected_run_id,
                            ),
                        )
                        if selected_run_id is not None
                        else ()
                    ),
                )
                .order_by(
                    InterruptPause.pause_version.desc(),
                    InterruptPause.created_at.desc(),
                    InterruptPause.id.desc(),
                )
            )
        ).all()
    )
    if len(active_pauses) > 1:
        raise RuntimeError("Task has more than one active interrupt pause")
    pending_interrupts = None
    if active_pauses:
        pause = active_pauses[0]
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection)
                    .where(
                        InterruptProjection.pause_id == pause.id,
                        InterruptProjection.task_id == task.id,
                        InterruptProjection.tenant_id == resolved.tenant_id,
                        InterruptProjection.workspace_id == resolved.workspace_id,
                        InterruptProjection.owner_user_id == resolved.user_id,
                    )
                    .order_by(
                        InterruptProjection.created_at,
                        InterruptProjection.id,
                    )
                )
            ).all()
        )
        if not projections or any(
            projection.status != pause.status for projection in projections
        ):
            raise RuntimeError("Interrupt pause projection state is inconsistent")
        pending_interrupts = {
            "pause_id": pause.id,
            "pause_version": pause.pause_version,
            "status": pause.status,
            "expires_at": pause.expires_at,
            "members": [
                {
                    "interrupt_id": projection.official_interrupt_id,
                    "response_version": projection.response_version,
                    "status": projection.status,
                    "payload": projection.payload,
                    "response": projection.response,
                    "responded_at": projection.responded_at,
                }
                for projection in projections
            ],
        }
        effective_status = "waiting_human"
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
        inbox_cursor_key: bytes | None = None,
    ) -> None:
        self._session_factory = session_factory
        key_material = inbox_cursor_key if inbox_cursor_key is not None else token_bytes(32)
        if len(key_material) < 32:
            raise ValueError("inbox cursor key must contain at least 32 bytes")
        self._inbox_cursor_key = sha256(
            b"crypto-alert-v2:product-inbox-cursor:key\0" + key_material
        ).digest()

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
                    User.identity_issuer == actor.identity_issuer,
                    User.external_subject == actor.user_id,
                )
            )
            if user is None:
                user = User(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    identity_issuer=actor.identity_issuer,
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
                _require_analysis_write(resolved)
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
                _require_analysis_write(resolved)
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
            _require_analysis_read(resolved)
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
            if run_id is not None:
                selected_run_exists = await session.scalar(
                    select(Run.id).where(
                        Run.id == run_id,
                        Run.task_id == task.id,
                        Run.tenant_id == resolved.tenant_id,
                        Run.workspace_id == resolved.workspace_id,
                        Run.owner_user_id == resolved.user_id,
                    )
                )
                if selected_run_exists is None:
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
            _require_analysis_write(resolved)
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

    async def fork_task(
        self,
        actor: ActorContext,
        task_id: str,
        submission: ForkSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        command_idempotency_key = (
            f"fork:{task_uuid}:{sha256(idempotency_key.encode()).hexdigest()}"
        )
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
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
                            TaskCommand.actor_user_id == resolved.user_id,
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
                replay_source_run_id = replay.payload.get("source_run_id")
                replay_checkpoint_id = replay.payload.get("checkpoint_id")
                same_checkpoint = (
                    submission.checkpoint_id is None
                    or (
                        isinstance(replay_checkpoint_id, str)
                        and hmac.compare_digest(
                            replay_checkpoint_id,
                            submission.checkpoint_id,
                        )
                    )
                )
                if (
                    replay_source_run_id != str(submission.source_run_id)
                    or not same_checkpoint
                ):
                    raise IdempotencyConflictError(
                        "Idempotency-Key was already used with a different fork payload."
                    )
                fork_run_id = replay.payload.get("fork_run_id")
                selected_run_id = (
                    UUID(fork_run_id) if isinstance(fork_run_id, str) else None
                )
                return await _task_view(
                    session,
                    resolved,
                    task,
                    selected_run_id=selected_run_id,
                )

            if task.status == "cancelled":
                raise ForkConflictError("Cancelled tasks cannot be forked.")

            source_run = await session.scalar(
                select(Run)
                .where(
                    Run.id == submission.source_run_id,
                    Run.task_id == task.id,
                    Run.thread_id == task.thread_id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if source_run is None:
                return None
            source_checkpoint_id = source_run.checkpoint_id
            if source_checkpoint_id is None:
                raise ForkConflictError("Source Run has no forkable checkpoint.")
            if submission.checkpoint_id is not None and not hmac.compare_digest(
                source_checkpoint_id,
                submission.checkpoint_id,
            ):
                raise ForkConflictError(
                    "Checkpoint does not match the owner-scoped source Run."
                )
            if any(
                command.status in {"pending", "dispatching"}
                for command in commands
            ):
                raise ForkConflictError(
                    "Task already has a command awaiting dispatch or reconciliation."
                )
            await _cancel_pending_pause_for_fork(session, resolved, task)
            request_hash = _payload_hash(
                {
                    "task_id": str(task.id),
                    "source_run_id": str(source_run.id),
                    "checkpoint_id": source_checkpoint_id,
                }
            )

            latest_attempt = await session.scalar(
                select(func.coalesce(func.max(Run.attempt), 0)).where(
                    Run.task_id == task.id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
            )
            fork_run = Run(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                attempt=int(latest_attempt or 0) + 1,
                status="queued",
                checkpoint_id=source_checkpoint_id,
                input_payload=source_run.input_payload,
                forked_from_run_id=source_run.id,
                forked_from_checkpoint_id=source_checkpoint_id,
            )
            command_payload = {
                "source_run_id": str(source_run.id),
                "fork_run_id": str(fork_run.id),
                "checkpoint_id": source_checkpoint_id,
            }
            session.add(fork_run)
            await session.flush()
            session.add(
                TaskCommand(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    actor_user_id=resolved.user_id,
                    task_id=task.id,
                    thread_id=task.thread_id,
                    command_type="fork",
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
            task.status = "queued"
            task.completed_at = None
            await session.flush()
            return await _task_view(
                session,
                resolved,
                task,
                selected_run_id=fork_run.id,
            )

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
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            task = await session.scalar(
                select(Task)
                .where(
                    Task.id == task_uuid,
                    Task.tenant_id == resolved.tenant_id,
                    Task.workspace_id == resolved.workspace_id,
                    Task.owner_user_id == resolved.user_id,
                )
            )
            if task is None:
                return None
            projection = await session.scalar(
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
                .limit(1)
            )
            if projection is None or projection.pause_id is None:
                return None
            member_count = len(
                (
                    await session.scalars(
                        select(InterruptProjection.id)
                        .where(
                            InterruptProjection.pause_id == projection.pause_id,
                            InterruptProjection.task_id == task.id,
                        )
                    )
                ).all()
            )
            if member_count != 1:
                raise InterruptBatchRequiredError(
                    "This pause has multiple interrupts and requires respond-all."
                )
            pause_id = projection.pause_id
            pause_version = await session.scalar(
                select(InterruptPause.pause_version).where(
                    InterruptPause.id == pause_id,
                    InterruptPause.task_id == task.id,
                )
            )
            if pause_version is None:
                return None

        response = ReviewResponse.model_validate(
            submission.model_dump(exclude={"response_version"})
        )
        batch = InterruptResponsesSubmission.model_validate(
            {
                "pause_id": pause_id,
                "pause_version": pause_version,
                "responses": [
                    {
                        "interrupt_id": interrupt_id,
                        "response_version": submission.response_version,
                        "response": response,
                    }
                ],
            }
        )
        return await self.respond_interrupts(
            actor,
            task_id,
            batch,
            idempotency_key,
        )

    async def respond_interrupts(
        self,
        actor: ActorContext,
        task_id: str,
        submission: InterruptResponsesSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None

        command_idempotency_key = (
            "respond-all:"
            + sha256(
                f"{task_uuid}:{submission.pause_id}:{idempotency_key}".encode()
            ).hexdigest()
        )
        submitted = {item.interrupt_id: item for item in submission.responses}

        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
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
            pause = await session.scalar(
                select(InterruptPause)
                .where(
                    InterruptPause.id == submission.pause_id,
                    InterruptPause.task_id == task.id,
                    InterruptPause.tenant_id == resolved.tenant_id,
                    InterruptPause.workspace_id == resolved.workspace_id,
                    InterruptPause.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if pause is None:
                return None
            projections = list(
                (
                    await session.scalars(
                        select(InterruptProjection)
                        .where(
                            InterruptProjection.pause_id == pause.id,
                            InterruptProjection.task_id == task.id,
                            InterruptProjection.tenant_id == resolved.tenant_id,
                            InterruptProjection.workspace_id == resolved.workspace_id,
                            InterruptProjection.owner_user_id == resolved.user_id,
                        )
                        .order_by(InterruptProjection.id)
                        .with_for_update()
                    )
                ).all()
            )
            if not projections:
                raise InterruptResponseConflictError(
                    "Interrupt pause has no registered members."
                )
            expected_ids = {item.official_interrupt_id for item in projections}
            if set(submitted) != expected_ids:
                raise InterruptResponseConflictError(
                    "Interrupt responses must exactly match the active pause members."
                )
            if pause.pause_version != submission.pause_version:
                raise InterruptResponseConflictError("Interrupt pause version is stale.")

            canonical_responses: list[dict[str, Any]] = []
            for projection in sorted(
                projections,
                key=lambda item: item.official_interrupt_id,
            ):
                item = submitted[projection.official_interrupt_id]
                if projection.response_version != item.response_version:
                    raise InterruptResponseConflictError(
                        "Interrupt response_version is stale."
                    )
                response = ReviewResponse.model_validate(item.response).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                canonical_responses.append(
                    {
                        "projection_id": str(projection.id),
                        "interrupt_id": projection.official_interrupt_id,
                        "namespace": projection.namespace,
                        "checkpoint_id": projection.checkpoint_id,
                        "response_version": projection.response_version,
                        "response": response,
                    }
                )
            request_identity = {
                "task_id": str(task.id),
                "pause_id": str(pause.id),
                "pause_version": pause.pause_version,
                "root_checkpoint": {
                    "thread_id": pause.root_thread_id,
                    "checkpoint_ns": pause.root_checkpoint_ns,
                    "checkpoint_id": pause.root_checkpoint_id,
                    "checkpoint_map": pause.root_checkpoint_map,
                },
                "responses": canonical_responses,
            }
            request_hash = _payload_hash(request_identity)
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

            parent_run = await session.scalar(
                select(Run)
                .where(
                    Run.id == pause.run_id,
                    Run.task_id == task.id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            latest_waiting_run_id = await session.scalar(
                select(Run.id)
                .where(
                    Run.task_id == task.id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                    Run.status == "waiting_human",
                )
                .order_by(Run.attempt.desc(), Run.id.desc())
                .limit(1)
                .with_for_update()
            )
            if (
                parent_run is None
                or parent_run.status != "waiting_human"
                or parent_run.id != latest_waiting_run_id
                or task.status != "waiting_human"
            ):
                raise InterruptResponseConflictError(
                    "Interrupt is stale for the latest waiting run."
                )
            now = datetime.now(UTC)
            if pause.status == "expired" or (
                pause.status == "pending"
                and pause.expires_at is not None
                and pause.expires_at <= now
            ):
                raise InterruptResponseConflictError(
                    "Interrupt response window has expired."
                )
            if pause.status != "pending" or any(
                projection.status != "pending" for projection in projections
            ):
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
                attempt=parent_run.attempt + 1,
                status="queued",
                input_payload=parent_run.input_payload,
                resume_of_run_id=parent_run.id,
            )
            command_payload = {
                "pause_id": str(pause.id),
                "pause_version": pause.pause_version,
                "root_checkpoint": request_identity["root_checkpoint"],
                "responses": canonical_responses,
                "expired": False,
            }
            session.add(resume_run)
            await session.flush()
            pause.status = "responding"
            pause.resume_run_id = resume_run.id
            pause.accepted_payload_hash = request_hash
            for projection, canonical in zip(
                sorted(projections, key=lambda item: item.official_interrupt_id),
                canonical_responses,
                strict=True,
            ):
                projection.status = "responding"
                projection.response = canonical["response"]
                projection.responded_at = now
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
            _require_analysis_read(resolved)
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

    async def list_inbox(
        self,
        actor: ActorContext,
        *,
        status: InboxQueryStatus = "active",
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if status not in _INBOX_QUERY_STATUSES:
            raise ValueError("unsupported inbox status")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            scope = _inbox_scope(resolved)
            parsed_cursor = (
                _parse_inbox_cursor(
                    cursor,
                    key=self._inbox_cursor_key,
                    scope=scope,
                    status=status,
                )
                if cursor is not None
                else None
            )
            statement = (
                select(InterruptPause, Task)
                .join(
                    Task,
                    and_(
                        InterruptPause.task_id == Task.id,
                        InterruptPause.tenant_id == Task.tenant_id,
                        InterruptPause.workspace_id == Task.workspace_id,
                        InterruptPause.owner_user_id == Task.owner_user_id,
                    ),
                )
                .where(
                    InterruptPause.tenant_id == resolved.tenant_id,
                    InterruptPause.workspace_id == resolved.workspace_id,
                    InterruptPause.owner_user_id == resolved.user_id,
                    Task.tenant_id == resolved.tenant_id,
                    Task.workspace_id == resolved.workspace_id,
                    Task.owner_user_id == resolved.user_id,
                )
            )
            status_filter = _INBOX_STATUS_FILTERS.get(status)
            if status_filter is not None:
                statement = statement.where(InterruptPause.status.in_(status_filter))
            if parsed_cursor is not None:
                statement = statement.where(
                    or_(
                        InterruptPause.created_at < parsed_cursor.created_at,
                        and_(
                            InterruptPause.created_at == parsed_cursor.created_at,
                            InterruptPause.id < parsed_cursor.pause_id,
                        ),
                    )
                )
            rows = (
                await session.execute(
                    statement.order_by(
                        InterruptPause.created_at.desc(),
                        InterruptPause.id.desc(),
                    ).limit(limit + 1)
                )
            ).all()
            page = rows[:limit]
            next_cursor = None
            if len(rows) > limit:
                last_pause = page[-1][0]
                next_cursor = _encode_inbox_cursor(
                    _InboxCursor(
                        created_at=last_pause.created_at,
                        pause_id=last_pause.id,
                        scope=scope,
                        status=status,
                    ),
                    key=self._inbox_cursor_key,
                )
            pause_ids = [pause.id for pause, _ in page]
            projections_by_pause: dict[UUID, list[InterruptProjection]] = {
                pause_id: [] for pause_id in pause_ids
            }
            if pause_ids:
                projections = list(
                    (
                        await session.scalars(
                            select(InterruptProjection)
                            .where(
                                InterruptProjection.pause_id.in_(pause_ids),
                                InterruptProjection.tenant_id == resolved.tenant_id,
                                InterruptProjection.workspace_id
                                == resolved.workspace_id,
                                InterruptProjection.owner_user_id == resolved.user_id,
                            )
                            .order_by(
                                InterruptProjection.created_at,
                                InterruptProjection.id,
                            )
                        )
                    ).all()
                )
                for projection in projections:
                    projections_by_pause[projection.pause_id].append(projection)

            items = []
            for pause, task in page:
                members = projections_by_pause[pause.id]
                if not members or len(members) > 64:
                    raise RuntimeError("Interrupt pause has an invalid member count")
                expected_member_statuses = {
                    "pending": {"pending"},
                    "responding": {"responding"},
                    "resolved": {"resolved"},
                    "expired": {"expired"},
                    "resume_failed": {"responding", "expired"},
                    "cancelled": {"cancelled"},
                }[pause.status]
                if any(
                    member.status not in expected_member_statuses for member in members
                ):
                    raise RuntimeError("Interrupt pause projection state is inconsistent")
                payloads = [
                    ArtifactReviewPayload.model_validate(member.payload)
                    for member in members
                ]
                symbol = task.request_payload["symbol"]
                horizon = task.request_payload["horizon"]
                if any(
                    payload.artifact.analysis.instrument != symbol
                    or payload.artifact.analysis.horizon != horizon
                    for payload in payloads
                ):
                    raise RuntimeError("Interrupt pause review scope is inconsistent")
                response_times = [member.responded_at for member in members]
                responded_at = (
                    max(item for item in response_times if item is not None)
                    if all(item is not None for item in response_times)
                    else None
                )
                items.append(
                    {
                        "task_id": str(pause.task_id),
                        "pause_id": pause.id,
                        "pause_version": pause.pause_version,
                        "status": pause.status,
                        "member_count": len(members),
                        "payload": payloads[0].model_dump(mode="json"),
                        "expires_at": pause.expires_at,
                        "responded_at": responded_at,
                        "created_at": pause.created_at,
                        "updated_at": pause.updated_at,
                        "symbol": symbol,
                        "horizon": horizon,
                        "query_text": task.request_payload.get("query_text"),
                    }
                )
            return {"items": items, "next_cursor": next_cursor}
