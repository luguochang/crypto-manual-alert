from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crypto_alert_v2.notifications.credentials import NotificationCredentialCipher
from crypto_alert_v2.persistence.models import NotificationDestination


@dataclass(frozen=True, slots=True)
class CredentialRewrapBatch:
    scanned_rows: int
    rewrapped_rows: int
    remaining_old_version_rows: int


@dataclass(frozen=True, slots=True)
class CredentialRotationResult:
    active_key_version: str
    batches: int
    scanned_rows: int
    rewrapped_rows: int
    remaining_old_version_rows: int


class CredentialRotationIncompleteError(RuntimeError):
    pass


async def rewrap_notification_credential_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    credential_cipher: NotificationCredentialCipher,
    batch_size: int = 100,
) -> CredentialRewrapBatch:
    if batch_size < 1 or batch_size > 1_000:
        raise ValueError("credential rewrap batch_size must be between 1 and 1000")

    active_version = credential_cipher.key_version
    rewrapped_rows = 0
    async with session_factory() as session, session.begin():
        destinations = list(
            (
                await session.scalars(
                    select(NotificationDestination)
                    .where(
                        NotificationDestination.credential_key_version != active_version
                    )
                    .order_by(NotificationDestination.id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for destination in destinations:
            previous_version = destination.credential_key_version
            previous_ciphertext = destination.credential_ciphertext
            credential = credential_cipher.decrypt(
                previous_ciphertext,
                destination_id=destination.id,
                tenant_id=destination.tenant_id,
                workspace_id=destination.workspace_id,
                owner_user_id=destination.owner_user_id,
                channel=destination.channel,
                key_version=previous_version,
            )
            next_ciphertext = credential_cipher.encrypt(
                credential,
                destination_id=destination.id,
                tenant_id=destination.tenant_id,
                workspace_id=destination.workspace_id,
                owner_user_id=destination.owner_user_id,
                channel=destination.channel,
            )
            result = await session.execute(
                update(NotificationDestination)
                .where(
                    NotificationDestination.id == destination.id,
                    NotificationDestination.credential_key_version == previous_version,
                    NotificationDestination.credential_ciphertext
                    == previous_ciphertext,
                )
                .values(
                    credential_ciphertext=next_ciphertext,
                    credential_key_version=active_version,
                    verified_at=None,
                    updated_at=func.now(),
                )
                .returning(NotificationDestination.id)
            )
            if result.scalar_one_or_none() is not None:
                rewrapped_rows += 1

    remaining = await count_notification_credentials_outside_active_version(
        session_factory,
        active_key_version=active_version,
    )
    return CredentialRewrapBatch(
        scanned_rows=len(destinations),
        rewrapped_rows=rewrapped_rows,
        remaining_old_version_rows=remaining,
    )


async def count_notification_credentials_outside_active_version(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    active_key_version: str,
) -> int:
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(NotificationDestination)
            .where(NotificationDestination.credential_key_version != active_key_version)
        )
    return int(count or 0)


async def rotate_notification_credentials(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    credential_cipher: NotificationCredentialCipher,
    batch_size: int = 100,
    max_batches: int = 100_000,
    inter_batch_delay_seconds: float = 0,
) -> CredentialRotationResult:
    if batch_size < 1 or batch_size > 1_000:
        raise ValueError("credential rotation batch_size must be between 1 and 1000")
    if max_batches < 1:
        raise ValueError("credential rotation max_batches must be positive")
    if inter_batch_delay_seconds < 0 or inter_batch_delay_seconds > 300:
        raise ValueError(
            "credential rotation inter_batch_delay_seconds must be between 0 and 300"
        )

    scanned_rows = 0
    rewrapped_rows = 0
    remaining = await count_notification_credentials_outside_active_version(
        session_factory,
        active_key_version=credential_cipher.key_version,
    )
    batches = 0
    while remaining > 0 and batches < max_batches:
        batch = await rewrap_notification_credential_batch(
            session_factory,
            credential_cipher=credential_cipher,
            batch_size=batch_size,
        )
        batches += 1
        scanned_rows += batch.scanned_rows
        rewrapped_rows += batch.rewrapped_rows
        remaining = batch.remaining_old_version_rows
        if remaining == 0:
            break
        if inter_batch_delay_seconds > 0:
            await asyncio.sleep(inter_batch_delay_seconds)
        elif batch.scanned_rows == 0 or batch.rewrapped_rows == 0:
            await asyncio.sleep(0.05)

    if remaining > 0:
        raise CredentialRotationIncompleteError(
            "notification credential rotation did not reach the retirement boundary"
        )
    return CredentialRotationResult(
        active_key_version=credential_cipher.key_version,
        batches=batches,
        scanned_rows=scanned_rows,
        rewrapped_rows=rewrapped_rows,
        remaining_old_version_rows=remaining,
    )


__all__ = [
    "CredentialRewrapBatch",
    "CredentialRotationIncompleteError",
    "CredentialRotationResult",
    "count_notification_credentials_outside_active_version",
    "rewrap_notification_credential_batch",
    "rotate_notification_credentials",
]
