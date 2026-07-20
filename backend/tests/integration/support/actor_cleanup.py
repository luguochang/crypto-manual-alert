from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.persistence.models import (
    DataDeletionJob,
    DataExportJob,
    DataLifecyclePolicy,
    MonitorCronCommand,
    MonitorDefinition,
    MonitorDestination,
    MonitorTrigger,
    Tenant,
    UsageLedgerEntry,
    WorkspaceEntitlement,
)


# These actor-owned tables intentionally use RESTRICT and must be cleared before
# the older tenant-owned graph, which is removed by its existing CASCADE rules.
_RESTRICTED_TENANT_DEPENDENTS = (
    UsageLedgerEntry,
    MonitorCronCommand,
    MonitorDestination,
    MonitorTrigger,
    MonitorDefinition,
    WorkspaceEntitlement,
    DataDeletionJob,
    DataExportJob,
    DataLifecyclePolicy,
)


async def delete_actor_test_data(
    session: AsyncSession,
    actor: ActorContext,
) -> bool:
    tenant_id = await session.scalar(
        select(Tenant.id).where(Tenant.external_id == actor.tenant_id)
    )
    if tenant_id is None:
        return False
    await delete_tenant_test_data(session, tenant_id)
    return True


async def delete_tenant_test_data(
    session: AsyncSession,
    tenant_id: UUID,
) -> None:
    for model in _RESTRICTED_TENANT_DEPENDENTS:
        await session.execute(delete(model).where(model.tenant_id == tenant_id))
    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
