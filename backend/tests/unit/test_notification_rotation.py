from __future__ import annotations

from typing import Any

import pytest

import crypto_alert_v2.notifications.rotation as rotation
from crypto_alert_v2.notifications.credentials import NotificationCredentialCipher
from crypto_alert_v2.notifications.rotation import CredentialRewrapBatch


@pytest.mark.asyncio
async def test_rotation_recovers_after_a_concurrent_cas_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batches = iter(
        (
            CredentialRewrapBatch(
                scanned_rows=1,
                rewrapped_rows=0,
                remaining_old_version_rows=1,
            ),
            CredentialRewrapBatch(
                scanned_rows=1,
                rewrapped_rows=1,
                remaining_old_version_rows=0,
            ),
        )
    )
    sleeps: list[float] = []

    async def count_remaining(*_args: Any, **_kwargs: Any) -> int:
        return 1

    async def rewrap_batch(*_args: Any, **_kwargs: Any) -> CredentialRewrapBatch:
        return next(batches)

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        rotation,
        "count_notification_credentials_outside_active_version",
        count_remaining,
    )
    monkeypatch.setattr(rotation, "rewrap_notification_credential_batch", rewrap_batch)
    monkeypatch.setattr(rotation.asyncio, "sleep", record_sleep)

    result = await rotation.rotate_notification_credentials(
        object(),  # type: ignore[arg-type]
        credential_cipher=NotificationCredentialCipher(
            key=b"n" * 32,
            key_version="v2",
        ),
        batch_size=1,
        max_batches=2,
    )

    assert result.batches == 2
    assert result.scanned_rows == 2
    assert result.rewrapped_rows == 1
    assert result.remaining_old_version_rows == 0
    assert sleeps == [0.05]


@pytest.mark.asyncio
async def test_rotation_validates_batch_size_before_reading_the_database() -> None:
    with pytest.raises(ValueError, match="batch_size must be between 1 and 1000"):
        await rotation.rotate_notification_credentials(
            object(),  # type: ignore[arg-type]
            credential_cipher=NotificationCredentialCipher(
                key=b"n" * 32,
                key_version="v2",
            ),
            batch_size=0,
        )
