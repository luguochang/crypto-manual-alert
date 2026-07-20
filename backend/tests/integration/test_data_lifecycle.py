from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema

from crypto_alert_v2.api.schemas import (
    DataDeletionSubmission,
    DataExportSubmission,
)
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.lifecycle.worker import LifecycleWorker
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    DataExportJob,
    Membership,
    Task,
    Tenant,
    Thread,
    User,
    Workspace,
)


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@pytest_asyncio.fixture
async def lifecycle_context() -> AsyncIterator[tuple[ProductAnalysisService, ActorContext, async_sessionmaker[AsyncSession]]]:
    assert DATABASE_URL is not None
    engine = create_async_engine(_asyncpg_url(DATABASE_URL), pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(PRODUCT_SCHEMA, if_not_exists=True))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    actor = ActorContext(
        tenant_id=f"lifecycle-tenant-{suffix}",
        workspace_id=f"lifecycle-workspace-{suffix}",
        user_id=f"lifecycle-user-{suffix}",
        identity_issuer="legacy",
        roles=("member",),
        permissions=("data_lifecycle:read", "data_lifecycle:write", "data_lifecycle:delete"),
    )
    tenant_id, workspace_id, user_id, membership_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with session_factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, external_id=actor.tenant_id, name="Lifecycle tenant"))
        session.add(User(id=user_id, tenant_id=tenant_id, identity_issuer="legacy", external_subject=actor.user_id))
        session.add(Workspace(id=workspace_id, tenant_id=tenant_id, external_id=actor.workspace_id, name="Lifecycle workspace"))
        await session.flush()
        session.add(Membership(
            id=membership_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role="member",
            permissions=list(actor.permissions),
            is_active=True,
        ))
    actor = actor.model_copy(update={"context_id": membership_id})
    service = ProductAnalysisService(session_factory=session_factory, clock=lambda: datetime.now(UTC))
    try:
        yield service, actor, session_factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_policy_export_idempotency_manifest_and_safe_bundle(lifecycle_context: object) -> None:
    service, actor, session_factory = lifecycle_context  # type: ignore[misc]
    policy = await service.get_data_lifecycle_policy(actor)
    assert policy["product_retention_days"] == 365
    assert policy["completed_checkpoint_retention_days"] == 30
    assert policy["backup_retention_days"] == 35
    assert policy["retain_raw_prompt"] is False
    assert policy["retain_raw_response"] is False

    first = await service.create_data_export(actor, DataExportSubmission(), "export-once")
    second = await service.create_data_export(actor, DataExportSubmission(), "export-once")
    assert first["id"] == second["id"]

    worker = LifecycleWorker(session_factory=session_factory, worker_id="lifecycle-test-worker")
    assert await worker.dispatch_once() is True
    result = await service.get_data_export_bundle(actor, first["id"])
    assert result is not None
    assert result["status"] == "succeeded"
    text = str(result["bundle"])
    assert "secret raw prompt" not in text
    assert "raw model response" not in text
    assert "secret" not in text.lower()


@pytest.mark.asyncio
async def test_deletion_is_owner_scoped_and_stops_at_pending_external(lifecycle_context: object) -> None:
    service, actor, session_factory = lifecycle_context  # type: ignore[misc]
    async with session_factory() as session, session.begin():
        from crypto_alert_v2.persistence.repositories import resolve_actor

        resolved = await resolve_actor(session, actor)
        thread_id, task_id = uuid4(), uuid4()
        session.add(Thread(id=thread_id, tenant_id=resolved.tenant_id, workspace_id=resolved.workspace_id, owner_user_id=resolved.user_id, official_thread_id=f"thread-{uuid4()}"))
        await session.flush()
        session.add(Task(
            id=task_id,
            tenant_id=resolved.tenant_id,
            workspace_id=resolved.workspace_id,
            owner_user_id=resolved.user_id,
            thread_id=thread_id,
            task_type="market_analysis",
            status="succeeded",
            idempotency_key=f"task-{uuid4()}",
            request_payload_hash="a" * 64,
            request_payload={"query_text": "secret raw prompt"},
        ))
    job = await service.create_data_deletion(
        actor,
        DataDeletionSubmission(confirmation="DELETE MY DATA"),
        "delete-once",
    )
    worker = LifecycleWorker(session_factory=session_factory, worker_id="lifecycle-delete-worker")
    assert await worker.dispatch_once() is True
    result = await service.get_data_deletion(actor, job["id"])
    assert result is not None
    assert result["status"] == "pending_external"
    assert result["system_status"]["product_db"] == "succeeded"
    assert result["system_status"]["langsmith"] == "pending_external"
    assert result["external_deletion_reference"]["langfuse"] is None
    async with session_factory() as session:
        assert await session.scalar(select(Task).where(Task.id == task_id)) is None


@pytest.mark.asyncio
async def test_expired_running_export_lease_is_recoverable(lifecycle_context: object) -> None:
    service, actor, session_factory = lifecycle_context  # type: ignore[misc]
    job = await service.create_data_export(actor, DataExportSubmission(), "lease-recovery")
    async with session_factory() as session, session.begin():
        await session.execute(
            update(DataExportJob)
            .where(DataExportJob.id == job["id"])
            .values(
                status="running",
                lease_owner="dead-worker",
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    worker = LifecycleWorker(session_factory=session_factory, worker_id="recovery-worker")
    assert await worker.dispatch_once() is True
    recovered = await service.get_data_export(actor, job["id"])
    assert recovered is not None
    assert recovered["status"] == "succeeded"
    assert recovered["attempt"] >= 1
