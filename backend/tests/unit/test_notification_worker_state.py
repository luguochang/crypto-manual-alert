from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from crypto_alert_v2.notifications.adapters import DeliveryResult
from crypto_alert_v2.workers.notification import NotificationLease, OutboxWorker


class _AsyncContext:
    def __init__(self, value: object = None) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *_: object) -> None:
        return None


class _Session(_AsyncContext):
    def __init__(self) -> None:
        super().__init__(self)

    def begin(self) -> _AsyncContext:
        return _AsyncContext()


def _worker(now: datetime) -> OutboxWorker:
    return OutboxWorker(
        session_factory=_Session,
        adapters={},
        worker_id="notification-worker",
        clock=lambda: now,
    )


def _lease(now: datetime) -> NotificationLease:
    return NotificationLease(
        notification_id=uuid4(),
        attempt_number=1,
        owner="notification-worker",
        fence_token=1,
        lease_expires_at=now + timedelta(seconds=30),
        trigger="automatic",
        task_id=uuid4(),
        run_id=uuid4(),
        artifact_id=uuid4(),
        decision_id=uuid4(),
        channel="bark",
        notification_type="analysis_completed",
        decision_version=1,
        payload={"action": "no_trade"},
        payload_hash="a" * 64,
        requested_by=None,
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
        destination_id=uuid4(),
    )


def _notification() -> SimpleNamespace:
    return SimpleNamespace(
        status="sending",
        delivered_at=None,
        terminal_at=None,
        lease_owner="notification-worker",
        lease_expires_at=None,
    )


def _attempt() -> SimpleNamespace:
    return SimpleNamespace(
        result="sending",
        reason=None,
        error_code=None,
        cost_units=Decimal("0"),
        retry_after_seconds=None,
        provider_receipt=None,
        finished_at=None,
    )


def _bind_loaded_state(
    worker: OutboxWorker,
    notification: SimpleNamespace,
    attempt: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def locked_lease(_: object, __: NotificationLease) -> SimpleNamespace:
        return notification

    async def active_attempt(_: object, __: SimpleNamespace) -> SimpleNamespace:
        return attempt

    monkeypatch.setattr(worker, "_locked_lease", locked_lease)
    monkeypatch.setattr(worker, "_active_attempt", active_attempt)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_receipt", [None, "receipt with spaces"])
async def test_delivered_result_without_safe_receipt_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
    provider_receipt: str | None,
) -> None:
    now = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)
    worker = _worker(now)
    notification = _notification()
    attempt = _attempt()
    _bind_loaded_state(worker, notification, attempt, monkeypatch)

    handled = await worker._finish_result(
        _lease(now),
        DeliveryResult(outcome="delivered", provider_receipt=provider_receipt),
    )

    assert handled is True
    assert notification.status == "unknown"
    assert notification.delivered_at is None
    assert notification.terminal_at == now
    assert notification.lease_owner is None
    assert attempt.result == "unknown"
    assert attempt.provider_receipt is None
    assert attempt.error_code == "provider_receipt_missing_or_invalid"
    assert attempt.finished_at == now


@pytest.mark.asyncio
async def test_delivered_result_with_safe_receipt_is_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)
    worker = _worker(now)
    notification = _notification()
    attempt = _attempt()
    _bind_loaded_state(worker, notification, attempt, monkeypatch)

    handled = await worker._finish_result(
        _lease(now),
        DeliveryResult.delivered(provider_receipt="bark:1721203200"),
    )

    assert handled is True
    assert notification.status == "delivered"
    assert notification.delivered_at == now
    assert notification.terminal_at == now
    assert notification.lease_owner is None
    assert attempt.result == "delivered"
    assert attempt.provider_receipt == "bark:1721203200"
    assert attempt.error_code is None
    assert attempt.finished_at == now
