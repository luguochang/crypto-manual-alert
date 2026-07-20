from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.monitors.conditions import require_monitor_condition_evaluator
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    MONITOR_STATUSES,
    MONITOR_TASK_TYPES,
    MonitorCronCommand,
    MonitorDefinition,
    MonitorDestination,
    MonitorTrigger,
    NotificationDestination,
    Task,
    TaskCommand,
    Thread,
    UsageLedgerEntry,
    WorkspaceEntitlement,
)
from crypto_alert_v2.persistence.repositories import (
    ActorContext,
    ActorScopedRepository,
    ResolvedActor,
    ScopedResourceNotFound,
    resolve_actor,
)


ACTIVE_MONITOR_STATUSES = ("draft", "active", "paused", "degraded")
ACTIVE_TASK_STATUSES = ("queued", "running", "waiting_human")


class MonitorPersistenceError(RuntimeError):
    """Base error for Product Scheduled Monitor persistence operations."""


class EntitlementDenied(MonitorPersistenceError):
    """Raised when the workspace has no currently usable entitlement."""


class MonitorVersionConflict(MonitorPersistenceError):
    """Raised when an optimistic monitor update uses a stale version."""


class MonitorIdempotencyConflict(MonitorPersistenceError):
    """Raised when a stable idempotency key is reused with another request."""


class TriggerAdmissionRejected(MonitorPersistenceError):
    """Raised for malformed trigger requests before an append-only receipt exists."""


@dataclass(frozen=True, slots=True)
class MonitorAdmission:
    trigger: MonitorTrigger
    thread: Thread | None
    task: Task | None
    task_command: TaskCommand | None
    usage: UsageLedgerEntry | None
    created: bool

    @property
    def admitted(self) -> bool:
        return self.trigger.status == "admitted"


@dataclass(frozen=True, slots=True)
class CronCommandLease:
    command: MonitorCronCommand
    fence_token: int


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _require_text(value: str, *, field: str, limit: int = 255) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > limit:
        raise ValueError(f"{field} must be between 1 and {limit} characters")
    return normalized


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _month_start(value: datetime) -> datetime:
    value = value.astimezone(UTC)
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _identity_digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _validate_hash(value: str, *, field: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ValueError(f"{field} must be a 64-character SHA-256 hex digest")
    try:
        int(normalized, 16)
    except ValueError as error:
        raise ValueError(
            f"{field} must be a 64-character SHA-256 hex digest"
        ) from error
    return normalized


def _parse_local_minute(value: Any, *, field: str) -> int:
    if (
        not isinstance(value, str)
        or len(value) != 5
        or value[2] != ":"
        or not value[:2].isdigit()
        or not value[3:].isdigit()
    ):
        raise ValueError(f"quiet_hours.{field} must be HH:MM")
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"quiet_hours.{field} must be HH:MM")
    try:
        hour, minute = (int(part) for part in parts)
    except ValueError as error:
        raise ValueError(f"quiet_hours.{field} must be HH:MM") from error
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"quiet_hours.{field} must be HH:MM")
    return hour * 60 + minute


