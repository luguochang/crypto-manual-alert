"""Run a local disposable-PostgreSQL Memory/Outcome service round-trip."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.api.schemas import (
    MemoryCreateSubmission,
    MemoryDeleteSubmission,
    MemoryUpdateSubmission,
)
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import get_settings
from crypto_alert_v2.workers.memory_outcome import MemoryDeletionWorker


async def main() -> None:
    settings = get_settings()
    if settings.product_database_url is None:
        raise RuntimeError("PRODUCT_DATABASE_URL is not configured")
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    actor = ActorContext(
        tenant_id="dev-tenant",
        workspace_id="dev-workspace",
        user_id="dev-user",
        identity_issuer="crypto-alert-v2-compose",
        context_id=UUID("99999999-9999-4999-8999-999999999999"),
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=factory)
    memory = await service.create_memory(
        actor,
        MemoryCreateSubmission(
            scope="workspace",
            purpose="profile",
            key="qa-roundtrip",
            content={"style": "concise"},
        ),
        "qa-memory-roundtrip-20260723",
    )
    listed = await service.list_memory(actor, limit=10)
    updated = await service.update_memory(
        actor,
        memory["id"],
        MemoryUpdateSubmission(enabled=False),
    )
    queued = await service.delete_memory(
        actor,
        memory["id"],
        MemoryDeleteSubmission(confirmation="DELETE_MEMORY"),
        f"qa-memory-delete-{memory['id']}",
    )
    worker = MemoryDeletionWorker(
        session_factory=factory,
        worker_id="qa-memory-worker",
    )
    processed = await worker.dispatch_once()
    after_delete = await service.list_memory(actor, limit=10, include_disabled=True)
    outcomes = await service.list_outcomes(actor, limit=10)
    print(
        json.dumps(
            {
                "created": str(memory["id"]),
                "listed_count": len(listed["items"]),
                "disabled": updated["enabled"] is False if updated else None,
                "deletion_status": queued["status"] if queued else None,
                "deletion_worker_processed": processed,
                "deleted_visible": any(
                    item["id"] == memory["id"] and item["deleted_at"] is not None
                    for item in after_delete["items"]
                ),
                "outcome_count": len(outcomes["items"]),
                "outcome_reportable": outcomes["reportable"],
            },
            sort_keys=True,
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
