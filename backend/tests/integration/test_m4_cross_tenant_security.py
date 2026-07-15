from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
from typing import AsyncIterator
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.api.app import create_app
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.auth.internal_token import (
    IDENTITY_DISCOVERY_AUDIENCE,
    InternalTokenIssuer,
    InternalTokenVerifier,
)
from crypto_alert_v2.auth.membership import DatabaseMembershipAuthority
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    InterruptPause,
    InterruptProjection,
    Membership,
    Run,
    Task,
    TaskCommand,
)
from crypto_alert_v2.persistence.repositories import resolve_actor
from tests.integration.test_product_analysis_service import (
    seed_waiting_interrupt,
    submission,
)


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


def actor(
    *,
    tenant_id: str,
    workspace_id: str,
    user_id: str,
) -> ActorContext:
    return ActorContext(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


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


@dataclass(frozen=True)
class SecurityHarness:
    session_factory: async_sessionmaker[AsyncSession]
    service: ProductAnalysisService
    client: httpx.AsyncClient
    owner: ActorContext
    same_tenant_peer: ActorContext
    cross_tenant_actor: ActorContext
    context_ids: dict[str, UUID]
    tokens: dict[str, str] = field(repr=False)

    def headers(
        self, principal: str, *, idempotency_key: str | None = None
    ) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.tokens[principal]}"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers


@pytest_asyncio.fixture
async def harness(connection: AsyncConnection) -> AsyncIterator[SecurityHarness]:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service = ProductAnalysisService(
        session_factory=session_factory,
        inbox_cursor_key=b"m4-security-matrix-inbox-key-material",
    )
    owner = actor(
        tenant_id="m4-tenant-a",
        workspace_id="m4-workspace-a",
        user_id="oidc|m4-owner",
    )
    same_tenant_peer = actor(
        tenant_id=owner.tenant_id,
        workspace_id=owner.workspace_id,
        user_id="oidc|m4-peer",
    )
    cross_tenant_actor = actor(
        tenant_id="m4-tenant-b",
        workspace_id=owner.workspace_id,
        user_id=owner.user_id,
    )
    for principal in (owner, same_tenant_peer, cross_tenant_actor):
        await service.provision_actor(
            principal,
            tenant_name=f"Tenant {principal.tenant_id}",
            workspace_name=f"Workspace {principal.workspace_id}",
            user_display_name=f"User {principal.user_id}",
        )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    scoped_issuer = InternalTokenIssuer(
        private_key=private_pem,
        key_id="m4-test-key",
        issuer="m4-security-gate",
        audience="m4-product-api",
    )
    scoped_verifier = InternalTokenVerifier(
        public_keys={"m4-test-key": public_pem},
        issuer="m4-security-gate",
        audience="m4-product-api",
    )
    identity_verifier = InternalTokenVerifier(
        public_keys={"m4-test-key": public_pem},
        issuer="m4-security-gate",
        audience=IDENTITY_DISCOVERY_AUDIENCE,
    )
    identity_issuer = InternalTokenIssuer(
        private_key=private_pem,
        key_id="m4-test-key",
        issuer="m4-security-gate",
        audience=IDENTITY_DISCOVERY_AUDIENCE,
    )
    principals = {
        "owner": owner,
        "same_tenant_peer": same_tenant_peer,
        "cross_tenant_actor": cross_tenant_actor,
    }
    async with session_factory() as session:
        context_ids = {
            name: (await resolve_actor(session, principal)).membership_id
            for name, principal in principals.items()
        }
    tokens = {
        name: scoped_issuer.issue_scoped(
            issuer=principal.identity_issuer,
            subject=principal.user_id,
            context_id=context_ids[name],
        )
        for name, principal in principals.items()
    }
    tokens["peer_with_owner_context"] = scoped_issuer.issue_scoped(
        issuer=same_tenant_peer.identity_issuer,
        subject=same_tenant_peer.user_id,
        context_id=context_ids["owner"],
    )
    tokens["owner_identity"] = identity_issuer.issue_identity(
        issuer=owner.identity_issuer,
        subject=owner.user_id,
    )
    tokens["peer_identity"] = identity_issuer.issue_identity(
        issuer=same_tenant_peer.identity_issuer,
        subject=same_tenant_peer.user_id,
    )
    membership_authority = DatabaseMembershipAuthority(
        session_factory=session_factory,
    )
    app = create_app(
        service=service,
        mode="production",
        token_verifier=scoped_verifier,
        identity_token_verifier=identity_verifier,
        membership_authority=membership_authority,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://product.m4.test",
    )
    try:
        yield SecurityHarness(
            session_factory=session_factory,
            service=service,
            client=client,
            owner=owner,
            same_tenant_peer=same_tenant_peer,
            cross_tenant_actor=cross_tenant_actor,
            context_ids=context_ids,
            tokens=tokens,
        )
    finally:
        await client.aclose()