def _normalize_quiet_hours(
    value: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("quiet_hours must be an object")
    start = value.get("start")
    end = value.get("end")
    start_minute = _parse_local_minute(start, field="start")
    end_minute = _parse_local_minute(end, field="end")
    if start_minute == end_minute:
        raise ValueError("quiet_hours start and end must differ")
    return {"start": str(start), "end": str(end)}


def _normalize_condition(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("condition must be an object")
    kind = value.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("condition must contain a non-empty string kind")
    return dict(value)


def _task_payload_from_template(template: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(template)
    if payload.get("task_type") == "market_analysis":
        payload.pop("task_type", None)
    return payload


def _in_quiet_hours(monitor: MonitorDefinition, value: datetime) -> bool:
    quiet_hours = monitor.quiet_hours
    if quiet_hours is None:
        return False
    try:
        start = _parse_local_minute(quiet_hours.get("start"), field="start")
        end = _parse_local_minute(quiet_hours.get("end"), field="end")
        local_time = value.astimezone(ZoneInfo(monitor.timezone))
    except (AttributeError, ValueError, ZoneInfoNotFoundError):
        return True
    current = local_time.hour * 60 + local_time.minute
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


class WorkspaceEntitlementRepository(ActorScopedRepository[WorkspaceEntitlement]):
    model = WorkspaceEntitlement

    async def current(
        self, *, now: datetime | None = None
    ) -> WorkspaceEntitlement | None:
        current_time = _as_utc(now)
        statement = (
            select(self.model)
            .where(
                self._actor_scope(),
                self.model.active.is_(True),
                self.model.valid_from <= current_time,
                or_(
                    self.model.valid_until.is_(None),
                    self.model.valid_until > current_time,
                ),
            )
            .order_by(self.model.valid_from.desc())
        )
        return await self.session.scalar(statement)


class UsageLedgerRepository(ActorScopedRepository[UsageLedgerEntry]):
    model = UsageLedgerEntry

    async def append(
        self,
        *,
        entitlement_id: UUID,
        period_start: datetime,
        idempotency_key: str,
        quantity: int = 1,
        unit: str = "trigger",
        monitor_id: UUID | None = None,
        trigger_id: UUID | None = None,
        ledger_metadata: Mapping[str, Any] | None = None,
    ) -> UsageLedgerEntry:
        if quantity < 1:
            raise ValueError("quantity must be positive")
        resolved = await resolve_actor(self.session, self.actor)
        key = _require_text(idempotency_key, field="idempotency_key")
        statement = (
            insert(UsageLedgerEntry)
            .values(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                entitlement_id=entitlement_id,
                monitor_id=monitor_id,
                trigger_id=trigger_id,
                period_start=_as_utc(period_start),
                quantity=quantity,
                unit=_require_text(unit, field="unit", limit=32),
                idempotency_key=key,
                metadata=dict(ledger_metadata or {}),
            )
            .on_conflict_do_nothing(
                index_elements=[
                    UsageLedgerEntry.tenant_id,
                    UsageLedgerEntry.workspace_id,
                    UsageLedgerEntry.idempotency_key,
                ]
            )
            .returning(UsageLedgerEntry.id)
        )
        inserted_id = await self.session.scalar(statement)
        if inserted_id is None:
            return await self.session.scalar(
                select(UsageLedgerEntry).where(
                    self._actor_scope(),
                    UsageLedgerEntry.idempotency_key == key,
                )
            )
        return await self.session.scalar(
            select(UsageLedgerEntry).where(UsageLedgerEntry.id == inserted_id)
        )

    async def list_for_period(
        self, period_start: datetime, *, limit: int = 500
    ) -> list[UsageLedgerEntry]:
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        statement = (
            select(self.model)
            .where(
                self._actor_scope(), self.model.period_start == _as_utc(period_start)
            )
            .order_by(self.model.created_at, self.model.id)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())


class MonitorDestinationRepository(ActorScopedRepository[MonitorDestination]):
    model = MonitorDestination

    async def list_for_monitor(self, monitor_id: UUID) -> list[MonitorDestination]:
        statement = (
            select(self.model)
            .where(self._actor_scope(), self.model.monitor_id == monitor_id)
            .order_by(self.model.created_at, self.model.id)
        )
        return list((await self.session.scalars(statement)).all())


class MonitorCronCommandRepository:
    """System-facing durable outbox operations; command payloads are control-only."""

    model = MonitorCronCommand

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lease(
        self,
        *,
        worker_id: str,
        limit: int = 25,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> list[CronCommandLease]:
        worker = _require_text(worker_id, field="worker_id")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if lease_seconds < 1 or lease_seconds > 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        current_time = _as_utc(now)
        statement = (
            select(self.model)
            .where(
                self.model.available_at <= current_time,
                or_(
                    self.model.status == "pending",
                    and_(
                        self.model.status == "leased",
                        self.model.lease_expires_at <= current_time,
                    ),
                ),
            )
            .order_by(self.model.available_at, self.model.created_at, self.model.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        commands = list((await self.session.scalars(statement)).all())
        leases: list[CronCommandLease] = []
        for command in commands:
            command.status = "leased"
            command.lease_owner = worker
            command.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
            command.fence_token += 1
            command.attempt += 1
            leases.append(
                CronCommandLease(command=command, fence_token=command.fence_token)
            )
        await self.session.flush()
        return leases

    async def finish(
        self,
        *,
        command_id: UUID,
        worker_id: str,
        fence_token: int,
        succeeded: bool,
        error: str | None = None,
        retry_at: datetime | None = None,
    ) -> MonitorCronCommand:
        worker = _require_text(worker_id, field="worker_id")
        if fence_token < 1:
            raise ValueError("fence_token must be positive")
        statement = (
            select(self.model).where(self.model.id == command_id).with_for_update()
        )
        command = await self.session.scalar(statement)
        if (
            command is None
            or command.status != "leased"
            or command.lease_owner != worker
            or command.fence_token != fence_token
        ):
            raise ScopedResourceNotFound("cron command lease not found")

        now = datetime.now(UTC)
        command.lease_owner = None
        command.lease_expires_at = None
        command.last_error = error[:500] if error else None
        command.completed_at = now if succeeded else None
        if succeeded:
            command.status = "succeeded"
        elif retry_at is not None:
            command.status = "pending"
            command.available_at = _as_utc(retry_at)
        else:
            command.status = "failed"
        if succeeded:
            monitor = await self.session.scalar(
                select(MonitorDefinition)
                .where(
                    MonitorDefinition.tenant_id == command.tenant_id,
                    MonitorDefinition.workspace_id == command.workspace_id,
                    MonitorDefinition.owner_user_id == command.owner_user_id,
                    MonitorDefinition.id == command.monitor_id,
                )
                .with_for_update()
            )
            if (
                monitor is not None
                and command.desired_revision <= monitor.desired_revision
            ):
                monitor.applied_revision = max(
                    monitor.applied_revision, command.desired_revision
                )
        await self.session.flush()
        return command


class MonitorRepository(ActorScopedRepository[MonitorDefinition]):
    """Actor-scoped monitor CRUD and the atomic trigger admission primitive."""

    model = MonitorDefinition

    def __init__(self, session: AsyncSession, actor: ActorContext) -> None:
        super().__init__(session, actor)
        self.entitlements = WorkspaceEntitlementRepository(session, actor)
        self.destinations = MonitorDestinationRepository(session, actor)
        self.usage = UsageLedgerRepository(session, actor)

    async def _resolved_actor(self) -> ResolvedActor:
        return await resolve_actor(self.session, self.actor)

    async def _locked_entitlement(
        self, resolved: ResolvedActor, *, now: datetime
    ) -> WorkspaceEntitlement | None:
        return await self.session.scalar(
            select(WorkspaceEntitlement)
            .where(
                WorkspaceEntitlement.tenant_id == resolved.tenant_id,
                WorkspaceEntitlement.workspace_id == resolved.workspace_id,
            )
            .with_for_update()
        )

    @staticmethod
    def _usable_entitlement(
        entitlement: WorkspaceEntitlement | None, *, now: datetime
    ) -> WorkspaceEntitlement | None:
        if entitlement is None or not entitlement.active:
            return None
        if entitlement.valid_from > now:
            return None
        if entitlement.valid_until is not None and entitlement.valid_until <= now:
            return None
        return entitlement

    @staticmethod
    def _validate_timezone(value: str) -> str:
        zone = _require_text(value, field="timezone", limit=128)
        try:
            ZoneInfo(zone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return zone

    async def require_entitlement(
        self, *, now: datetime | None = None
    ) -> WorkspaceEntitlement:
        resolved = await self._resolved_actor()
        current_time = _as_utc(now)
        entitlement = await self._locked_entitlement(resolved, now=current_time)
        usable = self._usable_entitlement(entitlement, now=current_time)
        if usable is None:
            raise EntitlementDenied("workspace entitlement is unavailable")
        return usable

    async def _derive_task_template(
        self,
        resolved: ResolvedActor,
        *,
        artifact_id: UUID,
        artifact_version_id: UUID,
        run_task_type: str,
    ) -> dict[str, Any]:
        lineage = (
            await self.session.execute(
                select(Artifact, ArtifactVersion, Task)
                .join(
                    ArtifactVersion,
                    and_(
                        ArtifactVersion.id == artifact_version_id,
                        ArtifactVersion.artifact_id == Artifact.id,
                        ArtifactVersion.tenant_id == Artifact.tenant_id,
                        ArtifactVersion.workspace_id == Artifact.workspace_id,
                        ArtifactVersion.owner_user_id == Artifact.owner_user_id,
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
                    Artifact.id == artifact_id,
                    Artifact.tenant_id == resolved.tenant_id,
                    Artifact.workspace_id == resolved.workspace_id,
                    Artifact.owner_user_id == resolved.user_id,
                    ArtifactVersion.status == "committed",
                )
            )
        ).one_or_none()
        if lineage is None:
            raise ScopedResourceNotFound("committed artifact lineage not found")
        _, _, source_task = lineage
        if source_task.task_type not in MONITOR_TASK_TYPES:
            raise ValueError("source task type is not schedulable")
        if source_task.task_type != run_task_type:
            raise ValueError("run_task_type must match the committed source task")

        source_payload = source_task.request_payload
        required = ("symbol", "horizon", "query_text")
        if any(
            not isinstance(source_payload.get(key), str)
            or not source_payload[key].strip()
            for key in required
        ):
            raise ValueError("source task does not contain a complete task template")
        template: dict[str, Any] = {
            "task_type": source_task.task_type,
            "symbol": source_payload["symbol"],
            "horizon": source_payload["horizon"],
            "query_text": source_payload["query_text"],
        }
        if source_task.task_type == "market_analysis":
            template["notify"] = bool(source_payload.get("notify", False))
        return template

    @staticmethod
    def _cron_control_payload(monitor: MonitorDefinition) -> dict[str, Any]:
        return {
            "monitor_id": str(monitor.id),
            "cron_binding_id": str(monitor.cron_binding_id),
            "cron_schedule": monitor.cron_schedule,
            "timezone": monitor.timezone,
            "expires_at": monitor.expires_at.isoformat()
            if monitor.expires_at
            else None,
            "quiet_hours": monitor.quiet_hours,
            "status": monitor.status,
            "schedule_version": monitor.schedule_version,
            "desired_revision": monitor.desired_revision,
        }

    async def _enqueue_cron_command(
        self,
        monitor: MonitorDefinition,
        *,
        command_type: str,
        idempotency_key: str | None = None,
        request_payload_hash: str | None = None,
    ) -> MonitorCronCommand:
        control_payload = self._cron_control_payload(monitor)
        command = MonitorCronCommand(
            id=uuid4(),
            tenant_id=monitor.tenant_id,
            workspace_id=monitor.workspace_id,
            owner_user_id=monitor.owner_user_id,
            monitor_id=monitor.id,
            command_type=command_type,
            desired_revision=monitor.desired_revision,
            request_payload_hash=_validate_hash(
                request_payload_hash or _payload_hash(control_payload),
                field="request_payload_hash",
            ),
            payload=control_payload,
            status="pending",
            idempotency_key=idempotency_key
            or f"monitor:{monitor.id}:revision:{monitor.desired_revision}",
            attempt=0,
            fence_token=0,
        )
        self.session.add(command)
        await self.session.flush()
        return command

    async def create_monitor(
        self,
        *,
        admission_idempotency_key: str,
        request_payload_hash: str,
        artifact_id: UUID,
        artifact_version_id: UUID,
        name: str,
        run_task_type: str,
        condition: Mapping[str, Any],
        cron_schedule: str,
        timezone: str,
        expires_at: datetime | None = None,
        quiet_hours: Mapping[str, Any] | None = None,
        status: str = "draft",
        now: datetime | None = None,
    ) -> MonitorDefinition:
        normalized_condition = _normalize_condition(condition)
        require_monitor_condition_evaluator(normalized_condition["kind"])
        admission_key = _require_text(
            admission_idempotency_key, field="admission_idempotency_key"
        )
        admission_hash = _validate_hash(
            request_payload_hash, field="request_payload_hash"
        )
        resolved = await self._resolved_actor()
        existing = await self.session.scalar(
            select(MonitorDefinition).where(
                MonitorDefinition.tenant_id == resolved.tenant_id,
                MonitorDefinition.workspace_id == resolved.workspace_id,
                MonitorDefinition.owner_user_id == resolved.user_id,
                MonitorDefinition.admission_idempotency_key == admission_key,
            )
        )
        if existing is not None:
            if existing.request_payload_hash != admission_hash:
                raise MonitorIdempotencyConflict(
                    "monitor admission idempotency key conflicts with its request hash"
                )
            return existing
        if run_task_type not in MONITOR_TASK_TYPES:
            raise ValueError("unsupported run_task_type")
        if status not in MONITOR_STATUSES:
            raise ValueError("unsupported monitor status")
        normalized_quiet_hours = _normalize_quiet_hours(quiet_hours)
        monitor_name = _require_text(name, field="name")
        schedule = _require_text(cron_schedule, field="cron_schedule")
        zone = self._validate_timezone(timezone)
        current_time = _as_utc(now)
        entitlement = await self._locked_entitlement(resolved, now=current_time)
        concurrent_existing = await self.session.scalar(
            select(MonitorDefinition).where(
                MonitorDefinition.tenant_id == resolved.tenant_id,
                MonitorDefinition.workspace_id == resolved.workspace_id,
                MonitorDefinition.owner_user_id == resolved.user_id,
                MonitorDefinition.admission_idempotency_key == admission_key,
            )
        )
        if concurrent_existing is not None:
            if concurrent_existing.request_payload_hash != admission_hash:
                raise MonitorIdempotencyConflict(
                    "monitor admission idempotency key conflicts with its request hash"
                )
            return concurrent_existing
        usable = self._usable_entitlement(entitlement, now=current_time)
        if usable is None:
            raise EntitlementDenied("workspace entitlement is unavailable")

        if status in ACTIVE_MONITOR_STATUSES:
            active_count = await self.session.scalar(
                select(func.count(MonitorDefinition.id)).where(
                    MonitorDefinition.tenant_id == resolved.tenant_id,
                    MonitorDefinition.workspace_id == resolved.workspace_id,
                    MonitorDefinition.status.in_(ACTIVE_MONITOR_STATUSES),
                )
            )
            if int(active_count or 0) >= usable.active_monitor_limit:
                raise EntitlementDenied("active monitor limit exceeded")

        template = await self._derive_task_template(
            resolved,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            run_task_type=run_task_type,
        )
        monitor = MonitorDefinition(
            id=uuid4(),
            tenant_id=resolved.tenant_id,
            workspace_id=resolved.workspace_id,
            owner_user_id=resolved.user_id,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            name=monitor_name,
            run_task_type=run_task_type,
            condition=normalized_condition,
            task_template=template,
            admission_idempotency_key=admission_key,
            request_payload_hash=admission_hash,
            cron_schedule=schedule,
            timezone=zone,
            expires_at=_as_utc(expires_at) if expires_at else None,
            quiet_hours=normalized_quiet_hours,
            status=status,
            schedule_version=1,
            desired_revision=1,
            applied_revision=0,
            cron_binding_id=uuid4(),
            version=1,
        )
        self.session.add(monitor)
        await self.session.flush()
        await self._enqueue_cron_command(
            monitor,
            command_type="create",
            idempotency_key=f"monitor:{monitor.id}:create:1",
            request_payload_hash=admission_hash,
        )
        return monitor

    async def update_monitor(
        self,
        monitor_id: UUID,
        *,
        expected_version: int,
        name: str | None = None,
        condition: Mapping[str, Any] | None = None,
        cron_schedule: str | None = None,
        timezone: str | None = None,
        expires_at: datetime | None = None,
        quiet_hours: Mapping[str, Any] | None = None,
        status: str | None = None,
        next_run_at: datetime | None = None,
        operation_idempotency_key: str | None = None,
        idempotency_key: str | None = None,
        operation_payload_hash: str | None = None,
    ) -> MonitorDefinition:
        if expected_version < 1:
            raise ValueError("expected_version must be positive")
        monitor = await self.session.scalar(
            select(MonitorDefinition)
            .where(self._actor_scope(), MonitorDefinition.id == monitor_id)
            .with_for_update()
        )
        if monitor is None:
            raise ScopedResourceNotFound("monitor not found")
        if operation_idempotency_key and idempotency_key:
            raise ValueError("provide only one operation idempotency key")
        operation_key = operation_idempotency_key or idempotency_key
        operation_fields = {
            "name": name,
            "condition": dict(condition) if condition is not None else None,
            "cron_schedule": cron_schedule,
            "timezone": timezone,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "quiet_hours": dict(quiet_hours) if quiet_hours is not None else None,
            "status": status,
            "next_run_at": next_run_at.isoformat() if next_run_at else None,
        }
        operation_hash = _validate_hash(
            operation_payload_hash or _payload_hash(operation_fields),
            field="operation_payload_hash",
        )
        requested_command_type = "update"
        if status == "paused":
            requested_command_type = "pause"
        elif status == "active":
            requested_command_type = "resume"
        elif status == "disabled":
            requested_command_type = "delete"
        if operation_key is not None:
            operation_key = _require_text(
                operation_key, field="operation_idempotency_key"
            )
            existing_command = await self.session.scalar(
                select(MonitorCronCommand).where(
                    MonitorCronCommand.tenant_id == monitor.tenant_id,
                    MonitorCronCommand.workspace_id == monitor.workspace_id,
                    MonitorCronCommand.owner_user_id == monitor.owner_user_id,
                    MonitorCronCommand.idempotency_key == operation_key,
                )
            )
            if existing_command is not None:
                if (
                    existing_command.monitor_id != monitor.id
                    or existing_command.command_type != requested_command_type
                    or existing_command.request_payload_hash != operation_hash
                ):
                    raise MonitorIdempotencyConflict(
                        "monitor operation idempotency key conflicts with its request hash"
                    )
                return monitor
        if monitor.version != expected_version:
            raise MonitorVersionConflict("monitor version is stale")
        if name is not None:
            monitor.name = _require_text(name, field="name")
        if condition is not None:
            monitor.condition = _normalize_condition(condition)
        schedule_changed = any(
            value is not None
            for value in (cron_schedule, timezone, expires_at, quiet_hours)
        )
        if cron_schedule is not None:
            monitor.cron_schedule = _require_text(cron_schedule, field="cron_schedule")
        if timezone is not None:
            monitor.timezone = self._validate_timezone(timezone)
        if expires_at is not None:
            monitor.expires_at = _as_utc(expires_at)
        if quiet_hours is not None:
            monitor.quiet_hours = _normalize_quiet_hours(quiet_hours)
        if status is not None:
            if status not in MONITOR_STATUSES:
                raise ValueError("unsupported monitor status")
            monitor.status = status
        if next_run_at is not None:
            monitor.next_run_at = _as_utc(next_run_at)

        if monitor.status in ACTIVE_MONITOR_STATUSES:
            entitlement = await self.require_entitlement()
            count = await self.session.scalar(
                select(func.count(MonitorDefinition.id)).where(
                    MonitorDefinition.tenant_id == monitor.tenant_id,
                    MonitorDefinition.workspace_id == monitor.workspace_id,
                    MonitorDefinition.status.in_(ACTIVE_MONITOR_STATUSES),
                )
            )
            if int(count or 0) > entitlement.active_monitor_limit:
                raise EntitlementDenied("active monitor limit exceeded")

        command_type = requested_command_type
        monitor.schedule_version += 1 if schedule_changed or status is not None else 0
        monitor.desired_revision += 1
        monitor.version += 1
        await self._enqueue_cron_command(
            monitor,
            command_type=command_type,
            idempotency_key=operation_key,
            request_payload_hash=operation_hash,
        )
        return monitor

    async def delete_monitor(
        self,
        monitor_id: UUID,
        *,
        expected_version: int,
        operation_idempotency_key: str | None = None,
        idempotency_key: str | None = None,
        operation_payload_hash: str | None = None,
    ) -> MonitorDefinition:
        return await self.update_monitor(
            monitor_id,
            expected_version=expected_version,
            status="disabled",
            operation_idempotency_key=operation_idempotency_key,
            idempotency_key=idempotency_key,
            operation_payload_hash=operation_payload_hash,
        )

    async def pause_monitor(
        self,
        monitor_id: UUID,
        *,
        expected_version: int,
        operation_idempotency_key: str,
        operation_payload_hash: str | None = None,
    ) -> MonitorDefinition:
        return await self.update_monitor(
            monitor_id,
            expected_version=expected_version,
            status="paused",
            operation_idempotency_key=operation_idempotency_key,
            operation_payload_hash=operation_payload_hash,
        )

    async def resume_monitor(
        self,
        monitor_id: UUID,
        *,
        expected_version: int,
        operation_idempotency_key: str,
        operation_payload_hash: str | None = None,
    ) -> MonitorDefinition:
        return await self.update_monitor(
            monitor_id,
            expected_version=expected_version,
            status="active",
            operation_idempotency_key=operation_idempotency_key,
            operation_payload_hash=operation_payload_hash,
        )

    async def add_destination(
        self, monitor_id: UUID, destination_id: UUID
    ) -> MonitorDestination:
        resolved = await self._resolved_actor()
        monitor_exists = await self.session.scalar(
            select(MonitorDefinition.id).where(
                MonitorDefinition.id == monitor_id,
                MonitorDefinition.tenant_id == resolved.tenant_id,
                MonitorDefinition.workspace_id == resolved.workspace_id,
                MonitorDefinition.owner_user_id == resolved.user_id,
            )
        )
        if monitor_exists is None:
            raise ScopedResourceNotFound("monitor not found")
        destination_exists = await self.session.scalar(
            select(NotificationDestination.id).where(
                NotificationDestination.id == destination_id,
                NotificationDestination.tenant_id == resolved.tenant_id,
                NotificationDestination.workspace_id == resolved.workspace_id,
                NotificationDestination.owner_user_id == resolved.user_id,
            )
        )
        if destination_exists is None:
            raise ScopedResourceNotFound("destination not found")
        binding = MonitorDestination(
            id=uuid4(),
            tenant_id=resolved.tenant_id,
            workspace_id=resolved.workspace_id,
            owner_user_id=resolved.user_id,
            monitor_id=monitor_id,
            destination_id=destination_id,
        )
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def remove_destination(self, monitor_id: UUID, destination_id: UUID) -> None:
        binding = await self.session.scalar(
            select(MonitorDestination)
            .where(
                self.destinations._actor_scope(),
                MonitorDestination.monitor_id == monitor_id,
                MonitorDestination.destination_id == destination_id,
            )
            .with_for_update()
        )
        if binding is None:
            raise ScopedResourceNotFound("monitor destination binding not found")
        await self.session.delete(binding)
        await self.session.flush()

    async def _find_existing_trigger(
        self,
        monitor: MonitorDefinition,
        *,
        kind: str,
        official_run_id: str | None,
        manual_stable_key: str | None,
    ) -> MonitorTrigger | None:
        identity_filter = (
            MonitorTrigger.official_run_id == official_run_id
            if kind == "cron"
            else MonitorTrigger.manual_stable_key == manual_stable_key
        )
        return await self.session.scalar(
            select(MonitorTrigger).where(
                MonitorTrigger.tenant_id == monitor.tenant_id,
                MonitorTrigger.workspace_id == monitor.workspace_id,
                MonitorTrigger.owner_user_id == monitor.owner_user_id,
                MonitorTrigger.monitor_id == monitor.id,
                identity_filter,
            )
        )

    async def _admission_result(
        self, trigger: MonitorTrigger, *, created: bool
    ) -> MonitorAdmission:
        task = None
        thread = None
        command = None
        usage = None
        if trigger.task_id is not None:
            task = await self.session.scalar(
                select(Task).where(Task.id == trigger.task_id)
            )
        if trigger.thread_id is not None:
            thread = await self.session.scalar(
                select(Thread).where(Thread.id == trigger.thread_id)
            )
        if task is not None:
            command = await self.session.scalar(
                select(TaskCommand).where(
                    TaskCommand.task_id == task.id,
                    TaskCommand.command_type == "submit",
                )
            )
            usage = await self.session.scalar(
                select(UsageLedgerEntry).where(
                    UsageLedgerEntry.trigger_id == trigger.id
                )
            )
        return MonitorAdmission(
            trigger=trigger,
            thread=thread,
            task=task,
            task_command=command,
            usage=usage,
            created=created,
        )

    async def admit_trigger(
        self,
        monitor_id: UUID,
        *,
        kind: str,
        cron_binding_id: UUID | None = None,
        official_cron_id: str | None = None,
        official_run_id: str | None = None,
        official_thread_id: str | None = None,
        manual_stable_key: str | None = None,
        schedule_version: int | None = None,
        received_at: datetime | None = None,
    ) -> MonitorAdmission:
        if kind not in ("manual", "cron"):
            raise TriggerAdmissionRejected("kind must be manual or cron")
        if kind == "cron":
            if not official_run_id:
                raise TriggerAdmissionRejected(
                    "cron admission requires official_run_id"
                )
            if cron_binding_id is None:
                raise TriggerAdmissionRejected(
                    "cron admission requires cron_binding_id"
                )
            if manual_stable_key is not None:
                raise TriggerAdmissionRejected(
                    "cron admission cannot use manual_stable_key"
                )
        elif not manual_stable_key:
            raise TriggerAdmissionRejected(
                "manual admission requires manual_stable_key"
            )
        current_time = _as_utc(received_at)
        resolved = await self._resolved_actor()
        monitor = await self.session.scalar(
            select(MonitorDefinition)
            .where(self._actor_scope(), MonitorDefinition.id == monitor_id)
            .with_for_update()
        )
        if monitor is None:
            raise ScopedResourceNotFound("monitor not found")
        if kind == "cron" and cron_binding_id != monitor.cron_binding_id:
            raise TriggerAdmissionRejected(
                "cron_binding_id does not match monitor binding"
            )
        condition = monitor.condition if isinstance(monitor.condition, Mapping) else {}
        require_monitor_condition_evaluator(condition.get("kind"))
        existing = await self._find_existing_trigger(
            monitor,
            kind=kind,
            official_run_id=official_run_id,
            manual_stable_key=manual_stable_key,
        )
        if existing is not None:
            return await self._admission_result(existing, created=False)

        if schedule_version is not None and schedule_version < 1:
            raise TriggerAdmissionRejected("schedule_version must be positive")
        effective_schedule_version = schedule_version or monitor.schedule_version
        trigger_id = uuid4()
        identity = official_run_id if kind == "cron" else manual_stable_key
        assert identity is not None
        suppression_reason: str | None = None
        entitlement = await self._locked_entitlement(resolved, now=current_time)
        usable = self._usable_entitlement(entitlement, now=current_time)
        if usable is None:
            suppression_reason = "entitlement_unavailable"
        elif monitor.status != "active":
            suppression_reason = f"monitor_status:{monitor.status}"
        elif monitor.expires_at is not None and monitor.expires_at <= current_time:
            suppression_reason = "monitor_expired"
        elif effective_schedule_version != monitor.schedule_version:
            suppression_reason = "stale_schedule_version"
        elif _in_quiet_hours(monitor, current_time):
            suppression_reason = "quiet_hours"
        else:
            active_monitor_count = await self.session.scalar(
                select(func.count(MonitorDefinition.id)).where(
                    MonitorDefinition.tenant_id == monitor.tenant_id,
                    MonitorDefinition.workspace_id == monitor.workspace_id,
                    MonitorDefinition.status.in_(ACTIVE_MONITOR_STATUSES),
                )
            )
            if int(active_monitor_count or 0) > usable.active_monitor_limit:
                suppression_reason = "active_monitor_limit_exceeded"

            latest_admission = await self.session.scalar(
                select(func.max(MonitorTrigger.admitted_at)).where(
                    MonitorTrigger.tenant_id == monitor.tenant_id,
                    MonitorTrigger.workspace_id == monitor.workspace_id,
                    MonitorTrigger.owner_user_id == monitor.owner_user_id,
                    MonitorTrigger.monitor_id == monitor.id,
                    MonitorTrigger.status == "admitted",
                )
            )
            if (
                suppression_reason is None
                and latest_admission is not None
                and current_time
                < latest_admission + timedelta(seconds=usable.min_interval_seconds)
            ):
                suppression_reason = "minimum_interval_not_elapsed"

            month = _month_start(current_time)
            monthly_units = await self.session.scalar(
                select(func.coalesce(func.sum(UsageLedgerEntry.quantity), 0)).where(
                    UsageLedgerEntry.tenant_id == monitor.tenant_id,
                    UsageLedgerEntry.workspace_id == monitor.workspace_id,
                    UsageLedgerEntry.period_start == month,
                )
            )
            if (
                suppression_reason is None
                and int(monthly_units or 0) >= usable.monthly_trigger_limit
            ):
                suppression_reason = "monthly_trigger_limit_exceeded"

            concurrent_tasks = await self.session.scalar(
                select(func.count(Task.id))
                .select_from(Task)
                .where(
                    Task.tenant_id == monitor.tenant_id,
                    Task.workspace_id == monitor.workspace_id,
                    Task.status.in_(ACTIVE_TASK_STATUSES),
                    Task.id.in_(
                        select(MonitorTrigger.task_id).where(
                            MonitorTrigger.tenant_id == monitor.tenant_id,
                            MonitorTrigger.workspace_id == monitor.workspace_id,
                            MonitorTrigger.status == "admitted",
                            MonitorTrigger.task_id.is_not(None),
                        )
                    ),
                )
            )
            if (
                suppression_reason is None
                and int(concurrent_tasks or 0) >= usable.max_concurrent_tasks
            ):
                suppression_reason = "max_concurrent_tasks_exceeded"

        if suppression_reason is not None:
            trigger = MonitorTrigger(
                id=trigger_id,
                tenant_id=monitor.tenant_id,
                workspace_id=monitor.workspace_id,
                owner_user_id=monitor.owner_user_id,
                monitor_id=monitor.id,
                official_cron_id=official_cron_id,
                official_run_id=official_run_id,
                official_thread_id=official_thread_id,
                manual_stable_key=manual_stable_key,
                kind=kind,
                status="suppressed",
                reason=suppression_reason,
                schedule_version=effective_schedule_version,
                received_at=current_time,
            )
            self.session.add(trigger)
            await self.session.flush()
            return await self._admission_result(trigger, created=True)

        task_payload = _task_payload_from_template(monitor.task_template)
        task_id = uuid4()
        thread_id = uuid4()
        task_idempotency_key = (
            f"monitor-trigger:{monitor.id}:{_identity_digest(kind, identity)}"
        )
        thread = Thread(
            id=thread_id,
            tenant_id=monitor.tenant_id,
            workspace_id=monitor.workspace_id,
            owner_user_id=monitor.owner_user_id,
            official_thread_id=None,
            title=monitor.name,
            context={
                "monitor_id": str(monitor.id),
                "trigger_id": str(trigger_id),
                "kind": kind,
                "schedule_version": monitor.schedule_version,
            },
        )
        self.session.add(thread)
        await self.session.flush()
        task = Task(
            id=task_id,
            tenant_id=monitor.tenant_id,
            workspace_id=monitor.workspace_id,
            owner_user_id=monitor.owner_user_id,
            thread_id=thread_id,
            task_type=monitor.run_task_type,
            status="queued",
            idempotency_key=task_idempotency_key,
            request_payload_hash=_payload_hash(task_payload),
            request_payload=task_payload,
        )
        self.session.add(task)
        await self.session.flush()
        trigger = MonitorTrigger(
            id=trigger_id,
            tenant_id=monitor.tenant_id,
            workspace_id=monitor.workspace_id,
            owner_user_id=monitor.owner_user_id,
            monitor_id=monitor.id,
            official_cron_id=official_cron_id,
            official_run_id=official_run_id,
            official_thread_id=official_thread_id,
            manual_stable_key=manual_stable_key,
            kind=kind,
            status="admitted",
            reason=None,
            schedule_version=monitor.schedule_version,
            task_id=task_id,
            thread_id=thread_id,
            received_at=current_time,
            admitted_at=current_time,
        )
        self.session.add(trigger)
        await self.session.flush()
        usage = UsageLedgerEntry(
            id=uuid4(),
            tenant_id=monitor.tenant_id,
            workspace_id=monitor.workspace_id,
            owner_user_id=monitor.owner_user_id,
            entitlement_id=usable.id,
            monitor_id=monitor.id,
            trigger_id=trigger_id,
            period_start=_month_start(current_time),
            quantity=1,
            unit="trigger",
            idempotency_key=f"monitor-trigger-usage:{monitor.id}:{_identity_digest(kind, identity)}",
            ledger_metadata={
                "kind": kind,
                "schedule_version": monitor.schedule_version,
            },
        )
        self.session.add(usage)
        command_payload = task_payload
        command = TaskCommand(
            id=uuid4(),
            tenant_id=monitor.tenant_id,
            workspace_id=monitor.workspace_id,
            actor_user_id=monitor.owner_user_id,
            task_id=task_id,
            thread_id=thread_id,
            command_type="submit",
            payload=command_payload,
            payload_hash=_payload_hash(command_payload),
            sequence=1,
            status="pending",
            attempt=0,
            idempotency_key=f"submit:{task_id}",
        )
        self.session.add(command)
        await self.session.flush()
        return MonitorAdmission(
            trigger=trigger,
            thread=thread,
            task=task,
            task_command=command,
            usage=usage,
            created=True,
        )

    async def admit(self, monitor_id: UUID, **kwargs: Any) -> MonitorAdmission:
        return await self.admit_trigger(monitor_id, **kwargs)


__all__ = [
    "CronCommandLease",
    "EntitlementDenied",
    "MonitorAdmission",
    "MonitorCronCommandRepository",
    "MonitorDestinationRepository",
    "MonitorIdempotencyConflict",
    "MonitorPersistenceError",
    "MonitorRepository",
    "MonitorVersionConflict",
    "TriggerAdmissionRejected",
    "UsageLedgerRepository",
    "WorkspaceEntitlementRepository",
]
