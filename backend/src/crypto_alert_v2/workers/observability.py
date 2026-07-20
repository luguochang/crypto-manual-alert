from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.observability.verification import (
    ObservabilityVerificationRequest,
    ObservabilityVerificationResult,
    ObservabilityProvider,
)
from crypto_alert_v2.persistence.repositories import (
    ObservabilityDeliveryLease,
    ObservabilityDeliveryRepository,
)


class ObservabilityVerificationStore(Protocol):
    async def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> ObservabilityDeliveryLease | None: ...

    async def mark_verified(
        self,
        lease: ObservabilityDeliveryLease,
        *,
        provider_trace_id: str,
        now: datetime,
    ) -> bool: ...

    async def mark_retryable(
        self,
        lease: ObservabilityDeliveryLease,
        *,
        next_attempt_at: datetime,
        error_code: str,
        error_type: str | None,
        now: datetime,
    ) -> bool: ...

    async def mark_terminal(
        self,
        lease: ObservabilityDeliveryLease,
        *,
        error_code: str,
        error_type: str | None,
        now: datetime,
    ) -> bool: ...

    async def release_owned_leases(self, *, worker_id: str, now: datetime) -> None: ...


class HostedTraceVerifier(Protocol):
    async def verify(
        self,
        request: ObservabilityVerificationRequest,
    ) -> ObservabilityVerificationResult: ...


