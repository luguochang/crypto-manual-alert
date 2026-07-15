from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from typing import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import crypto_alert_v2.api.service as service_module
from crypto_alert_v2.api.agent_server import (
    RemoteCancelResult,
    RemoteRunHandle,
    RemoteRunState,
)
from crypto_alert_v2.api.schemas import AnalysisSubmission, InterruptResponseSubmission
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.commands.dispatcher import CommandDispatcher
from crypto_alert_v2.domain.models import (
    Artifact as DomainArtifact,
    EvidenceVerdict,
    MarketAnalysis,
    MarketSnapshot as DomainMarketSnapshot,
    RiskVerdict,
)
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    InterruptProjection,
    MarketSnapshot,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    WebEvidence,
)
from crypto_alert_v2.persistence.repositories import ResolvedActor
from crypto_alert_v2.providers.search import WebEvidence as DomainWebEvidence
from tests.fixtures.golden_cases import (
    NOW,
    complete_market_snapshot,
    valid_market_analysis,
)


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


def submission(*, query_text: str = "Assess current BTC risk.") -> AnalysisSubmission:
    return AnalysisSubmission(
        symbol="BTC-USDT-SWAP",
        horizon="4h",
        query_text=query_text,
        notify=False,
    )


async def seed_waiting_interrupt(
    session_factory: async_sessionmaker[AsyncSession],
    service: ProductAnalysisService,
    actor: ActorContext,
    *,
    interrupt_id: str | None = None,
    response_version: int = 1,
    status: str = "pending",
    expires_at: datetime | None = None,
) -> tuple[dict[str, object], UUID, UUID]:
    suffix = uuid4().hex
    queued = await service.create_analysis(
        actor,
        submission(),
        idempotency_key=f"waiting-interrupt-task-{suffix}",
    )
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id))
        assert task is not None
        submit_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task.id,
                TaskCommand.command_type == "submit",
            )
        )
        assert submit_command is not None
        submit_command.status = "dispatched"
        task.status = "waiting_human"
        waiting_run = Run(
            id=uuid4(),
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
            owner_user_id=task.owner_user_id,
            thread_id=task.thread_id,
            task_id=task.id,
            attempt=1,
            status="waiting_human",
            official_assistant_id="official-assistant-review",
            official_run_id=f"official-review-run-{suffix}",
            checkpoint_id=f"checkpoint-{suffix}",
            input_payload=task.request_payload,
        )
        session.add(waiting_run)
        await session.flush()
        stored_response = (
            {"action": "approve", "edits": None, "comment": None}
            if status in {"responding", "resolved"}
            else None
        )
        projection_values: dict[str, object] = {
            "id": uuid4(),
            "tenant_id": task.tenant_id,
            "workspace_id": task.workspace_id,
            "owner_user_id": task.owner_user_id,
            "task_id": task.id,
            "run_id": waiting_run.id,
            "official_interrupt_id": interrupt_id or f"interrupt-{suffix}",
            "namespace": "review",
            "checkpoint_id": f"checkpoint-{suffix}",
            "response_version": response_version,
            "status": status,
            "payload": {"kind": "artifact_review", "artifact_version": 1},
            "expires_at": expires_at,
        }
        if stored_response is not None:
            projection_values.update(
                response=stored_response,
                responded_at=datetime.now(UTC),
            )
        projection = InterruptProjection(**projection_values)
        session.add(projection)
        await session.flush()
        return queued, waiting_run.id, projection.id


@pytest_asyncio.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as migration_connection:
        await migration_connection.run_sync(Base.metadata.create_all)
    database_connection = await engine.connect()
    transaction = await database_connection.begin()
    try:
        yield database_connection
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await database_connection.close()
        await engine.dispose()


class FailingRemoteRunner:
    async def start(self, **_: object) -> RemoteRunHandle:
        return RemoteRunHandle(
            assistant_id="official-assistant-failure",
            thread_id="official-thread-1",
            run_id="official-run-1",
        )

    async def join(self, _: RemoteRunHandle) -> dict[str, object]:
        return {
            "terminal_status": "failed",
            "errors": [
                {
                    "code": "provider_unavailable",
                    "provider": "okx",
                    "retryable": True,
                }
            ],
        }

    async def get(self, _: RemoteRunHandle) -> RemoteRunState:
        return RemoteRunState(status="success")

    async def cancel(self, _: RemoteRunHandle) -> RemoteCancelResult:
        return RemoteCancelResult(
            outcome="confirmed",
            state=RemoteRunState(status="interrupted"),
        )


