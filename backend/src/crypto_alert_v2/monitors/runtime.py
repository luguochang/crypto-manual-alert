from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.monitors.conditions import require_monitor_condition_evaluator
from crypto_alert_v2.monitors.models import MonitorIngressRequest
from crypto_alert_v2.persistence.models import (
    Membership,
    MonitorDefinition,
    MonitorTrigger,
    Tenant,
    User,
    Workspace,
)
from crypto_alert_v2.persistence.monitor_repository import MonitorRepository


@lru_cache(maxsize=4)
def _session_factory(database_url: str) -> async_sessionmaker[Any]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def admit_monitor_ingress(
    request: MonitorIngressRequest,
    *,
    official_run_id: str,
    official_thread_id: str | None,
) -> dict[str, Any]:
    """Admit one official Cron Run into the durable Product command queue."""

    official_run_id = official_run_id.strip()
    if not official_run_id:
        raise RuntimeError("monitor ingress requires the official LangGraph run_id")
    if official_thread_id is not None:
        official_thread_id = official_thread_id.strip() or None
    settings = get_settings()
    session_factory = _session_factory(settings.product_database_url)
    async with session_factory() as session, session.begin():
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
                    Membership.is_active,
                )
                .select_from(MonitorDefinition)
                .join(Tenant, Tenant.id == MonitorDefinition.tenant_id)
                .join(Workspace, Workspace.id == MonitorDefinition.workspace_id)
                .join(User, User.id == MonitorDefinition.owner_user_id)
                .outerjoin(
                    Membership,
                    and_(
                        Membership.tenant_id == MonitorDefinition.tenant_id,
                        Membership.workspace_id == MonitorDefinition.workspace_id,
                        Membership.user_id == MonitorDefinition.owner_user_id,
                    ),
                )
                .where(
                    MonitorDefinition.id == request.monitor_id,
                    MonitorDefinition.cron_binding_id == request.cron_binding_id,
                )
                .with_for_update(of=MonitorDefinition)
            )
        ).one_or_none()
        if row is None:
            raise PermissionError("monitor ingress binding is unavailable")

        monitor = row[0]
        condition = monitor.condition if isinstance(monitor.condition, Mapping) else {}
        require_monitor_condition_evaluator(condition.get("kind"))
        membership_id = row[5]
        membership_active = bool(row[8])
        if membership_id is None or not membership_active:
            existing = await session.scalar(
                select(MonitorTrigger).where(
                    MonitorTrigger.tenant_id == monitor.tenant_id,
                    MonitorTrigger.workspace_id == monitor.workspace_id,
                    MonitorTrigger.owner_user_id == monitor.owner_user_id,
                    MonitorTrigger.monitor_id == monitor.id,
                    MonitorTrigger.official_run_id == official_run_id,
                )
            )
            if existing is None:
                existing = MonitorTrigger(
                    id=uuid4(),
                    tenant_id=monitor.tenant_id,
                    workspace_id=monitor.workspace_id,
                    owner_user_id=monitor.owner_user_id,
                    monitor_id=monitor.id,
                    official_cron_id=monitor.official_cron_id,
                    official_run_id=official_run_id,
                    official_thread_id=official_thread_id,
                    manual_stable_key=None,
                    kind="cron",
                    status="suppressed",
                    reason="membership_revoked",
                    schedule_version=request.schedule_version,
                    received_at=datetime.now(UTC),
                )
                session.add(existing)
                await session.flush()
            return _receipt(existing, created=True)

        actor = ActorContext(
            tenant_id=row[1],
            workspace_id=row[2],
            identity_issuer=row[3],
            user_id=row[4],
            context_id=membership_id,
            roles=(row[6],),
            permissions=tuple(row[7]),
        )
        admission = await MonitorRepository(session, actor).admit_trigger(
            monitor.id,
            kind="cron",
            cron_binding_id=request.cron_binding_id,
            official_cron_id=monitor.official_cron_id,
            official_run_id=official_run_id,
            official_thread_id=official_thread_id,
            schedule_version=request.schedule_version,
        )
        return _receipt(admission.trigger, created=admission.created)


def _receipt(trigger: MonitorTrigger, *, created: bool) -> dict[str, Any]:
    return {
        "trigger_id": str(trigger.id),
        "monitor_id": str(trigger.monitor_id),
        "status": trigger.status,
        "reason": trigger.reason,
        "task_id": str(trigger.task_id) if trigger.task_id is not None else None,
        "created": created,
    }


__all__ = ["admit_monitor_ingress"]
