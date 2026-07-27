from base64 import b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import json
from secrets import token_bytes
from typing import Any, Callable, Sequence
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from crypto_alert_v2.api.request_identity import correlation_id_for_task
from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    DecisionRequestSubmission,
    DataDeletionSubmission,
    DataLifecyclePolicyUpdate,
    DataExportSubmission,
    DeepResearchSubmission,
    FeedbackSubmission,
    ImprovementCandidateSubmission,
    ImprovementDatasetSubmission,
    ImprovementExperimentSubmission,
    ImprovementReviewDecisionSubmission,
    ImprovementReleaseSubmission,
    ImprovementShadowSubmission,
    PostmortemSubmission,
    ForkSubmission,
    InboxQueryStatus,
    InboxReviewSubmission,
    InterruptResponseSubmission,
    InterruptResponsesSubmission,
    MonitorCreateSubmission,
    MonitorMutationSubmission,
    MonitorStatusFilter,
    MemoryCreateSubmission,
    MemoryDeleteSubmission,
    MemoryUpdateSubmission,
    NotificationResendSubmission,
    NotificationSettingsUpdate,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.domain.decision_request import (
    DecisionRequest,
    route_decision_request,
)
from crypto_alert_v2.domain.models import SUPPORTED_SYMBOLS
from crypto_alert_v2.domain.memory import MemoryRecord
from crypto_alert_v2.domain.outcome import quality_is_reportable
from crypto_alert_v2.evaluation.frozen_replay import (
    FrozenReplayPacket,
    freeze_replay_packet,
    rule_judge,
)
from crypto_alert_v2.evaluation.governance import (
    CandidateStatus,
    RuleCandidate,
    run_frozen_rule_experiment,
    transition_candidate,
)
from crypto_alert_v2.evaluation.release_gate import evaluate_release_gate
from crypto_alert_v2.evaluation.review_runtime import (
    CandidateReviewReceipt,
    CandidateReviewRuntime,
)
from crypto_alert_v2.api.agent_server import (
    RemoteCheckpoint,
    RemoteInterrupt,
    RemoteRunHandle,
)
from crypto_alert_v2.graph.request import (
    ReviewResponse,
    parse_review_interrupt_payload,
    validate_review_payload_for_task,
    validate_review_response_for_payload,
)
from crypto_alert_v2.monitors.conditions import (
    MonitorConditionEvaluatorUnavailableError,
    require_monitor_condition_evaluator,
)
from crypto_alert_v2.lifecycle import LifecycleService
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    Feedback,
    FrozenReplayRecord,
    ImprovementCandidate,
    ImprovementDataset,
    ImprovementDatasetMember,
    ImprovementExperiment,
    ImprovementReview,
    ImprovementReleaseEvent,
    ImprovementShadowRun,
    InterruptPause,
    InterruptProjection,
    MarketSnapshot as PersistedMarketSnapshot,
    Membership,
    MonitorDefinition,
    MonitorDestination,
    MonitorTrigger,
    NotificationAttempt,
    NotificationDestination,
    NotificationOutbox,
    ObservabilityDelivery,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    WebEvidence as PersistedWebEvidence,
    WatchlistItem,
    Workspace,
    WorkspaceEntitlement,
    UsageReconciliation,
    MemoryEntry,
    MemoryDeletionJob,
    OutcomeObservation,
    PostmortemCase,
)
from crypto_alert_v2.notifications.credentials import NotificationCredentialCipher
from crypto_alert_v2.notifications.outbox import request_manual_resend
from crypto_alert_v2.persistence.repositories import (
    ResolvedActor,
    ScopedResourceNotFound,
    TaskRunProjectionRepository,
    TaskRunStageEventRecord,
    resolve_actor,
)
from crypto_alert_v2.persistence.monitor_repository import (
    EntitlementDenied,
    MonitorIdempotencyConflict,
    MonitorRepository,
    MonitorVersionConflict,
)
from crypto_alert_v2.persistence.usage_governance import (
    UsageGovernanceRepository,
    entitlement_limits,
    reconciliation_view,
    usage_period_start,
)
from crypto_alert_v2.projections.task import project_task_run_sources


class IdempotencyConflictError(RuntimeError):
    pass


class TaskNotCancellableError(RuntimeError):
    pass


class RunNotCancellableError(RuntimeError):
    pass


class FeedbackConflictError(RuntimeError):
    pass


class WatchlistSymbolError(ValueError):
    pass


class TaskNotRetryableError(RuntimeError):
    pass


class ForkConflictError(RuntimeError):
    pass


class InterruptResponseConflictError(RuntimeError):
    pass


class InterruptBatchRequiredError(InterruptResponseConflictError):
    pass


class InvalidInboxCursorError(ValueError):
    pass


class NotificationSettingsConflictError(RuntimeError):
    pass


class NotificationSettingsUnavailableError(RuntimeError):
    pass


class MonitorConflictError(RuntimeError):
    pass


class MonitorEntitlementError(RuntimeError):
    pass


class CandidateReviewUnavailableError(RuntimeError):
    pass


class MonitorSourceError(ValueError):
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