class SuccessfulRemoteRunner:
    async def start(self, **_: object) -> RemoteRunHandle:
        return RemoteRunHandle(
            assistant_id="official-assistant-success",
            thread_id="official-thread-success",
            run_id="official-run-success",
        )

    async def join(self, _: RemoteRunHandle) -> dict[str, object]:
        analysis = MarketAnalysis.model_validate(valid_market_analysis())
        evidence_verdict = EvidenceVerdict(sufficient=True)
        risk_verdict = RiskVerdict(allowed=True)
        artifact = DomainArtifact(
            content_version=1,
            status="committed",
            analysis=analysis,
            evidence_verdict=evidence_verdict,
            risk_verdict=risk_verdict,
            source_references=["https://example.com/macro"],
        )
        market = DomainMarketSnapshot.model_validate(complete_market_snapshot())
        evidence = DomainWebEvidence(
            query="macro",
            final_url="https://example.com/macro",
            fetched_at=NOW,
            content_hash="b" * 64,
            title="Macro source",
            source="test_search",
            excerpt="Macro evidence.",
            evidence_relation="supports",
        )
        return {
            "terminal_status": "succeeded",
            "market_snapshot": market.model_dump(mode="json"),
            "web_evidence": [evidence.model_dump(mode="json")],
            "artifact": artifact.model_dump(mode="json"),
            "errors": [],
        }

    async def get(self, _: RemoteRunHandle) -> RemoteRunState:
        return RemoteRunState(status="success")

    async def cancel(self, _: RemoteRunHandle) -> RemoteCancelResult:
        return RemoteCancelResult(
            outcome="confirmed",
            state=RemoteRunState(status="interrupted"),
        )


