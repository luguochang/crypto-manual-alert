"""Exercise real Product PostgreSQL usage governance without running an Agent."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.schemas import AnalysisSubmission
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.persistence.models import (
    UsageLedgerEntry,
    UsageReconciliation,
    WorkspaceEntitlement,
)
from crypto_alert_v2.persistence.repositories import resolve_actor
from crypto_alert_v2.persistence.usage_governance import UsageQuotaExceeded


def _actor(suffix: str) -> ActorContext:
    return ActorContext(
        tenant_id="qa-usage-tenant",
        workspace_id=f"qa-usage-workspace-{suffix}",
        user_id="qa-usage-user",
        identity_issuer="crypto-alert-v2-qa",
        context_id=uuid4(),
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


def _submission(label: str) -> AnalysisSubmission:
    return AnalysisSubmission(
        symbol="BTC-USDT-SWAP",
        horizon="4h",
        query_text=f"Usage governance QA admission {label}.",
        notify=False,
    )


async def main() -> None:
    settings = get_settings()
    if settings.product_database_url is None:
        raise RuntimeError("PRODUCT_DATABASE_URL is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ProductAnalysisService(
        session_factory=factory,
        clock=lambda: datetime.now(UTC),
    )
    suffix = uuid4().hex[:12]
    actor = _actor(suffix)
    isolated_actor = _actor(f"{suffix}-isolated")
    await service.bootstrap_actor(actor)
    await service.bootstrap_actor(isolated_actor)

    async with factory() as session, session.begin():
        resolved = await resolve_actor(session, actor)
        entitlement = await session.scalar(
            select(WorkspaceEntitlement)
            .where(
                WorkspaceEntitlement.tenant_id == resolved.tenant_id,
                WorkspaceEntitlement.workspace_id == resolved.workspace_id,
            )
            .with_for_update()
        )
        if entitlement is None:
            raise RuntimeError("QA workspace entitlement was not provisioned")
        entitlement.monthly_agent_admission_limit = 1

    first = await service.create_analysis(
        actor,
        _submission("first"),
        f"qa-usage-admission-{suffix}",
    )
    replay = await service.create_analysis(
        actor,
        _submission("first"),
        f"qa-usage-admission-{suffix}",
    )
    quota_code = None
    try:
        await service.create_analysis(
            actor,
            _submission("over-limit"),
            f"qa-usage-over-limit-{suffix}",
        )
    except UsageQuotaExceeded as exc:
        quota_code = exc.code
    if quota_code != "quota_exceeded":
        raise RuntimeError("workspace quota did not reject the second admission")

    isolated = await service.create_analysis(
        isolated_actor,
        _submission("isolated"),
        f"qa-usage-isolated-{suffix}",
    )
    await service.cancel_task(
        actor,
        str(first["task_id"]),
        f"qa-usage-cancel-{suffix}",
    )
    await service.cancel_task(
        isolated_actor,
        str(isolated["task_id"]),
        f"qa-usage-isolated-cancel-{suffix}",
    )

    receipt = await service.reconcile_usage(actor, repair=True)
    governance = await service.get_usage_governance(actor)
    ledger_mutation_blocked = False
    reconciliation_mutation_blocked = False
    async with factory() as session:
        resolved = await resolve_actor(session, actor)
        usage_id = await session.scalar(
            select(UsageLedgerEntry.id)
            .where(
                UsageLedgerEntry.tenant_id == resolved.tenant_id,
                UsageLedgerEntry.workspace_id == resolved.workspace_id,
            )
            .limit(1)
        )
        usage_count = int(
            await session.scalar(
                select(func.count(UsageLedgerEntry.id)).where(
                    UsageLedgerEntry.tenant_id == resolved.tenant_id,
                    UsageLedgerEntry.workspace_id == resolved.workspace_id,
                )
            )
            or 0
        )
        if usage_id is None:
            raise RuntimeError("QA usage receipt was not persisted")
    try:
        async with factory() as session, session.begin():
            await session.execute(
                update(UsageLedgerEntry)
                .where(UsageLedgerEntry.id == usage_id)
                .values(quantity=2)
            )
    except DBAPIError:
        ledger_mutation_blocked = True
    try:
        async with factory() as session, session.begin():
            await session.execute(
                update(UsageReconciliation)
                .where(UsageReconciliation.id == receipt["id"])
                .values(status="discrepant")
            )
    except DBAPIError:
        reconciliation_mutation_blocked = True

    print(
        json.dumps(
            {
                "task_replay_same": replay["task_id"] == first["task_id"],
                "quota_code": quota_code,
                "isolated_workspace_admitted": isolated["status"] == "queued",
                "reconciliation_status": receipt["status"],
                "reconciliation_id": str(receipt["id"]),
                "agent_admission_source": receipt["source_totals"][
                    "agent_admission"
                ],
                "agent_admission_ledger": receipt["ledger_totals"][
                    "agent_admission"
                ],
                "latest_matches": (
                    governance["latest_reconciliation"]["id"] == receipt["id"]
                ),
                "usage_count": usage_count,
                "ledger_mutation_blocked": ledger_mutation_blocked,
                "reconciliation_mutation_blocked": reconciliation_mutation_blocked,
            },
            sort_keys=True,
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
