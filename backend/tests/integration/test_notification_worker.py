from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from crypto_alert_v2.notifications.adapters import (
    DeliveryRequest,
    DeliveryResult,
    DeliveryUncertainError,
)
from crypto_alert_v2.notifications.outbox import plan_notification
from crypto_alert_v2.persistence.models import NotificationAttempt, NotificationOutbox
from crypto_alert_v2.workers.notification import OutboxWorker
from tests.integration.test_outbox_idempotency import (
    notification_kwargs,
    seed_decision,
)


pytest_plugins = ("tests.integration.test_outbox_idempotency",)


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class RecordingAdapter:
    def __init__(self, results: list[DeliveryResult | BaseException]) -> None:
        self._results = iter(results)
        self.requests: list[DeliveryRequest] = []

    async def send(self, request: DeliveryRequest) -> DeliveryResult:
        self.requests.append(request)
        result = next(self._results)
        if isinstance(result, BaseException):
            raise result
        return result


class HangingAdapter:
    async def send(self, request: DeliveryRequest) -> DeliveryResult:
        del request
        await asyncio.Future()
        raise AssertionError("unreachable")


async def _planned_notification(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    clock: MutableClock,
) -> NotificationOutbox:
    decision = await seed_decision(session_factory)
    async with session_factory() as session, session.begin():
        plan = await plan_notification(
            session,
            **notification_kwargs(decision),
            payload={"task_id": str(decision.task_id), "action": "no_trade"},
            now=clock.now,
        )
    return plan.notification


@pytest.mark.asyncio
async def test_worker_claim_is_fenced_and_success_records_one_attempt(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    adapter = RecordingAdapter([DeliveryResult.delivered(provider_receipt="receipt-1")])
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker-1",
        clock=clock,
    )
    competitor = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker-2",
        clock=clock,
    )

    lease = await worker.claim_next()
    assert lease is not None
    assert lease.notification_id == notification.id
    assert lease.owner == "notification-worker-1"
    assert lease.fence_token == 1
    assert await competitor.claim_next() is None
    assert await worker.execute(lease) is True

    async with session_factory() as session:
        stored = await session.get(NotificationOutbox, notification.id)
        attempts = list(
            (
                await session.scalars(
                    select(NotificationAttempt).where(
                        NotificationAttempt.outbox_id == notification.id
                    )
                )
            ).all()
        )
    assert stored is not None
    assert stored.status == "delivered"
    assert stored.lease_owner is None
    assert len(attempts) == 1
    assert attempts[0].result == "delivered"
    assert attempts[0].owner == "notification-worker-1"
    assert adapter.requests[0].payload == {
        "action": "no_trade",
        "task_id": str(notification.task_id),
    }


@pytest.mark.asyncio
async def test_uncertain_delivery_becomes_unknown_and_is_never_auto_retried(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    adapter = RecordingAdapter([DeliveryUncertainError("response lost")])
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker",
        clock=clock,
    )

    assert await worker.dispatch_once() is True
    clock.now += timedelta(days=2)
    next_lease = await worker.claim_next()
    assert next_lease is None or next_lease.notification_id != notification.id
    if next_lease is not None:
        await worker.release_owned_leases()

    async with session_factory() as session:
        stored = await session.get(NotificationOutbox, notification.id)
        attempt_count = len(
            list(
                (
                    await session.scalars(
                        select(NotificationAttempt).where(
                            NotificationAttempt.outbox_id == notification.id
                        )
                    )
                ).all()
            )
        )
    assert stored is not None
    assert stored.status == "unknown"
    assert attempt_count == 1
    assert len(adapter.requests) == 1


@pytest.mark.asyncio
async def test_adapter_total_timeout_becomes_unknown_without_blocking_worker(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": HangingAdapter()},
        worker_id="notification-worker",
        clock=clock,
        send_timeout_seconds=0.01,
    )

    assert await asyncio.wait_for(worker.dispatch_once(), timeout=0.5) is True

    async with session_factory() as session:
        stored = await session.get(NotificationOutbox, notification.id)
        attempt = await session.scalar(
            select(NotificationAttempt).where(
                NotificationAttempt.outbox_id == notification.id
            )
        )
    assert stored is not None
    assert stored.status == "unknown"
    assert attempt is not None
    assert attempt.result == "unknown"
    assert attempt.error_code == "delivery_outcome_uncertain"


