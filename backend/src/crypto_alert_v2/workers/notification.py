from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import re
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.notifications.adapters import (
    DeliveryRequest,
    DeliveryResult,
    DeliveryUncertainError,
    NotificationAdapter,
    NotificationAdapterResolver,
)
from crypto_alert_v2.notifications.outbox import (
    NotificationNotResendable,
    NotificationRetryBudgetExhausted,
    request_manual_resend,
)
from crypto_alert_v2.persistence.models import NotificationAttempt, NotificationOutbox


AttemptTrigger = Literal["automatic", "manual"]

_SAFE_CODE = re.compile(r"[a-zA-Z0-9_.:-]{1,128}")
_SAFE_RECEIPT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}")


@dataclass(frozen=True, slots=True)
class NotificationLease:
    notification_id: UUID
    attempt_number: int
    owner: str
    fence_token: int
    lease_expires_at: datetime
    trigger: AttemptTrigger
    task_id: UUID
    run_id: UUID
    artifact_id: UUID
    decision_id: UUID
    channel: str
    notification_type: str
    decision_version: int
    payload: dict[str, Any]
    payload_hash: str
    requested_by: str | None
    tenant_id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    destination_id: UUID | None


class OutboxWorker:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        adapters: Mapping[str, NotificationAdapter],
        adapter_resolver: NotificationAdapterResolver | None = None,
        worker_id: str,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: int = 30,
        max_attempts: int = 5,
        retry_window_seconds: int = 86_400,
        base_backoff_seconds: int = 30,
        max_backoff_seconds: int = 3_600,
        send_timeout_seconds: float = 10.0,
    ) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise ValueError("worker_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if max_attempts != 5:
            raise ValueError("notification max_attempts is fixed at 5")
        if retry_window_seconds != 86_400:
            raise ValueError("notification retry window is fixed at 24 hours")
        if base_backoff_seconds < 1 or max_backoff_seconds < base_backoff_seconds:
            raise ValueError("notification backoff bounds are invalid")
        if send_timeout_seconds <= 0:
            raise ValueError("send_timeout_seconds must be positive")
        self._session_factory = session_factory
        self._adapters = {key.strip().lower(): value for key, value in adapters.items()}
        self._adapter_resolver = adapter_resolver
        self._worker_id = normalized_worker_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._retry_window = timedelta(seconds=retry_window_seconds)
        self._base_backoff_seconds = base_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._send_timeout_seconds = send_timeout_seconds

    async def dispatch_once(self) -> bool:
        lease = await self.claim_next()
        if lease is None:
            return False
        await self.execute(lease)
        return True

    async def claim_next(self) -> NotificationLease | None:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            await self._recover_expired_leases(session, now)
            await self._terminalize_expired_retry_windows(session, now)
            notification = await session.scalar(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.manual_resend_requested_at.is_not(None),
                    NotificationOutbox.status.in_(
                        ("unknown", "failed_retryable", "failed_terminal")
                    ),
                    NotificationOutbox.attempt_count < self._max_attempts,
                    NotificationOutbox.created_at > now - self._retry_window,
                )
                .order_by(
                    NotificationOutbox.manual_resend_requested_at,
                    NotificationOutbox.created_at,
                    NotificationOutbox.id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if notification is not None:
                return await self._claim_locked(
                    session,
                    notification,
                    now=now,
                    trigger="manual",
                    requested_by=notification.manual_resend_requested_by,
                )
            notification = await session.scalar(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status.in_(("planned", "failed_retryable")),
                    NotificationOutbox.manual_resend_requested_at.is_(None),
                    NotificationOutbox.available_at <= now,
                    NotificationOutbox.attempt_count < self._max_attempts,
                    NotificationOutbox.created_at > now - self._retry_window,
                )
                .order_by(
                    NotificationOutbox.available_at,
                    NotificationOutbox.created_at,
                    NotificationOutbox.id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if notification is None:
                return None
            return await self._claim_locked(
                session,
                notification,
                now=now,
                trigger="automatic",
                requested_by=None,
            )

    async def claim_manual_resend(
        self,
        notification_id: UUID,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_user_id: UUID,
        requested_by: str,
    ) -> NotificationLease:
        actor = _safe_requested_by(requested_by)
        now = self._now()
        async with self._session_factory() as session, session.begin():
            notification = await request_manual_resend(
                session,
                notification_id=notification_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
                requested_by=actor,
                reason="direct_worker_manual_resend",
                now=now,
            )
            if notification is None:
                raise NotificationNotResendable("notification was not found")
            return await self._claim_locked(
                session,
                notification,
                now=now,
                trigger="manual",
                requested_by=actor,
            )

    async def execute(self, lease: NotificationLease) -> bool:
        if not await self._mark_sending(lease):
            return False
        request = DeliveryRequest(
            notification_id=lease.notification_id,
            task_id=lease.task_id,
            run_id=lease.run_id,
            artifact_id=lease.artifact_id,
            decision_id=lease.decision_id,
            channel=lease.channel,
            notification_type=lease.notification_type,
            decision_version=lease.decision_version,
            payload=dict(lease.payload),
            payload_hash=lease.payload_hash,
            tenant_id=lease.tenant_id,
            workspace_id=lease.workspace_id,
            owner_user_id=lease.owner_user_id,
            destination_id=lease.destination_id,
        )
        try:
            adapter = (
                await self._adapter_resolver.resolve(request)
                if self._adapter_resolver is not None
                else self._adapters.get(lease.channel)
            )
            if adapter is None:
                result = DeliveryResult.terminal(reason="channel_not_configured")
            else:
                async with asyncio.timeout(self._send_timeout_seconds):
                    result = await adapter.send(request)
        except asyncio.CancelledError:
            await asyncio.shield(
                self._finish_uncertain(lease, reason="worker_cancelled_during_send")
            )
            raise
        except (DeliveryUncertainError, TimeoutError):
            await self._finish_uncertain(lease, reason="delivery_outcome_uncertain")
            return True
        except Exception as exc:
            result = DeliveryResult.retryable(
                reason=_safe_reason(f"adapter_{type(exc).__name__.lower()}")
            )
        return await self._finish_result(lease, result)

    async def release_owned_leases(self) -> None:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            notifications = list(
                (
                    await session.scalars(
                        select(NotificationOutbox)
                        .where(
                            NotificationOutbox.lease_owner == self._worker_id,
                            NotificationOutbox.status.in_(("leased", "sending")),
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for notification in notifications:
                attempt = await self._active_attempt(session, notification)
                if notification.status == "sending":
                    self._set_unknown(
                        notification,
                        attempt,
                        now=now,
                        reason="worker_shutdown_during_send",
                    )
                    continue
                self._release_without_send(notification, now=now)

    async def _claim_locked(
        self,
        session: AsyncSession,
        notification: NotificationOutbox,
        *,
        now: datetime,
        trigger: AttemptTrigger,
        requested_by: str | None,
    ) -> NotificationLease:
        attempt_number = notification.attempt_count + 1
        fence_token = notification.fence_token + 1
        lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        notification.status = "leased"
        notification.fence_token = fence_token
        notification.lease_owner = self._worker_id
        notification.lease_expires_at = lease_expires_at
        notification.terminal_at = None
        return NotificationLease(
            notification_id=notification.id,
            attempt_number=attempt_number,
            owner=self._worker_id,
            fence_token=fence_token,
            lease_expires_at=lease_expires_at,
            trigger=trigger,
            task_id=notification.task_id,
            run_id=notification.run_id,
            artifact_id=notification.artifact_id,
            decision_id=notification.decision_id,
            channel=notification.channel,
            notification_type=notification.type,
            decision_version=notification.decision_version,
            payload=dict(notification.payload),
            payload_hash=notification.payload_hash,
            requested_by=requested_by,
            tenant_id=notification.tenant_id,
            workspace_id=notification.workspace_id,
            owner_user_id=notification.owner_user_id,
            destination_id=notification.destination_id,
        )

    async def _mark_sending(self, lease: NotificationLease) -> bool:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            notification = await self._locked_lease(session, lease)
            if (
                notification is None
                or notification.status != "leased"
                or notification.lease_expires_at is None
                or notification.lease_expires_at <= now
                or notification.attempt_count + 1 != lease.attempt_number
                or notification.attempt_count >= self._max_attempts
                or notification.created_at <= now - self._retry_window
            ):
                return False
            attempt = NotificationAttempt(
                id=uuid4(),
                tenant_id=notification.tenant_id,
                workspace_id=notification.workspace_id,
                owner_user_id=notification.owner_user_id,
                task_id=notification.task_id,
                outbox_id=notification.id,
                attempt_number=lease.attempt_number,
                owner=lease.owner,
                fence_token=lease.fence_token,
                trigger=lease.trigger,
                requested_by=lease.requested_by,
                result="sending",
                created_at=now,
            )
            session.add(attempt)
            notification.attempt_count = lease.attempt_number
            notification.status = "sending"
            if lease.trigger == "manual":
                notification.manual_resend_requested_at = None
                notification.manual_resend_requested_by = None
                notification.manual_resend_reason = None
            await session.flush()
            return True

    async def _finish_uncertain(
        self,
        lease: NotificationLease,
        *,
        reason: str,
    ) -> bool:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            notification = await self._locked_lease(session, lease)
            if notification is None or notification.status != "sending":
                return False
            attempt = await self._active_attempt(session, notification)
            self._set_unknown(notification, attempt, now=now, reason=reason)
            return True

    async def _finish_result(
        self,
        lease: NotificationLease,
        result: DeliveryResult,
    ) -> bool:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            notification = await self._locked_lease(session, lease)
            if notification is None or notification.status != "sending":
                return False
            attempt = await self._active_attempt(session, notification)
            if attempt is None:
                return False
            cost_units = _nonnegative_cost(result.cost_units)
            attempt.cost_units = cost_units
            attempt.retry_after_seconds = _retry_after(result.retry_after_seconds)
            provider_receipt = _safe_receipt(result.provider_receipt)
            attempt.provider_receipt = provider_receipt
            attempt.finished_at = now

            if result.outcome == "delivered":
                if provider_receipt is None:
                    self._set_unknown(
                        notification,
                        attempt,
                        now=now,
                        reason="provider_receipt_missing_or_invalid",
                    )
                    return True
                attempt.result = "delivered"
                notification.status = "delivered"
                notification.delivered_at = now
                notification.terminal_at = now
                self._clear_lease(notification)
                return True

            reason = _safe_reason(result.reason or "delivery_failed")
            attempt.reason = reason
            attempt.error_code = reason
            if result.outcome == "terminal":
                attempt.result = "failed_terminal"
                notification.status = "failed_terminal"
                notification.terminal_at = now
                self._clear_lease(notification)
                return True

            if lease.trigger == "manual":
                attempt.result = "failed_terminal"
                notification.status = "failed_terminal"
                notification.terminal_at = now
                self._clear_lease(notification)
                return True

            retry_after = attempt.retry_after_seconds or 0
            exponential_delay = min(
                self._max_backoff_seconds,
                self._base_backoff_seconds
                * (2 ** max(0, notification.attempt_count - 1)),
            )
            delay_seconds = max(retry_after, exponential_delay)
            attempt.delay_seconds = delay_seconds
            retry_at = now + timedelta(seconds=delay_seconds)
            deadline = notification.created_at + self._retry_window
            if notification.attempt_count >= self._max_attempts or retry_at >= deadline:
                attempt.result = "failed_terminal"
                notification.status = "failed_terminal"
                notification.terminal_at = now
            else:
                attempt.result = "failed_retryable"
                notification.status = "failed_retryable"
                notification.available_at = retry_at
            self._clear_lease(notification)
            return True

    async def _recover_expired_leases(
        self,
        session: AsyncSession,
        now: datetime,
    ) -> None:
        notifications = list(
            (
                await session.scalars(
                    select(NotificationOutbox)
                    .where(
                        NotificationOutbox.status.in_(("leased", "sending")),
                        NotificationOutbox.lease_expires_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for notification in notifications:
            attempt = await self._active_attempt(session, notification)
            if notification.status == "sending":
                self._set_unknown(
                    notification,
                    attempt,
                    now=now,
                    reason="sending_lease_expired",
                )
                continue
            self._release_without_send(notification, now=now)

    async def _terminalize_expired_retry_windows(
        self,
        session: AsyncSession,
        now: datetime,
    ) -> None:
        notifications = list(
            (
                await session.scalars(
                    select(NotificationOutbox)
                    .where(
                        NotificationOutbox.status.in_(("planned", "failed_retryable")),
                        NotificationOutbox.created_at <= now - self._retry_window,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for notification in notifications:
            notification.status = "failed_terminal"
            notification.terminal_at = now
            self._clear_lease(notification)

    async def _locked_lease(
        self,
        session: AsyncSession,
        lease: NotificationLease,
    ) -> NotificationOutbox | None:
        return await session.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.id == lease.notification_id,
                NotificationOutbox.lease_owner == lease.owner,
                NotificationOutbox.fence_token == lease.fence_token,
            )
            .with_for_update()
        )

    async def _active_attempt(
        self,
        session: AsyncSession,
        notification: NotificationOutbox,
    ) -> NotificationAttempt | None:
        return await session.scalar(
            select(NotificationAttempt)
            .where(
                NotificationAttempt.outbox_id == notification.id,
                NotificationAttempt.attempt_number == notification.attempt_count,
                NotificationAttempt.owner == notification.lease_owner,
                NotificationAttempt.fence_token == notification.fence_token,
                NotificationAttempt.result.in_(("leased", "sending")),
            )
            .with_for_update()
        )

    def _release_without_send(
        self,
        notification: NotificationOutbox,
        *,
        now: datetime,
    ) -> None:
        if (
            notification.attempt_count >= self._max_attempts
            or notification.created_at <= now - self._retry_window
        ):
            notification.status = "failed_terminal"
            notification.terminal_at = now
        else:
            notification.status = "failed_retryable"
            notification.available_at = now
        self._clear_lease(notification)

    @staticmethod
    def _set_unknown(
        notification: NotificationOutbox,
        attempt: NotificationAttempt | None,
        *,
        now: datetime,
        reason: str,
    ) -> None:
        safe_reason = _safe_reason(reason)
        if attempt is not None:
            attempt.result = "unknown"
            attempt.reason = safe_reason
            attempt.error_code = safe_reason
            attempt.finished_at = now
        notification.status = "unknown"
        notification.terminal_at = now
        OutboxWorker._clear_lease(notification)

    @staticmethod
    def _clear_lease(notification: NotificationOutbox) -> None:
        notification.lease_owner = None
        notification.lease_expires_at = None

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("worker clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


def _safe_reason(value: str) -> str:
    if _SAFE_CODE.fullmatch(value):
        return value
    return "adapter_error"


def _safe_receipt(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not _SAFE_RECEIPT.fullmatch(normalized):
        return None
    return normalized


def _safe_requested_by(value: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise ValueError("requested_by is invalid")
    return normalized


def _retry_after(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 0:
        return None
    return min(value, 86_400)


def _nonnegative_cost(value: Decimal) -> Decimal:
    if value < 0:
        return Decimal("0")
    return value


__all__ = [
    "NotificationLease",
    "NotificationNotResendable",
    "NotificationRetryBudgetExhausted",
    "OutboxWorker",
]
