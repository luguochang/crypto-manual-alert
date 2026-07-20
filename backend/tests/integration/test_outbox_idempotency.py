from __future__ import annotations

import os
from typing import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema

from crypto_alert_v2.notifications.outbox import (
    NotificationPayloadConflict,
    SensitiveNotificationPayload,
    plan_notification,
)
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    Membership,
    NotificationOutbox,
    Run,
    Task,
    Tenant,
    Thread,
    User,
    Workspace,
)


PRODUCT_DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
REAL_DATABASE_TESTS = os.getenv("REAL_DATABASE_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not REAL_DATABASE_TESTS or not PRODUCT_DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest_asyncio.fixture
async def database_connection() -> AsyncIterator[AsyncConnection]:
    if not REAL_DATABASE_TESTS or PRODUCT_DATABASE_URL is None:
        pytest.skip("requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL")
    engine = create_async_engine(_asyncpg_url(PRODUCT_DATABASE_URL))
    async with engine.begin() as connection:
        await connection.execute(CreateSchema(PRODUCT_SCHEMA, if_not_exists=True))
        await connection.run_sync(Base.metadata.create_all)
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield connection
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


async def seed_decision(
    session_factory: async_sessionmaker[AsyncSession],
) -> Decision:
    tenant = Tenant(id=uuid4(), external_id=f"tenant-{uuid4()}", name="Tenant")
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        external_subject=f"user-{uuid4()}",
        display_name="User",
    )
    workspace = Workspace(
        id=uuid4(),
        tenant_id=tenant.id,
        external_id=f"workspace-{uuid4()}",
        name="Workspace",
    )
    membership = Membership(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        user_id=user.id,
        role="member",
        permissions=["analysis:read", "analysis:write"],
    )
    thread = Thread(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        title="Outbox test",
    )
    task = Task(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        thread_id=thread.id,
        task_type="market_analysis",
        status="succeeded",
        idempotency_key=f"outbox-{uuid4()}",
        request_payload_hash="0" * 64,
        request_payload={"symbol": "BTC-USDT-SWAP"},
    )
    run = Run(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        thread_id=thread.id,
        task_id=task.id,
        attempt=1,
        status="succeeded",
        input_payload={"symbol": "BTC-USDT-SWAP"},
    )
    artifact = Artifact(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        task_id=task.id,
        artifact_type="analysis_report",
        latest_version_number=1,
    )
    version = ArtifactVersion(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        artifact_id=artifact.id,
        task_id=task.id,
        run_id=run.id,
        version_number=1,
        schema_version="1.0",
        status="committed",
        content={"analysis": {"action": "no_trade"}},
    )
    decision = Decision(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        artifact_id=artifact.id,
        artifact_version_id=version.id,
        task_id=task.id,
        run_id=run.id,
        decision_version=1,
        decision={"action": "no_trade"},
        evidence_verdict={"sufficient": True},
        risk_verdict={"allowed": True},
    )
    async with session_factory() as session, session.begin():
        session.add(tenant)
        await session.flush()
        session.add_all([user, workspace])
        await session.flush()
        session.add_all([membership, thread])
        await session.flush()
        session.add(task)
        await session.flush()
        session.add(run)
        await session.flush()
        session.add(artifact)
        await session.flush()
        session.add(version)
        await session.flush()
        session.add(decision)
    return decision


def notification_kwargs(decision: Decision) -> dict[str, object]:
    return {
        "tenant_id": decision.tenant_id,
        "workspace_id": decision.workspace_id,
        "owner_user_id": decision.owner_user_id,
        "task_id": decision.task_id,
        "run_id": decision.run_id,
        "artifact_id": decision.artifact_id,
        "artifact_version_id": decision.artifact_version_id,
        "decision_id": decision.id,
        "decision_version": decision.decision_version,
        "channel": "bark",
        "notification_type": "analysis_completed",
    }


@pytest.mark.asyncio
async def test_same_logical_key_is_idempotent_and_payload_conflicts_are_audited(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    decision = await seed_decision(session_factory)
    payload = {"task_id": str(decision.task_id), "action": "no_trade"}

    async with session_factory() as session, session.begin():
        first = await plan_notification(
            session, **notification_kwargs(decision), payload=payload
        )
    async with session_factory() as session, session.begin():
        replay = await plan_notification(
            session, **notification_kwargs(decision), payload=payload
        )

    assert first.created is True
    assert replay.created is False
    assert replay.notification.id == first.notification.id

    async with session_factory() as session, session.begin():
        with pytest.raises(NotificationPayloadConflict):
            await plan_notification(
                session,
                **notification_kwargs(decision),
                payload={**payload, "action": "long"},
            )

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )
    assert count == 1


@pytest.mark.asyncio
async def test_secret_bearing_payload_is_rejected_before_database_write(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    decision = await seed_decision(session_factory)

    async with session_factory() as session, session.begin():
        with pytest.raises(SensitiveNotificationPayload):
            await plan_notification(
                session,
                **notification_kwargs(decision),
                payload={"authorization": "Bearer must-never-be-stored"},
            )

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )
    assert count == 0


@pytest.mark.asyncio
async def test_database_rejects_cross_scope_notification_lineage(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    first = await seed_decision(session_factory)
    second = await seed_decision(session_factory)
    mismatched = notification_kwargs(first)
    mismatched["run_id"] = second.run_id

    with pytest.raises(IntegrityError):
        async with session_factory() as session, session.begin():
            await plan_notification(
                session,
                **mismatched,
                payload={"task_id": str(first.task_id), "action": "no_trade"},
            )

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )
    assert count == 0