class SqlAlchemyObservabilityVerificationStore:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> ObservabilityDeliveryLease | None:
        async with self._session_factory() as session, session.begin():
            leases = await ObservabilityDeliveryRepository(session).lease_due(
                worker_id=worker_id,
                now=now,
                lease_seconds=lease_seconds,
                limit=1,
            )
            return leases[0] if leases else None

    async def mark_verified(
        self,
        lease: ObservabilityDeliveryLease,
        *,
        provider_trace_id: str,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            return await ObservabilityDeliveryRepository(session).mark_verified(
                delivery_id=lease.delivery_id,
                worker_id=lease.lease_owner,
                fence_token=lease.fence_token,
                provider_trace_id=provider_trace_id,
                now=now,
            )

    async def mark_retryable(
        self,
        lease: ObservabilityDeliveryLease,
        *,
        next_attempt_at: datetime,
        error_code: str,
        error_type: str | None,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            return await ObservabilityDeliveryRepository(session).mark_retryable(
                delivery_id=lease.delivery_id,
                worker_id=lease.lease_owner,
                fence_token=lease.fence_token,
                next_attempt_at=next_attempt_at,
                error_code=error_code,
                error_type=error_type,
                stage="hosted_query",
                now=now,
            )

    async def mark_terminal(
        self,
        lease: ObservabilityDeliveryLease,
        *,
        error_code: str,
        error_type: str | None,
        now: datetime,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            return await ObservabilityDeliveryRepository(session).mark_terminal(
                delivery_id=lease.delivery_id,
                worker_id=lease.lease_owner,
                fence_token=lease.fence_token,
                error_code=error_code,
                error_type=error_type,
                stage="hosted_query",
                now=now,
            )

    async def release_owned_leases(self, *, worker_id: str, now: datetime) -> None:
        async with self._session_factory() as session, session.begin():
            await ObservabilityDeliveryRepository(session).release_owned_leases(
                worker_id,
                now,
            )


class ObservabilityVerificationWorker:
    def __init__(
        self,
        *,
        store: ObservabilityVerificationStore,
        verifiers: Mapping[str, HostedTraceVerifier],
        worker_id: str,
        langsmith_project: str,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: int = 30,
        retry_seconds: float = 5.0,
        max_attempts: int = 30,
    ) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise ValueError("worker_id is required")
        if not langsmith_project.strip():
            raise ValueError("langsmith_project is required")
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be at least 3")
        if retry_seconds <= 0:
            raise ValueError("retry_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._store = store
        self._verifiers = dict(verifiers)
        self._worker_id = normalized_worker_id
        self._langsmith_project = langsmith_project.strip()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_seconds = lease_seconds
        self._retry_seconds = retry_seconds
        self._max_attempts = max_attempts

    async def dispatch_once(self) -> bool:
        lease = await self._store.claim_next(
            worker_id=self._worker_id,
            now=self._now(),
            lease_seconds=self._lease_seconds,
        )
        if lease is None:
            return False
        await self.execute(lease)
        return True

    async def execute(self, lease: ObservabilityDeliveryLease) -> bool:
        now = self._now()
        budget_error = self._budget_error(lease, now)
        if budget_error is not None:
            return await self._store.mark_terminal(
                lease,
                error_code=budget_error,
                error_type="VerificationBudgetExhausted",
                now=now,
            )
        if lease.event_type != "root_trace" or lease.event_version != 1:
            return await self._store.mark_terminal(
                lease,
                error_code="unsupported_observability_event",
                error_type="ConfigurationError",
                now=now,
            )
        verifier = self._verifiers.get(lease.provider)
        if verifier is None:
            return await self._store.mark_terminal(
                lease,
                error_code="hosted_verifier_not_configured",
                error_type="ConfigurationError",
                now=now,
            )
        try:
            request = ObservabilityVerificationRequest(
                provider=cast(ObservabilityProvider, lease.provider),
                provider_trace_id=lease.provider_trace_id,
                product_run_id=str(lease.run_id),
                correlation_id=lease.correlation_id,
                project_name=(
                    self._langsmith_project if lease.provider == "langsmith" else None
                ),
            )
            result = await verifier.verify(request)
        except asyncio.CancelledError:
            await asyncio.shield(
                self._retry(
                    lease,
                    code="worker_cancelled",
                    error_type="WorkerCancelled",
                    now=self._now(),
                )
            )
            raise
        except (TypeError, ValueError):
            return await self._store.mark_terminal(
                lease,
                error_code="hosted_verification_identity_invalid",
                error_type="ConfigurationError",
                now=self._now(),
            )
        except Exception:
            return await self._retry(
                lease,
                code="hosted_query_unexpected_failure",
                error_type="UnexpectedVerificationError",
                now=self._now(),
            )
        return await self._finish(lease, result)

    async def release_owned_leases(self) -> None:
        await self._store.release_owned_leases(
            worker_id=self._worker_id,
            now=self._now(),
        )

    async def _finish(
        self,
        lease: ObservabilityDeliveryLease,
        result: ObservabilityVerificationResult,
    ) -> bool:
        now = self._now()
        if result.result == "verified":
            if not result.provider_trace_id:
                return await self._store.mark_terminal(
                    lease,
                    error_code="hosted_verification_receipt_missing",
                    error_type="ProtocolError",
                    now=now,
                )
            return await self._store.mark_verified(
                lease,
                provider_trace_id=result.provider_trace_id,
                now=now,
            )
        if result.result == "terminal_failure":
            return await self._store.mark_terminal(
                lease,
                error_code=result.code,
                error_type=result.error_type,
                now=now,
            )
        budget_error = self._budget_error(lease, now)
        if budget_error is not None:
            return await self._store.mark_terminal(
                lease,
                error_code=budget_error,
                error_type=result.error_type or "VerificationBudgetExhausted",
                now=now,
            )
        return await self._retry(
            lease,
            code=result.code,
            error_type=result.error_type,
            now=now,
        )

    async def _retry(
        self,
        lease: ObservabilityDeliveryLease,
        *,
        code: str,
        error_type: str | None,
        now: datetime,
    ) -> bool:
        budget_error = self._budget_error(lease, now)
        if budget_error is not None:
            return await self._store.mark_terminal(
                lease,
                error_code=budget_error,
                error_type=error_type or "VerificationBudgetExhausted",
                now=now,
            )
        return await self._store.mark_retryable(
            lease,
            next_attempt_at=now + timedelta(seconds=self._retry_seconds),
            error_code=code,
            error_type=error_type,
            now=now,
        )

    def _budget_error(
        self,
        lease: ObservabilityDeliveryLease,
        now: datetime,
    ) -> str | None:
        if lease.verification_deadline is None:
            return "hosted_verification_deadline_missing"
        if now >= lease.verification_deadline:
            return "hosted_verification_deadline_exceeded"
        if lease.attempt_count >= self._max_attempts:
            return "hosted_verification_attempts_exhausted"
        return None

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("observability worker clock must be timezone-aware")
        return now


__all__ = [
    "ObservabilityVerificationStore",
    "ObservabilityVerificationWorker",
    "HostedTraceVerifier",
    "SqlAlchemyObservabilityVerificationStore",
]
