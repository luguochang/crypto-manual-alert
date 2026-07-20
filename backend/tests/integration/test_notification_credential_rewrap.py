from __future__ import annotations

from collections.abc import AsyncIterator
import os
from uuid import uuid4

from pydantic import SecretStr
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

from crypto_alert_v2.notifications.credentials import (
    NotificationCredentialCipher,
    NotificationCredentialError,
)
from crypto_alert_v2.notifications.rotation import (
    rewrap_notification_credential_batch,
    rotate_notification_credentials,
)
from crypto_alert_v2.persistence.base import Base, PRODUCT_SCHEMA
from crypto_alert_v2.persistence.models import NotificationDestination
from tests.integration.test_outbox_idempotency import seed_decision


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


async def _seed_destination(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cipher: NotificationCredentialCipher,
    credential: str,
) -> NotificationDestination:
    decision = await seed_decision(session_factory)
    destination_id = uuid4()
    destination = NotificationDestination(
        id=destination_id,
        tenant_id=decision.tenant_id,
        workspace_id=decision.workspace_id,
        owner_user_id=decision.owner_user_id,
        channel="bark",
        status="enabled",
        credential_ciphertext=cipher.encrypt(
            SecretStr(credential),
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


@pytest.mark.asyncio
async def test_rotation_rewraps_batches_and_can_retire_the_old_key(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    old_cipher = NotificationCredentialCipher(key=b"o" * 32, key_version="v1")
    first = await _seed_destination(
        session_factory,
        cipher=old_cipher,
        credential="first-rotation-device-key",
    )
    second = await _seed_destination(
        session_factory,
        cipher=old_cipher,
        credential="second-rotation-device-key",
    )
    rotating_cipher = NotificationCredentialCipher(
        key=b"n" * 32,
        key_version="v2",
        decrypt_keys={"v1": b"o" * 32},
    )

    first_batch = await rewrap_notification_credential_batch(
        session_factory,
        credential_cipher=rotating_cipher,
        batch_size=1,
    )
    assert first_batch.scanned_rows == 1
    assert first_batch.rewrapped_rows == 1
    assert first_batch.remaining_old_version_rows == 1

    completed = await rotate_notification_credentials(
        session_factory,
        credential_cipher=rotating_cipher,
        batch_size=1,
    )
    assert completed.rewrapped_rows == 1
    assert completed.remaining_old_version_rows == 0

    retired_cipher = NotificationCredentialCipher(key=b"n" * 32, key_version="v2")
    async with session_factory() as session:
        destinations = list(
            (
                await session.scalars(
                    select(NotificationDestination).where(
                        NotificationDestination.id.in_((first.id, second.id))
                    )
                )
            ).all()
        )
    assert {destination.credential_key_version for destination in destinations} == {
        "v2"
    }
    assert {
        retired_cipher.decrypt(
            destination.credential_ciphertext,
            destination_id=destination.id,
            tenant_id=destination.tenant_id,
            workspace_id=destination.workspace_id,
            owner_user_id=destination.owner_user_id,
            channel=destination.channel,
            key_version=destination.credential_key_version,
        ).get_secret_value()
        for destination in destinations
    } == {"first-rotation-device-key", "second-rotation-device-key"}

    replay = await rotate_notification_credentials(
        session_factory,
        credential_cipher=retired_cipher,
        batch_size=1,
    )
    assert replay.batches == 0
    assert replay.rewrapped_rows == 0


@pytest.mark.asyncio
async def test_unknown_key_version_fails_closed_without_changing_the_row(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    old_cipher = NotificationCredentialCipher(key=b"o" * 32, key_version="v1")
    destination = await _seed_destination(
        session_factory,
        cipher=old_cipher,
        credential="must-remain-encrypted",
    )
    async with session_factory() as session, session.begin():
        persisted = await session.get(NotificationDestination, destination.id)
        assert persisted is not None
        original_ciphertext = persisted.credential_ciphertext
        persisted.credential_key_version = "retired-without-key"

    rotating_cipher = NotificationCredentialCipher(
        key=b"n" * 32,
        key_version="v2",
        decrypt_keys={"v1": b"o" * 32},
    )
    with pytest.raises(NotificationCredentialError):
        await rewrap_notification_credential_batch(
            session_factory,
            credential_cipher=rotating_cipher,
            batch_size=10,
        )

    async with session_factory() as session:
        unchanged = await session.get(NotificationDestination, destination.id)
    assert unchanged is not None
    assert unchanged.credential_key_version == "retired-without-key"
    assert unchanged.credential_ciphertext == original_ciphertext