_MONITOR_STATUS_FILTERS: dict[MonitorStatusFilter, tuple[str, ...]] = {
    "running": ("draft", "active"),
    "paused": ("paused",),
    "attention": ("degraded",),
    "closed": ("expired", "disabled"),
    "all": ("draft", "active", "paused", "degraded", "expired", "disabled"),
}
_MONITOR_SCHEDULE_INTERVAL_SECONDS = {
    "*/5 * * * *": 300,
    "*/15 * * * *": 900,
    "0 * * * *": 3_600,
    "0 */4 * * *": 14_400,
    "0 0 * * *": 86_400,
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
                not (character.isalnum() or character in "-_") for character in cursor
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


def _optional_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _require_analysis_write(resolved: ResolvedActor) -> None:
    if "analysis:write" not in resolved.permissions:
        raise PermissionError("analysis:write permission is required")


def _require_analysis_read(resolved: ResolvedActor) -> None:
    if "analysis:read" not in resolved.permissions:
        raise PermissionError("analysis:read permission is required")


def _notification_view(
    notification: NotificationOutbox,
    attempts: list[NotificationAttempt],
    *,
    now: datetime,
) -> dict[str, Any]:
    manual_used = any(attempt.trigger == "manual" for attempt in attempts)
    manual_pending = notification.manual_resend_requested_at is not None
    return {
        "notification_id": notification.id,
        "task_id": notification.task_id,
        "run_id": notification.run_id,
        "artifact_id": notification.artifact_id,
        "artifact_version_id": notification.artifact_version_id,
        "decision_id": notification.decision_id,
        "decision_version": notification.decision_version,
        "channel": notification.channel,
        "type": notification.type,
        "status": notification.status,
        "attempt_count": notification.attempt_count,
        "manual_resend_pending": manual_pending,
        "manual_resend_available": (
            notification.status in {"unknown", "failed_retryable", "failed_terminal"}
            and not manual_pending
            and not manual_used
            and notification.attempt_count < 5
            and notification.created_at > now - timedelta(hours=24)
        ),
        "manual_resend_requested_at": notification.manual_resend_requested_at,
        "available_at": notification.available_at,
        "delivered_at": notification.delivered_at,
        "terminal_at": notification.terminal_at,
        "created_at": notification.created_at,
        "updated_at": notification.updated_at,
        "attempts": [
            {
                "attempt_id": attempt.id,
                "attempt_number": attempt.attempt_number,
                "trigger": attempt.trigger,
                "result": attempt.result,
                "reason": attempt.reason,
                "delay_seconds": attempt.delay_seconds,
                "retry_after_seconds": attempt.retry_after_seconds,
                "cost_units": str(attempt.cost_units),
                "provider_receipt": attempt.provider_receipt,
                "error_code": attempt.error_code,
                "created_at": attempt.created_at,
                "finished_at": attempt.finished_at,
            }
            for attempt in attempts
        ],
    }


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


def _feedback_view(feedback: Feedback | None) -> dict[str, Any] | None:
    if feedback is None:
        return None
    return {
        "feedback_id": feedback.id,
        "task_id": feedback.task_id,
        "run_id": feedback.run_id,
        "artifact_version_id": feedback.artifact_version_id,
        "rating": feedback.rating,
        "comment": feedback.comment,
        "created_at": feedback.created_at,
        "updated_at": feedback.updated_at,
    }


def _frozen_replay_view(record: FrozenReplayRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    packet = record.packet
    return {
        "id": record.id,
        "postmortem_id": record.postmortem_id,
        "task_id": record.task_id,
        "run_id": record.run_id,
        "artifact_version_id": record.artifact_version_id,
        "schema_version": record.schema_version,
        "source_hash": record.source_hash,
        "allow_live_fetch": packet.get("allow_live_fetch", False),
        "allow_live_side_effects": packet.get("allow_live_side_effects", False),
        "rule_metrics": record.rule_metrics,
        "created_at": record.created_at,
    }


def _postmortem_view(
    case: PostmortemCase,
    replay: FrozenReplayRecord | None = None,
) -> dict[str, Any]:
    return {
        "id": case.id,
        "feedback_id": case.feedback_id,
        "task_id": case.task_id,
        "run_id": case.run_id,
        "artifact_version_id": case.artifact_version_id,
        "category": case.category,
        "status": case.status,
        "title": case.title,
        "summary": case.summary,
        "root_cause": case.root_cause,
        "expected_behavior": case.expected_behavior,
        "actual_behavior": case.actual_behavior,
        "source_hash": case.source_hash,
        "frozen_replay": _frozen_replay_view(replay),
        "created_at": case.created_at,
        "updated_at": case.updated_at,
    }


def _improvement_dataset_view(
    dataset: ImprovementDataset,
    members: Sequence[ImprovementDatasetMember],
) -> dict[str, Any]:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "status": dataset.status,
        "replay_count": len(members),
        "case_names": [member.case_name for member in members],
        "source_hash": dataset.source_hash,
        "frozen_at": dataset.frozen_at,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def _improvement_experiment_view(
    experiment: ImprovementExperiment,
) -> dict[str, Any]:
    return {
        "id": experiment.id,
        "dataset_id": experiment.dataset_id,
        "candidate_id": experiment.candidate_id,
        "status": experiment.status,
        "prompt_version": experiment.prompt_version,
        "git_revision": experiment.git_revision,
        "case_results": experiment.case_results,
        "metrics": experiment.metrics,
        "gate_report": experiment.gate_report,
        "source_hash": experiment.source_hash,
        "completed_at": experiment.completed_at,
        "created_at": experiment.created_at,
    }


def _improvement_candidate_view(
    candidate: ImprovementCandidate,
    experiment: ImprovementExperiment | None = None,
    review: ImprovementReview | None = None,
    shadow: ImprovementShadowRun | None = None,
    release_events: Sequence[ImprovementReleaseEvent] = (),
) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "name": candidate.name,
        "base_version": candidate.base_version,
        "candidate_version": candidate.candidate_version,
        "rollback_target_version": candidate.rollback_target_version,
        "rationale": candidate.rationale,
        "diff": candidate.diff,
        "version_hash": candidate.version_hash,
        "status": candidate.status,
        "latest_experiment": (
            _improvement_experiment_view(experiment)
            if experiment is not None
            else None
        ),
        "latest_review": (
            _improvement_review_view(review) if review is not None else None
        ),
        "latest_shadow": (
            _improvement_shadow_view(shadow) if shadow is not None else None
        ),
        "release_events": [
            _improvement_release_event_view(event) for event in release_events
        ],
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _improvement_review_view(review: ImprovementReview) -> dict[str, Any]:
    return {
        "id": review.id,
        "candidate_id": review.candidate_id,
        "status": review.status,
        "official_assistant_id": review.official_assistant_id,
        "official_thread_id": review.official_thread_id,
        "official_run_id": review.official_run_id,
        "official_interrupt_id": review.official_interrupt_id,
        "interrupt_payload": review.interrupt_payload,
        "response": review.response,
        "decided_at": review.decided_at,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }


def _improvement_shadow_view(shadow: ImprovementShadowRun) -> dict[str, Any]:
    return {
        "id": shadow.id,
        "candidate_id": shadow.candidate_id,
        "baseline_version": shadow.baseline_version,
        "status": shadow.status,
        "minimum_runs": shadow.minimum_runs,
        "observed_runs": shadow.observed_runs,
        "comparison": shadow.comparison,
        "source_hash": shadow.source_hash,
        "completed_at": shadow.completed_at,
        "created_at": shadow.created_at,
        "updated_at": shadow.updated_at,
    }


def _improvement_release_event_view(
    event: ImprovementReleaseEvent,
) -> dict[str, Any]:
    return {
        "id": event.id,
        "candidate_id": event.candidate_id,
        "action": event.action,
        "from_version": event.from_version,
        "to_version": event.to_version,
        "rollback_target_version": event.rollback_target_version,
        "reason": event.reason,
        "evidence": event.evidence,
        "source_hash": event.source_hash,
        "created_at": event.created_at,
    }


def _candidate_review_receipt(review: ImprovementReview) -> CandidateReviewReceipt:
    checkpoint = review.checkpoint
    if (
        review.official_assistant_id is None
        or review.official_thread_id is None
        or review.official_run_id is None
        or review.official_interrupt_id is None
        or review.interrupt_payload is None
        or not isinstance(checkpoint, dict)
    ):
        raise CandidateReviewUnavailableError(
            "Candidate review has no complete official interrupt receipt."
        )
    remote_checkpoint = RemoteCheckpoint(
        thread_id=str(checkpoint["thread_id"]),
        checkpoint_ns=str(checkpoint["checkpoint_ns"]),
        checkpoint_id=str(checkpoint["checkpoint_id"]),
        checkpoint_map={
            str(key): str(value)
            for key, value in dict(checkpoint.get("checkpoint_map", {})).items()
        },
    )
    return CandidateReviewReceipt(
        handle=RemoteRunHandle(
            assistant_id=review.official_assistant_id,
            thread_id=review.official_thread_id,
            run_id=review.official_run_id,
        ),
        interrupt=RemoteInterrupt(
            interrupt_id=review.official_interrupt_id,
            namespace=remote_checkpoint.checkpoint_ns,
            checkpoint_id=remote_checkpoint.checkpoint_id,
            value=review.interrupt_payload,
        ),
        checkpoint=remote_checkpoint,
    )


def _memory_view(memory: MemoryEntry) -> dict[str, Any]:
    return {
        "id": memory.id,
        "tenant_id": memory.tenant_id,
        "workspace_id": memory.workspace_id,
        "owner_user_id": memory.owner_user_id,
        "session_id": memory.session_id,
        "scope": memory.scope,
        "purpose": memory.purpose,
        "key": memory.memory_key,
        "content": memory.content,
        "enabled": memory.enabled,
        "expires_at": memory.expires_at,
        "refreshed_at": memory.refreshed_at,
        "source_artifact_id": memory.source_artifact_id,
        "deleted_at": memory.deleted_at,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def _outcome_view(outcome: OutcomeObservation) -> dict[str, Any]:
    return {
        "id": outcome.id,
        "artifact_version_id": outcome.artifact_version_id,
        "task_id": outcome.task_id,
        "run_id": outcome.run_id,
        "action": outcome.action,
        "baseline": outcome.baseline,
        "status": outcome.status,
        "predicted_probability": (
            float(outcome.predicted_probability)
            if outcome.predicted_probability is not None
            else None
        ),
        "realized_label": (
            float(outcome.realized_label) if outcome.realized_label is not None else None
        ),
        "horizon": outcome.horizon,
        "source": outcome.source,
        "maturation_at": outcome.maturation_at,
        "observed_at": outcome.observed_at,
        "metrics": outcome.metrics,
        "source_hash": outcome.source_hash,
        "created_at": outcome.created_at,
        "updated_at": outcome.updated_at,
    }


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
        "task_type": getattr(task, "task_type", "market_analysis"),
        "correlation_id": correlation_id_for_task(task.id),
        "status": task.status,
        "symbol": request_payload["symbol"],
        "horizon": request_payload["horizon"],
        "query_text": request_payload.get("query_text"),
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "market_snapshot": None,
        "web_evidence": [],
        "artifact": None,
        "deep_research_artifact": None,
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


def _public_error(
    payload: dict[str, Any] | None,
    *,
    correlation_id: str | None = None,
) -> list[dict[str, Any]]:
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
                **(
                    {"correlation_id": correlation_id}
                    if correlation_id is not None
                    else {}
                ),
            }
        ]
    first = errors[0] if isinstance(errors[0], dict) else {}
    code = str(first.get("code") or "analysis_failed")
    messages = {
        "provider_unavailable": "无法连接市场数据提供方，当前未生成分析结果。",
        "research_unavailable": "检索服务没有返回可验证来源，当前未生成分析结果。",
        "deep_research_unavailable": "深度研究未能生成可验证报告，请检查检索或模型状态。",
        "deep_research_review_unavailable": "当前工作区要求人工审核，但深度研究报告审核尚未启用。",
        "model_unavailable": "分析模型暂时不可用，当前未生成分析结果。",
        "model_invalid_output": "分析模型未返回有效结构化结果，当前未生成分析结果。",
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
    web_evidence = payload.get("web_evidence")
    verified_evidence_count = len(web_evidence) if isinstance(web_evidence, list) else 0
    message = messages.get(code, "分析未能完成，请检查错误码后重试。")
    if code == "research_unavailable" and verified_evidence_count > 0:
        message = (
            "研究检索阶段未完成；本次运行已保留 "
            f"{verified_evidence_count} 条可验证来源，但没有生成新的分析结果。"
        )
    diagnostics: dict[str, Any] = {}
    provider = first.get("provider")
    error_type = first.get("error_type")
    attempt = first.get("attempt")
    endpoint = first.get("endpoint")
    fallback_from = first.get("fallback_from")
    primary_attempt = first.get("primary_attempt")
    if _safe_diagnostic_identifier(provider, max_length=64):
        diagnostics["provider"] = provider
    if _safe_diagnostic_identifier(error_type, max_length=128):
        diagnostics["error_type"] = error_type
    if (
        isinstance(attempt, int)
        and not isinstance(attempt, bool)
        and 1 <= attempt <= 100
    ):
        diagnostics["attempt"] = attempt
    if _safe_diagnostic_identifier(endpoint, max_length=128):
        diagnostics["endpoint"] = endpoint
    if _safe_diagnostic_identifier(fallback_from, max_length=64):
        diagnostics["fallback_from"] = fallback_from
    if (
        isinstance(primary_attempt, int)
        and not isinstance(primary_attempt, bool)
        and 1 <= primary_attempt <= 100
    ):
        diagnostics["primary_attempt"] = primary_attempt
    return [
        {
            "code": code,
            "message": message,
            "retryable": bool(first.get("retryable", code != "analysis_failed")),
            **(
                {"correlation_id": correlation_id} if correlation_id is not None else {}
            ),
            **diagnostics,
        }
    ]


def _safe_diagnostic_identifier(value: object, *, max_length: int) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= max_length:
        return False
    return all(
        character.isascii() and (character.isalnum() or character in "._-")
        for character in value
    )


def _completion_projection(
    *,
    status: str,
    notification_requested: bool,
    notification_status: str | None,
    observability_statuses: Sequence[str] = (),
) -> tuple[dict[str, str], list[str]]:
    analysis = {
        "succeeded": "complete",
        "blocked": "blocked",
        "failed": "failed",
        "cancelled": "cancelled",
    }.get(status, "pending")
    if not notification_requested:
        notification = "not_requested"
        warnings: list[str] = []
    elif status != "succeeded":
        notification = "not_started"
        warnings = []
    elif notification_status in {None, "planned", "leased", "sending"}:
        notification = "pending"
        warnings = []
    elif notification_status == "failed_retryable":
        notification = "retrying"
        warnings = ["notification_delivery_retrying"]
    elif notification_status == "delivered":
        notification = "complete"
        warnings = []
    elif notification_status == "failed_terminal":
        notification = "failed"
        warnings = ["notification_delivery_failed"]
    else:
        notification = "unknown"
        warnings = ["notification_delivery_unknown"]

    requested_observability = [
        delivery_status
        for delivery_status in observability_statuses
        if delivery_status != "not_requested"
    ]
    if not requested_observability:
        observability = "not_enabled"
    elif all(
        delivery_status == "verified" for delivery_status in requested_observability
    ):
        observability = "complete"
    elif any(
        delivery_status in {"failed_terminal", "unknown"}
        for delivery_status in requested_observability
    ):
        observability = "degraded"
        warnings.append("observability_delivery_failed")
    else:
        observability = "pending"
        if status in {"succeeded", "blocked", "failed", "cancelled"}:
            warnings.append("observability_delivery_pending")
    return {
        "analysis": analysis,
        "notification": notification,
        "observability": observability,
    }, warnings


_PRODUCT_STAGE_BY_EVENT_TYPE = {
    "market.snapshot.committed": "market_snapshot",
    "research.evidence.committed": "web_evidence",
    "agent.output.committed": "analysis",
    "evidence.verdict.committed": "evidence_verdict",
    "risk.verdict.committed": "risk_verdict",
    "artifact.committed": "artifact",
    "notification.planned": "notification",
    "run.terminal": "run",
}
_TERMINAL_RUN_STATUSES = {"succeeded", "blocked", "failed", "cancelled"}


def _project_stage_history(
    run: Run,
    events: Sequence[TaskRunStageEventRecord],
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    for event in events:
        stage = _PRODUCT_STAGE_BY_EVENT_TYPE.get(event.event_type)
        if stage is None:
            raise RuntimeError("Domain Event type has no Product stage projection")
        if event.event_type == "run.terminal":
            if run.status not in _TERMINAL_RUN_STATUSES:
                raise RuntimeError("Non-terminal Run contains a terminal Domain Event")
            status = run.status
        elif event.event_type == "notification.planned":
            status = "planned"
        else:
            status = "committed"
        stages.append(
            {
                "sequence": event.sequence,
                "stage": stage,
                "status": status,
                "recorded_at": event.recorded_at,
                "source": (
                    "official_stream"
                    if event.from_official_stream
                    else "product_projection"
                ),
            }
        )
    return {
        "run_id": run.id,
        "stages": stages,
        "product_event_cursor": events[-1].sequence if events else None,
        "official_stream_cursor": run.official_stream_last_event_id,
        "official_stream_cursor_at": run.official_stream_last_event_at,
    }


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
        select(Run).where(*run_filters).order_by(Run.attempt.desc()).limit(1).subquery()
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
    cancel_commands = list(
        (
            await session.execute(
                select(
                    TaskCommand.created_at,
                    TaskCommand.command_type,
                    TaskCommand.payload,
                )
                .where(
                    TaskCommand.task_id == task.id,
                    TaskCommand.tenant_id == resolved.tenant_id,
                    TaskCommand.workspace_id == resolved.workspace_id,
                    TaskCommand.actor_user_id == resolved.user_id,
                    TaskCommand.command_type.in_(("cancel_task", "cancel_run")),
                    TaskCommand.status.in_(("pending", "dispatching")),
                )
                .order_by(TaskCommand.sequence.desc())
            )
        ).all()
    )
    cancel_requested_at = next(
        (
            created_at
            for created_at, command_type, payload in cancel_commands
            if command_type == "cancel_task"
            or (
                latest_run is not None
                and command_type == "cancel_run"
                and payload.get("run_id") == str(latest_run.id)
            )
        ),
        None,
    )
    market_snapshot = None
    web_evidence = []
    stage_history = None
    if latest_run is not None:
        projection_repository = TaskRunProjectionRepository(session, resolved)
        records = await projection_repository.get_sources(
            task_id=task.id,
            run_id=latest_run.id,
        )
        run_sources = project_task_run_sources(records)
        market_snapshot = run_sources.market_snapshot
        web_evidence = run_sources.web_evidence
        stage_events = await projection_repository.get_stage_events(
            task_id=task.id,
            run_id=latest_run.id,
        )
        stage_history = _project_stage_history(latest_run, stage_events)
    artifact_statement = (
        select(Artifact.artifact_type, ArtifactVersion.content)
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
    artifact_row = (await session.execute(artifact_statement)).one_or_none()
    artifact_type = artifact_row[0] if artifact_row is not None else None
    artifact_content = artifact_row[1] if artifact_row is not None else None
    if (
        artifact_content is None
        and latest_run is not None
        and latest_run.status == "blocked"
        and latest_run.output_payload
    ):
        artifact_content = latest_run.output_payload.get("artifact")
        artifact_type = "analysis_report"
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
    notification_status = None
    if request_payload.get("notify") is True and latest_run is not None:
        notification_status = await session.scalar(
            select(NotificationOutbox.status)
            .where(
                NotificationOutbox.task_id == task.id,
                NotificationOutbox.run_id == latest_run.id,
                NotificationOutbox.tenant_id == resolved.tenant_id,
                NotificationOutbox.workspace_id == resolved.workspace_id,
                NotificationOutbox.owner_user_id == resolved.user_id,
            )
            .order_by(
                NotificationOutbox.created_at.desc(), NotificationOutbox.id.desc()
            )
            .limit(1)
        )
    observability_statuses: list[str] = []
    if latest_run is not None:
        observability_statuses = [
            row[0]
            for row in (
                await session.execute(
                    select(ObservabilityDelivery.status)
                    .where(
                        ObservabilityDelivery.task_id == task.id,
                        ObservabilityDelivery.run_id == latest_run.id,
                        ObservabilityDelivery.tenant_id == resolved.tenant_id,
                        ObservabilityDelivery.workspace_id == resolved.workspace_id,
                        ObservabilityDelivery.owner_user_id == resolved.user_id,
                    )
                    .order_by(ObservabilityDelivery.provider)
                )
            ).all()
        ]
    completion_scope, warnings = _completion_projection(
        status=effective_status,
        notification_requested=request_payload.get("notify") is True,
        notification_status=notification_status,
        observability_statuses=observability_statuses,
    )
    correlation_id = correlation_id_for_task(task.id)
    return {
        "task_id": str(task.id),
        "task_type": getattr(task, "task_type", "market_analysis"),
        "correlation_id": correlation_id,
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
        "artifact": (artifact_content if artifact_type == "analysis_report" else None),
        "deep_research_artifact": (
            artifact_content if artifact_type == "deep_research_report" else None
        ),
        "errors": _public_error(
            latest_run.output_payload if latest_run is not None else None,
            correlation_id=correlation_id,
        ),
        "completion_scope": completion_scope,
        "warnings": warnings,
        "agent_stream": agent_stream,
        "stage_history": stage_history,
        "pending_interrupts": pending_interrupts,
        "projection_scope": {
            "mode": "selected_run" if selected_run_id is not None else "latest",
            "selected_run_id": selected_run_id,
        },
    }


def _monitor_trigger_view(trigger: MonitorTrigger) -> dict[str, Any]:
    return {
        "id": trigger.id,
        "trigger_kind": trigger.kind,
        "status": trigger.status,
        "reason": trigger.reason,
        "task_id": trigger.task_id,
        "triggered_at": trigger.received_at,
        "created_at": trigger.received_at,
    }


async def _monitor_view(
    session: AsyncSession,
    resolved: ResolvedActor,
    monitor: MonitorDefinition,
) -> dict[str, Any]:
    destination_ids = list(
        (
            await session.scalars(
                select(MonitorDestination.destination_id)
                .where(
                    MonitorDestination.tenant_id == resolved.tenant_id,
                    MonitorDestination.workspace_id == resolved.workspace_id,
                    MonitorDestination.owner_user_id == resolved.user_id,
                    MonitorDestination.monitor_id == monitor.id,
                )
                .order_by(MonitorDestination.created_at, MonitorDestination.id)
            )
        ).all()
    )
    latest_trigger = await session.scalar(
        select(MonitorTrigger)
        .where(
            MonitorTrigger.tenant_id == resolved.tenant_id,
            MonitorTrigger.workspace_id == resolved.workspace_id,
            MonitorTrigger.owner_user_id == resolved.user_id,
            MonitorTrigger.monitor_id == monitor.id,
        )
        .order_by(MonitorTrigger.received_at.desc(), MonitorTrigger.id.desc())
        .limit(1)
    )
    template = monitor.task_template
    return {
        "id": monitor.id,
        "name": monitor.name,
        "status": monitor.status,
        "run_task_type": monitor.run_task_type,
        "artifact_id": monitor.artifact_id,
        "artifact_version_id": monitor.artifact_version_id,
        "symbol": template["symbol"],
        "horizon": template["horizon"],
        "condition": monitor.condition,
        "schedule": monitor.cron_schedule,
        "timezone": monitor.timezone,
        "quiet_hours": monitor.quiet_hours,
        "expires_at": monitor.expires_at,
        "destination_ids": destination_ids,
        "version": monitor.version,
        "schedule_version": monitor.schedule_version,
        "cron_configured": monitor.official_cron_id is not None,
        "next_run_at": monitor.next_run_at,
        "latest_trigger": (
            _monitor_trigger_view(latest_trigger)
            if latest_trigger is not None
            else None
        ),
        "created_at": monitor.created_at,
        "updated_at": monitor.updated_at,
    }


class ProductAnalysisService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        inbox_cursor_key: bytes | None = None,
        notification_credential_cipher: NotificationCredentialCipher | None = None,
        candidate_review_runtime: CandidateReviewRuntime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        key_material = (
            inbox_cursor_key if inbox_cursor_key is not None else token_bytes(32)
        )
        if len(key_material) < 32:
            raise ValueError("inbox cursor key must contain at least 32 bytes")
        self._inbox_cursor_key = sha256(
            b"crypto-alert-v2:product-inbox-cursor:key\0" + key_material
        ).digest()
        self._notification_credential_cipher = notification_credential_cipher
        self._candidate_review_runtime = candidate_review_runtime
        self._lifecycle = LifecycleService(
            session_factory=session_factory,
            clock=self._clock,
        )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Product service clock must be timezone-aware")
        return now

    async def check_database(self) -> None:
        async with self._session_factory() as session:
            await session.execute(select(1))

    async def get_usage_governance(
        self,
        actor: ActorContext,
        *,
        period_start: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        period = usage_period_start(period_start or now)
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            repository = UsageGovernanceRepository(session, resolved)
            entitlement = await repository.require_entitlement(now=now)
            totals = {unit: 0 for unit in entitlement_limits(entitlement)}
            totals.update(await repository.current_totals(period_start=period))
            latest = await session.scalar(
                select(UsageReconciliation)
                .where(
                    UsageReconciliation.tenant_id == resolved.tenant_id,
                    UsageReconciliation.workspace_id == resolved.workspace_id,
                    UsageReconciliation.period_start == period,
                )
                .order_by(
                    UsageReconciliation.created_at.desc(),
                    UsageReconciliation.id.desc(),
                )
                .limit(1)
            )
            return {
                "period_start": period,
                "entitlement": {
                    "allowed_task_types": entitlement.allowed_task_types,
                    "active_monitor_limit": entitlement.active_monitor_limit,
                    "min_interval_seconds": entitlement.min_interval_seconds,
                    "max_concurrent_tasks": entitlement.max_concurrent_tasks,
                    "max_retention_days": entitlement.max_retention_days,
                    "limits": entitlement_limits(entitlement),
                    "valid_from": entitlement.valid_from,
                    "valid_until": entitlement.valid_until,
                },
                "totals": totals,
                "latest_reconciliation": (
                    reconciliation_view(latest) if latest is not None else None
                ),
            }

    async def reconcile_usage(
        self,
        actor: ActorContext,
        *,
        period_start: datetime | None = None,
        repair: bool = True,
    ) -> dict[str, Any]:
        now = self._now()
        period = usage_period_start(period_start or now)
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            receipt = await UsageGovernanceRepository(
                session, resolved
            ).reconcile(period_start=period, repair=repair, now=now)
            return reconciliation_view(receipt)

    async def bootstrap_actor(self, actor: ActorContext) -> None:
        await self.provision_actor(
            actor,
            tenant_name="Development Tenant",
            workspace_name="Development Workspace",
            user_display_name="Development User",
        )
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            entitlement = await session.scalar(
                select(WorkspaceEntitlement).where(
                    WorkspaceEntitlement.tenant_id == resolved.tenant_id,
                    WorkspaceEntitlement.workspace_id == resolved.workspace_id,
                )
            )
            if entitlement is None:
                session.add(
                    WorkspaceEntitlement(
                        id=uuid4(),
                        tenant_id=resolved.tenant_id,
                        workspace_id=resolved.workspace_id,
                        active=True,
                        active_monitor_limit=20,
                        min_interval_seconds=300,
                        max_concurrent_tasks=5,
                        monthly_trigger_limit=10_000,
                        valid_from=self._now(),
                    )
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
                        id=actor.context_id or uuid4(),
                        tenant_id=tenant.id,
                        workspace_id=workspace.id,
                        user_id=user.id,
                        role=actor.roles[0] if actor.roles else "member",
                        permissions=list(actor.permissions),
                        is_active=True,
                    )
                )
            else:
                if actor.context_id is not None and membership.id != actor.context_id:
                    raise ValueError(
                        "development bootstrap context does not match existing membership"
                    )
                membership.role = actor.roles[0] if actor.roles else "member"
                membership.permissions = list(actor.permissions)
                membership.is_active = True

            await session.flush()
            existing_symbols = set(
                (
                    await session.scalars(
                        select(WatchlistItem.symbol).where(
                            WatchlistItem.tenant_id == tenant.id,
                            WatchlistItem.workspace_id == workspace.id,
                            WatchlistItem.owner_user_id == user.id,
                        )
                    )
                ).all()
            )
            for symbol in SUPPORTED_SYMBOLS:
                if symbol not in existing_symbols:
                    session.add(
                        WatchlistItem(
                            id=uuid4(),
                            tenant_id=tenant.id,
                            workspace_id=workspace.id,
                            owner_user_id=user.id,
                            symbol=symbol,
                        )
                    )

    async def get_home(self, actor: ActorContext) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            watchlist = list(
                (
                    await session.scalars(
                        select(WatchlistItem)
                        .where(
                            WatchlistItem.tenant_id == resolved.tenant_id,
                            WatchlistItem.workspace_id == resolved.workspace_id,
                            WatchlistItem.owner_user_id == resolved.user_id,
                        )
                        .order_by(WatchlistItem.created_at, WatchlistItem.symbol)
                    )
                ).all()
            )
            snapshots = list(
                (
                    await session.scalars(
                        select(PersistedMarketSnapshot)
                        .where(
                            PersistedMarketSnapshot.tenant_id == resolved.tenant_id,
                            PersistedMarketSnapshot.workspace_id
                            == resolved.workspace_id,
                            PersistedMarketSnapshot.owner_user_id == resolved.user_id,
                        )
                        .order_by(
                            PersistedMarketSnapshot.symbol,
                            PersistedMarketSnapshot.created_at.desc(),
                        )
                    )
                ).all()
            )
            latest_snapshots: dict[str, dict[str, Any]] = {}
            for snapshot in snapshots:
                latest_snapshots.setdefault(snapshot.symbol, snapshot.snapshot)

            active_tasks = list(
                (
                    await session.scalars(
                        select(Task)
                        .where(
                            Task.tenant_id == resolved.tenant_id,
                            Task.workspace_id == resolved.workspace_id,
                            Task.owner_user_id == resolved.user_id,
                            Task.status.in_(("queued", "running", "waiting_human")),
                        )
                        .order_by(Task.created_at.desc(), Task.id.desc())
                        .limit(10)
                    )
                ).all()
            )
            active_views = []
            for task in active_tasks:
                run = await session.scalar(
                    select(Run)
                    .where(
                        Run.task_id == task.id,
                        Run.tenant_id == resolved.tenant_id,
                        Run.workspace_id == resolved.workspace_id,
                        Run.owner_user_id == resolved.user_id,
                    )
                    .order_by(Run.attempt.desc())
                    .limit(1)
                )
                active_views.append(
                    {
                        "task_id": task.id,
                        "run_id": run.id if run is not None else None,
                        "status": task.status,
                        "symbol": task.request_payload["symbol"],
                        "horizon": task.request_payload["horizon"],
                        "created_at": task.created_at,
                    }
                )
            pending_inbox_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(InterruptPause)
                    .where(
                        InterruptPause.tenant_id == resolved.tenant_id,
                        InterruptPause.workspace_id == resolved.workspace_id,
                        InterruptPause.owner_user_id == resolved.user_id,
                        InterruptPause.status.in_(("pending", "responding")),
                    )
                )
                or 0
            )
            home = {
                "watchlist": [
                    {
                        "symbol": item.symbol,
                        "latest_snapshot": latest_snapshots.get(item.symbol),
                        "created_at": item.created_at,
                    }
                    for item in watchlist
                ],
                "active_tasks": active_views,
                "pending_inbox_count": pending_inbox_count,
            }
        reports = await self.list_artifacts(actor, limit=10)
        home["recent_reports"] = reports["items"]
        return home

    async def set_watchlist_symbol(
        self,
        actor: ActorContext,
        symbol: str,
        *,
        included: bool,
    ) -> dict[str, Any]:
        if symbol not in SUPPORTED_SYMBOLS:
            raise WatchlistSymbolError("Unsupported watchlist symbol.")
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            item = await session.scalar(
                select(WatchlistItem)
                .where(
                    WatchlistItem.tenant_id == resolved.tenant_id,
                    WatchlistItem.workspace_id == resolved.workspace_id,
                    WatchlistItem.owner_user_id == resolved.user_id,
                    WatchlistItem.symbol == symbol,
                )
                .with_for_update()
            )
            if included and item is None:
                session.add(
                    WatchlistItem(
                        id=uuid4(),
                        tenant_id=resolved.tenant_id,
                        workspace_id=resolved.workspace_id,
                        owner_user_id=resolved.user_id,
                        symbol=symbol,
                    )
                )
            elif not included and item is not None:
                await session.delete(item)
        return await self.get_home(actor)

    async def create_analysis(
        self,
        actor: ActorContext,
        submission: AnalysisSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._create_product_task(
            actor,
            submission,
            idempotency_key,
            task_type="market_analysis",
            thread_title=f"{submission.symbol} {submission.horizon} analysis",
        )

    async def create_decision_request(
        self,
        actor: ActorContext,
        submission: DecisionRequestSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        request = submission.to_domain_request(
            actor_id=actor.user_id,
            workspace_id=actor.workspace_id,
        )
        route = route_decision_request(request)
        task = None
        if route.status == "admitted" and route.task_type is not None:
            assert request.symbol is not None
            assert request.horizon is not None
            task = await self._create_product_task(
                actor,
                request,
                idempotency_key,
                task_type=route.task_type,
                thread_title=(
                    f"{request.symbol} {request.horizon} "
                    f"{route.task_type.replace('_', ' ')}"
                ),
            )
        return {
            "request": request,
            "route": route,
            "task": task,
        }

    async def create_deep_research(
        self,
        actor: ActorContext,
        submission: DeepResearchSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._create_product_task(
            actor,
            submission,
            idempotency_key,
            task_type="deep_research",
            thread_title=f"{submission.symbol} {submission.horizon} deep research",
        )

    async def create_monitor(
        self,
        actor: ActorContext,
        submission: MonitorCreateSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        require_monitor_condition_evaluator(submission.condition.kind)
        request_payload = submission.model_dump(mode="json")
        request_hash = _payload_hash(request_payload)
        now = self._now()
        if submission.expires_at is not None and submission.expires_at <= now:
            raise MonitorSourceError("Monitor expiry must be in the future.")
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            repository = MonitorRepository(session, actor)
            existing = await session.scalar(
                select(MonitorDefinition).where(
                    MonitorDefinition.tenant_id == resolved.tenant_id,
                    MonitorDefinition.workspace_id == resolved.workspace_id,
                    MonitorDefinition.owner_user_id == resolved.user_id,
                    MonitorDefinition.admission_idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                try:
                    entitlement = await repository.require_entitlement(now=now)
                except EntitlementDenied as exc:
                    raise MonitorEntitlementError(str(exc)) from exc
                interval = _MONITOR_SCHEDULE_INTERVAL_SECONDS[submission.schedule]
                if interval < entitlement.min_interval_seconds:
                    raise MonitorEntitlementError(
                        "The selected schedule is faster than the workspace entitlement."
                    )
            try:
                monitor = await repository.create_monitor(
                    admission_idempotency_key=idempotency_key,
                    request_payload_hash=request_hash,
                    artifact_id=submission.artifact_id,
                    artifact_version_id=submission.artifact_version_id,
                    name=submission.name,
                    run_task_type=submission.run_task_type,
                    condition=submission.condition.model_dump(mode="json"),
                    cron_schedule=submission.schedule,
                    timezone=submission.timezone,
                    expires_at=submission.expires_at,
                    quiet_hours=(
                        submission.quiet_hours.model_dump(mode="json")
                        if submission.quiet_hours is not None
                        else None
                    ),
                    status="draft",
                    now=now,
                )
            except MonitorIdempotencyConflict as exc:
                raise IdempotencyConflictError(str(exc)) from exc
            except MonitorConditionEvaluatorUnavailableError:
                raise
            except EntitlementDenied as exc:
                raise MonitorEntitlementError(str(exc)) from exc
            except (ValueError, ScopedResourceNotFound) as exc:
                raise MonitorSourceError(str(exc)) from exc

            existing_destinations = {
                item.destination_id
                for item in await repository.destinations.list_for_monitor(monitor.id)
            }
            try:
                for destination_id in submission.destination_ids:
                    if destination_id not in existing_destinations:
                        await repository.add_destination(monitor.id, destination_id)
            except ScopedResourceNotFound as exc:
                raise MonitorSourceError(str(exc)) from exc
            return await _monitor_view(session, resolved, monitor)

    async def list_monitors(
        self,
        actor: ActorContext,
        *,
        status_filter: MonitorStatusFilter,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            statuses = _MONITOR_STATUS_FILTERS[status_filter]
            monitors = list(
                (
                    await session.scalars(
                        select(MonitorDefinition)
                        .where(
                            MonitorDefinition.tenant_id == resolved.tenant_id,
                            MonitorDefinition.workspace_id == resolved.workspace_id,
                            MonitorDefinition.owner_user_id == resolved.user_id,
                            MonitorDefinition.status.in_(statuses),
                        )
                        .order_by(
                            MonitorDefinition.updated_at.desc(),
                            MonitorDefinition.id.desc(),
                        )
                    )
                ).all()
            )
            return {
                "items": [
                    await _monitor_view(session, resolved, monitor)
                    for monitor in monitors
                ]
            }

    async def list_monitor_triggers(
        self,
        actor: ActorContext,
        monitor_id: str,
        *,
        limit: int,
    ) -> dict[str, Any] | None:
        monitor_uuid = _optional_uuid(monitor_id)
        if monitor_uuid is None:
            return None
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            monitor = await session.scalar(
                select(MonitorDefinition).where(
                    MonitorDefinition.id == monitor_uuid,
                    MonitorDefinition.tenant_id == resolved.tenant_id,
                    MonitorDefinition.workspace_id == resolved.workspace_id,
                    MonitorDefinition.owner_user_id == resolved.user_id,
                )
            )
            if monitor is None:
                return None
            triggers = list(
                (
                    await session.scalars(
                        select(MonitorTrigger)
                        .where(
                            MonitorTrigger.tenant_id == resolved.tenant_id,
                            MonitorTrigger.workspace_id == resolved.workspace_id,
                            MonitorTrigger.owner_user_id == resolved.user_id,
                            MonitorTrigger.monitor_id == monitor.id,
                        )
                        .order_by(
                            MonitorTrigger.received_at.desc(),
                            MonitorTrigger.id.desc(),
                        )
                        .limit(limit)
                    )
                ).all()
            )
            return {"items": [_monitor_trigger_view(item) for item in triggers]}

    async def pause_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return await self._change_monitor_status(
            actor,
            monitor_id,
            submission,
            idempotency_key,
            target_status="paused",
            allowed_statuses={"draft", "active", "degraded", "paused"},
        )

    async def resume_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return await self._change_monitor_status(
            actor,
            monitor_id,
            submission,
            idempotency_key,
            target_status="active",
            allowed_statuses={"paused", "degraded", "active"},
        )

    async def disable_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return await self._change_monitor_status(
            actor,
            monitor_id,
            submission,
            idempotency_key,
            target_status="disabled",
            allowed_statuses={
                "draft",
                "active",
                "paused",
                "degraded",
                "expired",
                "disabled",
            },
        )

    async def _change_monitor_status(
        self,
        actor: ActorContext,
        monitor_id: str,
        submission: MonitorMutationSubmission,
        idempotency_key: str,
        *,
        target_status: str,
        allowed_statuses: set[str],
    ) -> dict[str, Any] | None:
        monitor_uuid = _optional_uuid(monitor_id)
        if monitor_uuid is None:
            return None
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            repository = MonitorRepository(session, actor)
            current = await repository.get(monitor_uuid)
            if current is None:
                return None
            if current.status not in allowed_statuses:
                raise MonitorConflictError(
                    f"Monitor cannot transition from {current.status} to {target_status}."
                )
            try:
                if target_status == "paused":
                    monitor = await repository.pause_monitor(
                        monitor_uuid,
                        expected_version=submission.expected_version,
                        operation_idempotency_key=idempotency_key,
                    )
                elif target_status == "active":
                    monitor = await repository.resume_monitor(
                        monitor_uuid,
                        expected_version=submission.expected_version,
                        operation_idempotency_key=idempotency_key,
                    )
                else:
                    monitor = await repository.delete_monitor(
                        monitor_uuid,
                        expected_version=submission.expected_version,
                        operation_idempotency_key=idempotency_key,
                    )
            except MonitorVersionConflict as exc:
                raise MonitorConflictError(str(exc)) from exc
            except MonitorIdempotencyConflict as exc:
                raise IdempotencyConflictError(str(exc)) from exc
            except EntitlementDenied as exc:
                raise MonitorEntitlementError(str(exc)) from exc
            await session.refresh(monitor)
            return await _monitor_view(session, resolved, monitor)

    async def trigger_monitor(
        self,
        actor: ActorContext,
        monitor_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        monitor_uuid = _optional_uuid(monitor_id)
        if monitor_uuid is None:
            return None
        stable_key = (
            "manual:"
            + sha256(f"{monitor_uuid}\0{idempotency_key}".encode("utf-8")).hexdigest()
        )
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            repository = MonitorRepository(session, actor)
            monitor = await repository.get(monitor_uuid)
            if monitor is None:
                return None
            await repository.admit_trigger(
                monitor_uuid,
                kind="manual",
                manual_stable_key=stable_key,
                schedule_version=monitor.schedule_version,
                received_at=self._now(),
            )
            return await _monitor_view(session, resolved, monitor)

    async def _create_product_task(
        self,
        actor: ActorContext,
        submission: AnalysisSubmission | DeepResearchSubmission | DecisionRequest,
        idempotency_key: str,
        *,
        task_type: str,
        thread_title: str,
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

                task_id = uuid4()
                await UsageGovernanceRepository(session, resolved).admit_agent(
                    task_type=task_type,
                    resource_type="task",
                    resource_id=str(task_id),
                    idempotency_key=f"agent-admission:{task_id}",
                    now=self._now(),
                )
                thread = Thread(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    owner_user_id=resolved.user_id,
                    title=thread_title,
                    context={},
                )
                session.add(thread)
                await session.flush()
                task = Task(
                    id=task_id,
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    owner_user_id=resolved.user_id,
                    thread_id=thread.id,
                    task_type=task_type,
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
                latest_run.cancel_requested_at = self._now()

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

    async def cancel_run(
        self,
        actor: ActorContext,
        run_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        try:
            run_uuid = UUID(run_id)
        except ValueError:
            return None
        command_idempotency_key = (
            f"cancel-run:{run_uuid}:{sha256(idempotency_key.encode()).hexdigest()}"
        )
        payload = {"run_id": str(run_uuid)}
        payload_hash = _payload_hash(payload)
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            run = await session.scalar(
                select(Run)
                .where(
                    Run.id == run_uuid,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if run is None:
                return None
            task = await session.scalar(
                select(Task)
                .where(
                    Task.id == run.task_id,
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
                return await _task_view(
                    session,
                    resolved,
                    task,
                    selected_run_id=run.id,
                )
            if run.status in {"succeeded", "blocked", "failed", "cancelled"}:
                raise RunNotCancellableError(
                    "Only queued, running, or waiting runs can be cancelled."
                )
            if any(
                command.command_type == "cancel_task"
                and command.status in {"pending", "dispatching"}
                for command in commands
            ):
                raise RunNotCancellableError(
                    "Task cancellation is already pending for this Run."
                )
            if any(
                command.command_type == "cancel_run"
                and command.status in {"pending", "dispatching"}
                and command.payload.get("run_id") == str(run.id)
                for command in commands
            ):
                return await _task_view(
                    session,
                    resolved,
                    task,
                    selected_run_id=run.id,
                )

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

            run.cancel_requested_at = self._now()
            session.add(
                TaskCommand(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    actor_user_id=resolved.user_id,
                    task_id=task.id,
                    thread_id=task.thread_id,
                    command_type="cancel_run",
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
            return await _task_view(
                session,
                resolved,
                task,
                selected_run_id=run.id,
            )

    async def retry_task(
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
            f"retry:{task_uuid}:{sha256(idempotency_key.encode()).hexdigest()}"
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
                retry_run_id = replay.payload.get("retry_run_id")
                selected_run_id = (
                    UUID(retry_run_id) if isinstance(retry_run_id, str) else None
                )
                return await _task_view(
                    session,
                    resolved,
                    task,
                    selected_run_id=selected_run_id,
                )

            source_run = await session.scalar(
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
            cancelled_run_is_retryable = (
                task.status == "cancelled"
                and source_run is not None
                and source_run.status == "cancelled"
                and any(
                    command.command_type == "cancel_run"
                    and command.status == "dispatched"
                    and command.payload.get("run_id") == str(source_run.id)
                    for command in commands
                )
            )
            if (
                task.status not in {"failed", "blocked"}
                and not cancelled_run_is_retryable
            ):
                raise TaskNotRetryableError(
                    "Only failed, blocked, or Run-cancelled tasks can be retried."
                )
            if any(
                command.status in {"pending", "dispatching"} for command in commands
            ):
                raise TaskNotRetryableError(
                    "Task already has a command awaiting dispatch or reconciliation."
                )

            if source_run is None or source_run.status not in {
                "failed",
                "blocked",
                "cancelled",
            }:
                raise TaskNotRetryableError("The latest terminal Run is not retryable.")

            latest_attempt = await session.scalar(
                select(func.coalesce(func.max(Run.attempt), 0)).where(
                    Run.task_id == task.id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
            )
            retry_run = Run(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                attempt=int(latest_attempt or 0) + 1,
                status="queued",
                input_payload=source_run.input_payload,
                retry_of_run_id=source_run.id,
            )
            command_payload = {
                "source_run_id": str(source_run.id),
                "retry_run_id": str(retry_run.id),
            }
            session.add(retry_run)
            await session.flush()
            session.add(
                TaskCommand(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    actor_user_id=resolved.user_id,
                    task_id=task.id,
                    thread_id=task.thread_id,
                    command_type="retry",
                    payload=command_payload,
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
            task.status = "queued"
            task.completed_at = None
            await session.flush()
            return await _task_view(
                session,
                resolved,
                task,
                selected_run_id=retry_run.id,
            )

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
                same_checkpoint = submission.checkpoint_id is None or (
                    isinstance(replay_checkpoint_id, str)
                    and hmac.compare_digest(
                        replay_checkpoint_id,
                        submission.checkpoint_id,
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
                command.status in {"pending", "dispatching"} for command in commands
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
                select(Task).where(
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
                        select(InterruptProjection.id).where(
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
                raise InterruptResponseConflictError(
                    "Interrupt pause version is stale."
                )

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
                payload = parse_review_interrupt_payload(projection.payload)
                validate_review_payload_for_task(
                    payload,
                    task_type=task.task_type,
                    symbol=task.request_payload["symbol"],
                    horizon=task.request_payload["horizon"],
                )
                validated_response = validate_review_response_for_payload(
                    payload,
                    ReviewResponse.model_validate(item.response),
                )
                response = validated_response.model_dump(
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
            now = self._now()
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

    async def respond_inbox_review(
        self,
        actor: ActorContext,
        pause_id: UUID,
        submission: InboxReviewSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            pause = await session.scalar(
                select(InterruptPause).where(
                    InterruptPause.id == pause_id,
                    InterruptPause.tenant_id == resolved.tenant_id,
                    InterruptPause.workspace_id == resolved.workspace_id,
                    InterruptPause.owner_user_id == resolved.user_id,
                )
            )
            if pause is None:
                return None
            projections = list(
                (
                    await session.scalars(
                        select(InterruptProjection)
                        .where(
                            InterruptProjection.pause_id == pause.id,
                            InterruptProjection.task_id == pause.task_id,
                            InterruptProjection.tenant_id == resolved.tenant_id,
                            InterruptProjection.workspace_id == resolved.workspace_id,
                            InterruptProjection.owner_user_id == resolved.user_id,
                        )
                        .order_by(InterruptProjection.id)
                    )
                ).all()
            )
            if not projections:
                raise InterruptResponseConflictError(
                    "Inbox review has no registered members."
                )
            if len(projections) != 1:
                raise InterruptBatchRequiredError(
                    "This Inbox review has multiple members and must be handled in Work."
                )
            if pause.pause_version != submission.pause_version:
                raise InterruptResponseConflictError(
                    "Interrupt pause version is stale."
                )
            projection = projections[0]
            task_id = str(pause.task_id)
            aggregate = InterruptResponsesSubmission.model_validate(
                {
                    "pause_id": pause.id,
                    "pause_version": pause.pause_version,
                    "responses": [
                        {
                            "interrupt_id": projection.official_interrupt_id,
                            "response_version": projection.response_version,
                            "response": submission.response,
                        }
                    ],
                }
            )

        accepted = await self.respond_interrupts(
            actor,
            task_id,
            aggregate,
            idempotency_key,
        )
        if accepted is None:
            return None

        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            pause = await session.scalar(
                select(InterruptPause).where(
                    InterruptPause.id == pause_id,
                    InterruptPause.tenant_id == resolved.tenant_id,
                    InterruptPause.workspace_id == resolved.workspace_id,
                    InterruptPause.owner_user_id == resolved.user_id,
                )
            )
            if pause is None:
                return None
            responded_at = await session.scalar(
                select(func.max(InterruptProjection.responded_at)).where(
                    InterruptProjection.pause_id == pause.id,
                    InterruptProjection.task_id == pause.task_id,
                    InterruptProjection.tenant_id == resolved.tenant_id,
                    InterruptProjection.workspace_id == resolved.workspace_id,
                    InterruptProjection.owner_user_id == resolved.user_id,
                )
            )
            if responded_at is None:
                raise InterruptResponseConflictError(
                    "Inbox review response was not persisted."
                )
            return {
                "task_id": task_id,
                "pause_id": pause.id,
                "pause_version": pause.pause_version,
                "status": pause.status,
                "responded_at": responded_at,
            }

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
                        "task_type": task.task_type,
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

    async def get_run(
        self,
        actor: ActorContext,
        run_id: str,
    ) -> dict[str, Any] | None:
        try:
            run_uuid = UUID(run_id)
        except ValueError:
            return None
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            row = (
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
                        Run.id == run_uuid,
                        Run.tenant_id == resolved.tenant_id,
                        Run.workspace_id == resolved.workspace_id,
                        Run.owner_user_id == resolved.user_id,
                        Task.tenant_id == resolved.tenant_id,
                        Task.workspace_id == resolved.workspace_id,
                        Task.owner_user_id == resolved.user_id,
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            run, task = row
            run_projection = await _task_view(
                session,
                resolved,
                task,
                selected_run_id=run.id,
            )
            task_view = await _task_view(session, resolved, task)
            current_run_id = await session.scalar(
                select(Run.id)
                .where(
                    Run.task_id == task.id,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
                .order_by(Run.attempt.desc())
                .limit(1)
            )
            feedback = await session.scalar(
                select(Feedback).where(
                    Feedback.tenant_id == resolved.tenant_id,
                    Feedback.workspace_id == resolved.workspace_id,
                    Feedback.owner_user_id == resolved.user_id,
                    Feedback.task_id == task.id,
                    Feedback.run_id == run.id,
                )
            )
            return {
                "run": {
                    "run_id": str(run.id),
                    "task_id": str(task.id),
                    "task_type": task.task_type,
                    "attempt": run.attempt,
                    "status": run.status,
                    "symbol": task.request_payload["symbol"],
                    "horizon": task.request_payload["horizon"],
                    "created_at": run.created_at,
                    "finished_at": run.finished_at,
                    "main_action": _run_main_action(run),
                },
                "task": task_view,
                "run_projection": run_projection,
                "is_current_run": current_run_id == run.id,
                "feedback": _feedback_view(feedback),
            }

    async def submit_feedback(
        self,
        actor: ActorContext,
        run_id: str,
        submission: FeedbackSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        try:
            run_uuid = UUID(run_id)
        except ValueError:
            return None
        feedback_key = (
            f"feedback:{run_uuid}:{sha256(idempotency_key.encode()).hexdigest()}"
        )
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            run = await session.scalar(
                select(Run)
                .where(
                    Run.id == run_uuid,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if run is None:
                return None
            existing = await session.scalar(
                select(Feedback).where(
                    Feedback.workspace_id == resolved.workspace_id,
                    Feedback.idempotency_key == feedback_key,
                )
            )
            if existing is not None:
                return _feedback_view(existing) or {}
            existing_for_run = await session.scalar(
                select(Feedback).where(
                    Feedback.tenant_id == resolved.tenant_id,
                    Feedback.workspace_id == resolved.workspace_id,
                    Feedback.owner_user_id == resolved.user_id,
                    Feedback.run_id == run.id,
                )
            )
            if existing_for_run is not None:
                raise FeedbackConflictError(
                    "Feedback has already been recorded for this Run."
                )
            artifact_version_id = await session.scalar(
                select(ArtifactVersion.id)
                .where(
                    ArtifactVersion.tenant_id == resolved.tenant_id,
                    ArtifactVersion.workspace_id == resolved.workspace_id,
                    ArtifactVersion.owner_user_id == resolved.user_id,
                    ArtifactVersion.task_id == run.task_id,
                    ArtifactVersion.run_id == run.id,
                )
                .order_by(ArtifactVersion.version_number.desc())
                .limit(1)
            )
            feedback = Feedback(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                task_id=run.task_id,
                run_id=run.id,
                artifact_version_id=artifact_version_id,
                rating=submission.rating,
                comment=submission.comment,
                idempotency_key=feedback_key,
            )
            session.add(feedback)
            await session.flush()
            if feedback.rating == "negative":
                source_payload = {
                    "feedback_id": str(feedback.id),
                    "run_id": str(run.id),
                    "task_id": str(run.task_id),
                    "artifact_version_id": (
                        str(artifact_version_id)
                        if artifact_version_id is not None
                        else None
                    ),
                    "rating": feedback.rating,
                    "comment": feedback.comment,
                }
                session.add(
                    PostmortemCase(
                        id=uuid4(),
                        tenant_id=resolved.tenant_id,
                        workspace_id=resolved.workspace_id,
                        owner_user_id=resolved.user_id,
                        feedback_id=feedback.id,
                        task_id=run.task_id,
                        run_id=run.id,
                        artifact_version_id=artifact_version_id,
                        category="negative_feedback",
                        status="open",
                        title="Negative feedback badcase",
                        summary=feedback.comment or (
                            "The operator marked this persisted run as needing improvement."
                        ),
                        root_cause=None,
                        expected_behavior=None,
                        actual_behavior=None,
                        source_hash=_payload_hash(source_payload),
                        idempotency_key=f"postmortem:feedback:{feedback.id}",
                    )
                )
                await session.flush()
            return _feedback_view(feedback) or {}

    async def create_postmortem(
        self,
        actor: ActorContext,
        run_id: str,
        submission: PostmortemSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        run_uuid = _optional_uuid(run_id)
        if run_uuid is None:
            return None
        operation_key = (
            f"postmortem:{run_uuid}:{sha256(idempotency_key.encode()).hexdigest()}"
        )
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            run = await session.scalar(
                select(Run).where(
                    Run.id == run_uuid,
                    Run.tenant_id == resolved.tenant_id,
                    Run.workspace_id == resolved.workspace_id,
                    Run.owner_user_id == resolved.user_id,
                )
            )
            if run is None:
                return None
            artifact_version_id = await session.scalar(
                select(ArtifactVersion.id)
                .where(
                    ArtifactVersion.tenant_id == resolved.tenant_id,
                    ArtifactVersion.workspace_id == resolved.workspace_id,
                    ArtifactVersion.owner_user_id == resolved.user_id,
                    ArtifactVersion.task_id == run.task_id,
                    ArtifactVersion.run_id == run.id,
                )
                .order_by(ArtifactVersion.version_number.desc())
                .limit(1)
            )
            source_payload = {
                "run_id": str(run.id),
                "task_id": str(run.task_id),
                "artifact_version_id": (
                    str(artifact_version_id)
                    if artifact_version_id is not None
                    else None
                ),
                **submission.model_dump(mode="json"),
            }
            source_hash = _payload_hash(source_payload)
            existing = await session.scalar(
                select(PostmortemCase).where(
                    PostmortemCase.tenant_id == resolved.tenant_id,
                    PostmortemCase.workspace_id == resolved.workspace_id,
                    PostmortemCase.owner_user_id == resolved.user_id,
                    PostmortemCase.idempotency_key == operation_key,
                )
            )
            if existing is not None:
                if existing.source_hash != source_hash:
                    raise IdempotencyConflictError(
                        "Postmortem idempotency key conflicts with its payload."
                    )
                replay = await session.scalar(
                    select(FrozenReplayRecord).where(
                        FrozenReplayRecord.postmortem_id == existing.id
                    )
                )
                return _postmortem_view(existing, replay)
            case = PostmortemCase(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                feedback_id=None,
                task_id=run.task_id,
                run_id=run.id,
                artifact_version_id=artifact_version_id,
                category=submission.category,
                status="open",
                title=submission.title,
                summary=submission.summary,
                root_cause=submission.root_cause,
                expected_behavior=submission.expected_behavior,
                actual_behavior=submission.actual_behavior,
                source_hash=source_hash,
                idempotency_key=operation_key,
            )
            session.add(case)
            await session.flush()
            return _postmortem_view(case)

    async def list_postmortems(
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
                    select(PostmortemCase, FrozenReplayRecord)
                    .outerjoin(
                        FrozenReplayRecord,
                        FrozenReplayRecord.postmortem_id == PostmortemCase.id,
                    )
                    .where(
                        PostmortemCase.tenant_id == resolved.tenant_id,
                        PostmortemCase.workspace_id == resolved.workspace_id,
                        PostmortemCase.owner_user_id == resolved.user_id,
                    )
                    .order_by(PostmortemCase.created_at.desc(), PostmortemCase.id.desc())
                    .limit(limit)
                )
            ).all()
            return {
                "items": [_postmortem_view(case, replay) for case, replay in rows],
                "limit": limit,
            }

    async def freeze_postmortem(
        self,
        actor: ActorContext,
        postmortem_id: str,
    ) -> dict[str, Any] | None:
        case_uuid = _optional_uuid(postmortem_id)
        if case_uuid is None:
            return None
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            case = await session.scalar(
                select(PostmortemCase)
                .where(
                    PostmortemCase.id == case_uuid,
                    PostmortemCase.tenant_id == resolved.tenant_id,
                    PostmortemCase.workspace_id == resolved.workspace_id,
                    PostmortemCase.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if case is None:
                return None
            existing = await session.scalar(
                select(FrozenReplayRecord).where(
                    FrozenReplayRecord.postmortem_id == case.id
                )
            )
            if existing is not None:
                return _postmortem_view(case, existing)

            task = await session.scalar(select(Task).where(Task.id == case.task_id))
            run = await session.scalar(select(Run).where(Run.id == case.run_id))
            if task is None or run is None:
                raise RuntimeError("Postmortem source Task or Run is unavailable")
            artifact_version = (
                await session.scalar(
                    select(ArtifactVersion).where(
                        ArtifactVersion.id == case.artifact_version_id
                    )
                )
                if case.artifact_version_id is not None
                else None
            )
            market = await session.scalar(
                select(PersistedMarketSnapshot)
                .where(PersistedMarketSnapshot.run_id == run.id)
                .order_by(PersistedMarketSnapshot.fetched_at.desc())
                .limit(1)
            )
            evidence_rows = list(
                (
                    await session.scalars(
                        select(PersistedWebEvidence)
                        .where(PersistedWebEvidence.run_id == run.id)
                        .order_by(PersistedWebEvidence.created_at, PersistedWebEvidence.id)
                    )
                ).all()
            )
            decision = await session.scalar(
                select(Decision).where(Decision.run_id == run.id)
            )
            packet = freeze_replay_packet(
                request=task.request_payload,
                versions={
                    "task_type": task.task_type,
                    "run_attempt": run.attempt,
                    "artifact_schema_version": (
                        artifact_version.schema_version
                        if artifact_version is not None
                        else None
                    ),
                    "artifact_version_number": (
                        artifact_version.version_number
                        if artifact_version is not None
                        else None
                    ),
                },
                market=(market.snapshot if market is not None else {}),
                evidence=tuple(
                    {
                        **row.payload,
                        "source_url": row.source_url,
                        "title": row.title,
                        "fetched_at": row.fetched_at.isoformat(),
                        "published_at": (
                            row.published_at.isoformat()
                            if row.published_at is not None
                            else None
                        ),
                    }
                    for row in evidence_rows
                ),
                gates={
                    "evidence": (
                        decision.evidence_verdict if decision is not None else {}
                    ),
                    "risk": decision.risk_verdict if decision is not None else {},
                },
                observed_output={
                    "terminal_status": run.status,
                    "main_action": (
                        decision.decision.get("main_action")
                        if decision is not None
                        else _run_main_action(run)
                    ),
                    "artifact": (
                        artifact_version.content if artifact_version is not None else None
                    ),
                    "failure_code": run.failure_code,
                },
            )
            metrics = rule_judge(packet)
            record = FrozenReplayRecord(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                postmortem_id=case.id,
                task_id=case.task_id,
                run_id=case.run_id,
                artifact_version_id=case.artifact_version_id,
                schema_version=packet.schema_version,
                packet=packet.model_dump(mode="json"),
                source_hash=packet.source_hash,
                rule_metrics=metrics.model_dump(mode="json"),
            )
            session.add(record)
            case.status = "frozen"
            await session.flush()
            await session.refresh(case)
            await session.refresh(record)
            return _postmortem_view(case, record)

    async def create_improvement_dataset(
        self,
        actor: ActorContext,
        submission: ImprovementDatasetSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            replay_rows = list(
                (
                    await session.scalars(
                        select(FrozenReplayRecord)
                        .where(
                            FrozenReplayRecord.id.in_(submission.replay_ids),
                            FrozenReplayRecord.tenant_id == resolved.tenant_id,
                            FrozenReplayRecord.workspace_id == resolved.workspace_id,
                            FrozenReplayRecord.owner_user_id == resolved.user_id,
                        )
                        .order_by(FrozenReplayRecord.created_at, FrozenReplayRecord.id)
                    )
                ).all()
            )
            if len(replay_rows) != len(submission.replay_ids):
                return None
            source_payload = {
                "name": submission.name,
                "replays": [
                    {"id": str(row.id), "source_hash": row.source_hash}
                    for row in replay_rows
                ],
            }
            source_hash = _payload_hash(source_payload)
            operation_key = (
                f"dataset:{sha256(idempotency_key.encode()).hexdigest()}"
            )
            existing = await session.scalar(
                select(ImprovementDataset).where(
                    ImprovementDataset.tenant_id == resolved.tenant_id,
                    ImprovementDataset.workspace_id == resolved.workspace_id,
                    ImprovementDataset.owner_user_id == resolved.user_id,
                    ImprovementDataset.idempotency_key == operation_key,
                )
            )
            if existing is not None:
                if existing.source_hash != source_hash:
                    raise IdempotencyConflictError(
                        "Improvement Dataset idempotency key conflicts with its payload."
                    )
                members = list(
                    (
                        await session.scalars(
                            select(ImprovementDatasetMember)
                            .where(ImprovementDatasetMember.dataset_id == existing.id)
                            .order_by(ImprovementDatasetMember.ordinal)
                        )
                    ).all()
                )
                return _improvement_dataset_view(existing, members)
            dataset = ImprovementDataset(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                name=submission.name,
                status="frozen",
                source_hash=source_hash,
                idempotency_key=operation_key,
                frozen_at=self._now(),
            )
            session.add(dataset)
            await session.flush()
            members: list[ImprovementDatasetMember] = []
            for ordinal, row in enumerate(replay_rows, start=1):
                member = ImprovementDatasetMember(
                    id=uuid4(),
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    owner_user_id=resolved.user_id,
                    dataset_id=dataset.id,
                    replay_id=row.id,
                    case_name=f"frozen-{ordinal:03d}",
                    ordinal=ordinal,
                    source_hash=row.source_hash,
                )
                members.append(member)
                session.add(member)
            await session.flush()
            await session.refresh(dataset)
            for member in members:
                await session.refresh(member)
            return _improvement_dataset_view(dataset, members)

    async def list_improvement_datasets(
        self,
        actor: ActorContext,
        *,
        limit: int,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            datasets = list(
                (
                    await session.scalars(
                        select(ImprovementDataset)
                        .where(
                            ImprovementDataset.tenant_id == resolved.tenant_id,
                            ImprovementDataset.workspace_id == resolved.workspace_id,
                            ImprovementDataset.owner_user_id == resolved.user_id,
                        )
                        .order_by(
                            ImprovementDataset.created_at.desc(),
                            ImprovementDataset.id.desc(),
                        )
                        .limit(limit)
                    )
                ).all()
            )
            items: list[dict[str, Any]] = []
            for dataset in datasets:
                members = list(
                    (
                        await session.scalars(
                            select(ImprovementDatasetMember)
                            .where(ImprovementDatasetMember.dataset_id == dataset.id)
                            .order_by(ImprovementDatasetMember.ordinal)
                        )
                    ).all()
                )
                items.append(_improvement_dataset_view(dataset, members))
            return {"items": items, "limit": limit}

    async def create_improvement_candidate(
        self,
        actor: ActorContext,
        submission: ImprovementCandidateSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        candidate = RuleCandidate.create(
            name=submission.name,
            base_version=submission.base_version,
            candidate_version=submission.candidate_version,
            rollback_target_version=submission.rollback_target_version,
            rationale=submission.rationale,
            diff=submission.diff,
        )
        operation_key = f"candidate:{sha256(idempotency_key.encode()).hexdigest()}"
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            existing = await session.scalar(
                select(ImprovementCandidate).where(
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                    ImprovementCandidate.idempotency_key == operation_key,
                )
            )
            if existing is not None:
                if existing.version_hash != candidate.version_hash:
                    raise IdempotencyConflictError(
                        "Improvement Candidate idempotency key conflicts with its payload."
                    )
                return _improvement_candidate_view(existing)
            record = ImprovementCandidate(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                name=candidate.name,
                base_version=candidate.base_version,
                candidate_version=candidate.candidate_version,
                rollback_target_version=candidate.rollback_target_version,
                rationale=candidate.rationale,
                diff=dict(candidate.diff),
                version_hash=candidate.version_hash,
                status=CandidateStatus.DRAFT.value,
                idempotency_key=operation_key,
            )
            session.add(record)
            await session.flush()
            await session.refresh(record)
            return _improvement_candidate_view(record)

    async def list_improvement_candidates(
        self,
        actor: ActorContext,
        *,
        limit: int,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            candidates = list(
                (
                    await session.scalars(
                        select(ImprovementCandidate)
                        .where(
                            ImprovementCandidate.tenant_id == resolved.tenant_id,
                            ImprovementCandidate.workspace_id == resolved.workspace_id,
                            ImprovementCandidate.owner_user_id == resolved.user_id,
                        )
                        .order_by(
                            ImprovementCandidate.created_at.desc(),
                            ImprovementCandidate.id.desc(),
                        )
                        .limit(limit)
                    )
                ).all()
            )
            items: list[dict[str, Any]] = []
            for candidate in candidates:
                latest = await session.scalar(
                    select(ImprovementExperiment)
                    .where(ImprovementExperiment.candidate_id == candidate.id)
                    .order_by(
                        ImprovementExperiment.created_at.desc(),
                        ImprovementExperiment.id.desc(),
                    )
                    .limit(1)
                )
                review = await session.scalar(
                    select(ImprovementReview).where(
                        ImprovementReview.candidate_id == candidate.id
                    )
                )
                shadow = await session.scalar(
                    select(ImprovementShadowRun)
                    .where(ImprovementShadowRun.candidate_id == candidate.id)
                    .order_by(ImprovementShadowRun.created_at.desc())
                    .limit(1)
                )
                release_events = list(
                    (
                        await session.scalars(
                            select(ImprovementReleaseEvent)
                            .where(ImprovementReleaseEvent.candidate_id == candidate.id)
                            .order_by(ImprovementReleaseEvent.created_at)
                        )
                    ).all()
                )
                items.append(
                    _improvement_candidate_view(
                        candidate,
                        latest,
                        review,
                        shadow,
                        release_events,
                    )
                )
            return {"items": items, "limit": limit}

    async def run_improvement_experiment(
        self,
        actor: ActorContext,
        candidate_id: UUID,
        submission: ImprovementExperimentSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        operation_key = f"experiment:{sha256(idempotency_key.encode()).hexdigest()}"
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            candidate = await session.scalar(
                select(ImprovementCandidate)
                .where(
                    ImprovementCandidate.id == candidate_id,
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            dataset = await session.scalar(
                select(ImprovementDataset).where(
                    ImprovementDataset.id == submission.dataset_id,
                    ImprovementDataset.tenant_id == resolved.tenant_id,
                    ImprovementDataset.workspace_id == resolved.workspace_id,
                    ImprovementDataset.owner_user_id == resolved.user_id,
                    ImprovementDataset.status == "frozen",
                )
            )
            if candidate is None or dataset is None:
                return None
            existing = await session.scalar(
                select(ImprovementExperiment).where(
                    ImprovementExperiment.tenant_id == resolved.tenant_id,
                    ImprovementExperiment.workspace_id == resolved.workspace_id,
                    ImprovementExperiment.owner_user_id == resolved.user_id,
                    ImprovementExperiment.idempotency_key == operation_key,
                )
            )
            if existing is not None:
                return _improvement_candidate_view(candidate, existing)
            members = list(
                (
                    await session.scalars(
                        select(ImprovementDatasetMember)
                        .where(
                            ImprovementDatasetMember.dataset_id == dataset.id,
                            ImprovementDatasetMember.tenant_id == resolved.tenant_id,
                            ImprovementDatasetMember.workspace_id == resolved.workspace_id,
                            ImprovementDatasetMember.owner_user_id == resolved.user_id,
                        )
                        .order_by(ImprovementDatasetMember.ordinal)
                    )
                ).all()
            )
            replay_rows = list(
                (
                    await session.scalars(
                        select(FrozenReplayRecord).where(
                            FrozenReplayRecord.id.in_(
                                [member.replay_id for member in members]
                            ),
                            FrozenReplayRecord.tenant_id == resolved.tenant_id,
                            FrozenReplayRecord.workspace_id == resolved.workspace_id,
                            FrozenReplayRecord.owner_user_id == resolved.user_id,
                        )
                    )
                ).all()
            )
            replay_by_id = {row.id: row for row in replay_rows}
            if len(replay_by_id) != len(members):
                raise RuntimeError("Improvement Dataset contains unavailable replays")
            frozen_cases = tuple(
                (
                    member.case_name,
                    FrozenReplayPacket.model_validate(replay_by_id[member.replay_id].packet),
                )
                for member in members
            )
            candidate_domain = RuleCandidate.create(
                name=candidate.name,
                base_version=candidate.base_version,
                candidate_version=candidate.candidate_version,
                rollback_target_version=candidate.rollback_target_version,
                rationale=candidate.rationale,
                diff=candidate.diff,
            )
            result = run_frozen_rule_experiment(
                frozen_cases,
                candidate=candidate_domain,
                prompt_version=submission.prompt_version,
                git_revision=submission.git_revision,
            )
            minimum_scores = candidate.diff.get("minimum_scores", {})
            thresholds = {
                metric: float(minimum_scores.get(metric, 1.0))
                for metric in ("structure", "evidence", "risk", "product_output")
            }
            gate = evaluate_release_gate(
                result,
                thresholds=thresholds,
                expected_case_names=[member.case_name for member in members],
            )
            case_results = [
                {"case_name": item.case_name, "scores": item.scores}
                for item in result.case_results
            ]
            gate_report = {
                "approved": gate.approved,
                "reasons": list(gate.reasons),
                "metrics": gate.metrics,
                "thresholds": gate.thresholds,
                "prompt_version": gate.prompt_version,
                "git_revision": gate.git_revision,
            }
            source_hash = _payload_hash(
                {
                    "candidate": candidate.version_hash,
                    "dataset": dataset.source_hash,
                    "prompt_version": submission.prompt_version,
                    "git_revision": submission.git_revision,
                    "gate": gate_report,
                }
            )
            experiment = ImprovementExperiment(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                dataset_id=dataset.id,
                candidate_id=candidate.id,
                status="succeeded" if gate.approved else "failed",
                prompt_version=submission.prompt_version,
                git_revision=submission.git_revision,
                case_results=case_results,
                metrics=result.metrics,
                gate_report=gate_report,
                source_hash=source_hash,
                idempotency_key=operation_key,
                completed_at=self._now(),
            )
            session.add(experiment)
            if candidate.status == CandidateStatus.DRAFT.value:
                candidate.status = transition_candidate(
                    CandidateStatus.DRAFT, CandidateStatus.EVALUATED
                ).value
            elif candidate.status != CandidateStatus.EVALUATED.value:
                raise ValueError(
                    "only draft or evaluated candidates can run a frozen experiment"
                )
            await session.flush()
            await session.refresh(candidate)
            await session.refresh(experiment)
            return _improvement_candidate_view(candidate, experiment)

    async def request_improvement_review(
        self,
        actor: ActorContext,
        candidate_id: UUID,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if self._candidate_review_runtime is None:
            raise CandidateReviewUnavailableError(
                "Candidate review runtime is not configured."
            )
        operation_key = f"candidate-review:{sha256(idempotency_key.encode()).hexdigest()}"
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            candidate = await session.scalar(
                select(ImprovementCandidate)
                .where(
                    ImprovementCandidate.id == candidate_id,
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if candidate is None:
                return None
            experiment = await session.scalar(
                select(ImprovementExperiment)
                .where(ImprovementExperiment.candidate_id == candidate.id)
                .order_by(
                    ImprovementExperiment.created_at.desc(),
                    ImprovementExperiment.id.desc(),
                )
                .limit(1)
            )
            if (
                experiment is None
                or experiment.status != "succeeded"
                or not bool(experiment.gate_report.get("approved"))
            ):
                raise ValueError(
                    "Candidate review requires a passing frozen Release Gate."
                )
            review = await session.scalar(
                select(ImprovementReview)
                .where(ImprovementReview.candidate_id == candidate.id)
                .with_for_update()
            )
            if review is None:
                if candidate.status != CandidateStatus.EVALUATED.value:
                    raise ValueError(
                        "only evaluated candidates can request human review"
                    )
                review_id_value = uuid4()
                await UsageGovernanceRepository(session, resolved).admit_agent(
                    task_type="candidate_review",
                    resource_type="improvement_review",
                    resource_id=str(review_id_value),
                    idempotency_key=(
                        f"candidate-review-admission:{review_id_value}"
                    ),
                    now=self._now(),
                )
                review = ImprovementReview(
                    id=review_id_value,
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    owner_user_id=resolved.user_id,
                    candidate_id=candidate.id,
                    task_id=None,
                    run_id=None,
                    interrupt_pause_id=None,
                    reviewer_user_id=None,
                    status="pending",
                    idempotency_key=operation_key,
                    response=None,
                    decided_at=None,
                )
                candidate.status = transition_candidate(
                    CandidateStatus.EVALUATED, CandidateStatus.PENDING_REVIEW
                ).value
                session.add(review)
                await session.flush()
                await session.refresh(candidate)
                await session.refresh(review)
            elif review.idempotency_key != operation_key:
                raise IdempotencyConflictError(
                    "Candidate already has a review under another idempotency key."
                )
            if review.official_interrupt_id is not None:
                return _improvement_candidate_view(candidate, experiment, review)
            review_id = str(review.id)
            candidate_version = candidate.candidate_version
            rationale = candidate.rationale

        receipt = await self._candidate_review_runtime.start(
            actor=actor,
            review_id=review_id,
            candidate_id=str(candidate_id),
            candidate_version=candidate_version,
            rationale=rationale,
        )
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            candidate = await session.scalar(
                select(ImprovementCandidate).where(
                    ImprovementCandidate.id == candidate_id,
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                )
            )
            review = await session.scalar(
                select(ImprovementReview)
                .where(
                    ImprovementReview.id == UUID(review_id),
                    ImprovementReview.candidate_id == candidate_id,
                    ImprovementReview.tenant_id == resolved.tenant_id,
                    ImprovementReview.workspace_id == resolved.workspace_id,
                    ImprovementReview.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if candidate is None or review is None or review.status != "pending":
                raise RuntimeError("Candidate review changed while Aegra was starting")
            review.official_assistant_id = receipt.handle.assistant_id
            review.official_thread_id = receipt.handle.thread_id
            review.official_run_id = receipt.handle.run_id
            review.official_interrupt_id = receipt.interrupt.interrupt_id
            review.interrupt_payload = receipt.interrupt.value
            review.checkpoint = {
                "thread_id": receipt.checkpoint.thread_id,
                "checkpoint_ns": receipt.checkpoint.checkpoint_ns,
                "checkpoint_id": receipt.checkpoint.checkpoint_id,
                "checkpoint_map": receipt.checkpoint.checkpoint_map,
            }
            await session.flush()
            await session.refresh(review)
            experiment = await session.scalar(
                select(ImprovementExperiment)
                .where(ImprovementExperiment.candidate_id == candidate.id)
                .order_by(ImprovementExperiment.created_at.desc())
                .limit(1)
            )
            return _improvement_candidate_view(candidate, experiment, review)

    async def decide_improvement_review(
        self,
        actor: ActorContext,
        candidate_id: UUID,
        submission: ImprovementReviewDecisionSubmission,
    ) -> dict[str, Any] | None:
        if self._candidate_review_runtime is None:
            raise CandidateReviewUnavailableError(
                "Candidate review runtime is not configured."
            )
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            candidate = await session.scalar(
                select(ImprovementCandidate).where(
                    ImprovementCandidate.id == candidate_id,
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                )
            )
            review = await session.scalar(
                select(ImprovementReview).where(
                    ImprovementReview.candidate_id == candidate_id,
                    ImprovementReview.tenant_id == resolved.tenant_id,
                    ImprovementReview.workspace_id == resolved.workspace_id,
                    ImprovementReview.owner_user_id == resolved.user_id,
                )
            )
            if candidate is None or review is None:
                return None
            if review.status != "pending":
                return _improvement_candidate_view(candidate, review=review)
            receipt = _candidate_review_receipt(review)
            review_id = str(review.id)

        result = await self._candidate_review_runtime.decide(
            actor=actor,
            review_id=review_id,
            receipt=receipt,
            action=submission.action,
            comment=submission.comment,
        )
        expected_status = (
            CandidateStatus.APPROVED
            if submission.action == "approve"
            else CandidateStatus.REJECTED
        )
        if result.get("status") != expected_status.value:
            raise RuntimeError("Aegra candidate review returned an inconsistent status")
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            candidate = await session.scalar(
                select(ImprovementCandidate)
                .where(
                    ImprovementCandidate.id == candidate_id,
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            review = await session.scalar(
                select(ImprovementReview)
                .where(ImprovementReview.candidate_id == candidate_id)
                .with_for_update()
            )
            if candidate is None or review is None:
                raise RuntimeError("Candidate review disappeared after Aegra resume")
            if review.status == "pending":
                candidate.status = transition_candidate(
                    CandidateStatus(candidate.status), expected_status
                ).value
                review.status = expected_status.value
                review.reviewer_user_id = resolved.user_id
                review.response = {
                    "action": submission.action,
                    **(
                        {"comment": submission.comment}
                        if submission.comment is not None
                        else {}
                    ),
                }
                review.decided_at = self._now()
                await session.flush()
                await session.refresh(candidate)
                await session.refresh(review)
            experiment = await session.scalar(
                select(ImprovementExperiment)
                .where(ImprovementExperiment.candidate_id == candidate.id)
                .order_by(ImprovementExperiment.created_at.desc())
                .limit(1)
            )
            return _improvement_candidate_view(candidate, experiment, review)

    async def run_improvement_shadow(
        self,
        actor: ActorContext,
        candidate_id: UUID,
        submission: ImprovementShadowSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        operation_key = f"candidate-shadow:{sha256(idempotency_key.encode()).hexdigest()}"
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            candidate = await session.scalar(
                select(ImprovementCandidate)
                .where(
                    ImprovementCandidate.id == candidate_id,
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if candidate is None:
                return None
            review = await session.scalar(
                select(ImprovementReview).where(
                    ImprovementReview.candidate_id == candidate.id
                )
            )
            experiment = await session.scalar(
                select(ImprovementExperiment)
                .where(ImprovementExperiment.candidate_id == candidate.id)
                .order_by(ImprovementExperiment.created_at.desc())
                .limit(1)
            )
            if (
                review is None
                or review.status != "approved"
                or experiment is None
                or experiment.status != "succeeded"
            ):
                raise ValueError(
                    "Shadow requires an approved review and passing experiment."
                )
            existing = await session.scalar(
                select(ImprovementShadowRun).where(
                    ImprovementShadowRun.tenant_id == resolved.tenant_id,
                    ImprovementShadowRun.workspace_id == resolved.workspace_id,
                    ImprovementShadowRun.owner_user_id == resolved.user_id,
                    ImprovementShadowRun.idempotency_key == operation_key,
                )
            )
            if existing is not None:
                return _improvement_candidate_view(
                    candidate, experiment, review, existing
                )
            observed_runs = len(experiment.case_results)
            passed = (
                observed_runs >= submission.minimum_runs
                and bool(experiment.gate_report.get("approved"))
            )
            comparison = {
                "mode": "frozen_replay_shadow",
                "allow_live_fetch": False,
                "allow_live_side_effects": False,
                "candidate_metrics": experiment.metrics,
                "baseline_thresholds": experiment.gate_report.get("thresholds", {}),
                "release_gate_approved": bool(
                    experiment.gate_report.get("approved")
                ),
                "reasons": (
                    []
                    if passed
                    else [
                        "insufficient_frozen_cases"
                        if observed_runs < submission.minimum_runs
                        else "release_gate_failed"
                    ]
                ),
            }
            source_hash = _payload_hash(
                {
                    "candidate": candidate.version_hash,
                    "experiment": experiment.source_hash,
                    "minimum_runs": submission.minimum_runs,
                    "observed_runs": observed_runs,
                    "comparison": comparison,
                }
            )
            shadow = ImprovementShadowRun(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                candidate_id=candidate.id,
                baseline_version=candidate.base_version,
                status="passed" if passed else "failed",
                minimum_runs=submission.minimum_runs,
                observed_runs=min(observed_runs, submission.minimum_runs),
                comparison=comparison,
                source_hash=source_hash,
                idempotency_key=operation_key,
                completed_at=self._now(),
            )
            session.add(shadow)
            candidate.status = transition_candidate(
                CandidateStatus(candidate.status), CandidateStatus.SHADOW
            ).value
            await session.flush()
            await session.refresh(candidate)
            await session.refresh(shadow)
            return _improvement_candidate_view(candidate, experiment, review, shadow)

    async def promote_improvement_candidate(
        self,
        actor: ActorContext,
        candidate_id: UUID,
        submission: ImprovementReleaseSubmission,
    ) -> dict[str, Any] | None:
        return await self._record_improvement_release(
            actor,
            candidate_id,
            action="promoted",
            reason=submission.reason,
        )

    async def rollback_improvement_candidate(
        self,
        actor: ActorContext,
        candidate_id: UUID,
        submission: ImprovementReleaseSubmission,
    ) -> dict[str, Any] | None:
        return await self._record_improvement_release(
            actor,
            candidate_id,
            action="rolled_back",
            reason=submission.reason,
        )

    async def _record_improvement_release(
        self,
        actor: ActorContext,
        candidate_id: UUID,
        *,
        action: str,
        reason: str,
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            candidate = await session.scalar(
                select(ImprovementCandidate)
                .where(
                    ImprovementCandidate.id == candidate_id,
                    ImprovementCandidate.tenant_id == resolved.tenant_id,
                    ImprovementCandidate.workspace_id == resolved.workspace_id,
                    ImprovementCandidate.owner_user_id == resolved.user_id,
                )
                .with_for_update()
            )
            if candidate is None:
                return None
            review = await session.scalar(
                select(ImprovementReview).where(
                    ImprovementReview.candidate_id == candidate.id
                )
            )
            shadow = await session.scalar(
                select(ImprovementShadowRun)
                .where(ImprovementShadowRun.candidate_id == candidate.id)
                .order_by(ImprovementShadowRun.created_at.desc())
                .limit(1)
            )
            experiment = await session.scalar(
                select(ImprovementExperiment)
                .where(ImprovementExperiment.candidate_id == candidate.id)
                .order_by(ImprovementExperiment.created_at.desc())
                .limit(1)
            )
            if review is None or shadow is None or experiment is None:
                raise ValueError("Release requires review, experiment and shadow receipts.")
            events = list(
                (
                    await session.scalars(
                        select(ImprovementReleaseEvent)
                        .where(ImprovementReleaseEvent.candidate_id == candidate.id)
                        .order_by(ImprovementReleaseEvent.created_at)
                    )
                ).all()
            )
            existing = next((event for event in events if event.action == action), None)
            if existing is not None:
                return _improvement_candidate_view(
                    candidate, experiment, review, shadow, events
                )
            if action == "promoted":
                if (
                    candidate.status != CandidateStatus.SHADOW.value
                    or review.status != "approved"
                    or shadow.status != "passed"
                ):
                    raise ValueError(
                        "Promotion requires approved review and passing shadow."
                    )
                from_version = candidate.base_version
                to_version = candidate.candidate_version
                target_status = CandidateStatus.ACTIVE
            elif action == "rolled_back":
                if candidate.status != CandidateStatus.ACTIVE.value or not any(
                    event.action == "promoted" for event in events
                ):
                    raise ValueError("Rollback requires an active promoted candidate.")
                from_version = candidate.candidate_version
                to_version = candidate.rollback_target_version
                target_status = CandidateStatus.ROLLED_BACK
            else:
                raise ValueError("unsupported improvement release action")
            evidence = {
                "review_id": str(review.id),
                "official_thread_id": review.official_thread_id,
                "official_run_id": review.official_run_id,
                "experiment_source_hash": experiment.source_hash,
                "shadow_source_hash": shadow.source_hash,
                "shadow_mode": shadow.comparison.get("mode"),
            }
            source_hash = _payload_hash(
                {
                    "candidate": candidate.version_hash,
                    "action": action,
                    "from_version": from_version,
                    "to_version": to_version,
                    "reason": reason,
                    "evidence": evidence,
                }
            )
            event = ImprovementReleaseEvent(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                candidate_id=candidate.id,
                review_id=review.id,
                shadow_run_id=shadow.id,
                action=action,
                from_version=from_version,
                to_version=to_version,
                rollback_target_version=candidate.rollback_target_version,
                reason=reason,
                evidence=evidence,
                source_hash=source_hash,
            )
            session.add(event)
            candidate.status = transition_candidate(
                CandidateStatus(candidate.status), target_status
            ).value
            await session.flush()
            await session.refresh(candidate)
            await session.refresh(event)
            return _improvement_candidate_view(
                candidate, experiment, review, shadow, [*events, event]
            )

    async def list_artifacts(
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
                    select(ArtifactVersion, Artifact, Task)
                    .join(
                        Artifact,
                        and_(
                            Artifact.id == ArtifactVersion.artifact_id,
                            Artifact.tenant_id == ArtifactVersion.tenant_id,
                            Artifact.workspace_id == ArtifactVersion.workspace_id,
                            Artifact.owner_user_id == ArtifactVersion.owner_user_id,
                            Artifact.task_id == ArtifactVersion.task_id,
                        ),
                    )
                    .join(
                        Task,
                        and_(
                            Task.id == ArtifactVersion.task_id,
                            Task.tenant_id == ArtifactVersion.tenant_id,
                            Task.workspace_id == ArtifactVersion.workspace_id,
                            Task.owner_user_id == ArtifactVersion.owner_user_id,
                        ),
                    )
                    .where(
                        ArtifactVersion.tenant_id == resolved.tenant_id,
                        ArtifactVersion.workspace_id == resolved.workspace_id,
                        ArtifactVersion.owner_user_id == resolved.user_id,
                    )
                    .order_by(
                        ArtifactVersion.created_at.desc(),
                        ArtifactVersion.id.desc(),
                    )
                    .limit(limit)
                )
            ).all()
            items = []
            for version, artifact, task in rows:
                analysis = version.content.get("analysis")
                main_action = (
                    analysis.get("main_action") if isinstance(analysis, dict) else None
                )
                items.append(
                    {
                        "artifact_id": artifact.id,
                        "artifact_version_id": version.id,
                        "artifact_type": artifact.artifact_type,
                        "schema_version": version.schema_version,
                        "version_number": version.version_number,
                        "status": version.status,
                        "task_id": version.task_id,
                        "run_id": version.run_id,
                        "symbol": task.request_payload["symbol"],
                        "horizon": task.request_payload["horizon"],
                        "main_action": main_action,
                        "created_at": version.created_at,
                    }
                )
            return {"items": items, "limit": limit}

    async def get_artifact(
        self,
        actor: ActorContext,
        artifact_id: str,
        *,
        version_number: int | None = None,
    ) -> dict[str, Any] | None:
        try:
            artifact_uuid = UUID(artifact_id)
        except ValueError:
            return None
        if version_number is not None and version_number < 1:
            return None

        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            artifact_task = (
                await session.execute(
                    select(Artifact, Task)
                    .join(
                        Task,
                        and_(
                            Task.id == Artifact.task_id,
                            Task.tenant_id == Artifact.tenant_id,
                            Task.workspace_id == Artifact.workspace_id,
                            Task.owner_user_id == Artifact.owner_user_id,
                        ),
                    )
                    .where(
                        Artifact.id == artifact_uuid,
                        Artifact.tenant_id == resolved.tenant_id,
                        Artifact.workspace_id == resolved.workspace_id,
                        Artifact.owner_user_id == resolved.user_id,
                        Task.tenant_id == resolved.tenant_id,
                        Task.workspace_id == resolved.workspace_id,
                        Task.owner_user_id == resolved.user_id,
                    )
                )
            ).one_or_none()
            if artifact_task is None:
                return None
            artifact, task = artifact_task
            versions = list(
                (
                    await session.scalars(
                        select(ArtifactVersion)
                        .where(
                            ArtifactVersion.artifact_id == artifact.id,
                            ArtifactVersion.tenant_id == resolved.tenant_id,
                            ArtifactVersion.workspace_id == resolved.workspace_id,
                            ArtifactVersion.owner_user_id == resolved.user_id,
                            ArtifactVersion.task_id == task.id,
                        )
                        .order_by(ArtifactVersion.version_number.desc())
                    )
                ).all()
            )
            selected = next(
                (
                    version
                    for version in versions
                    if version_number is None
                    or version.version_number == version_number
                ),
                None,
            )
            if version_number is not None and selected is None:
                return None

            selected_detail = None
            if selected is not None:
                decision = await session.scalar(
                    select(Decision).where(
                        Decision.artifact_version_id == selected.id,
                        Decision.artifact_id == artifact.id,
                        Decision.task_id == task.id,
                        Decision.run_id == selected.run_id,
                        Decision.tenant_id == resolved.tenant_id,
                        Decision.workspace_id == resolved.workspace_id,
                        Decision.owner_user_id == resolved.user_id,
                    )
                )
                market_snapshots = list(
                    (
                        await session.scalars(
                            select(PersistedMarketSnapshot)
                            .where(
                                PersistedMarketSnapshot.run_id == selected.run_id,
                                PersistedMarketSnapshot.task_id == task.id,
                                PersistedMarketSnapshot.tenant_id == resolved.tenant_id,
                                PersistedMarketSnapshot.workspace_id
                                == resolved.workspace_id,
                                PersistedMarketSnapshot.owner_user_id
                                == resolved.user_id,
                            )
                            .order_by(PersistedMarketSnapshot.created_at)
                        )
                    ).all()
                )
                web_evidence = list(
                    (
                        await session.scalars(
                            select(PersistedWebEvidence)
                            .where(
                                PersistedWebEvidence.run_id == selected.run_id,
                                PersistedWebEvidence.task_id == task.id,
                                PersistedWebEvidence.tenant_id == resolved.tenant_id,
                                PersistedWebEvidence.workspace_id
                                == resolved.workspace_id,
                                PersistedWebEvidence.owner_user_id == resolved.user_id,
                            )
                            .order_by(PersistedWebEvidence.created_at)
                        )
                    ).all()
                )
                selected_detail = {
                    "artifact_version_id": selected.id,
                    "artifact_id": artifact.id,
                    "version_number": selected.version_number,
                    "schema_version": selected.schema_version,
                    "status": selected.status,
                    "task_id": selected.task_id,
                    "run_id": selected.run_id,
                    "created_at": selected.created_at,
                    "content": selected.content,
                    "decision": (
                        {
                            "decision_id": decision.id,
                            "decision_version": decision.decision_version,
                            "decision": decision.decision,
                            "evidence_verdict": decision.evidence_verdict,
                            "risk_verdict": decision.risk_verdict,
                            "created_at": decision.created_at,
                        }
                        if decision is not None
                        else None
                    ),
                    "market_snapshots": [
                        snapshot.snapshot for snapshot in market_snapshots
                    ],
                    "web_evidence": [evidence.payload for evidence in web_evidence],
                }

            return {
                "artifact_id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "task_id": task.id,
                "symbol": task.request_payload["symbol"],
                "horizon": task.request_payload["horizon"],
                "latest_version_number": artifact.latest_version_number,
                "versions": [
                    {
                        "artifact_version_id": version.id,
                        "artifact_id": version.artifact_id,
                        "version_number": version.version_number,
                        "schema_version": version.schema_version,
                        "status": version.status,
                        "task_id": version.task_id,
                        "run_id": version.run_id,
                        "created_at": version.created_at,
                    }
                    for version in versions
                ],
                "selected_version": selected_detail,
            }

    async def list_notifications(
        self,
        actor: ActorContext,
        task_id: str,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            task_exists = await session.scalar(
                select(Task.id).where(
                    Task.id == task_uuid,
                    Task.tenant_id == resolved.tenant_id,
                    Task.workspace_id == resolved.workspace_id,
                    Task.owner_user_id == resolved.user_id,
                )
            )
            if task_exists is None:
                return None
            notifications = list(
                (
                    await session.scalars(
                        select(NotificationOutbox)
                        .where(
                            NotificationOutbox.task_id == task_uuid,
                            NotificationOutbox.tenant_id == resolved.tenant_id,
                            NotificationOutbox.workspace_id == resolved.workspace_id,
                            NotificationOutbox.owner_user_id == resolved.user_id,
                        )
                        .order_by(
                            NotificationOutbox.created_at.desc(),
                            NotificationOutbox.id.desc(),
                        )
                    )
                ).all()
            )
            attempts_by_outbox: dict[UUID, list[NotificationAttempt]] = {
                notification.id: [] for notification in notifications
            }
            if notifications:
                attempts = list(
                    (
                        await session.scalars(
                            select(NotificationAttempt)
                            .where(
                                NotificationAttempt.outbox_id.in_(
                                    tuple(attempts_by_outbox)
                                ),
                                NotificationAttempt.tenant_id == resolved.tenant_id,
                                NotificationAttempt.workspace_id
                                == resolved.workspace_id,
                                NotificationAttempt.owner_user_id == resolved.user_id,
                                NotificationAttempt.task_id == task_uuid,
                            )
                            .order_by(
                                NotificationAttempt.outbox_id,
                                NotificationAttempt.attempt_number,
                            )
                        )
                    ).all()
                )
                for attempt in attempts:
                    attempts_by_outbox[attempt.outbox_id].append(attempt)
            now = self._now()
            return {
                "task_id": task_uuid,
                "items": [
                    _notification_view(
                        notification,
                        attempts_by_outbox[notification.id],
                        now=now,
                    )
                    for notification in notifications
                ],
            }

    async def request_notification_resend(
        self,
        actor: ActorContext,
        notification_id: str,
        submission: NotificationResendSubmission,
    ) -> dict[str, Any] | None:
        try:
            notification_uuid = UUID(notification_id)
        except ValueError:
            return None
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            now = self._now()
            notification = await request_manual_resend(
                session,
                notification_id=notification_uuid,
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                requested_by=str(resolved.user_id),
                reason=submission.reason,
                now=now,
            )
            if notification is None:
                return None
            attempts = list(
                (
                    await session.scalars(
                        select(NotificationAttempt)
                        .where(
                            NotificationAttempt.outbox_id == notification.id,
                            NotificationAttempt.tenant_id == resolved.tenant_id,
                            NotificationAttempt.workspace_id == resolved.workspace_id,
                            NotificationAttempt.owner_user_id == resolved.user_id,
                            NotificationAttempt.task_id == notification.task_id,
                        )
                        .order_by(NotificationAttempt.attempt_number)
                    )
                ).all()
            )
            return _notification_view(
                notification,
                attempts,
                now=now,
            )

    async def get_notification_settings(
        self,
        actor: ActorContext,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            destination = await session.scalar(
                select(NotificationDestination).where(
                    NotificationDestination.tenant_id == resolved.tenant_id,
                    NotificationDestination.workspace_id == resolved.workspace_id,
                    NotificationDestination.owner_user_id == resolved.user_id,
                    NotificationDestination.channel == "bark",
                )
            )
            return {
                "channel": "bark",
                "enabled": destination is not None and destination.status == "enabled",
                "configured": destination is not None,
                "updated_at": destination.updated_at
                if destination is not None
                else None,
            }

    async def update_notification_settings(
        self,
        actor: ActorContext,
        submission: NotificationSettingsUpdate,
    ) -> dict[str, Any]:
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            locked_user_id = await session.scalar(
                select(User.id)
                .where(
                    User.id == resolved.user_id,
                    User.tenant_id == resolved.tenant_id,
                )
                .with_for_update()
            )
            if locked_user_id is None:
                raise NotificationSettingsUnavailableError(
                    "Notification settings owner is unavailable."
                )
            destination = await session.scalar(
                select(NotificationDestination)
                .where(
                    NotificationDestination.tenant_id == resolved.tenant_id,
                    NotificationDestination.workspace_id == resolved.workspace_id,
                    NotificationDestination.owner_user_id == resolved.user_id,
                    NotificationDestination.channel == "bark",
                )
                .with_for_update()
            )
            credential = submission.device_key
            if destination is None and credential is None:
                if submission.enabled:
                    raise NotificationSettingsConflictError(
                        "A Bark device key is required before notifications can be enabled."
                    )
                return {
                    "channel": "bark",
                    "enabled": False,
                    "configured": False,
                    "updated_at": None,
                }
            if credential is not None and self._notification_credential_cipher is None:
                raise NotificationSettingsUnavailableError(
                    "Notification credential encryption is not configured."
                )

            now = self._now()
            if destination is None:
                destination_id = uuid4()
                assert credential is not None
                assert self._notification_credential_cipher is not None
                destination = NotificationDestination(
                    id=destination_id,
                    tenant_id=resolved.tenant_id,
                    workspace_id=resolved.workspace_id,
                    owner_user_id=resolved.user_id,
                    channel="bark",
                    status="enabled" if submission.enabled else "disabled",
                    credential_ciphertext=(
                        self._notification_credential_cipher.encrypt(
                            credential,
                            destination_id=destination_id,
                            tenant_id=resolved.tenant_id,
                            workspace_id=resolved.workspace_id,
                            owner_user_id=resolved.user_id,
                            channel="bark",
                        )
                    ),
                    credential_key_version=(
                        self._notification_credential_cipher.key_version
                    ),
                    updated_at=now,
                )
                session.add(destination)
            else:
                if credential is not None:
                    assert self._notification_credential_cipher is not None
                    destination.credential_ciphertext = (
                        self._notification_credential_cipher.encrypt(
                            credential,
                            destination_id=destination.id,
                            tenant_id=destination.tenant_id,
                            workspace_id=destination.workspace_id,
                            owner_user_id=destination.owner_user_id,
                            channel=destination.channel,
                        )
                    )
                    destination.credential_key_version = (
                        self._notification_credential_cipher.key_version
                    )
                    destination.verified_at = None
                elif (
                    submission.enabled
                    and self._notification_credential_cipher is not None
                    and not self._notification_credential_cipher.supports_decryption(
                        destination.credential_key_version
                    )
                ):
                    raise NotificationSettingsConflictError(
                        "The Bark device key must be re-entered after key rotation."
                    )
                destination.status = "enabled" if submission.enabled else "disabled"
                destination.updated_at = now
            await session.flush()
            return {
                "channel": "bark",
                "enabled": destination.status == "enabled",
                "configured": True,
                "updated_at": destination.updated_at,
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
                    raise RuntimeError(
                        "Interrupt pause projection state is inconsistent"
                    )
                payloads = [
                    parse_review_interrupt_payload(member.payload) for member in members
                ]
                symbol = task.request_payload["symbol"]
                horizon = task.request_payload["horizon"]
                try:
                    for payload in payloads:
                        validate_review_payload_for_task(
                            payload,
                            task_type=task.task_type,
                            symbol=symbol,
                            horizon=horizon,
                        )
                except ValueError as exc:
                    raise RuntimeError(
                        "Interrupt pause review scope is inconsistent"
                    ) from exc
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

    async def get_data_lifecycle_policy(self, actor: ActorContext) -> dict[str, Any]:
        return await self._lifecycle.get_policy(actor)

    async def update_data_lifecycle_policy(
        self, actor: ActorContext, submission: DataLifecyclePolicyUpdate
    ) -> dict[str, Any]:
        return await self._lifecycle.update_policy(actor, submission)

    async def create_data_export(
        self,
        actor: ActorContext,
        submission: DataExportSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._lifecycle.create_export(actor, submission, idempotency_key)

    async def get_data_export(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        return await self._lifecycle.get_export(actor, export_id)

    async def get_data_export_manifest(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        return await self._lifecycle.get_export_manifest(actor, export_id)

    async def get_data_export_bundle(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        return await self._lifecycle.get_export_bundle(actor, export_id)

    async def create_data_deletion(
        self,
        actor: ActorContext,
        submission: DataDeletionSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return await self._lifecycle.create_deletion(actor, submission, idempotency_key)

    async def get_data_deletion(
        self, actor: ActorContext, deletion_id: UUID
    ) -> dict[str, Any] | None:
        return await self._lifecycle.get_deletion(actor, deletion_id)

    async def list_memory(
        self,
        actor: ActorContext,
        *,
        limit: int,
        include_disabled: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            conditions = [
                MemoryEntry.tenant_id == resolved.tenant_id,
                MemoryEntry.workspace_id == resolved.workspace_id,
                MemoryEntry.owner_user_id == resolved.user_id,
            ]
            if not include_disabled:
                conditions.extend(
                    (MemoryEntry.enabled.is_(True), MemoryEntry.deleted_at.is_(None))
                )
            if session_id is not None:
                conditions.append(MemoryEntry.session_id == session_id)
            records = list(
                (
                    await session.scalars(
                        select(MemoryEntry)
                        .where(*conditions)
                        .order_by(MemoryEntry.updated_at.desc(), MemoryEntry.id.desc())
                        .limit(limit)
                    )
                ).all()
            )
            return {"items": [_memory_view(item) for item in records], "limit": limit}

    async def create_memory(
        self,
        actor: ActorContext,
        submission: MemoryCreateSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del idempotency_key
        now = self._now()
        if submission.expires_at is not None and submission.expires_at <= now:
            raise ValueError("Memory expiry must be in the future.")
        MemoryRecord(
            memory_id=uuid4(),
            scope=submission.scope,
            purpose=submission.purpose,
            key=submission.key,
            content=submission.content,
            enabled=submission.enabled,
            expires_at=submission.expires_at,
            refreshed_at=submission.refreshed_at,
            source_artifact_id=submission.source_artifact_id,
        )
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            existing = await session.scalar(
                select(MemoryEntry)
                .where(
                    MemoryEntry.tenant_id == resolved.tenant_id,
                    MemoryEntry.workspace_id == resolved.workspace_id,
                    MemoryEntry.owner_user_id == resolved.user_id,
                    MemoryEntry.session_id == submission.session_id,
                    MemoryEntry.purpose == submission.purpose,
                    MemoryEntry.memory_key == submission.key,
                    MemoryEntry.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if existing is not None:
                existing.content = submission.content
                existing.enabled = submission.enabled
                existing.expires_at = submission.expires_at
                existing.refreshed_at = submission.refreshed_at
                existing.source_artifact_id = submission.source_artifact_id
                existing.updated_at = now
                await session.flush()
                return _memory_view(existing)
            memory = MemoryEntry(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                session_id=submission.session_id,
                scope=submission.scope,
                purpose=submission.purpose,
                memory_key=submission.key,
                content=submission.content,
                enabled=submission.enabled,
                expires_at=submission.expires_at,
                refreshed_at=submission.refreshed_at,
                source_artifact_id=submission.source_artifact_id,
            )
            session.add(memory)
            await session.flush()
            return _memory_view(memory)

    async def update_memory(
        self,
        actor: ActorContext,
        memory_id: UUID,
        submission: MemoryUpdateSubmission,
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            memory = await session.scalar(
                select(MemoryEntry)
                .where(
                    MemoryEntry.id == memory_id,
                    MemoryEntry.tenant_id == resolved.tenant_id,
                    MemoryEntry.workspace_id == resolved.workspace_id,
                    MemoryEntry.owner_user_id == resolved.user_id,
                    MemoryEntry.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if memory is None:
                return None
            if submission.content is not None:
                memory.content = submission.content
            if submission.enabled is not None:
                memory.enabled = submission.enabled
            if submission.expires_at is not None:
                if submission.expires_at <= self._now():
                    raise ValueError("Memory expiry must be in the future.")
                memory.expires_at = submission.expires_at
            if submission.refreshed_at is not None:
                memory.refreshed_at = submission.refreshed_at
            if memory.purpose == "event" and memory.refreshed_at is None:
                raise ValueError("event memory requires refreshed_at")
            memory.updated_at = self._now()
            await session.flush()
            return _memory_view(memory)

    async def delete_memory(
        self,
        actor: ActorContext,
        memory_id: UUID,
        submission: MemoryDeleteSubmission,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        del submission
        async with self._session_factory() as session, session.begin():
            resolved = await resolve_actor(session, actor)
            _require_analysis_write(resolved)
            memory = await session.scalar(
                select(MemoryEntry)
                .where(
                    MemoryEntry.id == memory_id,
                    MemoryEntry.tenant_id == resolved.tenant_id,
                    MemoryEntry.workspace_id == resolved.workspace_id,
                    MemoryEntry.owner_user_id == resolved.user_id,
                    MemoryEntry.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if memory is None:
                return None
            existing = await session.scalar(
                select(MemoryDeletionJob).where(
                    MemoryDeletionJob.tenant_id == resolved.tenant_id,
                    MemoryDeletionJob.workspace_id == resolved.workspace_id,
                    MemoryDeletionJob.owner_user_id == resolved.user_id,
                    MemoryDeletionJob.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.memory_id != memory.id:
                    raise IdempotencyConflictError(
                        "Idempotency-Key was already used for a different Memory."
                    )
                return {
                    "memory_id": existing.memory_id,
                    "status": existing.status,
                    "requested_at": existing.requested_at,
                    "completed_at": existing.completed_at,
                }
            memory.enabled = False
            job = MemoryDeletionJob(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                memory_id=memory.id,
                idempotency_key=idempotency_key,
                status="queued",
                requested_at=self._now(),
            )
            session.add(job)
            await session.flush()
            return {
                "memory_id": job.memory_id,
                "status": job.status,
                "requested_at": job.requested_at,
                "completed_at": job.completed_at,
            }

    async def list_outcomes(
        self,
        actor: ActorContext,
        *,
        limit: int,
        status_filter: str | None = None,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            resolved = await resolve_actor(session, actor)
            _require_analysis_read(resolved)
            conditions = [
                OutcomeObservation.tenant_id == resolved.tenant_id,
                OutcomeObservation.workspace_id == resolved.workspace_id,
                OutcomeObservation.owner_user_id == resolved.user_id,
            ]
            if status_filter is not None:
                conditions.append(OutcomeObservation.status == status_filter)
            records = list(
                (
                    await session.scalars(
                        select(OutcomeObservation)
                        .where(*conditions)
                        .order_by(OutcomeObservation.created_at.desc(), OutcomeObservation.id.desc())
                        .limit(limit)
                    )
                ).all()
            )
            matured = [item for item in records if item.status == "matured"]
            window_start = min((item.created_at for item in matured), default=None)
            reportable = bool(
                window_start is not None
                and quality_is_reportable(
                    sample_count=len(matured), window_start=window_start, now=self._now()
                )
            )
            return {
                "items": [_outcome_view(item) for item in records],
                "limit": limit,
                "reportable": reportable,
                "sample_count": len(matured),
                "window_start": window_start,
            }
