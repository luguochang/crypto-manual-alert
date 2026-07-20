from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.monitors.agent_server_cron import (
    AgentServerCronAdapter,
    MonitorCronDegradedError,
)
from crypto_alert_v2.monitors.models import MonitorCronSpec
from crypto_alert_v2.persistence.models import (
    Membership,
    MonitorCronCommand,
    MonitorDefinition,
    Tenant,
    User,
    Workspace,
)
from crypto_alert_v2.persistence.monitor_repository import (
    CronCommandLease,
    MonitorCronCommandRepository,
)


class MonitorCronWorker:
    """Reconciles Product Cron-control outbox rows through the official SDK."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        adapter: AgentServerCronAdapter,
        worker_id: str,
        lease_seconds: int = 30,
        retry_seconds: float = 5.0,
        max_attempts: int = 10,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if retry_seconds <= 0:
            raise ValueError("retry_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._session_factory = session_factory
        self._adapter = adapter
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._retry_seconds = retry_seconds
        self._max_attempts = max_attempts

    async def dispatch_once(self) -> bool:
        lease = await self._lease_one()
        if lease is None:
            return False
        try:
            context = await self._load_context(lease.command)
            remote = await self._apply_remote(context)
        except Exception as exc:
            await self._record_failure(lease, exc)
            return True
        await self._record_success(lease, context.monitor, remote)
        return True

    async def _lease_one(self) -> CronCommandLease | None:
        async with self._session_factory() as session, session.begin():
            leases = await MonitorCronCommandRepository(session).lease(
                worker_id=self._worker_id,
                limit=1,
                lease_seconds=self._lease_seconds,
            )
            return leases[0] if leases else None

    async def _load_context(self, command: MonitorCronCommand) -> "_CronContext":
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(
                        MonitorDefinition,
                        Tenant.external_id,
                        Workspace.external_id,
                        User.identity_issuer,
                        User.external_subject,
                        Membership.id,
                        Membership.role,
                        Membership.permissions,
                    )
                    .select_from(MonitorDefinition)
                    .join(Tenant, Tenant.id == MonitorDefinition.tenant_id)
                    .join(Workspace, Workspace.id == MonitorDefinition.workspace_id)
                    .join(User, User.id == MonitorDefinition.owner_user_id)
                    .outerjoin(
                        Membership,
                        (Membership.tenant_id == MonitorDefinition.tenant_id)
                        & (Membership.workspace_id == MonitorDefinition.workspace_id)
                        & (Membership.user_id == MonitorDefinition.owner_user_id),
                    )
                    .where(
                        MonitorDefinition.id == command.monitor_id,
                        MonitorDefinition.tenant_id == command.tenant_id,
                        MonitorDefinition.workspace_id == command.workspace_id,
                        MonitorDefinition.owner_user_id == command.owner_user_id,
                    )
                )
            ).one_or_none()
        if row is None or row[5] is None:
            raise RuntimeError("monitor Cron owner scope is unavailable")
        actor = ActorContext(
            tenant_id=row[1],
            workspace_id=row[2],
            identity_issuer=row[3],
            user_id=row[4],
            context_id=row[5],
            roles=(row[6],),
            permissions=tuple(row[7]),
        )
        return _CronContext(
            monitor=row[0],
            actor=actor,
            command_type=command.command_type,
        )

    async def _apply_remote(self, context: "_CronContext") -> "_RemoteResult":
        monitor = context.monitor
        spec = MonitorCronSpec(
            monitor_id=monitor.id,
            schedule_version=monitor.schedule_version,
            cron_binding_id=monitor.cron_binding_id,
            schedule=monitor.cron_schedule,
            timezone=monitor.timezone,
            end_time=monitor.expires_at,
        )
        if context.command_type == "delete":
            cron_id = monitor.official_cron_id
            if cron_id is None:
                matches = await self._adapter.search(
                    context.actor, spec.cron_binding_id
                )
                if len(matches) > 1:
                    raise MonitorCronDegradedError(
                        spec.cron_binding_id,
                        reason="multiple Agent Server Crons share one binding",
                        match_count=len(matches),
                    )
                cron_id = _cron_id(matches[0]) if matches else None
            if cron_id is not None:
                await self._adapter.delete(context.actor, cron_id)
            return _RemoteResult(cron_id=None, next_run_at=None)

        cron_id = monitor.official_cron_id
        if cron_id is None:
            reconciled = await self._adapter.reconcile(context.actor, spec)
            cron_id = _cron_id(reconciled)
            if cron_id is None:
                matches = await self._adapter.search(
                    context.actor, spec.cron_binding_id
                )
                if len(matches) != 1:
                    raise MonitorCronDegradedError(
                        spec.cron_binding_id,
                        reason="created Cron could not be reconciled to one binding",
                        match_count=len(matches),
                    )
                cron_id = _cron_id(matches[0])
        if cron_id is None:
            raise RuntimeError("Agent Server Cron response has no cron_id")

        enabled = monitor.status not in {"paused", "disabled", "expired"}
        updated = await self._adapter.update(
            context.actor,
            cron_id,
            spec,
            enabled=enabled,
        )
        return _RemoteResult(
            cron_id=cron_id,
            next_run_at=_next_run_at(updated),
        )

    async def _record_success(
        self,
        lease: CronCommandLease,
        monitor_snapshot: MonitorDefinition,
        remote: "_RemoteResult",
    ) -> None:
        async with self._session_factory() as session, session.begin():
            monitor = await session.scalar(
                select(MonitorDefinition)
                .where(MonitorDefinition.id == monitor_snapshot.id)
                .with_for_update()
            )
            if monitor is None:
                raise RuntimeError("monitor disappeared during Cron reconciliation")
            monitor.official_cron_id = remote.cron_id
            monitor.next_run_at = remote.next_run_at
            if monitor.status == "draft":
                monitor.status = "active"
                monitor.version += 1
            await MonitorCronCommandRepository(session).finish(
                command_id=lease.command.id,
                worker_id=self._worker_id,
                fence_token=lease.fence_token,
                succeeded=True,
            )

    async def _record_failure(
        self,
        lease: CronCommandLease,
        error: Exception,
    ) -> None:
        terminal = (
            isinstance(error, MonitorCronDegradedError)
            or lease.command.attempt >= self._max_attempts
        )
        retry_at = None
        if not terminal:
            retry_at = datetime.now(UTC) + timedelta(seconds=self._retry_seconds)
        async with self._session_factory() as session, session.begin():
            if terminal:
                monitor = await session.scalar(
                    select(MonitorDefinition)
                    .where(MonitorDefinition.id == lease.command.monitor_id)
                    .with_for_update()
                )
                if monitor is not None and monitor.status not in {
                    "disabled",
                    "expired",
                }:
                    monitor.status = "degraded"
                    monitor.version += 1
            await MonitorCronCommandRepository(session).finish(
                command_id=lease.command.id,
                worker_id=self._worker_id,
                fence_token=lease.fence_token,
                succeeded=False,
                error=type(error).__name__,
                retry_at=retry_at,
            )

    async def release_owned_leases(self) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(MonitorCronCommand)
                .where(
                    MonitorCronCommand.status == "leased",
                    MonitorCronCommand.lease_owner == self._worker_id,
                )
                .values(
                    status="pending",
                    lease_owner=None,
                    lease_expires_at=None,
                    available_at=datetime.now(UTC),
                )
            )


class _CronContext:
    def __init__(
        self,
        *,
        monitor: MonitorDefinition,
        actor: ActorContext,
        command_type: str,
    ) -> None:
        self.monitor = monitor
        self.actor = actor
        self.command_type = command_type


class _RemoteResult:
    def __init__(
        self,
        *,
        cron_id: str | None,
        next_run_at: datetime | None,
    ) -> None:
        self.cron_id = cron_id
        self.next_run_at = next_run_at


def _cron_id(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("cron_id")
    return str(raw) if isinstance(raw, (str, UUID)) and str(raw) else None


def _next_run_at(value: object) -> datetime | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("next_run_date")
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


__all__ = ["MonitorCronWorker"]