async def seed_review(
    harness: SecurityHarness,
    principal: ActorContext,
    label: str,
) -> dict[str, object]:
    queued, _, _ = await seed_waiting_interrupt(
        harness.session_factory,
        harness.service,
        principal,
        interrupt_id=f"m4-{label}-interrupt",
        query_text=f"M4 security matrix {label}.",
    )
    return queued


async def seed_forkable_task(
    harness: SecurityHarness,
    principal: ActorContext,
) -> tuple[str, UUID, str]:
    queued = await harness.service.create_analysis(
        principal,
        submission(query_text="M4 fork isolation source."),
        idempotency_key="m4-fork-source",
    )
    task_id = UUID(str(queued["task_id"]))
    checkpoint_id = f"m4-fork-checkpoint-{uuid4()}"
    source_run_id = uuid4()
    async with harness.session_factory() as session, session.begin():
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
        task.status = "succeeded"
        task.completed_at = datetime.now(UTC)
        session.add(
            Run(
                id=source_run_id,
                tenant_id=task.tenant_id,
                workspace_id=task.workspace_id,
                owner_user_id=task.owner_user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                attempt=1,
                status="succeeded",
                checkpoint_id=checkpoint_id,
                input_payload=task.request_payload,
                finished_at=datetime.now(UTC),
            )
        )
    return str(task_id), source_run_id, checkpoint_id


def task_ids(payload: dict[str, object]) -> set[str]:
    items = payload.get("items")
    assert isinstance(items, list)
    return {
        str(item["task_id"])
        for item in items
        if isinstance(item, dict) and "task_id" in item
    }


def respond_all_payload(task_view: dict[str, object]) -> dict[str, object]:
    pause = task_view.get("pending_interrupts")
    assert isinstance(pause, dict)
    members = pause.get("members")
    assert isinstance(members, list) and members
    return {
        "pause_id": str(pause["pause_id"]),
        "pause_version": pause["pause_version"],
        "responses": [
            {
                "interrupt_id": member["interrupt_id"],
                "response_version": member["response_version"],
                "response": {"action": "approve", "comment": "M4 security gate"},
            }
            for member in members
            if isinstance(member, dict)
        ],
    }


@pytest.mark.asyncio
async def test_identity_context_discovery_and_selection_are_user_scoped(
    harness: SecurityHarness,
) -> None:
    owner_contexts = await harness.client.get(
        "/api/v2/auth/contexts",
        headers=harness.headers("owner_identity"),
    )
    peer_contexts = await harness.client.get(
        "/api/v2/auth/contexts",
        headers=harness.headers("peer_identity"),
    )
    assert owner_contexts.status_code == 200
    assert peer_contexts.status_code == 200
    assert {UUID(item["context_id"]) for item in owner_contexts.json()["items"]} == {
        harness.context_ids["owner"],
        harness.context_ids["cross_tenant_actor"],
    }
    assert {UUID(item["context_id"]) for item in peer_contexts.json()["items"]} == {
        harness.context_ids["same_tenant_peer"]
    }

    denied = await harness.client.post(
        "/api/v2/auth/context/select",
        headers=harness.headers("peer_identity"),
        json={"context_id": str(harness.context_ids["owner"])},
    )
    selected = await harness.client.post(
        "/api/v2/auth/context/select",
        headers=harness.headers("owner_identity"),
        json={"context_id": str(harness.context_ids["owner"])},
    )
    assert denied.status_code == 404
    assert denied.json() == {
        "detail": {
            "code": "auth_context_not_found",
            "message": "The selected authorization context is unavailable.",
        }
    }
    assert selected.status_code == 200
    assert UUID(selected.json()["context_id"]) == harness.context_ids["owner"]


