from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.observability.verification import (
    ObservabilityVerificationResult,
)
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    Membership,
    ObservabilityDelivery,
    Run,
    Task,
    Tenant,
    Thread,
    User,
    Workspace,
)
from crypto_alert_v2.persistence.repositories import (
    ObservabilityDeliveryIntent,
    ObservabilityDeliveryRepository,
)
from crypto_alert_v2.workers.observability import (
    ObservabilityVerificationWorker,
    SqlAlchemyObservabilityVerificationStore,
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


@dataclass(frozen=True, slots=True)
class SeededRun:
    tenant_id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    task_id: UUID
    run_id: UUID
    actor: ActorContext


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


async def _seed_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    label: str,
) -> SeededRun:
    tenant_id = uuid4()
    workspace_id = uuid4()
    owner_user_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    tenant = Tenant(
        id=tenant_id, external_id=f"tenant-{label}-{uuid4()}", name="Tenant"
    )
    user = User(
        id=owner_user_id,
        tenant_id=tenant_id,
        identity_issuer="legacy",
        external_subject=f"user-{label}-{uuid4()}",
        display_name="Owner",
    )
    workspace = Workspace(
        id=workspace_id,
        tenant_id=tenant_id,
        external_id=f"workspace-{label}-{uuid4()}",
        name="Workspace",
    )
    membership = Membership(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=owner_user_id,
        role="member",
        permissions=["analysis:read", "analysis:write"],
    )
    thread = Thread(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        title="Observability repository test",
    )
    task = Task(
        id=task_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        thread_id=thread.id,
        task_type="market_analysis",
        status="succeeded",
        idempotency_key=f"observability-{label}-{uuid4()}",
        request_payload_hash="0" * 64,
        request_payload={"symbol": "BTC-USDT-SWAP"},
    )
    run = Run(
        id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        thread_id=thread.id,
        task_id=task_id,
        attempt=1,
        status="succeeded",
        input_payload={"symbol": "BTC-USDT-SWAP"},
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
    actor = ActorContext(
        tenant_id=tenant.external_id,
        workspace_id=workspace.external_id,
        user_id=user.external_subject,
        identity_issuer="legacy",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    return SeededRun(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        task_id=task_id,
        run_id=run_id,
        actor=actor,
    )


def _intents(
    seed: SeededRun, *, suffix: str = "1", second_status: str = "planned"
) -> tuple[ObservabilityDeliveryIntent, ...]:
    deadline = datetime(2026, 7, 17, 13, 0, tzinfo=UTC)
    return (
        ObservabilityDeliveryIntent(
            provider="langsmith",
            status="planned",
            skip_reason=None,
            sampled=True,
            provider_trace_id=None,
            verification_deadline=deadline,
            delivery_key=f"{seed.run_id}:langsmith:{suffix}",
            correlation_id=f"corr-{seed.run_id}",
        ),
        ObservabilityDeliveryIntent(
            provider="langfuse",
            status=second_status,
            skip_reason=None,
            sampled=True,
            provider_trace_id=None,
            verification_deadline=deadline,
            delivery_key=f"{seed.run_id}:langfuse:{suffix}",
            correlation_id=f"corr-{seed.run_id}",
        ),
    )


async def _ensure(
    session_factory: async_sessionmaker[AsyncSession], seed: SeededRun
) -> list[ObservabilityDelivery]:
    async with session_factory() as session, session.begin():
        repository = ObservabilityDeliveryRepository(session)
        return await repository.ensure_intents(
            tenant_id=seed.tenant_id,
            workspace_id=seed.workspace_id,
            owner_user_id=seed.owner_user_id,
            task_id=seed.task_id,
            run_id=seed.run_id,
            intents=_intents(seed),
        )


@pytest.mark.asyncio
async def test_ensure_intents_is_idempotent_and_list_is_actor_scoped(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    first = await _seed_run(session_factory, label="first")
    second = await _seed_run(session_factory, label="second")

    first_rows = await _ensure(session_factory, first)
    replay_rows = await _ensure(session_factory, first)
    assert {row.id for row in replay_rows} == {row.id for row in first_rows}
    assert {row.provider for row in first_rows} == {"langsmith", "langfuse"}

    async with session_factory() as session:
        repository = ObservabilityDeliveryRepository(session, actor=first.actor)
        visible = await repository.list_for_run(
            task_id=first.task_id, run_id=first.run_id
        )
        hidden = await repository.list_for_run(
            task_id=second.task_id, run_id=second.run_id
        )
    assert {row.id for row in visible} == {row.id for row in first_rows}
    assert hidden == []

    async with session_factory() as session:
        count = await session.scalar(select(ObservabilityDelivery.id))
        assert count is not None


@pytest.mark.asyncio
async def test_lease_and_fenced_transitions_reject_stale_worker(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    seed = await _seed_run(session_factory, label="fence")
    await _ensure(session_factory, seed)
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)

    async with session_factory() as session, session.begin():
        repository = ObservabilityDeliveryRepository(session)
        leases = await repository.lease_due(worker_id="worker-a", now=now, limit=2)
        assert len(leases) == 2
        lease = leases[0]
        assert lease.status == "leased"
        assert lease.event_type == "root_trace"
        assert lease.event_version == 1
        assert lease.provider_trace_id is None
        assert lease.verification_deadline == datetime(2026, 7, 17, 13, 0, tzinfo=UTC)
        assert lease.attempt_count == 1
        assert lease.fence_token == 1
        assert (
            await repository.mark_verified(
                delivery_id=lease.delivery_id,
                worker_id="worker-a",
                fence_token=lease.fence_token,
                provider_trace_id="trace-verified",
                now=now,
            )
            is True
        )
        assert (
            await repository.mark_terminal(
                delivery_id=lease.delivery_id,
                worker_id="worker-a",
                fence_token=lease.fence_token,
                error_code="stale-write",
                now=now,
            )
            is False
        )
        assert (
            await repository.mark_retryable(
                delivery_id=leases[1].delivery_id,
                worker_id="worker-old",
                fence_token=leases[1].fence_token,
                next_attempt_at=now + timedelta(minutes=1),
                error_code="wrong-owner",
                now=now,
            )
            is False
        )
        assert (
            await repository.mark_terminal(
                delivery_id=leases[1].delivery_id,
                worker_id="worker-a",
                fence_token=leases[1].fence_token,
                error_code="verification_deadline_exhausted",
                now=now,
            )
            is True
        )

    async with session_factory() as session:
        stored = {
            row.provider: row
            for row in (
                await session.scalars(
                    select(ObservabilityDelivery).where(
                        ObservabilityDelivery.run_id == seed.run_id
                    )
                )
            ).all()
        }
    verified_provider = lease.provider
    terminal_provider = "langfuse" if verified_provider == "langsmith" else "langsmith"
    assert stored[verified_provider].status == "verified"
    assert stored[verified_provider].provider_trace_id == "trace-verified"
    assert stored[terminal_provider].status == "failed_terminal"
    assert stored[terminal_provider].terminal_at == now


@pytest.mark.asyncio
async def test_expired_lease_becomes_unknown_and_can_be_leased_for_verification(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    seed = await _seed_run(session_factory, label="expiry")
    await _ensure(session_factory, seed)
    leased_at = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    expired_at = leased_at + timedelta(seconds=31)

    async with session_factory() as session, session.begin():
        repository = ObservabilityDeliveryRepository(session)
        leases = await repository.lease_due(
            worker_id="worker-crashed", now=leased_at, limit=1
        )
        assert len(leases) == 1
        recovered = await repository.recover_expired_leases(now=expired_at)
        assert len(recovered) == 1
        assert recovered[0].status == "unknown"
        assert recovered[0].lease_owner is None
        assert recovered[0].last_error_code == "lease_expired"
        assert (
            await repository.mark_verified(
                delivery_id=leases[0].delivery_id,
                worker_id="worker-crashed",
                fence_token=leases[0].fence_token,
                provider_trace_id="stale-trace",
                now=expired_at,
            )
            is False
        )

        verification_leases = await repository.lease_due(
            worker_id="verifier", now=expired_at, limit=1
        )
        assert len(verification_leases) == 1
        assert verification_leases[0].status == "verifying"
        assert verification_leases[0].fence_token == leases[0].fence_token + 1

    async with session_factory() as session:
        stored = await session.get(ObservabilityDelivery, leases[0].delivery_id)
    assert stored is not None
    assert stored.status == "verifying"


@pytest.mark.asyncio
async def test_release_owned_leases_retries_only_this_workers_read_only_leases(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    seed = await _seed_run(session_factory, label="shutdown")
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)

    async with session_factory() as session, session.begin():
        repository = ObservabilityDeliveryRepository(session)
        await repository.ensure_intents(
            tenant_id=seed.tenant_id,
            workspace_id=seed.workspace_id,
            owner_user_id=seed.owner_user_id,
            task_id=seed.task_id,
            run_id=seed.run_id,
            intents=_intents(seed, second_status="unknown"),
        )
        leases = await repository.lease_due(
            worker_id="worker-shutdown", now=now, limit=2
        )
        assert {lease.status for lease in leases} == {"leased", "verifying"}

        assert await repository.release_owned_leases("other-worker", now) == []
        released = await repository.release_owned_leases("worker-shutdown", now)
        assert {delivery.id for delivery in released} == {
            lease.delivery_id for lease in leases
        }
        assert all(delivery.status == "failed_retryable" for delivery in released)
        assert all(delivery.lease_owner is None for delivery in released)
        assert all(delivery.lease_expires_at is None for delivery in released)
        assert all(delivery.next_attempt_at == now for delivery in released)
        assert all(
            delivery.last_error_code == "worker_shutdown" for delivery in released
        )

        for lease in leases:
            assert (
                await repository.mark_verified(
                    delivery_id=lease.delivery_id,
                    worker_id="worker-shutdown",
                    fence_token=lease.fence_token,
                    provider_trace_id="late-stale-trace",
                    now=now,
                )
                is False
            )

    async with session_factory() as session:
        stored = list(
            (
                await session.scalars(
                    select(ObservabilityDelivery).where(
                        ObservabilityDelivery.run_id == seed.run_id
                    )
                )
            ).all()
        )
    assert len(stored) == 2
    assert {delivery.status for delivery in stored} == {"failed_retryable"}
    assert {delivery.last_error_code for delivery in stored} == {"worker_shutdown"}


@pytest.mark.asyncio
async def test_verification_worker_persists_hosted_visibility_with_real_postgres(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    seed = await _seed_run(session_factory, label="worker-verification")
    trace_id = "a" * 32
    async with session_factory() as session, session.begin():
        await ObservabilityDeliveryRepository(session).ensure_intents(
            tenant_id=seed.tenant_id,
            workspace_id=seed.workspace_id,
            owner_user_id=seed.owner_user_id,
            task_id=seed.task_id,
            run_id=seed.run_id,
            intents=(
                ObservabilityDeliveryIntent(
                    provider="langfuse",
                    status="planned",
                    skip_reason=None,
                    sampled=True,
                    provider_trace_id=trace_id,
                    verification_deadline=datetime(2026, 7, 17, 13, 0, tzinfo=UTC),
                    delivery_key=f"{seed.run_id}:langfuse:worker",
                    correlation_id=f"corr-{seed.run_id}",
                ),
            ),
        )

    class VisibleVerifier:
        async def verify(self, request: object) -> ObservabilityVerificationResult:
            assert getattr(request, "provider_trace_id") == trace_id
            return ObservabilityVerificationResult(
                provider="langfuse",
                provider_trace_id=trace_id,
                result="verified",
                code="hosted_trace_visible",
            )

    worker = ObservabilityVerificationWorker(
        store=SqlAlchemyObservabilityVerificationStore(session_factory),
        verifiers={"langfuse": VisibleVerifier()},
        worker_id="real-postgres-verifier",
        langsmith_project="crypto-alert-v2-test",
        clock=lambda: datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
    )

    assert await worker.dispatch_once() is True

    async with session_factory() as session:
        stored = await session.scalar(
            select(ObservabilityDelivery).where(
                ObservabilityDelivery.task_id == seed.task_id,
                ObservabilityDelivery.run_id == seed.run_id,
                ObservabilityDelivery.provider == "langfuse",
            )
        )
    assert stored is not None
    assert stored.status == "verified"
    assert stored.provider_trace_id == trace_id
    assert stored.verified_at == datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    assert stored.lease_owner is None
    assert stored.lease_expires_at is None
