from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crypto_alert_v2.config import get_settings
from crypto_alert_v2.persistence.models import (
    DataDeletionJob,
    DataDeletionReceipt,
    Tenant,
    User,
    Workspace,
)


async def _mutation_is_blocked(session_factory: async_sessionmaker, statement: object) -> bool:
    try:
        async with session_factory() as session, session.begin():
            await session.execute(statement)
    except DBAPIError:
        return True
    return False


async def run() -> dict[str, object]:
    settings = get_settings()
    engine = create_async_engine(settings.product_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    tenant_id, workspace_id, user_id, job_id, receipt_id = (uuid4() for _ in range(5))
    observed_at = datetime.now(UTC)
    evidence = {"qa_purpose": "lifecycle_receipt_parent_retention"}
    receipt_hash = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    async with session_factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, external_id=f"receipt-qa-{suffix}", name="Receipt QA"))
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                identity_issuer="receipt-qa",
                external_subject=f"receipt-qa-{suffix}",
            )
        )
        session.add(
            Workspace(
                id=workspace_id,
                tenant_id=tenant_id,
                external_id=f"receipt-qa-{suffix}",
                name="Receipt QA",
            )
        )
        await session.flush()
        session.add(
            DataDeletionJob(
                id=job_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                idempotency_key=f"receipt-qa-{suffix}",
                request_payload_hash="a" * 64,
                confirmation_hash="b" * 64,
                status="succeeded",
            )
        )
        await session.flush()
        session.add(
            DataDeletionReceipt(
                id=receipt_id,
                deletion_job_id=job_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=user_id,
                system="product_db",
                phase="survivor_scan",
                attempt=1,
                outcome="succeeded",
                affected_count=0,
                survivor_count=0,
                observed_at=observed_at,
                reference=None,
                evidence=evidence,
                receipt_hash=receipt_hash,
            )
        )

    async with session_factory() as session, session.begin():
        await session.execute(delete(DataDeletionJob).where(DataDeletionJob.id == job_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))

    async with session_factory() as session:
        receipt_count = await session.scalar(
            select(func.count()).select_from(DataDeletionReceipt).where(
                DataDeletionReceipt.id == receipt_id
            )
        )
        parent_count = await session.scalar(
            select(func.count()).select_from(Tenant).where(Tenant.id == tenant_id)
        )
        retained_hash = await session.scalar(
            select(DataDeletionReceipt.receipt_hash).where(DataDeletionReceipt.id == receipt_id)
        )

    update_blocked = await _mutation_is_blocked(
        session_factory,
        update(DataDeletionReceipt)
        .where(DataDeletionReceipt.id == receipt_id)
        .values(evidence={"tampered": True}),
    )
    delete_blocked = await _mutation_is_blocked(
        session_factory,
        delete(DataDeletionReceipt).where(DataDeletionReceipt.id == receipt_id),
    )
    await engine.dispose()
    return {
        "parent_count": parent_count,
        "receipt_count": receipt_count,
        "receipt_hash_unchanged": retained_hash == receipt_hash,
        "receipt_update_blocked": update_blocked,
        "receipt_delete_blocked": delete_blocked,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), sort_keys=True))
