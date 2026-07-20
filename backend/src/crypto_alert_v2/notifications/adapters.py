from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from crypto_alert_v2.testing.failure_injection import (
    FailureInjectionController,
    FailureInjectionScenario,
)


DeliveryOutcome = Literal["delivered", "retryable", "terminal"]


@dataclass(frozen=True, slots=True)
class DeliveryRequest:
    notification_id: UUID
    task_id: UUID
    run_id: UUID
    artifact_id: UUID
    decision_id: UUID
    channel: str
    notification_type: str
    decision_version: int
    payload: dict[str, Any]
    payload_hash: str
    tenant_id: UUID | None = None
    workspace_id: UUID | None = None
    owner_user_id: UUID | None = None
    destination_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    outcome: DeliveryOutcome
    reason: str | None = None
    retry_after_seconds: int | None = None
    cost_units: Decimal = Decimal("0")
    provider_receipt: str | None = None

    @classmethod
    def delivered(
        cls,
        *,
        provider_receipt: str,
        cost_units: Decimal = Decimal("0"),
    ) -> "DeliveryResult":
        return cls(
            outcome="delivered",
            provider_receipt=provider_receipt,
            cost_units=cost_units,
        )

    @classmethod
    def retryable(
        cls,
        *,
        reason: str,
        retry_after_seconds: int | None = None,
        cost_units: Decimal = Decimal("0"),
    ) -> "DeliveryResult":
        return cls(
            outcome="retryable",
            reason=reason,
            retry_after_seconds=retry_after_seconds,
            cost_units=cost_units,
        )

    @classmethod
    def terminal(
        cls,
        *,
        reason: str,
        cost_units: Decimal = Decimal("0"),
    ) -> "DeliveryResult":
        return cls(outcome="terminal", reason=reason, cost_units=cost_units)


class DeliveryUncertainError(RuntimeError):
    """The provider may have accepted a request for which no receipt was observed."""


class NotificationAdapter(Protocol):
    async def send(self, request: DeliveryRequest) -> DeliveryResult: ...


class NotificationAdapterResolver(Protocol):
    async def resolve(self, request: DeliveryRequest) -> NotificationAdapter | None: ...


class _BarkResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: int
    timestamp: int | str | None = None


class BarkNotificationAdapter:
    """Bark transport with the device credential held only as a SecretStr."""

    __slots__ = (
        "_base_url",
        "_client",
        "_clock",
        "_device_key",
        "_failure_injection",
    )

    def __init__(
        self,
        *,
        device_key: SecretStr,
        client: httpx.AsyncClient,
        base_url: str = "https://api.day.app",
        clock: Callable[[], datetime] | None = None,
        failure_injection: FailureInjectionController | None = None,
    ) -> None:
        if not device_key.get_secret_value().strip():
            raise ValueError("Bark device key is required")
        self._device_key = device_key
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._failure_injection = failure_injection

    async def send(self, request: DeliveryRequest) -> DeliveryResult:
        if (
            self._failure_injection is not None
            and self._failure_injection.snapshot().scenario
            is FailureInjectionScenario.NOTIFICATION_FAILURE
        ):
            return DeliveryResult.retryable(reason="injected_notification_failure")
        title = _payload_text(request.payload, "title", default="Crypto analysis")
        body = _payload_text(
            request.payload,
            "body",
            default=_payload_text(
                request.payload, "action", default="Analysis complete"
            ),
        )
        endpoint = f"{self._base_url}/push"
        try:
            response = await self._client.post(
                endpoint,
                json={
                    "device_key": self._device_key.get_secret_value(),
                    "title": title,
                    "body": body,
                    "group": "crypto-alert-v2",
                    "isArchive": "1",
                },
            )
        except (httpx.ConnectTimeout, httpx.PoolTimeout):
            return DeliveryResult.retryable(reason="bark_connection_timeout")
        except (httpx.ReadTimeout, httpx.WriteTimeout):
            raise DeliveryUncertainError("bark_delivery_uncertain") from None
        except httpx.TimeoutException:
            raise DeliveryUncertainError("bark_delivery_uncertain") from None
        except httpx.TransportError:
            return DeliveryResult.retryable(reason="bark_transport_error")

        retry_after = _retry_after_seconds(
            response.headers.get("Retry-After"),
            now=self._now(),
        )
        if response.status_code == 429 or response.status_code >= 500:
            return DeliveryResult.retryable(
                reason=f"bark_http_{response.status_code}",
                retry_after_seconds=retry_after,
            )
        if not 200 <= response.status_code < 300:
            return DeliveryResult.terminal(reason=f"bark_http_{response.status_code}")

        try:
            body = _BarkResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            raise DeliveryUncertainError("bark_response_invalid") from None
        if body.code == 429 or body.code >= 500:
            return DeliveryResult.retryable(
                reason=f"bark_code_{body.code}",
                retry_after_seconds=retry_after,
            )
        if body.code != 200:
            return DeliveryResult.terminal(reason=f"bark_code_{body.code}")

        receipt = response.headers.get("X-Request-ID") or _bark_timestamp_receipt(
            body.timestamp
        )
        if receipt is None:
            raise DeliveryUncertainError("bark_receipt_missing")
        return DeliveryResult.delivered(provider_receipt=receipt)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Bark adapter clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


def _payload_text(payload: dict[str, Any], key: str, *, default: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return default
    return value.strip()[:1000]


def _bark_timestamp_receipt(value: int | str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized.isdigit() or len(normalized) > 20:
        return None
    return f"bark:{normalized}"


def _retry_after_seconds(value: str | None, *, now: datetime) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None or retry_at.utcoffset() is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        parsed = max(0, int((retry_at.astimezone(UTC) - now).total_seconds()))
    return max(0, min(parsed, 86_400))


__all__ = [
    "BarkNotificationAdapter",
    "DeliveryOutcome",
    "DeliveryRequest",
    "DeliveryResult",
    "DeliveryUncertainError",
    "NotificationAdapter",
    "NotificationAdapterResolver",
]