@pytest.mark.asyncio
async def test_owner_peer_and_cross_tenant_read_matrix(
    harness: SecurityHarness,
) -> None:
    seeded = {
        "owner": await seed_review(harness, harness.owner, "owner-read"),
        "same_tenant_peer": await seed_review(
            harness,
            harness.same_tenant_peer,
            "peer-read",
        ),
        "cross_tenant_actor": await seed_review(
            harness,
            harness.cross_tenant_actor,
            "cross-read",
        ),
    }

    for principal, own_task in seeded.items():
        own_task_id = str(own_task["task_id"])
        own_detail = await harness.client.get(
            f"/api/v2/tasks/{own_task_id}",
            headers=harness.headers(principal),
        )
        assert own_detail.status_code == 200
        assert own_detail.json()["task_id"] == own_task_id

        for other_principal, other_task in seeded.items():
            if other_principal == principal:
                continue
            other_task_id = str(other_task["task_id"])
            denied = await harness.client.get(
                f"/api/v2/tasks/{other_task_id}",
                headers=harness.headers(principal),
            )
            assert denied.status_code == 404
            assert denied.json() == {"detail": "Task not found"}

        runs = await harness.client.get(
            "/api/v2/runs?limit=100",
            headers=harness.headers(principal),
        )
        inbox = await harness.client.get(
            "/api/v2/inbox?status=all&limit=100",
            headers=harness.headers(principal),
        )
        assert runs.status_code == 200
        assert inbox.status_code == 200
        assert task_ids(runs.json()) == {own_task_id}
        assert task_ids(inbox.json()) == {own_task_id}

    wrong_context = await harness.client.get(
        f"/api/v2/tasks/{seeded['owner']['task_id']}",
        headers=harness.headers("peer_with_owner_context"),
    )
    assert wrong_context.status_code == 403
    assert wrong_context.json() == {
        "detail": {
            "code": "auth_context_not_found",
            "message": "The authorization context is unavailable.",
        }
    }


@pytest.mark.asyncio
async def test_respond_and_cancel_writes_are_owner_scoped(
    harness: SecurityHarness,
) -> None:
    review_task = await seed_review(harness, harness.owner, "owner-write")
    review_task_id = str(review_task["task_id"])
    owner_view = await harness.service.get_task(harness.owner, review_task_id)
    assert owner_view is not None
    review_payload = respond_all_payload(owner_view)

    cancel_task = await harness.service.create_analysis(
        harness.owner,
        submission(query_text="M4 owner cancellation scope."),
        idempotency_key="m4-owner-cancel-task",
    )
    cancel_task_id = str(cancel_task["task_id"])

    for principal in ("same_tenant_peer", "cross_tenant_actor"):
        response = await harness.client.post(
            f"/api/v2/tasks/{review_task_id}/interrupts/respond-all",
            headers=harness.headers(
                principal, idempotency_key=f"m4-{principal}-respond"
            ),
            json=review_payload,
        )
        cancellation = await harness.client.post(
            f"/api/v2/tasks/{cancel_task_id}/cancel",
            headers=harness.headers(
                principal, idempotency_key=f"m4-{principal}-cancel"
            ),
        )
        assert response.status_code == 404
        assert cancellation.status_code == 404

    async with harness.session_factory() as session:
        pre_owner_commands = await session.scalar(
            select(func.count())
            .select_from(TaskCommand)
            .where(
                TaskCommand.task_id.in_((UUID(review_task_id), UUID(cancel_task_id))),
                TaskCommand.command_type.in_(("respond", "cancel_task")),
            )
        )
    assert pre_owner_commands == 0

    owner_response = await harness.client.post(
        f"/api/v2/tasks/{review_task_id}/interrupts/respond-all",
        headers=harness.headers("owner", idempotency_key="m4-owner-respond"),
        json=review_payload,
    )
    owner_cancel = await harness.client.post(
        f"/api/v2/tasks/{cancel_task_id}/cancel",
        headers=harness.headers("owner", idempotency_key="m4-owner-cancel"),
    )
    assert owner_response.status_code == 202
    assert owner_cancel.status_code == 202

    async with harness.session_factory() as session:
        write_commands = list(
            (
                await session.scalars(
                    select(TaskCommand)
                    .where(
                        TaskCommand.task_id.in_(
                            (UUID(review_task_id), UUID(cancel_task_id))
                        ),
                        TaskCommand.command_type.in_(("respond", "cancel_task")),
                    )
                    .order_by(TaskCommand.task_id, TaskCommand.sequence)
                )
            ).all()
        )
    assert [command.command_type for command in write_commands] == [
        "respond",
        "cancel_task",
    ] or [command.command_type for command in write_commands] == [
        "cancel_task",
        "respond",
    ]
    assert {command.actor_user_id for command in write_commands} == {
        write_commands[0].actor_user_id
    }


