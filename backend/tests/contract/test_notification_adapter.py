from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from crypto_alert_v2.notifications.adapters import (
    BarkNotificationAdapter,
    DeliveryUncertainError,
    DeliveryRequest,
)


@pytest.mark.asyncio
async def test_bark_uses_fixed_push_endpoint_without_credential_in_url() -> None:
    device_key = "test-device-key-must-not-appear-in-url"
    observed: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            headers={"X-Request-ID": "receipt-1"},
            json={"code": 200, "timestamp": 1784160000},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = BarkNotificationAdapter(
            device_key=SecretStr(device_key),
            client=client,
            base_url="https://api.day.app",
        )
        result = await adapter.send(
            DeliveryRequest(
                notification_id=uuid4(),
                task_id=uuid4(),
                run_id=uuid4(),
                artifact_id=uuid4(),
                decision_id=uuid4(),
                channel="bark",
                notification_type="analysis_completed",
                decision_version=1,
                payload={"title": "Analysis ready", "body": "No trade"},
                payload_hash="0" * 64,
            )
        )

    assert result.outcome == "delivered"
    assert result.provider_receipt == "receipt-1"
    assert len(observed) == 1
    assert str(observed[0].url) == "https://api.day.app/push"
    assert device_key not in str(observed[0].url)
    assert json.loads(observed[0].content) == {
        "body": "No trade",
        "device_key": device_key,
        "group": "crypto-alert-v2",
        "isArchive": "1",
        "title": "Analysis ready",
    }


def _request() -> DeliveryRequest:
    return DeliveryRequest(
        notification_id=uuid4(),
        task_id=uuid4(),
        run_id=uuid4(),
        artifact_id=uuid4(),
        decision_id=uuid4(),
        channel="bark",
        notification_type="analysis_completed",
        decision_version=1,
        payload={"body": "No trade"},
        payload_hash="0" * 64,
    )


@pytest.mark.asyncio
async def test_bark_http_success_with_business_rejection_is_terminal() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"code": 400})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = BarkNotificationAdapter(
            device_key=SecretStr("test-device-key"),
            client=client,
        )
        result = await adapter.send(_request())

    assert result.outcome == "terminal"
    assert result.reason == "bark_code_400"


@pytest.mark.asyncio
async def test_bark_success_without_verifiable_receipt_is_unknown() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"code": 200})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = BarkNotificationAdapter(
            device_key=SecretStr("test-device-key"),
            client=client,
        )
        with pytest.raises(DeliveryUncertainError, match="bark_receipt_missing"):
            await adapter.send(_request())


@pytest.mark.asyncio
async def test_bark_connection_timeout_is_retryable() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect failed", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = BarkNotificationAdapter(
            device_key=SecretStr("test-device-key"),
            client=client,
        )
        result = await adapter.send(_request())

    assert result.outcome == "retryable"
    assert result.reason == "bark_connection_timeout"


@pytest.mark.asyncio
async def test_bark_http_date_retry_after_is_respected() -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)

    async def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            request=request,
            headers={"Retry-After": "Thu, 16 Jul 2026 10:00:00 GMT"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = BarkNotificationAdapter(
            device_key=SecretStr("test-device-key"),
            client=client,
            clock=lambda: now,
        )
        result = await adapter.send(_request())

    assert result.outcome == "retryable"
    assert result.retry_after_seconds == 7200
