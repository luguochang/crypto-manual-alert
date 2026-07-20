from __future__ import annotations

from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.notifications.adapters import (
    BarkNotificationAdapter,
    DeliveryRequest,
    NotificationAdapter,
    NotificationAdapterResolver,
)
from crypto_alert_v2.notifications.credentials import NotificationCredentialCipher
from crypto_alert_v2.persistence.models import NotificationDestination
from crypto_alert_v2.testing.failure_injection import FailureInjectionController


class DatabaseNotificationAdapterResolver(NotificationAdapterResolver):
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        credential_cipher: NotificationCredentialCipher,
        http_client: httpx.AsyncClient,
        failure_injection: FailureInjectionController | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._credential_cipher = credential_cipher
        self._http_client = http_client
        self._failure_injection = failure_injection

    async def resolve(self, request: DeliveryRequest) -> NotificationAdapter | None:
        if (
            request.destination_id is None
            or request.tenant_id is None
            or request.workspace_id is None
            or request.owner_user_id is None
        ):
            return None
        async with self._session_factory() as session:
            destination = await session.scalar(
                select(NotificationDestination).where(
                    NotificationDestination.id == request.destination_id,
                    NotificationDestination.tenant_id == request.tenant_id,
                    NotificationDestination.workspace_id == request.workspace_id,
                    NotificationDestination.owner_user_id == request.owner_user_id,
                    NotificationDestination.channel == request.channel,
                    NotificationDestination.status == "enabled",
                )
            )
        if destination is None:
            return None
        credential = self._credential_cipher.decrypt(
            destination.credential_ciphertext,
            destination_id=destination.id,
            tenant_id=destination.tenant_id,
            workspace_id=destination.workspace_id,
            owner_user_id=destination.owner_user_id,
            channel=destination.channel,
            key_version=destination.credential_key_version,
        )
        if destination.channel == "bark":
            return BarkNotificationAdapter(
                device_key=credential,
                client=self._http_client,
                failure_injection=self._failure_injection,
            )
        return None


__all__ = ["DatabaseNotificationAdapterResolver"]
