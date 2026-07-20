from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Generic, Iterable, Protocol, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    DomainEvent,
    MarketSnapshot,
    Membership,
    OBSERVABILITY_DELIVERY_PROVIDERS,
    OBSERVABILITY_DELIVERY_STATUSES,
    ObservabilityDelivery,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    WebEvidence,
    Workspace,
)


class ActorContext(Protocol):
    tenant_id: str
    workspace_id: str
    user_id: str
    identity_issuer: str
    context_id: UUID | None


class ScopedResourceNotFound(LookupError):
    """Raised without disclosing whether a resource exists outside the actor scope."""


@dataclass(frozen=True, slots=True)
class ResolvedActor:
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    membership_id: UUID
    role: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtifactCommit:
    artifact_version: ArtifactVersion
    decision: Decision


@dataclass(frozen=True, slots=True)
class TaskRunSourceRecords:
    market_snapshot: dict[str, Any] | None
    web_evidence: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class TaskRunStageEventRecord:
    event_type: str
    sequence: int
    recorded_at: datetime
    from_official_stream: bool


@dataclass(frozen=True, slots=True)
class ObservabilityDeliveryIntent:
    """Typed, non-payload intent for one provider delivery."""

    provider: str
    status: str
    skip_reason: str | None
    sampled: bool
    provider_trace_id: str | None
    verification_deadline: datetime | None
    delivery_key: str
    correlation_id: str
    event_type: str = "root_trace"
    event_version: int = 1


@dataclass(frozen=True, slots=True)
class ObservabilityDeliveryLease:
    delivery_id: UUID
    provider: str
    event_type: str
    event_version: int
    status: str
    tenant_id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    task_id: UUID
    run_id: UUID
    correlation_id: str
    delivery_key: str
    provider_trace_id: str | None
    verification_deadline: datetime | None
    attempt_count: int
    fence_token: int
    lease_owner: str
    lease_expires_at: datetime


ModelT = TypeVar("ModelT", bound=Base)


class ActorScopedRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession, actor: ActorContext) -> None:
        if not actor.tenant_id or not actor.workspace_id or not actor.user_id:
            raise PermissionError(
                "actor tenant, workspace and user identifiers are required"
            )
        self.session = session
        self.actor = actor

    def _actor_scope(self, model: type[Any] | None = None) -> Any:
        resource = model or self.model
        actor_column = getattr(resource, "owner_user_id", None)
        if actor_column is None:
            actor_column = getattr(resource, "actor_user_id", None)
        if actor_column is None and resource is Membership:
            actor_column = Membership.user_id
        owner_scope = (actor_column == User.id,) if actor_column is not None else ()
        return exists(
            select(1)
            .select_from(Tenant)
            .join(
                Workspace,
                and_(
                    Workspace.tenant_id == Tenant.id,
                    Workspace.id == resource.workspace_id,
                ),
            )
            .join(
                Membership,
                and_(
                    Membership.tenant_id == Tenant.id,
                    Membership.workspace_id == Workspace.id,
                    Membership.is_active.is_(True),
                ),
            )
            .join(
                User,
                and_(
                    Membership.user_id == User.id,
                    User.tenant_id == Tenant.id,
                    User.identity_issuer == self.actor.identity_issuer,
                ),
            )
            .where(
                Tenant.id == resource.tenant_id,
                Tenant.external_id == self.actor.tenant_id,
                Workspace.external_id == self.actor.workspace_id,
                User.external_subject == self.actor.user_id,
                *owner_scope,
                *(
                    (Membership.id == self.actor.context_id,)
                    if self.actor.context_id is not None
                    else ()
                ),
            )
        )

    def _select(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self._actor_scope())

    async def get(self, resource_id: UUID) -> ModelT | None:
        statement = self._select().where(self.model.id == resource_id)
        return await self.session.scalar(statement)

    async def list(self, *, limit: int = 100) -> list[ModelT]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        statement = self._select().order_by(self.model.created_at.desc()).limit(limit)
        return list((await self.session.scalars(statement)).all())


class MembershipRepository(ActorScopedRepository[Membership]):
    model = Membership


