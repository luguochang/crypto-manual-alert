from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema

from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    Membership,
    Run,
    Task,
    Tenant,
    Thread,
    User,
    Workspace,
)
from crypto_alert_v2.persistence.unit_of_work import ProductUnitOfWork


PRODUCT_DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
REAL_DATABASE_TESTS = os.getenv("REAL_DATABASE_TESTS") == "1"

pytestmark = [
    pytest.mark.skipif(
        not REAL_DATABASE_TESTS or not PRODUCT_DATABASE_URL,
        reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
    ),
]


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    driver_separator = url.find("://")
    if url.startswith("postgresql+") and driver_separator != -1:
        return "postgresql+asyncpg" + url[driver_separator:]
    return url


@pytest_asyncio.fixture
async def database_connection() -> AsyncIterator[AsyncConnection]:
    assert PRODUCT_DATABASE_URL is not None
    engine = create_async_engine(_asyncpg_url(PRODUCT_DATABASE_URL))

    async with engine.begin() as migration_connection:
        if migration_connection.dialect.name != "postgresql":
            raise AssertionError("PRODUCT_DATABASE_URL must point to PostgreSQL")
        await migration_connection.execute(CreateSchema(PRODUCT_SCHEMA, if_not_exists=True))
        await migration_connection.run_sync(Base.metadata.create_all)

    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield connection
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


@dataclass(frozen=True, slots=True)
class _Actor:
    tenant_id: str
    workspace_id: str
    user_id: str


async def _seed_artifact_lineage(
    session_factory: async_sessionmaker[AsyncSession],
    actor: _Actor,
) -> tuple[Artifact, Artifact, UUID]:
    tenant = Tenant(id=uuid4(), external_id=actor.tenant_id, name="Integration Tenant")
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        external_subject=actor.user_id,
        display_name="Integration User",
    )
    workspace = Workspace(
        id=uuid4(),
        tenant_id=tenant.id,
        external_id=actor.workspace_id,
        name="Integration Workspace",
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
        title="BTC analysis",
    )
    task = Task(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        thread_id=thread.id,
        task_type="market_analysis",
        status="running",
        idempotency_key="artifact-transaction-analysis-1",
        request_payload_hash="0" * 64,
        request_payload={"symbol": "BTC-USDT-SWAP", "horizon": "4h"},
    )
    run = Run(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        thread_id=thread.id,
        task_id=task.id,
        attempt=1,
        status="running",
        input_payload={"symbol": "BTC-USDT-SWAP"},
    )
    committed_artifact = Artifact(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        task_id=task.id,
        artifact_type="analysis_report",
    )
    rolled_back_artifact = Artifact(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        owner_user_id=user.id,
        task_id=task.id,
        artifact_type="analysis_report_draft",
    )

    async with session_factory() as session:
        async with session.begin():
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
            session.add_all([committed_artifact, rolled_back_artifact])

    return committed_artifact, rolled_back_artifact, run.id


async def _row_counts(
    session_factory: async_sessionmaker[AsyncSession], artifact_id: object
) -> tuple[int, int]:
    async with session_factory() as session:
        version_count = await session.scalar(
            select(func.count())
            .select_from(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact_id)
        )
        decision_count = await session.scalar(
            select(func.count())
            .select_from(Decision)
            .where(Decision.artifact_id == artifact_id)
        )
    return int(version_count or 0), int(decision_count or 0)


@pytest.mark.asyncio
async def test_artifact_version_and_decision_commit_atomically(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = _Actor(
        tenant_id=f"tenant-{os.urandom(8).hex()}",
        workspace_id=f"workspace-{os.urandom(8).hex()}",
        user_id=f"oidc|{os.urandom(8).hex()}",
    )
    committed_artifact, rolled_back_artifact, run_id = await _seed_artifact_lineage(
        session_factory, actor
    )

    with pytest.raises(RuntimeError, match="force rollback"):
        async with ProductUnitOfWork(session_factory, actor) as unit_of_work:
            await unit_of_work.artifacts.commit_version_and_decision(
                artifact_id=rolled_back_artifact.id,
                run_id=run_id,
                content={"status": "committed", "analysis": {"action": "no_trade"}},
                decision={"action": "no_trade", "reason": "insufficient edge"},
                evidence_verdict={"sufficient": True},
                risk_verdict={"allowed": True},
            )
            raise RuntimeError("force rollback")

    assert await _row_counts(session_factory, rolled_back_artifact.id) == (0, 0)

    async with ProductUnitOfWork(session_factory, actor) as unit_of_work:
        commit = await unit_of_work.artifacts.commit_version_and_decision(
            artifact_id=committed_artifact.id,
            run_id=run_id,
            content={"status": "committed", "analysis": {"action": "no_trade"}},
            decision={"action": "no_trade", "reason": "insufficient edge"},
            evidence_verdict={"sufficient": True},
            risk_verdict={"allowed": True},
        )
        await unit_of_work.commit()

    assert commit.artifact_version.version_number == 1
    assert commit.decision.artifact_version_id == commit.artifact_version.id
    assert await _row_counts(session_factory, committed_artifact.id) == (1, 1)