@pytest.mark.asyncio
async def test_interrupt_view_and_response_are_actor_scoped(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    owner = ActorContext(
        tenant_id="interrupt-scope-tenant",
        workspace_id="interrupt-scope-workspace",
        user_id="oidc|interrupt-scope-owner",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    other_actors = (
        owner.model_copy(update={"user_id": "oidc|interrupt-scope-other-owner"}),
        owner.model_copy(update={"workspace_id": "interrupt-scope-other-workspace"}),
        owner.model_copy(update={"tenant_id": "interrupt-scope-other-tenant"}),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(owner)
    for other_actor in other_actors:
        await service.bootstrap_actor(other_actor)
    queued, waiting_run_id, projection_id = await seed_waiting_interrupt(
        session_factory,
        service,
        owner,
        interrupt_id="scoped-interrupt",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    owner_view = await service.get_task(owner, str(queued["task_id"]))

    assert owner_view is not None
    assert owner_view["status"] == "waiting_human"
    assert owner_view["pending_interrupts"] == [
        {
            "task_id": str(queued["task_id"]),
            "run_id": str(waiting_run_id),
            "interrupt_id": "scoped-interrupt",
            "namespace": "review",
            "checkpoint_id": owner_view["pending_interrupts"][0]["checkpoint_id"],
            "response_version": 1,
            "status": "pending",
            "payload": {"kind": "artifact_review", "artifact_version": 1},
            "response": None,
            "expires_at": owner_view["pending_interrupts"][0]["expires_at"],
            "responded_at": None,
        }
    ]
    review = InterruptResponseSubmission(response_version=1, action="approve")
    for other_actor in other_actors:
        assert await service.get_task(other_actor, str(queued["task_id"])) is None
        assert (
            await service.respond_interrupt(
                other_actor,
                str(queued["task_id"]),
                "scoped-interrupt",
                review,
                f"scoped-response-{other_actor.tenant_id}-{other_actor.workspace_id}",
            )
            is None
        )

    async with session_factory() as session:
        projection = await session.scalar(
            select(InterruptProjection).where(InterruptProjection.id == projection_id)
        )
        respond_count = await session.scalar(
            select(func.count())
            .select_from(TaskCommand)
            .where(
                TaskCommand.task_id == UUID(str(queued["task_id"])),
                TaskCommand.command_type == "respond",
            )
        )
    assert projection is not None
    assert projection.status == "pending"
    assert projection.response is None
    assert respond_count == 0


@pytest.mark.asyncio
async def test_respond_interrupt_persists_lineage_command_and_idempotent_view(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="interrupt-success-tenant",
        workspace_id="interrupt-success-workspace",
        user_id="oidc|interrupt-success-owner",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    queued, waiting_run_id, projection_id = await seed_waiting_interrupt(
        session_factory,
        service,
        actor,
        interrupt_id="successful-interrupt",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    review = InterruptResponseSubmission(
        response_version=1,
        action="approve",
        comment="Reviewed and approved.",
    )

    first = await service.respond_interrupt(
        actor,
        str(queued["task_id"]),
        "successful-interrupt",
        review,
        "successful-interrupt-response",
    )
    replay = await service.respond_interrupt(
        actor,
        str(queued["task_id"]),
        "successful-interrupt",
        review,
        "successful-interrupt-response",
    )

    assert first is not None
    assert replay is not None
    assert first["status"] == "waiting_human"
    assert replay["status"] == "waiting_human"
    assert replay["pending_interrupts"] == first["pending_interrupts"]
    assert first["pending_interrupts"][0]["status"] == "responding"
    assert first["pending_interrupts"][0]["response"] == {
        "action": "approve",
        "comment": "Reviewed and approved.",
    }
    assert first["pending_interrupts"][0]["responded_at"] is not None

    with pytest.raises(service_module.IdempotencyConflictError):
        await service.respond_interrupt(
            actor,
            str(queued["task_id"]),
            "successful-interrupt",
            InterruptResponseSubmission(response_version=1, action="reject"),
            "successful-interrupt-response",
        )
    with pytest.raises(service_module.InterruptResponseConflictError):
        await service.respond_interrupt(
            actor,
            str(queued["task_id"]),
            "successful-interrupt",
            InterruptResponseSubmission(response_version=1, action="reject"),
            "different-interrupt-response-key",
        )

    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id))
        projection = await session.scalar(
            select(InterruptProjection).where(InterruptProjection.id == projection_id)
        )
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.task_id == task_id).order_by(Run.attempt)
                )
            ).all()
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand)
                    .where(TaskCommand.task_id == task_id)
                    .order_by(TaskCommand.sequence)
                )
            ).all()
        )
    assert task is not None
    assert task.status == "waiting_human"
    assert projection is not None
    assert projection.status == "responding"
    assert projection.responded_at is not None
    assert projection.response == {
        "action": "approve",
        "comment": "Reviewed and approved.",
    }
    assert [run.attempt for run in runs] == [1, 2]
    assert runs[0].id == waiting_run_id
    assert runs[0].status == "waiting_human"
    assert runs[1].status == "queued"
    assert runs[1].resume_of_run_id == waiting_run_id
    assert runs[1].input_payload == runs[0].input_payload
    assert [(command.command_type, command.status) for command in commands] == [
        ("submit", "dispatched"),
        ("respond", "pending"),
    ]
    assert [command.sequence for command in commands] == [1, 2]
    assert commands[1].payload == {
        "projection_id": str(projection_id),
        "interrupt_id": "successful-interrupt",
        "checkpoint_id": projection.checkpoint_id,
        "response_version": 1,
        "response": projection.response,
        "expired": False,
    }

    async with session_factory() as session, session.begin():
        persisted_task = await session.scalar(select(Task).where(Task.id == task_id))
        resumed_run = await session.scalar(
            select(Run).where(Run.task_id == task_id, Run.attempt == 2)
        )
        assert persisted_task is not None
        assert resumed_run is not None
        persisted_task.status = "running"
        resumed_run.status = "running"

    running_view = await service.get_task(actor, str(task_id))

    assert running_view is not None
    assert running_view["status"] == "running"
    assert running_view["pending_interrupts"][0]["status"] == "responding"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("projection_status", "projection_version", "expires_in_seconds", "message"),
    (
        ("pending", 2, 300, "Interrupt response_version is stale."),
        ("resolved", 1, 300, "Interrupt has already been responded to."),
        ("expired", 1, -1, "Interrupt response window has expired."),
        ("pending", 1, -1, "Interrupt response window has expired."),
    ),
)
async def test_respond_interrupt_rejects_stale_resolved_and_expired_projection(
    connection: AsyncConnection,
    projection_status: str,
    projection_version: int,
    expires_in_seconds: int,
    message: str,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id=f"interrupt-conflict-{projection_status}-{projection_version}",
        workspace_id=f"interrupt-conflict-workspace-{expires_in_seconds}",
        user_id=f"oidc|interrupt-conflict-{uuid4().hex}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    queued, _, projection_id = await seed_waiting_interrupt(
        session_factory,
        service,
        actor,
        interrupt_id="conflicting-interrupt",
        response_version=projection_version,
        status=projection_status,
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
    )

    with pytest.raises(service_module.InterruptResponseConflictError) as error:
        await service.respond_interrupt(
            actor,
            str(queued["task_id"]),
            "conflicting-interrupt",
            InterruptResponseSubmission(response_version=1, action="approve"),
            "conflicting-interrupt-response",
        )

    assert str(error.value) == message
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        projection = await session.scalar(
            select(InterruptProjection).where(InterruptProjection.id == projection_id)
        )
        run_count = await session.scalar(
            select(func.count()).select_from(Run).where(Run.task_id == task_id)
        )
        respond_count = await session.scalar(
            select(func.count())
            .select_from(TaskCommand)
            .where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert projection is not None
    assert projection.status == projection_status
    assert run_count == 1
    assert respond_count == 0


@pytest.mark.asyncio
async def test_respond_interrupt_rejects_projection_from_an_older_waiting_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="interrupt-stale-run-tenant",
        workspace_id="interrupt-stale-run-workspace",
        user_id="oidc|interrupt-stale-run-owner",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    queued, waiting_run_id, _ = await seed_waiting_interrupt(
        session_factory,
        service,
        actor,
        interrupt_id="old-run-interrupt",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session, session.begin():
        first_run = await session.scalar(select(Run).where(Run.id == waiting_run_id))
        assert first_run is not None
        session.add(
            Run(
                id=uuid4(),
                tenant_id=first_run.tenant_id,
                workspace_id=first_run.workspace_id,
                owner_user_id=first_run.owner_user_id,
                thread_id=first_run.thread_id,
                task_id=first_run.task_id,
                attempt=2,
                status="waiting_human",
                official_assistant_id="official-assistant-review",
                official_run_id=f"newer-waiting-run-{uuid4().hex}",
                checkpoint_id=f"newer-checkpoint-{uuid4().hex}",
                input_payload=first_run.input_payload,
            )
        )

    with pytest.raises(service_module.InterruptResponseConflictError) as error:
        await service.respond_interrupt(
            actor,
            str(task_id),
            "old-run-interrupt",
            InterruptResponseSubmission(response_version=1, action="approve"),
            "old-run-interrupt-response",
        )

    assert str(error.value) == "Interrupt is stale for the latest waiting run."


@pytest.mark.asyncio
@pytest.mark.parametrize("same_request", (True, False))
async def test_concurrent_interrupt_responses_have_one_database_writer(
    same_request: bool,
) -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    actor = ActorContext(
        tenant_id=f"concurrent-interrupt-tenant-{suffix}",
        workspace_id=f"concurrent-interrupt-workspace-{suffix}",
        user_id=f"oidc|concurrent-interrupt-owner-{suffix}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    try:
        await service.bootstrap_actor(actor)
        queued, waiting_run_id, projection_id = await seed_waiting_interrupt(
            session_factory,
            service,
            actor,
            interrupt_id=f"concurrent-interrupt-{suffix}",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        first_review = InterruptResponseSubmission(
            response_version=1,
            action="approve",
            comment="First concurrent response.",
        )
        second_review = (
            first_review
            if same_request
            else InterruptResponseSubmission(
                response_version=1,
                action="reject",
                comment="Competing concurrent response.",
            )
        )
        first_key = f"concurrent-response-{suffix}"
        second_key = first_key if same_request else f"competing-response-{suffix}"

        results = await asyncio.gather(
            service.respond_interrupt(
                actor,
                str(queued["task_id"]),
                f"concurrent-interrupt-{suffix}",
                first_review,
                first_key,
            ),
            service.respond_interrupt(
                actor,
                str(queued["task_id"]),
                f"concurrent-interrupt-{suffix}",
                second_review,
                second_key,
            ),
            return_exceptions=True,
        )

        successes = [result for result in results if isinstance(result, dict)]
        conflicts = [
            result
            for result in results
            if isinstance(result, service_module.InterruptResponseConflictError)
        ]
        if same_request:
            assert len(successes) == 2
            assert conflicts == []
            assert (
                successes[0]["pending_interrupts"] == successes[1]["pending_interrupts"]
            )
        else:
            assert len(successes) == 1
            assert len(conflicts) == 1
        assert all(
            isinstance(result, (dict, service_module.InterruptResponseConflictError))
            for result in results
        )

        task_id = UUID(str(queued["task_id"]))
        async with session_factory() as session:
            projection = await session.scalar(
                select(InterruptProjection).where(
                    InterruptProjection.id == projection_id
                )
            )
            runs = list(
                (
                    await session.scalars(
                        select(Run).where(Run.task_id == task_id).order_by(Run.attempt)
                    )
                ).all()
            )
            respond_commands = list(
                (
                    await session.scalars(
                        select(TaskCommand).where(
                            TaskCommand.task_id == task_id,
                            TaskCommand.command_type == "respond",
                        )
                    )
                ).all()
            )
        assert projection is not None
        assert projection.status == "responding"
        assert projection.responded_at is not None
        assert [run.attempt for run in runs] == [1, 2]
        assert runs[1].resume_of_run_id == waiting_run_id
        assert len(respond_commands) == 1
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(Tenant).where(Tenant.external_id == actor.tenant_id)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_task_does_not_cross_tenant_workspace_or_owner_scope(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    owner = ActorContext(
        tenant_id="cancel-owner-tenant",
        workspace_id="cancel-owner-workspace",
        user_id="oidc|cancel-owner",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    other = ActorContext(
        tenant_id="cancel-other-tenant",
        workspace_id="cancel-other-workspace",
        user_id="oidc|cancel-other",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(owner)
    await service.bootstrap_actor(other)
    queued = await service.create_analysis(
        owner,
        submission(),
        idempotency_key="cross-tenant-cancel-owner",
    )

    assert await service.cancel_task(
        other,
        str(queued["task_id"]),
        "cross-tenant-cancel-attempt",
    ) is None
    owner_view = await service.get_task(owner, str(queued["task_id"]))
    assert owner_view is not None
    assert owner_view["status"] == "queued"
    assert owner_view["cancel_requested_at"] is None
    async with session_factory() as session:
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand)
                    .where(TaskCommand.task_id == UUID(str(queued["task_id"])))
                    .order_by(TaskCommand.sequence)
                )
            ).all()
        )
    assert [(command.command_type, command.status) for command in commands] == [
        ("submit", "pending")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse_idempotency_key", [True, False])
async def test_concurrent_cancel_requests_create_one_durable_command(
    reuse_idempotency_key: bool,
) -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    concurrent_actor = ActorContext(
        tenant_id=f"concurrent-cancel-tenant-{suffix}",
        workspace_id=f"concurrent-cancel-workspace-{suffix}",
        user_id=f"oidc|concurrent-cancel-user-{suffix}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    try:
        await service.bootstrap_actor(concurrent_actor)
        queued = await service.create_analysis(
            concurrent_actor,
            submission(),
            idempotency_key=f"concurrent-cancel-task-{suffix}",
        )
        first_key = f"concurrent-cancel-request-{suffix}"
        second_key = (
            first_key
            if reuse_idempotency_key
            else f"concurrent-cancel-retry-{suffix}"
        )

        first, second = await asyncio.gather(
            service.cancel_task(
                concurrent_actor,
                str(queued["task_id"]),
                first_key,
            ),
            service.cancel_task(
                concurrent_actor,
                str(queued["task_id"]),
                second_key,
            ),
        )

        assert first is not None
        assert second is not None
        assert first["cancel_requested_at"] is not None
        assert second["cancel_requested_at"] == first["cancel_requested_at"]
        task_id = UUID(str(queued["task_id"]))
        async with session_factory() as session:
            commands = list(
                (
                    await session.scalars(
                        select(TaskCommand)
                        .where(TaskCommand.task_id == task_id)
                        .order_by(TaskCommand.sequence)
                    )
                ).all()
            )
        assert [command.sequence for command in commands] == [1, 2]
        assert [(command.command_type, command.status) for command in commands] == [
            ("submit", "cancelled"),
            ("cancel_task", "pending"),
        ]
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(Tenant).where(Tenant.external_id == concurrent_actor.tenant_id)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_admission_key_and_payload_returns_one_persisted_task(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="idempotency-tenant",
        workspace_id="idempotency-workspace",
        user_id="oidc|idempotency-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)

    first = await service.create_analysis(
        actor,
        submission(),
        idempotency_key="admission-replay-1",
    )
    replay = await service.create_analysis(
        actor,
        submission(),
        idempotency_key="admission-replay-1",
    )

    assert replay["task_id"] == first["task_id"]
    async with session_factory() as session:
        counts = {
            model.__tablename__: await session.scalar(
                select(func.count())
                .select_from(model)
                .join(Tenant, model.tenant_id == Tenant.id)
                .where(Tenant.external_id == actor.tenant_id)
            )
            for model in (Thread, Task, TaskCommand)
        }
    assert counts == {"threads": 1, "tasks": 1, "task_commands": 1}


@pytest.mark.asyncio
async def test_same_admission_key_with_different_payload_is_a_conflict(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="idempotency-conflict-tenant",
        workspace_id="idempotency-conflict-workspace",
        user_id="oidc|idempotency-conflict-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    await service.create_analysis(
        actor,
        submission(),
        idempotency_key="admission-conflict-1",
    )

    with pytest.raises(service_module.IdempotencyConflictError) as error:
        await service.create_analysis(
            actor,
            submission(query_text="Use a different analysis payload."),
            idempotency_key="admission-conflict-1",
        )

    assert str(error.value) == (
        "Idempotency-Key was already used with a different analysis payload."
    )
    async with session_factory() as session:
        counts = {
            model.__tablename__: await session.scalar(
                select(func.count())
                .select_from(model)
                .join(Tenant, model.tenant_id == Tenant.id)
                .where(Tenant.external_id == actor.tenant_id)
            )
            for model in (Thread, Task, TaskCommand)
        }
    assert counts == {"threads": 1, "tasks": 1, "task_commands": 1}


@pytest.mark.asyncio
async def test_admission_key_is_isolated_between_actors_in_one_workspace(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor_one = ActorContext(
        tenant_id="actor-scope-tenant",
        workspace_id="actor-scope-workspace",
        user_id="oidc|actor-scope-user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    actor_two = actor_one.model_copy(
        update={"user_id": "oidc|actor-scope-user-2"}
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor_one)
    await service.bootstrap_actor(actor_two)

    first = await service.create_analysis(
        actor_one,
        submission(),
        idempotency_key="shared-actor-key-1",
    )
    second = await service.create_analysis(
        actor_two,
        submission(),
        idempotency_key="shared-actor-key-1",
    )

    assert second["task_id"] != first["task_id"]


@pytest.mark.asyncio
async def test_same_external_actor_ids_are_isolated_between_tenants(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    first_actor = ActorContext(
        tenant_id="tenant-scope-a",
        workspace_id="shared-workspace",
        user_id="oidc|shared-subject",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    second_actor = first_actor.model_copy(update={"tenant_id": "tenant-scope-b"})
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(first_actor)
    await service.bootstrap_actor(second_actor)

    first = await service.create_analysis(
        first_actor,
        submission(),
        idempotency_key="shared-admission-key",
    )
    second = await service.create_analysis(
        second_actor,
        submission(),
        idempotency_key="shared-admission-key",
    )

    assert first["task_id"] != second["task_id"]


@pytest.mark.asyncio
async def test_concurrent_same_payload_admission_returns_the_database_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = str(UUID(int=id(monkeypatch)))
    actor = ActorContext(
        tenant_id=f"concurrent-idempotency-tenant-{suffix}",
        workspace_id=f"concurrent-idempotency-workspace-{suffix}",
        user_id=f"oidc|concurrent-idempotency-user-{suffix}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    original_find = service_module._find_admission_task
    both_prechecked = asyncio.Event()
    precheck_count = 0

    async def synchronized_find(
        session: AsyncSession,
        resolved: ResolvedActor,
        idempotency_key: str,
    ) -> Task | None:
        nonlocal precheck_count
        result = await original_find(session, resolved, idempotency_key)
        if result is None and precheck_count < 2:
            precheck_count += 1
            if precheck_count == 2:
                both_prechecked.set()
            await both_prechecked.wait()
        return result

    monkeypatch.setattr(service_module, "_find_admission_task", synchronized_find)
    try:
        first, second = await asyncio.gather(
            service.create_analysis(
                actor,
                submission(),
                idempotency_key="concurrent-admission-1",
            ),
            service.create_analysis(
                actor,
                submission(),
                idempotency_key="concurrent-admission-1",
            ),
        )

        assert second["task_id"] == first["task_id"]
        async with session_factory() as session:
            counts = {
                model.__tablename__: await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .join(Tenant, model.tenant_id == Tenant.id)
                    .where(Tenant.external_id == actor.tenant_id)
                )
                for model in (Thread, Task, TaskCommand)
            }
        assert counts == {"threads": 1, "tasks": 1, "task_commands": 1}
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(Tenant).where(Tenant.external_id == actor.tenant_id)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_agent_stream_uses_official_run_id_from_highest_attempt(
    connection: AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="latest-attempt-tenant",
        workspace_id="latest-attempt-workspace",
        user_id="oidc|latest-attempt-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    queued = await service.create_analysis(
        actor,
        submission(),
        idempotency_key="latest-attempt-agent-stream-1",
    )
    task_id = UUID(queued["task_id"])

    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id))
        assert task is not None
        thread = await session.scalar(select(Thread).where(Thread.id == task.thread_id))
        assert thread is not None
        thread.official_thread_id = f"official-thread-{task.id}"
        task.status = "running"
        first_run = Run(
            id=uuid4(),
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
            owner_user_id=task.owner_user_id,
            thread_id=task.thread_id,
            task_id=task.id,
            attempt=1,
            status="running",
            official_assistant_id="official-assistant-attempt-1",
            official_run_id=f"official-run-attempt-1-{task.id}",
            input_payload=task.request_payload,
        )
        second_run = Run(
            id=uuid4(),
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
            owner_user_id=task.owner_user_id,
            thread_id=task.thread_id,
            task_id=task.id,
            attempt=2,
            status="running",
            official_assistant_id="official-assistant-attempt-2",
            official_run_id=f"official-run-attempt-2-{task.id}",
            input_payload=task.request_payload,
        )
        market = DomainMarketSnapshot.model_validate(complete_market_snapshot())
        evidence = DomainWebEvidence(
            query="old attempt evidence",
            final_url="https://example.com/old-attempt",
            fetched_at=NOW,
            content_hash="c" * 64,
            title="Old attempt source",
            source="test_search",
            excerpt="This belongs only to attempt one.",
            evidence_relation="supports",
        )
        session.add_all([first_run, second_run])
        await session.flush()
        session.add_all(
            [
                MarketSnapshot(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    workspace_id=task.workspace_id,
                    owner_user_id=task.owner_user_id,
                    task_id=task.id,
                    run_id=first_run.id,
                    symbol=market.symbol,
                    snapshot=market.model_dump(mode="json"),
                    fetched_at=market.fetched_at,
                ),
                WebEvidence(
                    id=uuid4(),
                    tenant_id=task.tenant_id,
                    workspace_id=task.workspace_id,
                    owner_user_id=task.owner_user_id,
                    task_id=task.id,
                    run_id=first_run.id,
                    source_url=str(evidence.final_url),
                    title=evidence.title,
                    payload=evidence.model_dump(mode="json"),
                    fetched_at=evidence.fetched_at,
                    published_at=evidence.published_at,
                ),
            ]
        )

    view = await service.get_task(actor, queued["task_id"])

    assert view is not None
    assert view["agent_stream"] == {
        "protocol": "langgraph-v2",
        "assistant_id": "official-assistant-attempt-2",
        "thread_id": f"official-thread-{task_id}",
        "run_id": f"official-run-attempt-2-{task_id}",
    }
    assert view["market_snapshot"] is None
    assert view["web_evidence"] == []
    monkeypatch.setenv("AGENT_ASSISTANT_ID", "replacement-assistant")
    replacement_service = ProductAnalysisService(session_factory=session_factory)

    replacement_view = await replacement_service.get_task(actor, queued["task_id"])

    assert replacement_view is not None
    assert replacement_view["agent_stream"] == view["agent_stream"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_component",
    ("assistant_id", "thread_id", "run_id"),
)
async def test_agent_stream_is_null_when_persisted_triple_is_incomplete(
    connection: AsyncConnection,
    missing_component: str,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id=f"missing-{missing_component}-tenant",
        workspace_id=f"missing-{missing_component}-workspace",
        user_id=f"oidc|missing-{missing_component}-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    queued = await service.create_analysis(
        actor,
        submission(),
        idempotency_key=f"missing-{missing_component}-agent-stream-1",
    )
    task_id = UUID(queued["task_id"])

    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id))
        assert task is not None
        thread = await session.scalar(select(Thread).where(Thread.id == task.thread_id))
        assert thread is not None
        thread.official_thread_id = (
            None
            if missing_component == "thread_id"
            else f"official-thread-{task.id}"
        )
        task.status = "running"
        session.add(
            Run(
                id=uuid4(),
                tenant_id=task.tenant_id,
                workspace_id=task.workspace_id,
                owner_user_id=task.owner_user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                attempt=1,
                status="running",
                official_assistant_id=(
                    None
                    if missing_component == "assistant_id"
                    else "official-assistant"
                ),
                official_run_id=(
                    None
                    if missing_component == "run_id"
                    else f"official-run-{task.id}"
                ),
                input_payload=task.request_payload,
            )
        )

    view = await service.get_task(actor, queued["task_id"])

    assert view is not None
    assert view["agent_stream"] is None


@pytest.mark.asyncio
async def test_agent_stream_does_not_join_latest_run_to_the_wrong_task_thread(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="wrong-thread-tenant",
        workspace_id="wrong-thread-workspace",
        user_id="oidc|wrong-thread-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    queued = await service.create_analysis(
        actor,
        submission(),
        idempotency_key="wrong-thread-agent-stream-1",
    )
    task_id = UUID(queued["task_id"])

    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id))
        assert task is not None
        task_thread = await session.scalar(
            select(Thread).where(Thread.id == task.thread_id)
        )
        assert task_thread is not None
        task_thread.official_thread_id = f"official-task-thread-{task.id}"
        wrong_thread = Thread(
            id=uuid4(),
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
            owner_user_id=task.owner_user_id,
            official_thread_id=f"official-wrong-thread-{task.id}",
            title="Wrong task thread",
            context={},
        )
        session.add(wrong_thread)
        await session.flush()
        task.status = "running"
        session.add(
            Run(
                id=uuid4(),
                tenant_id=task.tenant_id,
                workspace_id=task.workspace_id,
                owner_user_id=task.owner_user_id,
                thread_id=wrong_thread.id,
                task_id=task.id,
                attempt=1,
                status="running",
                official_assistant_id="official-assistant",
                official_run_id=f"official-run-{task.id}",
                input_payload=task.request_payload,
            )
        )

    view = await service.get_task(actor, queued["task_id"])

    assert view is not None
    assert view["agent_stream"] is None


@pytest.mark.asyncio
async def test_task_command_remote_failure_is_persisted_and_readable(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="service-tenant",
        workspace_id="service-workspace",
        user_id="oidc|service-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)

    queued = await service.create_analysis(
        actor,
        AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Assess current BTC risk.",
            notify=False,
        ),
        idempotency_key="failure-analysis-1",
    )
    assert queued["status"] == "queued"
    assert queued["agent_stream"] is None

    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=FailingRemoteRunner(),
        worker_id="failure-worker",
    )
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor, queued["task_id"])

    assert view is not None
    assert view["status"] == "failed"
    assert view["agent_stream"] == {
        "protocol": "langgraph-v2",
        "assistant_id": "official-assistant-failure",
        "thread_id": "official-thread-1",
        "run_id": "official-run-1",
    }
    assert view["artifact"] is None
    assert view["errors"] == [
        {
            "code": "provider_unavailable",
            "message": "无法连接市场数据提供方，当前未生成分析结果。",
            "retryable": True,
            "provider": "okx",
        }
    ]
    task_uuid = UUID(queued["task_id"])
    async with session_factory() as session:
        run_count = await session.scalar(
            select(func.count()).select_from(Run).where(Run.task_id == task_uuid)
        )
        command_count = await session.scalar(
            select(func.count())
            .select_from(TaskCommand)
            .where(TaskCommand.task_id == task_uuid)
        )
        command_status = await session.scalar(
            select(TaskCommand.status).where(TaskCommand.task_id == task_uuid)
        )
    assert run_count == 1
    assert command_count == 1
    assert command_status == "dispatched"


@pytest.mark.asyncio
async def test_success_persists_stage_records_and_atomic_artifact(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    actor = ActorContext(
        tenant_id="success-tenant",
        workspace_id="success-workspace",
        user_id="oidc|success-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor)
    queued = await service.create_analysis(
        actor,
        AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Assess current BTC risk.",
            notify=False,
        ),
        idempotency_key="success-analysis-1",
    )
    assert queued["agent_stream"] is None

    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulRemoteRunner(),
        worker_id="success-worker",
    )
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor, queued["task_id"])

    assert view is not None
    assert view["status"] == "succeeded"
    assert view["agent_stream"] == {
        "protocol": "langgraph-v2",
        "assistant_id": "official-assistant-success",
        "thread_id": "official-thread-success",
        "run_id": "official-run-success",
    }
    assert view["completed_at"] is not None
    assert isinstance(view["market_snapshot"], DomainMarketSnapshot)
    assert view["market_snapshot"].symbol == "BTC-USDT-SWAP"
    assert len(view["web_evidence"]) == 1
    assert isinstance(view["web_evidence"][0], DomainWebEvidence)
    assert str(view["web_evidence"][0].final_url) == "https://example.com/macro"
    assert view["artifact"]["analysis"]["main_action"] == "open_long"
    assert view["errors"] == []
    run_list = await service.list_runs(actor, limit=25)
    assert run_list == {
        "items": [
            {
                "run_id": run_list["items"][0]["run_id"],
                "task_id": queued["task_id"],
                "attempt": 1,
                "status": "succeeded",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "created_at": run_list["items"][0]["created_at"],
                "finished_at": run_list["items"][0]["finished_at"],
                "main_action": "open_long",
            }
        ],
        "limit": 25,
    }
    other_actor = actor.model_copy(update={"user_id": "oidc|success-other-user"})
    await service.bootstrap_actor(other_actor)
    assert await service.list_runs(other_actor, limit=25) == {
        "items": [],
        "limit": 25,
    }
    replayed = await service.create_analysis(
        actor,
        AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Assess current BTC risk.",
            notify=False,
        ),
        idempotency_key="success-analysis-1",
    )
    assert replayed["task_id"] == queued["task_id"]
    assert replayed["status"] == "succeeded"
    assert replayed["agent_stream"] == view["agent_stream"]
    assert isinstance(replayed["market_snapshot"], DomainMarketSnapshot)
    assert isinstance(replayed["web_evidence"][0], DomainWebEvidence)
    assert replayed["artifact"]["analysis"]["main_action"] == "open_long"
    task_uuid = UUID(queued["task_id"])
    async with session_factory() as session:
        counts = {
            model.__tablename__: await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.task_id == task_uuid)
            )
            for model in (
                MarketSnapshot,
                WebEvidence,
                Artifact,
                ArtifactVersion,
                Decision,
            )
        }
    assert counts == {
        "market_snapshots": 1,
        "web_evidence": 1,
        "artifacts": 1,
        "artifact_versions": 1,
        "decisions": 1,
    }

    async with session_factory() as session:
        first_run = await session.scalar(
            select(Run).where(Run.task_id == task_uuid, Run.attempt == 1)
        )
        assert first_run is not None
        first_run_id = first_run.id
        session.add(
            Run(
                id=uuid4(),
                tenant_id=first_run.tenant_id,
                workspace_id=first_run.workspace_id,
                owner_user_id=first_run.owner_user_id,
                thread_id=first_run.thread_id,
                task_id=first_run.task_id,
                attempt=2,
                status="failed",
                official_assistant_id="official-assistant-failure-2",
                official_run_id="official-run-failure-2",
                input_payload=first_run.input_payload,
                output_payload={
                    "terminal_status": "failed",
                    "errors": [
                        {
                            "code": "provider_unavailable",
                            "retryable": True,
                        }
                    ],
                },
                finished_at=first_run.finished_at,
            )
        )
        await session.commit()

    latest_attempt = await service.get_task(actor, queued["task_id"])
    historical_attempt = await service.get_task(
        actor,
        queued["task_id"],
        run_id=first_run_id,
    )

    assert latest_attempt is not None
    assert latest_attempt["status"] == "failed"
    assert latest_attempt["artifact"] is None
    assert latest_attempt["errors"][0]["code"] == "provider_unavailable"
    assert historical_attempt is not None
    assert historical_attempt["status"] == "succeeded"
    assert historical_attempt["artifact"]["analysis"]["main_action"] == "open_long"
    assert len(historical_attempt["web_evidence"]) == 1