class ThreadRepository(ActorScopedRepository[Thread]):
    model = Thread


class TaskRepository(ActorScopedRepository[Task]):
    model = Task


class RunRepository(ActorScopedRepository[Run]):
    model = Run


class MarketSnapshotRepository(ActorScopedRepository[MarketSnapshot]):
    model = MarketSnapshot


class WebEvidenceRepository(ActorScopedRepository[WebEvidence]):
    model = WebEvidence


class ObservabilityDeliveryRepository:
    """Product-owned state machine for provider trace delivery verification."""

    model = ObservabilityDelivery

    def __init__(
        self,
        session: AsyncSession,
        actor: ActorContext | ResolvedActor | None = None,
    ) -> None:
        self.session = session
        self.actor = actor

    def _actor_scope(self, model: type[Any]) -> Any:
        if self.actor is None:
            return True
        if isinstance(self.actor, ResolvedActor):
            return and_(
                model.tenant_id == self.actor.tenant_id,
                model.workspace_id == self.actor.workspace_id,
                model.owner_user_id == self.actor.user_id,
            )
        return ActorScopedRepository._actor_scope(self, model)

    @staticmethod
    def _validate_worker_id(worker_id: str) -> str:
        normalized = worker_id.strip()
        if not normalized or len(normalized) > 255:
            raise ValueError("worker_id must be between 1 and 255 characters")
        return normalized

    @staticmethod
    def _validate_text(value: str, *, field: str, max_length: int) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > max_length:
            raise ValueError(f"{field} must be between 1 and {max_length} characters")
        return normalized

    def _scope_predicates(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_user_id: UUID,
        task_id: UUID,
        run_id: UUID | None = None,
    ) -> tuple[Any, ...]:
        predicates: tuple[Any, ...] = (
            self.model.tenant_id == tenant_id,
            self.model.workspace_id == workspace_id,
            self.model.owner_user_id == owner_user_id,
            self.model.task_id == task_id,
        )
        if run_id is not None:
            predicates += (self.model.run_id == run_id,)
        return predicates

    async def ensure_intents(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_user_id: UUID,
        task_id: UUID,
        run_id: UUID,
        intents: Iterable[ObservabilityDeliveryIntent],
    ) -> list[ObservabilityDelivery]:
        """Insert provider intents idempotently and return the canonical rows.

        This method only writes Product state. It deliberately does not construct
        or call a LangSmith/Langfuse client, flush a callback, or perform I/O.
        """

        intent_list = list(intents)
        if not intent_list:
            return []
        if self.actor is not None:
            task_scope = (
                Task.tenant_id == tenant_id,
                Task.workspace_id == workspace_id,
                Task.owner_user_id == owner_user_id,
                Task.id == task_id,
                self._actor_scope(Task),
            )
            if await self.session.scalar(select(Task.id).where(*task_scope)) is None:
                raise ScopedResourceNotFound("task scope not found")

        logical_keys: set[tuple[str, str, int]] = set()
        rows: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for intent in intent_list:
            provider = self._validate_text(
                intent.provider, field="provider", max_length=32
            ).lower()
            if provider not in OBSERVABILITY_DELIVERY_PROVIDERS:
                raise ValueError(f"unsupported observability provider: {provider}")
            status = self._validate_text(intent.status, field="status", max_length=32)
            if status not in OBSERVABILITY_DELIVERY_STATUSES:
                raise ValueError(f"unsupported observability status: {status}")
            if status in {"leased", "verifying"}:
                raise ValueError("ensure_intents cannot create an active lease")
            skip_reason = (
                self._validate_text(
                    intent.skip_reason, field="skip_reason", max_length=128
                )
                if intent.skip_reason is not None
                else None
            )
            if (status == "not_requested") != (skip_reason is not None):
                raise ValueError(
                    "not_requested intents require skip_reason and other intents must omit it"
                )
            provider_trace_id = (
                self._validate_text(
                    intent.provider_trace_id,
                    field="provider_trace_id",
                    max_length=255,
                )
                if intent.provider_trace_id is not None
                else None
            )
            if status == "verified" and provider_trace_id is None:
                raise ValueError("verified intents require provider_trace_id")
            event_type = self._validate_text(
                intent.event_type, field="event_type", max_length=64
            )
            if intent.event_version < 1:
                raise ValueError("event_version must be positive")
            logical_key = (provider, event_type, intent.event_version)
            if logical_key in logical_keys:
                raise ValueError("duplicate provider event intent")
            logical_keys.add(logical_key)
            rows.append(
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "workspace_id": workspace_id,
                    "owner_user_id": owner_user_id,
                    "task_id": task_id,
                    "run_id": run_id,
                    "provider": provider,
                    "event_type": event_type,
                    "event_version": intent.event_version,
                    "delivery_key": self._validate_text(
                        intent.delivery_key, field="delivery_key", max_length=255
                    ),
                    "correlation_id": self._validate_text(
                        intent.correlation_id, field="correlation_id", max_length=255
                    ),
                    "status": status,
                    "sampled": intent.sampled,
                    "skip_reason": skip_reason,
                    "provider_trace_id": provider_trace_id,
                    "verification_deadline": intent.verification_deadline,
                    "verified_at": now if status == "verified" else None,
                }
            )

        logical_conflict = [
            "tenant_id",
            "workspace_id",
            "task_id",
            "run_id",
            "provider",
            "event_type",
            "event_version",
        ]
        statement = (
            insert(self.model)
            .values(rows)
            .on_conflict_do_nothing(index_elements=logical_conflict)
        )
        await self.session.execute(statement)
        requested_logical_keys = [
            and_(
                self.model.provider == row["provider"],
                self.model.event_type == row["event_type"],
                self.model.event_version == row["event_version"],
            )
            for row in rows
        ]
        result = await self.session.scalars(
            select(self.model)
            .where(
                *self._scope_predicates(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_user_id=owner_user_id,
                    task_id=task_id,
                    run_id=run_id,
                ),
                or_(*requested_logical_keys),
            )
            .order_by(
                self.model.provider, self.model.event_type, self.model.event_version
            )
        )
        deliveries = list(result.all())
        if len(deliveries) != len(rows):
            raise ScopedResourceNotFound("observability delivery intent not found")
        return deliveries

    async def list_for_run(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        limit: int = 100,
    ) -> list[ObservabilityDelivery]:
        if self.actor is None:
            raise PermissionError("list_for_run requires an actor scope")
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        statement = (
            select(self.model)
            .where(
                self.model.task_id == task_id,
                self.model.run_id == run_id,
                self._actor_scope(self.model),
            )
            .order_by(
                self.model.provider, self.model.event_type, self.model.event_version
            )
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def recover_expired_leases(
        self,
        *,
        now: datetime | None = None,
    ) -> list[ObservabilityDelivery]:
        current_time = now or datetime.now(UTC)
        statement = (
            select(self.model)
            .where(
                self.model.status.in_(("leased", "verifying")),
                self.model.lease_expires_at <= current_time,
            )
            .order_by(self.model.lease_expires_at, self.model.id)
            .with_for_update(skip_locked=True)
        )
        expired = list((await self.session.scalars(statement)).all())
        for delivery in expired:
            delivery.status = "unknown"
            delivery.lease_owner = None
            delivery.lease_expires_at = None
            delivery.next_attempt_at = current_time
            delivery.last_retry_state = "unknown"
            delivery.last_error_code = "lease_expired"
            delivery.last_error_type = "LeaseExpired"
            delivery.last_error_summary = (
                "Provider outcome could not be confirmed after lease expiry."
            )
            delivery.last_error_at = current_time
        if expired:
            await self.session.flush()
        return expired

    async def release_owned_leases(
        self,
        worker_id: str,
        now: datetime | None = None,
    ) -> list[ObservabilityDelivery]:
        """Release this worker's read-only provider leases for safe retry."""

        owner = self._validate_worker_id(worker_id)
        current_time = now or datetime.now(UTC)
        statement = (
            select(self.model)
            .where(
                self.model.lease_owner == owner,
                self.model.status.in_(("leased", "verifying")),
            )
            .order_by(self.model.lease_expires_at, self.model.id)
            .with_for_update(skip_locked=True)
        )
        owned = list((await self.session.scalars(statement)).all())
        for delivery in owned:
            delivery.status = "failed_retryable"
            delivery.lease_owner = None
            delivery.lease_expires_at = None
            delivery.next_attempt_at = current_time
            delivery.last_retry_state = "scheduled"
            delivery.last_error_code = "worker_shutdown"
            delivery.last_error_type = "WorkerShutdown"
            delivery.last_error_summary = (
                "Worker shutdown released a read-only provider verification lease."
            )
            delivery.last_error_at = current_time
        if owned:
            await self.session.flush()
        return owned

    async def lease_due(
        self,
        *,
        worker_id: str,
        now: datetime | None = None,
        lease_seconds: int = 30,
        limit: int = 1,
    ) -> list[ObservabilityDeliveryLease]:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        owner = self._validate_worker_id(worker_id)
        current_time = now or datetime.now(UTC)
        await self.recover_expired_leases(now=current_time)
        due = or_(
            self.model.next_attempt_at.is_(None),
            self.model.next_attempt_at <= current_time,
        )
        statement = (
            select(self.model)
            .where(
                self.model.status.in_(("planned", "failed_retryable", "unknown")),
                due,
            )
            .order_by(self.model.next_attempt_at, self.model.created_at, self.model.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        deliveries = list((await self.session.scalars(statement)).all())
        lease_expires_at = current_time + timedelta(seconds=lease_seconds)
        leases: list[ObservabilityDeliveryLease] = []
        for delivery in deliveries:
            delivery.status = "verifying" if delivery.status == "unknown" else "leased"
            delivery.attempt_count += 1
            delivery.fence_token += 1
            delivery.lease_owner = owner
            delivery.lease_expires_at = lease_expires_at
            delivery.next_attempt_at = None
            leases.append(
                ObservabilityDeliveryLease(
                    delivery_id=delivery.id,
                    provider=delivery.provider,
                    event_type=delivery.event_type,
                    event_version=delivery.event_version,
                    status=delivery.status,
                    tenant_id=delivery.tenant_id,
                    workspace_id=delivery.workspace_id,
                    owner_user_id=delivery.owner_user_id,
                    task_id=delivery.task_id,
                    run_id=delivery.run_id,
                    correlation_id=delivery.correlation_id,
                    delivery_key=delivery.delivery_key,
                    provider_trace_id=delivery.provider_trace_id,
                    verification_deadline=delivery.verification_deadline,
                    attempt_count=delivery.attempt_count,
                    fence_token=delivery.fence_token,
                    lease_owner=owner,
                    lease_expires_at=lease_expires_at,
                )
            )
        if deliveries:
            await self.session.flush()
        return leases

    async def _fenced_transition(
        self,
        *,
        delivery_id: UUID,
        worker_id: str,
        fence_token: int,
        values: dict[str, Any],
    ) -> bool:
        owner = self._validate_worker_id(worker_id)
        if fence_token < 1:
            raise ValueError("fence_token must be positive")
        statement = (
            update(self.model)
            .where(
                self.model.id == delivery_id,
                self.model.lease_owner == owner,
                self.model.fence_token == fence_token,
                self.model.status.in_(("leased", "verifying")),
                self._actor_scope(self.model),
            )
            .values(**values)
        )
        result = await self.session.execute(statement)
        return result.rowcount == 1

    async def mark_verified(
        self,
        *,
        delivery_id: UUID,
        worker_id: str,
        fence_token: int,
        provider_trace_id: str,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or datetime.now(UTC)
        receipt = self._validate_text(
            provider_trace_id, field="provider_trace_id", max_length=255
        )
        return await self._fenced_transition(
            delivery_id=delivery_id,
            worker_id=worker_id,
            fence_token=fence_token,
            values={
                "status": "verified",
                "provider_trace_id": receipt,
                "verified_at": current_time,
                "lease_owner": None,
                "lease_expires_at": None,
                "next_attempt_at": None,
                "last_retry_state": "not_applicable",
                "last_error_code": None,
                "last_error_type": None,
                "last_error_summary": None,
                "last_error_at": None,
            },
        )

    async def mark_retryable(
        self,
        *,
        delivery_id: UUID,
        worker_id: str,
        fence_token: int,
        next_attempt_at: datetime,
        error_code: str,
        error_type: str | None = None,
        error_summary: str | None = None,
        stage: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or datetime.now(UTC)
        return await self._fenced_transition(
            delivery_id=delivery_id,
            worker_id=worker_id,
            fence_token=fence_token,
            values={
                "status": "failed_retryable",
                "lease_owner": None,
                "lease_expires_at": None,
                "next_attempt_at": next_attempt_at,
                "last_stage": stage,
                "last_retry_state": "scheduled",
                "last_error_code": self._validate_text(
                    error_code, field="error_code", max_length=128
                ),
                "last_error_type": error_type,
                "last_error_summary": error_summary,
                "last_error_at": current_time,
            },
        )

    async def mark_unknown(
        self,
        *,
        delivery_id: UUID,
        worker_id: str,
        fence_token: int,
        next_attempt_at: datetime | None = None,
        error_code: str = "provider_outcome_unknown",
        error_type: str | None = None,
        error_summary: str | None = None,
        stage: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or datetime.now(UTC)
        return await self._fenced_transition(
            delivery_id=delivery_id,
            worker_id=worker_id,
            fence_token=fence_token,
            values={
                "status": "unknown",
                "lease_owner": None,
                "lease_expires_at": None,
                "next_attempt_at": next_attempt_at or current_time,
                "last_stage": stage,
                "last_retry_state": "unknown",
                "last_error_code": self._validate_text(
                    error_code, field="error_code", max_length=128
                ),
                "last_error_type": error_type,
                "last_error_summary": error_summary,
                "last_error_at": current_time,
            },
        )

    async def mark_failed_retryable(self, **kwargs: Any) -> bool:
        return await self.mark_retryable(**kwargs)

    async def mark_terminal(
        self,
        *,
        delivery_id: UUID,
        worker_id: str,
        fence_token: int,
        error_code: str,
        error_type: str | None = None,
        error_summary: str | None = None,
        stage: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or datetime.now(UTC)
        return await self._fenced_transition(
            delivery_id=delivery_id,
            worker_id=worker_id,
            fence_token=fence_token,
            values={
                "status": "failed_terminal",
                "lease_owner": None,
                "lease_expires_at": None,
                "next_attempt_at": None,
                "terminal_at": current_time,
                "last_stage": stage,
                "last_retry_state": "exhausted",
                "last_error_code": self._validate_text(
                    error_code, field="error_code", max_length=128
                ),
                "last_error_type": error_type,
                "last_error_summary": error_summary,
                "last_error_at": current_time,
            },
        )

    async def mark_failed_terminal(self, **kwargs: Any) -> bool:
        return await self.mark_terminal(**kwargs)


class TaskRunProjectionRepository:
    def __init__(self, session: AsyncSession, actor: ResolvedActor) -> None:
        self.session = session
        self.actor = actor

    async def get_sources(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
    ) -> TaskRunSourceRecords:
        scope = (
            MarketSnapshot.tenant_id == self.actor.tenant_id,
            MarketSnapshot.workspace_id == self.actor.workspace_id,
            MarketSnapshot.owner_user_id == self.actor.user_id,
            MarketSnapshot.task_id == task_id,
            MarketSnapshot.run_id == run_id,
        )
        market_snapshot = await self.session.scalar(
            select(MarketSnapshot.snapshot)
            .where(*scope)
            .order_by(
                MarketSnapshot.fetched_at.desc(),
                MarketSnapshot.created_at.desc(),
                MarketSnapshot.id.desc(),
            )
            .limit(1)
        )
        web_evidence = tuple(
            (
                await self.session.scalars(
                    select(WebEvidence.payload)
                    .where(
                        WebEvidence.tenant_id == self.actor.tenant_id,
                        WebEvidence.workspace_id == self.actor.workspace_id,
                        WebEvidence.owner_user_id == self.actor.user_id,
                        WebEvidence.task_id == task_id,
                        WebEvidence.run_id == run_id,
                    )
                    .order_by(
                        WebEvidence.fetched_at.asc(),
                        WebEvidence.created_at.asc(),
                        WebEvidence.id.asc(),
                    )
                )
            ).all()
        )
        return TaskRunSourceRecords(
            market_snapshot=market_snapshot,
            web_evidence=web_evidence,
        )

    async def get_stage_events(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
    ) -> tuple[TaskRunStageEventRecord, ...]:
        rows = (
            await self.session.execute(
                select(
                    DomainEvent.event_type,
                    DomainEvent.sequence,
                    DomainEvent.created_at,
                    DomainEvent.source_event_id.is_not(None).label(
                        "from_official_stream"
                    ),
                )
                .where(
                    DomainEvent.tenant_id == self.actor.tenant_id,
                    DomainEvent.workspace_id == self.actor.workspace_id,
                    DomainEvent.owner_user_id == self.actor.user_id,
                    DomainEvent.task_id == task_id,
                    DomainEvent.run_id == run_id,
                )
                .order_by(DomainEvent.sequence.asc())
            )
        ).all()
        return tuple(
            TaskRunStageEventRecord(
                event_type=row[0],
                sequence=row[1],
                recorded_at=row[2],
                from_official_stream=row[3],
            )
            for row in rows
        )


class ArtifactVersionRepository(ActorScopedRepository[ArtifactVersion]):
    model = ArtifactVersion


class DecisionRepository(ActorScopedRepository[Decision]):
    model = Decision


class TaskCommandRepository(ActorScopedRepository[TaskCommand]):
    model = TaskCommand


class ArtifactRepository(ActorScopedRepository[Artifact]):
    model = Artifact

    async def commit_version(
        self,
        *,
        artifact_id: UUID,
        run_id: UUID,
        content: dict[str, Any],
        schema_version: str = "1.0",
    ) -> ArtifactVersion:
        artifact_run = (
            await self.session.execute(
                select(Artifact, Run)
                .join(
                    Run,
                    and_(
                        Run.id == run_id,
                        Run.task_id == Artifact.task_id,
                        Run.tenant_id == Artifact.tenant_id,
                        Run.workspace_id == Artifact.workspace_id,
                        Run.owner_user_id == Artifact.owner_user_id,
                    ),
                )
                .where(Artifact.id == artifact_id, self._actor_scope(Artifact))
                .with_for_update(of=Artifact)
            )
        ).one_or_none()
        if artifact_run is None:
            raise ScopedResourceNotFound("artifact and run lineage not found")

        artifact, run = artifact_run
        version_number = (
            int(
                (
                    await self.session.scalar(
                        select(
                            func.coalesce(func.max(ArtifactVersion.version_number), 0)
                        ).where(
                            ArtifactVersion.artifact_id == artifact.id,
                            self._actor_scope(ArtifactVersion),
                        )
                    )
                )
                or 0
            )
            + 1
        )
        artifact_version = ArtifactVersion(
            id=uuid4(),
            tenant_id=artifact.tenant_id,
            workspace_id=artifact.workspace_id,
            owner_user_id=artifact.owner_user_id,
            artifact_id=artifact.id,
            task_id=artifact.task_id,
            run_id=run.id,
            version_number=version_number,
            schema_version=schema_version,
            status="committed",
            content=content,
        )
        artifact.latest_version_number = version_number
        self.session.add(artifact_version)
        await self.session.flush()
        return artifact_version

    async def commit_version_and_decision(
        self,
        *,
        artifact_id: UUID,
        run_id: UUID,
        content: dict[str, Any],
        decision: dict[str, Any],
        evidence_verdict: dict[str, Any],
        risk_verdict: dict[str, Any],
        schema_version: str = "1.0",
    ) -> ArtifactCommit:
        artifact_run_statement = (
            select(Artifact, Run)
            .join(
                Run,
                and_(
                    Run.id == run_id,
                    Run.task_id == Artifact.task_id,
                    Run.tenant_id == Artifact.tenant_id,
                    Run.workspace_id == Artifact.workspace_id,
                    Run.owner_user_id == Artifact.owner_user_id,
                ),
            )
            .where(Artifact.id == artifact_id, self._actor_scope(Artifact))
            .with_for_update(of=Artifact)
        )
        artifact_run = (
            await self.session.execute(artifact_run_statement)
        ).one_or_none()
        if artifact_run is None:
            raise ScopedResourceNotFound("artifact and run lineage not found")

        artifact, run = artifact_run
        version_statement = select(
            func.coalesce(func.max(ArtifactVersion.version_number), 0)
        ).where(
            ArtifactVersion.artifact_id == artifact.id,
            self._actor_scope(ArtifactVersion),
        )
        version_number = int((await self.session.scalar(version_statement)) or 0) + 1

        artifact_version = ArtifactVersion(
            id=uuid4(),
            tenant_id=artifact.tenant_id,
            workspace_id=artifact.workspace_id,
            owner_user_id=artifact.owner_user_id,
            artifact_id=artifact.id,
            task_id=artifact.task_id,
            run_id=run.id,
            version_number=version_number,
            schema_version=schema_version,
            status="committed",
            content=content,
        )
        final_decision = Decision(
            id=uuid4(),
            tenant_id=artifact.tenant_id,
            workspace_id=artifact.workspace_id,
            owner_user_id=artifact.owner_user_id,
            artifact_id=artifact.id,
            artifact_version_id=artifact_version.id,
            task_id=artifact.task_id,
            run_id=run.id,
            decision_version=version_number,
            decision=decision,
            evidence_verdict=evidence_verdict,
            risk_verdict=risk_verdict,
        )
        artifact.latest_version_number = version_number
        self.session.add_all([artifact_version, final_decision])
        await self.session.flush()
        return ArtifactCommit(
            artifact_version=artifact_version, decision=final_decision
        )


async def resolve_actor(session: AsyncSession, actor: ActorContext) -> ResolvedActor:
    if not actor.tenant_id or not actor.workspace_id or not actor.user_id:
        raise PermissionError(
            "actor tenant, workspace and user identifiers are required"
        )

    statement = (
        select(
            Tenant.id,
            Workspace.id,
            User.id,
            Membership.id,
            Membership.role,
            Membership.permissions,
        )
        .select_from(Tenant)
        .join(
            Workspace,
            and_(
                Workspace.tenant_id == Tenant.id,
                Workspace.external_id == actor.workspace_id,
            ),
        )
        .join(
            Membership,
            and_(
                Membership.tenant_id == Tenant.id,
                Membership.workspace_id == Workspace.id,
                Membership.is_active.is_(True),
            ),
        )
        .join(
            User,
            and_(
                Membership.user_id == User.id,
                User.tenant_id == Tenant.id,
                User.identity_issuer == actor.identity_issuer,
                User.external_subject == actor.user_id,
            ),
        )
        .where(
            Tenant.external_id == actor.tenant_id,
            *(
                (Membership.id == actor.context_id,)
                if actor.context_id is not None
                else ()
            ),
        )
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise PermissionError("actor is not an active member of the workspace")
    return ResolvedActor(
        tenant_id=row[0],
        workspace_id=row[1],
        user_id=row[2],
        membership_id=row[3],
        role=row[4],
        permissions=tuple(row[5]),
    )


__all__ = [
    "ActorContext",
    "ActorScopedRepository",
    "ArtifactCommit",
    "ArtifactRepository",
    "ArtifactVersionRepository",
    "DecisionRepository",
    "MarketSnapshotRepository",
    "MembershipRepository",
    "OBSERVABILITY_DELIVERY_PROVIDERS",
    "OBSERVABILITY_DELIVERY_STATUSES",
    "ObservabilityDeliveryIntent",
    "ObservabilityDeliveryLease",
    "ObservabilityDeliveryRepository",
    "ResolvedActor",
    "RunRepository",
    "ScopedResourceNotFound",
    "TaskCommandRepository",
    "TaskRunProjectionRepository",
    "TaskRunStageEventRecord",
    "TaskRunSourceRecords",
    "TaskRepository",
    "ThreadRepository",
    "WebEvidenceRepository",
    "resolve_actor",
]
