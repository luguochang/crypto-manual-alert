from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from uuid import uuid4

from langgraph_sdk import get_client
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.request_identity import transport_headers
from crypto_alert_v2.api.schemas import DataDeletionSubmission
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.worker_authorization import (
    create_agent_server_authorization_provider,
)
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.lifecycle.adapters import (
    AegraCheckpointAdapter,
    AegraStoreAdapter,
    NotConfiguredLifecycleAdapter,
)
from crypto_alert_v2.lifecycle.worker import LifecycleWorker
from crypto_alert_v2.persistence.models import (
    DataDeletionReceipt,
    Membership,
    Task,
    Tenant,
    Thread,
    User,
    Workspace,
)


async def run() -> dict[str, object]:
    settings = get_settings()
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    tenant_id, workspace_id, user_id, membership_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    actor = ActorContext(
        tenant_id=f"lifecycle-qa-tenant-{suffix}",
        workspace_id=f"lifecycle-qa-workspace-{suffix}",
        user_id=f"lifecycle-qa-user-{suffix}",
        identity_issuer="lifecycle-qa",
        context_id=membership_id,
        roles=("member",),
        permissions=(
            "analysis:read",
            "analysis:write",
            "data_lifecycle:read",
            "data_lifecycle:write",
            "data_lifecycle:delete",
        ),
    )
    async with session_factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, external_id=actor.tenant_id, name="Lifecycle QA"))
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                identity_issuer=actor.identity_issuer,
                external_subject=actor.user_id,
            )
        )
        session.add(
            Workspace(
                id=workspace_id,
                tenant_id=tenant_id,
                external_id=actor.workspace_id,
                name="Lifecycle QA",
            )
        )
        await session.flush()
        session.add(
            Membership(
                id=membership_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role="member",
                permissions=list(actor.permissions),
                is_active=True,
            )
        )

    client = get_client(url=settings.agent_server_url)
    authorization_provider = create_agent_server_authorization_provider(settings)
    headers = transport_headers(
        request_id=f"lifecycle-qa-{suffix}",
        authorization=authorization_provider(actor),
    )
    official_thread = await client.threads.create(
        metadata={"qa_purpose": "lifecycle_receipt"},
        headers=headers,
    )
    official_thread_id = str(official_thread["thread_id"])
    await client.store.put_item(
        ["lifecycle-qa"],
        "survivor-canary",
        {"kind": "lifecycle-qa"},
        headers=headers,
    )

    product_thread_id, task_id = uuid4(), uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            Thread(
                id=product_thread_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                official_thread_id=official_thread_id,
            )
        )
        await session.flush()
        session.add(
            Task(
                id=task_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                thread_id=product_thread_id,
                task_type="market_analysis",
                status="succeeded",
                idempotency_key=f"lifecycle-qa-task-{suffix}",
                request_payload_hash="a" * 64,
                request_payload={"qa": True},
            )
        )

    service = ProductAnalysisService(session_factory=session_factory)
    deletion = await service.create_data_deletion(
        actor,
        DataDeletionSubmission(confirmation="DELETE MY DATA"),
        f"lifecycle-qa-delete-{suffix}",
    )
    worker = LifecycleWorker(
        session_factory=session_factory,
        worker_id=f"lifecycle-qa-worker-{suffix}",
        deletion_adapters=(
            AegraCheckpointAdapter(
                client=client,
                authorization_provider=authorization_provider,
            ),
            AegraStoreAdapter(
                client=client,
                authorization_provider=authorization_provider,
            ),
            NotConfiguredLifecycleAdapter(
                "object_storage", reason="QA deployment has no object storage backend"
            ),
            NotConfiguredLifecycleAdapter(
                "search", reason="QA deployment has no Product search index"
            ),
            NotConfiguredLifecycleAdapter(
                "langsmith", reason="QA trace delivery is disabled"
            ),
            NotConfiguredLifecycleAdapter(
                "langfuse", reason="QA trace delivery is disabled"
            ),
        ),
    )
    dispatched = await worker.dispatch_once()
    result = await service.get_data_deletion(actor, deletion["id"])
    if result is None:
        raise RuntimeError("deletion result disappeared")

    async with session_factory() as session:
        receipts = list(
            await session.scalars(
                select(DataDeletionReceipt)
                .where(DataDeletionReceipt.deletion_job_id == deletion["id"])
                .order_by(DataDeletionReceipt.system, DataDeletionReceipt.phase)
            )
        )
    mutation_blocked = False
    try:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(DataDeletionReceipt)
                .where(DataDeletionReceipt.id == receipts[0].id)
                .values(evidence={"tampered": True})
            )
    except DBAPIError:
        mutation_blocked = True

    by_key = {(receipt.system, receipt.phase): receipt for receipt in receipts}
    output = {
        "dispatched": dispatched,
        "status": result["status"],
        "receipt_count": len(receipts),
        "receipt_system_count": len({receipt.system for receipt in receipts}),
        "survivor_scan_count": sum(
            receipt.phase == "survivor_scan" for receipt in receipts
        ),
        "product_survivors": by_key[("product_db", "survivor_scan")].survivor_count,
        "checkpoint_deleted": by_key[("checkpoint", "delete")].affected_count,
        "checkpoint_survivors": by_key[("checkpoint", "survivor_scan")].survivor_count,
        "store_deleted": by_key[("store", "delete")].affected_count,
        "store_survivors": by_key[("store", "survivor_scan")].survivor_count,
        "logs_status": result["system_status"]["logs"],
        "backups_status": result["system_status"]["backups"],
        "object_storage_status": result["system_status"]["object_storage"],
        "receipt_hashes_valid": all(
            len(receipt.receipt_hash) == 64 for receipt in receipts
        ),
        "receipt_mutation_blocked": mutation_blocked,
        "observed_at_timezone_aware": all(
            receipt.observed_at.tzinfo is not None for receipt in receipts
        ),
        "qa_completed_at": datetime.now(UTC).isoformat(),
    }
    await engine.dispose()
    return output


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), sort_keys=True))
