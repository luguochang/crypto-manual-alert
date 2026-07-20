from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json
import os
from typing import Any
from uuid import uuid4

import httpx
from pydantic import SecretStr
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

from crypto_alert_v2.api.schemas import NotificationSettingsUpdate
from crypto_alert_v2.api.service import (
    NotificationSettingsConflictError,
    ProductAnalysisService,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.notifications.adapters import DeliveryResult
from crypto_alert_v2.notifications.credentials import NotificationCredentialCipher
from crypto_alert_v2.notifications.outbox import plan_notification
from crypto_alert_v2.notifications.resolver import DatabaseNotificationAdapterResolver
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import (
    Decision,
    NotificationDestination,
    NotificationOutbox,
    Tenant,
)
from crypto_alert_v2.workers.notification import OutboxWorker
from tests.integration.test_outbox_idempotency import (
    notification_kwargs,
    seed_decision,
)
from tests.integration.support.actor_cleanup import delete_actor_test_data


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


async def _destination(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    decision: Decision,
    cipher: NotificationCredentialCipher,
    device_key: str,
    status: str = "enabled",
) -> NotificationDestination:
    destination_id = uuid4()
    destination = NotificationDestination(
        id=destination_id,
        tenant_id=decision.tenant_id,
        workspace_id=decision.workspace_id,
        owner_user_id=decision.owner_user_id,
        channel="bark",
        status=status,
        credential_ciphertext=cipher.encrypt(
            SecretStr(device_key),
            destination_id=destination_id,
            tenant_id=decision.tenant_id,
            workspace_id=decision.workspace_id,
            owner_user_id=decision.owner_user_id,
            channel="bark",
        ),
        credential_key_version=cipher.key_version,
    )
    async with session_factory() as session, session.begin():
        session.add(destination)
    return destination


async def _plan(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    decision: Decision,
    destination_id: object | None,
    body: str,
    now: datetime,
) -> NotificationOutbox:
    async with session_factory() as session, session.begin():
        plan = await plan_notification(
            session,
            **notification_kwargs(decision),
            destination_id=destination_id,
            payload={"title": "Analysis complete", "body": body},
            now=now,
        )
    return plan.notification


@pytest.mark.asyncio
async def test_worker_routes_each_tenant_only_to_its_encrypted_destination(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    first = await seed_decision(session_factory)
    second = await seed_decision(session_factory)
    cipher = NotificationCredentialCipher(key=b"n" * 32, key_version="v1")
    first_destination = await _destination(
        session_factory,
        decision=first,
        cipher=cipher,
        device_key="first-owner-device-key",
    )
    second_destination = await _destination(
        session_factory,
        decision=second,
        cipher=cipher,
        device_key="second-owner-device-key",
    )
    now = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    first_notification = await _plan(
        session_factory,
        decision=first,
        destination_id=first_destination.id,
        body="first-owner-result",
        now=now,
    )
    second_notification = await _plan(
        session_factory,
        decision=second,
        destination_id=second_destination.id,
        body="second-owner-result",
        now=now,
    )
    deliveries: list[dict[str, Any]] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.day.app/push")
        deliveries.append(json.loads(request.content))
        return httpx.Response(200, json={"code": 200, "timestamp": 1720000000})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        resolver = DatabaseNotificationAdapterResolver(
            session_factory=session_factory,
            credential_cipher=cipher,
            http_client=client,
        )
        worker = OutboxWorker(
            session_factory=session_factory,
            adapters={},
            adapter_resolver=resolver,
            worker_id="notification-destination-test",
            clock=lambda: now,
        )

        assert await worker.dispatch_once() is True
        assert await worker.dispatch_once() is True
        assert await worker.dispatch_once() is False

    assert {delivery["body"]: delivery["device_key"] for delivery in deliveries} == {
        "first-owner-result": "first-owner-device-key",
        "second-owner-result": "second-owner-device-key",
    }
    async with session_factory() as session:
        statuses = dict(
            (
                await session.execute(
                    select(NotificationOutbox.id, NotificationOutbox.status).where(
                        NotificationOutbox.id.in_(
                            (first_notification.id, second_notification.id)
                        )
                    )
                )
            ).all()
        )
    assert statuses == {
        first_notification.id: "delivered",
        second_notification.id: "delivered",
    }


@pytest.mark.asyncio
async def test_database_rejects_cross_scope_destination_binding(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    first = await seed_decision(session_factory)
    second = await seed_decision(session_factory)
    cipher = NotificationCredentialCipher(key=b"n" * 32, key_version="v1")
    second_destination = await _destination(
        session_factory,
        decision=second,
        cipher=cipher,
        device_key="second-owner-device-key",
    )

    with pytest.raises(IntegrityError):
        await _plan(
            session_factory,
            decision=first,
            destination_id=second_destination.id,
            body="must-not-route-cross-scope",
            now=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        )


class _FallbackAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, request: object) -> DeliveryResult:
        del request
        self.calls += 1
        return DeliveryResult.delivered(provider_receipt="fallback-must-not-run")


@pytest.mark.asyncio
async def test_disabled_destination_never_falls_back_to_a_global_adapter(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    decision = await seed_decision(session_factory)
    cipher = NotificationCredentialCipher(key=b"n" * 32, key_version="v1")
    destination = await _destination(
        session_factory,
        decision=decision,
        cipher=cipher,
        device_key="disabled-owner-device-key",
        status="disabled",
    )
    now = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    notification = await _plan(
        session_factory,
        decision=decision,
        destination_id=destination.id,
        body="disabled-destination",
        now=now,
    )
    fallback = _FallbackAdapter()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: None)
    ) as client:
        resolver = DatabaseNotificationAdapterResolver(
            session_factory=session_factory,
            credential_cipher=cipher,
            http_client=client,
        )
        worker = OutboxWorker(
            session_factory=session_factory,
            adapters={"bark": fallback},
            adapter_resolver=resolver,
            worker_id="disabled-destination-test",
            clock=lambda: now,
        )

        assert await worker.dispatch_once() is True

    assert fallback.calls == 0
    async with session_factory() as session:
        persisted = await session.get(NotificationOutbox, notification.id)
    assert persisted is not None
    assert persisted.status == "failed_terminal"


@pytest.mark.asyncio
async def test_concurrent_first_settings_updates_serialize_to_one_destination() -> None:
    assert PRODUCT_DATABASE_URL is not None
    engine = create_async_engine(_asyncpg_url(PRODUCT_DATABASE_URL))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    actor_suffix = str(uuid4())
    actor = ActorContext(
        tenant_id=f"notification-settings-tenant-{actor_suffix}",
        workspace_id=f"notification-settings-workspace-{actor_suffix}",
        user_id=f"oidc|notification-settings-user-{actor_suffix}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    cipher = NotificationCredentialCipher(key=b"n" * 32, key_version="v1")
    service = ProductAnalysisService(
        session_factory=session_factory,
        notification_credential_cipher=cipher,
    )
    await service.bootstrap_actor(actor)
    try:
        first, second = await asyncio.gather(
            service.update_notification_settings(
                actor,
                NotificationSettingsUpdate(
                    enabled=True,
                    device_key=SecretStr("first-concurrent-device-key"),
                ),
            ),
            service.update_notification_settings(
                actor,
                NotificationSettingsUpdate(
                    enabled=True,
                    device_key=SecretStr("second-concurrent-device-key"),
                ),
            ),
        )

        assert first["configured"] is True
        assert second["configured"] is True
        assert (await service.get_notification_settings(actor))["enabled"] is True
        async with session_factory() as session:
            destinations = list(
                (
                    await session.scalars(
                        select(NotificationDestination)
                        .join(Tenant, NotificationDestination.tenant_id == Tenant.id)
                        .where(Tenant.external_id == actor.tenant_id)
                    )
                ).all()
            )
            count = await session.scalar(
                select(func.count())
                .select_from(NotificationDestination)
                .join(Tenant, NotificationDestination.tenant_id == Tenant.id)
                .where(Tenant.external_id == actor.tenant_id)
            )
        assert count == 1
        destination = destinations[0]
        decrypted = cipher.decrypt(
            destination.credential_ciphertext,
            destination_id=destination.id,
            tenant_id=destination.tenant_id,
            workspace_id=destination.workspace_id,
            owner_user_id=destination.owner_user_id,
            channel=destination.channel,
            key_version=destination.credential_key_version,
        )
        assert decrypted.get_secret_value() in {
            "first-concurrent-device-key",
            "second-concurrent-device-key",
        }
    finally:
        async with session_factory() as session, session.begin():
            await delete_actor_test_data(session, actor)
        await engine.dispose()


@pytest.mark.asyncio
async def test_settings_remain_usable_during_key_overlap_and_fail_after_retirement() -> (
    None
):
    assert PRODUCT_DATABASE_URL is not None
    engine = create_async_engine(_asyncpg_url(PRODUCT_DATABASE_URL))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    actor_suffix = str(uuid4())
    actor = ActorContext(
        tenant_id=f"notification-rotation-tenant-{actor_suffix}",
        workspace_id=f"notification-rotation-workspace-{actor_suffix}",
        user_id=f"oidc|notification-rotation-user-{actor_suffix}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    old_cipher = NotificationCredentialCipher(key=b"o" * 32, key_version="v1")
    old_service = ProductAnalysisService(
        session_factory=session_factory,
        notification_credential_cipher=old_cipher,
    )
    await old_service.bootstrap_actor(actor)
    try:
        await old_service.update_notification_settings(
            actor,
            NotificationSettingsUpdate(
                enabled=True,
                device_key=SecretStr("rotation-overlap-device-key"),
            ),
        )

        overlap_service = ProductAnalysisService(
            session_factory=session_factory,
            notification_credential_cipher=NotificationCredentialCipher(
                key=b"n" * 32,
                key_version="v2",
                decrypt_keys={"v1": b"o" * 32},
            ),
        )
        await overlap_service.update_notification_settings(
            actor,
            NotificationSettingsUpdate(enabled=False),
        )
        enabled = await overlap_service.update_notification_settings(
            actor,
            NotificationSettingsUpdate(enabled=True),
        )
        assert enabled["enabled"] is True

        retired_service = ProductAnalysisService(
            session_factory=session_factory,
            notification_credential_cipher=NotificationCredentialCipher(
                key=b"n" * 32,
                key_version="v2",
            ),
        )
        with pytest.raises(
            NotificationSettingsConflictError,
            match="must be re-entered after key rotation",
        ):
            await retired_service.update_notification_settings(
                actor,
                NotificationSettingsUpdate(enabled=True),
            )

        async with session_factory() as session:
            destination = await session.scalar(
                select(NotificationDestination)
                .join(Tenant, NotificationDestination.tenant_id == Tenant.id)
                .where(Tenant.external_id == actor.tenant_id)
            )
        assert destination is not None
        assert destination.status == "enabled"
        assert destination.credential_key_version == "v1"
    finally:
        async with session_factory() as session, session.begin():
            await delete_actor_test_data(session, actor)
        await engine.dispose()