@pytest.mark.asyncio
async def test_membership_revoke_immediately_invalidates_a_preissued_token(
    harness: SecurityHarness,
) -> None:
    review_task = await seed_review(harness, harness.owner, "revoked-review")
    review_task_id = str(review_task["task_id"])
    cancel_task = await harness.service.create_analysis(
        harness.owner,
        submission(query_text="M4 revoked-session cancellation."),
        idempotency_key="m4-revoked-cancel-task",
    )
    cancel_task_id = str(cancel_task["task_id"])
    before_revoke = await harness.client.get(
        f"/api/v2/tasks/{review_task_id}",
        headers=harness.headers("owner"),
    )
    assert before_revoke.status_code == 200
    review_payload = respond_all_payload(before_revoke.json())

    async with harness.session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == UUID(review_task_id)))
        assert task is not None
        membership = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == task.tenant_id,
                Membership.workspace_id == task.workspace_id,
                Membership.user_id == task.owner_user_id,
            )
        )
        assert membership is not None
        membership.is_active = False

    stale_headers = harness.headers("owner")
    read_requests = (
        f"/api/v2/tasks/{review_task_id}",
        "/api/v2/runs?limit=100",
        "/api/v2/inbox?status=all&limit=100",
    )
    for path in read_requests:
        denied = await harness.client.get(path, headers=stale_headers)
        assert denied.status_code == 403
        assert denied.json() == {
            "detail": {
                "code": "auth_context_not_found",
                "message": "The authorization context is unavailable.",
            }
        }

    denied_response = await harness.client.post(
        f"/api/v2/tasks/{review_task_id}/interrupts/respond-all",
        headers=harness.headers("owner", idempotency_key="m4-stale-session-respond"),
        json=review_payload,
    )
    denied_cancel = await harness.client.post(
        f"/api/v2/tasks/{cancel_task_id}/cancel",
        headers=harness.headers("owner", idempotency_key="m4-stale-session-cancel"),
    )
    denied_create = await harness.client.post(
        "/api/v2/analysis",
        headers=harness.headers("owner", idempotency_key="m4-stale-session-create"),
        json=submission(query_text="M4 stale session create attempt.").model_dump(
            mode="json"
        ),
    )
    assert {
        denied_response.status_code,
        denied_cancel.status_code,
        denied_create.status_code,
    } == {403}

    async with harness.session_factory() as session:
        denied_write_count = await session.scalar(
            select(func.count())
            .select_from(TaskCommand)
            .where(
                TaskCommand.task_id.in_((UUID(review_task_id), UUID(cancel_task_id))),
                TaskCommand.command_type.in_(("respond", "cancel_task")),
            )
        )
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == UUID(review_task_id))
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == UUID(review_task_id)
                    )
                )
            ).all()
        )
    assert denied_write_count == 0
    assert pause is not None and pause.status == "pending"
    assert {projection.status for projection in projections} == {"pending"}


@pytest.mark.asyncio
async def test_fork_write_isolation_requires_owner_admission(
    harness: SecurityHarness,
) -> None:
    task_id, source_run_id, checkpoint_id = await seed_forkable_task(
        harness,
        harness.owner,
    )
    path = f"/api/v2/tasks/{task_id}/fork"
    payload = {
        "source_run_id": str(source_run_id),
        "checkpoint_id": checkpoint_id,
    }

    for principal in ("same_tenant_peer", "cross_tenant_actor"):
        denied = await harness.client.post(
            path,
            headers=harness.headers(principal, idempotency_key=f"m4-{principal}-fork"),
            json=payload,
        )
        assert denied.status_code == 404

    admitted = await harness.client.post(
        path,
        headers=harness.headers("owner", idempotency_key="m4-owner-fork"),
        json=payload,
    )
    assert admitted.status_code == 202
    assert admitted.json()["task_id"] == task_id
    assert admitted.json()["status"] == "queued"

    async with harness.session_factory() as session:
        fork_commands = list(
            (
                await session.scalars(
                    select(TaskCommand).where(
                        TaskCommand.task_id == UUID(task_id),
                        TaskCommand.command_type == "fork",
                    )
                )
            ).all()
        )
        runs = list(
            (
                await session.scalars(
                    select(Run)
                    .where(Run.task_id == UUID(task_id))
                    .order_by(Run.attempt)
                )
            ).all()
        )
    assert len(fork_commands) == 1
    assert [run.attempt for run in runs] == [1, 2]
    assert runs[1].checkpoint_id == checkpoint_id
    assert runs[1].forked_from_run_id == source_run_id
    assert runs[1].forked_from_checkpoint_id == checkpoint_id

    async with harness.session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == UUID(task_id)))
        assert task is not None
        membership = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == task.tenant_id,
                Membership.workspace_id == task.workspace_id,
                Membership.user_id == task.owner_user_id,
            )
        )
        assert membership is not None
        membership.is_active = False

    stale_session = await harness.client.post(
        path,
        headers=harness.headers("owner", idempotency_key="m4-revoked-owner-fork"),
        json=payload,
    )
    assert stale_session.status_code == 403
