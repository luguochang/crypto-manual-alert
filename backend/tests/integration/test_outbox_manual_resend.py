from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from crypto_alert_v2.api.schemas import NotificationResendSubmission
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.notifications.adapters import (
    DeliveryResult,
    DeliveryUncertainError,
)
from crypto_alert_v2.persistence.models import (
    NotificationAttempt,
    NotificationOutbox,
    Tenant,
    User,
    Workspace,
)
from crypto_alert_v2.workers.notification import NotificationNotResendable, OutboxWorker
from tests.integration.test_notification_worker import (
    MutableClock,
    RecordingAdapter,
    _planned_notification,
)

pytest_plugins = ("tests.integration.test_outbox_idempotency",)


@pytest.mark.asyncio
async def test_manual_resend_appends_attempt_to_same_notification(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    adapter = RecordingAdapter(
        [
            DeliveryUncertainError("provider receipt was lost"),
            DeliveryResult.delivered(provider_receipt="manual-receipt"),
        ]
    )
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker",
        clock=clock,
    )

    assert await worker.dispatch_once() is True
    manual_lease = await worker.claim_manual_resend(
        notification.id,
        tenant_id=notification.tenant_id,
        workspace_id=notification.workspace_id,
        owner_user_id=notification.owner_user_id,
        requested_by="operator-user-id",
    )
    assert manual_lease.notification_id == notification.id
    assert manual_lease.trigger == "manual"
    assert await worker.execute(manual_lease) is True

    async with session_factory() as session:
        outbox_count = await session.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )
        attempts = list(
            (
                await session.scalars(
                    select(NotificationAttempt)
                    .where(NotificationAttempt.outbox_id == notification.id)
                    .order_by(NotificationAttempt.attempt_number)
                )
            ).all()
        )
    assert outbox_count == 1
    assert [attempt.trigger for attempt in attempts] == ["automatic", "manual"]
    assert attempts[1].requested_by == "operator-user-id"
    assert attempts[1].result == "delivered"


@pytest.mark.asyncio
async def test_manual_retryable_failure_never_reenters_automatic_queue(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    adapter = RecordingAdapter(
        [
            DeliveryUncertainError("provider receipt was lost"),
            DeliveryResult.retryable(reason="provider_unavailable"),
        ]
    )
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker",
        clock=clock,
    )

    assert await worker.dispatch_once() is True
    manual = await worker.claim_manual_resend(
        notification.id,
        tenant_id=notification.tenant_id,
        workspace_id=notification.workspace_id,
        owner_user_id=notification.owner_user_id,
        requested_by="operator-user-id",
    )
    assert await worker.execute(manual) is True
    assert await worker.dispatch_once() is False
    with pytest.raises(NotificationNotResendable):
        await worker.claim_manual_resend(
            notification.id,
            tenant_id=notification.tenant_id,
            workspace_id=notification.workspace_id,
            owner_user_id=notification.owner_user_id,
            requested_by="operator-user-id",
        )

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
    assert [attempt.trigger for attempt in attempts] == ["automatic", "manual"]
    assert attempts[-1].result == "failed_terminal"


@pytest.mark.asyncio
async def test_product_api_service_queues_manual_resend_for_worker_delivery(
    database_connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        database_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    clock = MutableClock()
    notification = await _planned_notification(session_factory, clock=clock)
    adapter = RecordingAdapter(
        [
            DeliveryUncertainError("provider receipt was lost"),
            DeliveryResult.delivered(provider_receipt="manual-receipt"),
        ]
    )
    worker = OutboxWorker(
        session_factory=session_factory,
        adapters={"bark": adapter},
        worker_id="notification-worker",
        clock=clock,
    )
    assert await worker.dispatch_once() is True

    async with session_factory() as session:
        tenant = await session.get(Tenant, notification.tenant_id)
        workspace = await session.get(Workspace, notification.workspace_id)
        user = await session.get(User, notification.owner_user_id)
    assert tenant is not None
    assert workspace is not None
    assert user is not None
    actor = ActorContext(
        tenant_id=tenant.external_id,
        workspace_id=workspace.external_id,
        user_id=user.external_subject,
        identity_issuer=user.identity_issuer,
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory, clock=clock)

    before = await service.list_notifications(actor, str(notification.task_id))
    assert before is not None
    assert before["items"][0]["status"] == "unknown"
    assert before["items"][0]["manual_resend_available"] is True

    queued = await service.request_notification_resend(
        actor,
        str(notification.id),
        NotificationResendSubmission(reason="User confirmed a single retry."),
    )
    assert queued is not None
    assert queued["manual_resend_pending"] is True
    assert queued["manual_resend_available"] is False

    assert await worker.dispatch_once() is True
    after = await service.list_notifications(actor, str(notification.task_id))
    assert after is not None
    assert after["items"][0]["status"] == "delivered"
    assert after["items"][0]["manual_resend_pending"] is False
    assert after["items"][0]["manual_resend_available"] is False
    assert [attempt["trigger"] for attempt in after["items"][0]["attempts"]] == [
        "automatic",
        "manual",
    ]
