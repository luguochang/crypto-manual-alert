from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.domain.outcome import evaluate_outcome
from crypto_alert_v2.persistence.models import (
    ArtifactVersion,
    MemoryDeletionJob,
    MemoryEntry,
    OutcomeObservation,
    Task,
)


class ExchangeSnapshot(Protocol):
    raw_hash: str
    ticker: Any
    candles: tuple[Any, ...]


class ExchangeMarketProvider(Protocol):
    def fetch_snapshot(
        self, symbol: str, *, horizon: str | None = None, correlation_id: str | None = None
    ) -> ExchangeSnapshot: ...


class MemoryDeletionWorker:
    """Scrubs queued memory rows through the same lease pattern as lifecycle jobs."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        worker_id: str,
        lease_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        self._session_factory = session_factory
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("worker clock must be timezone-aware")
        return value

    async def _claim(self) -> UUID | None:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            job = (
                await session.scalars(
                    select(MemoryDeletionJob)
                    .where(
                        or_(
                            MemoryDeletionJob.status == "queued",
                            and_(
                                MemoryDeletionJob.status == "running",
                                or_(
                                    MemoryDeletionJob.lease_expires_at.is_(None),
                                    MemoryDeletionJob.lease_expires_at <= now,
                                ),
                            ),
                        ),
                        MemoryDeletionJob.available_at <= now,
                    )
                    .order_by(MemoryDeletionJob.requested_at, MemoryDeletionJob.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).first()
            if job is None:
                return None
            job.status = "running"
            job.lease_owner = self._worker_id
            job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            job.attempt += 1
            return job.id

    async def dispatch_once(self) -> bool:
        job_id = await self._claim()
        if job_id is None:
            return False
        now = self._now()
        async with self._session_factory() as session, session.begin():
            job = await session.scalar(
                select(MemoryDeletionJob).where(
                    MemoryDeletionJob.id == job_id,
                    MemoryDeletionJob.status == "running",
                    MemoryDeletionJob.lease_owner == self._worker_id,
                )
            )
            if job is None:
                return True
            memory = await session.scalar(
                select(MemoryEntry).where(MemoryEntry.id == job.memory_id).with_for_update()
            )
            if memory is not None:
                memory.enabled = False
                memory.content = {"deleted": True}
                memory.deleted_at = now
                memory.updated_at = now
            job.status = "succeeded"
            job.completed_at = now
            job.lease_owner = None
            job.lease_expires_at = None
            job.last_error = None
            job.updated_at = now
        return True

    async def release_owned_leases(self) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(MemoryDeletionJob)
                .where(
                    MemoryDeletionJob.status == "running",
                    MemoryDeletionJob.lease_owner == self._worker_id,
                )
                .values(
                    status="queued",
                    lease_owner=None,
                    lease_expires_at=None,
                    available_at=self._now(),
                )
            )


class OutcomeMaturationWorker:
    """Matures Product outcomes only from an injected exchange-native provider."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        provider: ExchangeMarketProvider | None,
        worker_id: str,
        lease_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        self._session_factory = session_factory
        self._provider = provider
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("worker clock must be timezone-aware")
        return value

    async def _claim(self) -> UUID | None:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            row = (
                await session.scalars(
                    select(OutcomeObservation)
                    .where(
                        OutcomeObservation.status.in_(("scheduled", "pending")),
                        OutcomeObservation.maturation_at <= now,
                        OutcomeObservation.available_at <= now,
                        or_(
                            OutcomeObservation.lease_expires_at.is_(None),
                            OutcomeObservation.lease_expires_at <= now,
                        ),
                    )
                    .order_by(OutcomeObservation.maturation_at, OutcomeObservation.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).first()
            if row is None:
                return None
            row.status = "pending"
            row.lease_owner = self._worker_id
            row.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            row.attempt += 1
            return row.id

    async def dispatch_once(self) -> bool:
        observation_id = await self._claim()
        if observation_id is None:
            return False
        if self._provider is None:
            await self._finish(observation_id, status="failed", error="exchange provider unavailable")
            return True
        try:
            async with self._session_factory() as session:
                row = (
                    await session.execute(
                        select(OutcomeObservation, Task, ArtifactVersion)
                        .join(Task, Task.id == OutcomeObservation.task_id)
                        .join(
                            ArtifactVersion,
                            ArtifactVersion.id == OutcomeObservation.artifact_version_id,
                        )
                        .where(
                            OutcomeObservation.id == observation_id,
                            OutcomeObservation.lease_owner == self._worker_id,
                        )
                    )
                ).one_or_none()
                if row is None:
                    return True
                observation, task, artifact_version = row
                symbol = task.request_payload.get("symbol")
                if not isinstance(symbol, str):
                    raise ValueError("outcome task has no symbol")
                snapshot = await asyncio.to_thread(
                    self._provider.fetch_snapshot,
                    symbol,
                    horizon=observation.horizon,
                    correlation_id=str(observation.id),
                )
                analysis = artifact_version.content.get("analysis", {})
                reference_price = Decimal(str(analysis.get("reference_price", "0")))
                if reference_price <= 0:
                    raise ValueError("artifact has no positive reference price")
                close_price = snapshot.ticker.last
                candles = list(snapshot.candles)
                high_price = max((c.high for c in candles), default=close_price)
                low_price = min((c.low for c in candles), default=close_price)
                predicted = observation.predicted_probability
                metrics = evaluate_outcome(
                    action=observation.action,
                    baseline=observation.baseline,
                    predicted_probability=float(predicted) if predicted is not None else None,
                    realized_label=float(close_price >= reference_price),
                    reference_price=reference_price,
                    close_price=close_price,
                    high_price=high_price,
                    low_price=low_price,
                    fees=observation.fees,
                    slippage=observation.slippage,
                    funding=observation.funding,
                )
                payload = metrics.model_dump(mode="json")
                payload["source"] = "exchange_native"
                payload["observed_at"] = self._now().isoformat()
                source_hash = hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode("utf-8")
                ).hexdigest()
            await self._finish(
                observation_id,
                status="matured",
                metrics=payload,
                realized_label=float(close_price >= reference_price),
                observed_at=self._now(),
                prices=(reference_price, close_price, high_price, low_price),
                source_hash=source_hash,
            )
        except Exception as exc:
            await self._finish(observation_id, status="failed", error=type(exc).__name__)
        return True

    async def _finish(
        self,
        observation_id: UUID,
        *,
        status: str,
        error: str | None = None,
        metrics: dict[str, Any] | None = None,
        realized_label: float | None = None,
        observed_at: datetime | None = None,
        prices: tuple[Decimal, Decimal, Decimal, Decimal] | None = None,
        source_hash: str | None = None,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(OutcomeObservation)
                .where(
                    OutcomeObservation.id == observation_id,
                    OutcomeObservation.lease_owner == self._worker_id,
                )
                .with_for_update()
            )
            if row is None:
                return
            row.status = status
            row.metrics = metrics
            row.realized_label = realized_label
            row.observed_at = observed_at
            row.source_hash = source_hash
            if prices is not None:
                row.reference_price, row.close_price, row.high_price, row.low_price = prices
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = self._now()
            if error:
                row.metrics = {"error": error}

    async def release_owned_leases(self) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(OutcomeObservation)
                .where(
                    OutcomeObservation.status == "pending",
                    OutcomeObservation.lease_owner == self._worker_id,
                )
                .values(
                    status="scheduled",
                    lease_owner=None,
                    lease_expires_at=None,
                    available_at=self._now(),
                )
            )


__all__ = ["MemoryDeletionWorker", "OutcomeMaturationWorker", "ExchangeMarketProvider"]