@pytest.mark.asyncio
async def test_retryable_delivery_stops_after_exactly_five_attempts(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    retryable = DeliveryResult.retryable(reason="provider_unavailable")
    adapter = RecordingAdapter([retryable, retryable, retryable, retryable, retryable])
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker",
        clock=clock,
    )

    for _ in range(5):
        assert await worker.dispatch_once() is True
        clock.now += timedelta(hours=1)
    assert await worker.dispatch_once() is False

    async with session_factory() as session:
        stored = await session.get(NotificationOutbox, notification.id)
        attempts = list(
            (
                await session.scalars(
                    select(NotificationAttempt)
                    .where(NotificationAttempt.outbox_id == notification.id)
                    .order_by(NotificationAttempt.attempt_number)
                )
            ).all()
        )
    assert stored is not None
    assert stored.status == "failed_terminal"
    assert stored.attempt_count == 5
    assert len(attempts) == 5
    assert all(attempt.result == "failed_retryable" for attempt in attempts[:-1])
    assert attempts[-1].result == "failed_terminal"


@pytest.mark.asyncio
async def test_pre_send_lease_releases_do_not_consume_delivery_budget(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    adapter = RecordingAdapter([DeliveryResult.delivered(provider_receipt="receipt-1")])
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker",
        clock=clock,
    )

    for _ in range(6):
        assert await worker.claim_next() is not None
        await worker.release_owned_leases()

    async with session_factory() as session:
        before_send = await session.get(NotificationOutbox, notification.id)
        attempt_count = await session.scalar(
            select(func.count())
            .select_from(NotificationAttempt)
            .where(NotificationAttempt.outbox_id == notification.id)
        )
    assert before_send is not None
    assert before_send.attempt_count == 0
    assert attempt_count == 0

    assert await worker.dispatch_once() is True
    async with session_factory() as session:
        delivered = await session.get(NotificationOutbox, notification.id)
    assert delivered is not None
    assert delivered.status == "delivered"
    assert delivered.attempt_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_receipt", [None, "receipt with spaces"])
async def test_delivered_without_safe_provider_receipt_becomes_unknown(
    database_connection: AsyncConnection,
    provider_receipt: str | None,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    adapter = RecordingAdapter(
        [DeliveryResult(outcome="delivered", provider_receipt=provider_receipt)]
    )
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker",
        clock=clock,
    )

    assert await worker.dispatch_once() is True
    assert await worker.dispatch_once() is False

    async with session_factory() as session:
        stored = await session.get(NotificationOutbox, notification.id)
        attempt = await session.scalar(
            select(NotificationAttempt).where(
                NotificationAttempt.outbox_id == notification.id
            )
        )
    assert stored is not None
    assert stored.status == "unknown"
    assert stored.delivered_at is None
    assert stored.terminal_at == clock.now
    assert attempt is not None
    assert attempt.result == "unknown"
    assert attempt.provider_receipt is None
    assert attempt.error_code == "provider_receipt_missing_or_invalid"
    assert len(adapter.requests) == 1


@pytest.mark.asyncio
async def test_replacement_worker_reconciles_expired_sending_lease_to_unknown(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    original = OutboxWorker(
        session_factory=session_factory,
        adapters={},
        worker_id="notification-worker-original",
        clock=clock,
        lease_seconds=30,
    )
    replacement = OutboxWorker(
        session_factory=session_factory,
        adapters={},
        worker_id="notification-worker-replacement",
        clock=clock,
        lease_seconds=30,
    )

    lease = await original.claim_next()
    assert lease is not None
    assert await original._mark_sending(lease) is True
    clock.now += timedelta(seconds=31)

    assert await replacement.claim_next() is None

    async with session_factory() as session:
        stored = await session.get(NotificationOutbox, notification.id)
        attempt = await session.scalar(
            select(NotificationAttempt).where(
                NotificationAttempt.outbox_id == notification.id
            )
        )
    assert stored is not None
    assert stored.status == "unknown"
    assert stored.lease_owner is None
    assert stored.lease_expires_at is None
    assert stored.attempt_count == 1
    assert stored.terminal_at == clock.now
    assert attempt is not None
    assert attempt.result == "unknown"
    assert attempt.error_code == "sending_lease_expired"
    assert attempt.finished_at == clock.now
