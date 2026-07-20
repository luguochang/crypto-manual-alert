from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.lifecycle.service import (
    DATA_LIFECYCLE_EXTERNAL_SYSTEMS,
    DATA_LIFECYCLE_SYSTEMS,
    LifecycleService,
    delete_actor_product_rows,
)
from crypto_alert_v2.persistence.models import (
    DataDeletionJob,
    DataExportJob,
    DataLifecyclePolicy,
)


class LifecycleWorker:
    """Durable Product worker for local export and explicitly external deletion."""

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
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self._session_factory = session_factory
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._service = LifecycleService(session_factory=session_factory, clock=self._clock)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("lifecycle worker clock must be timezone-aware")
        return now

    async def _claim(self, model: Any) -> UUID | None:
        now = self._now()
        lease_until = now + timedelta(seconds=self._lease_seconds)
        async with self._session_factory() as session, session.begin():
            statement = (
                select(model)
                .where(
                    model.available_at <= now,
                    or_(
                        model.status == "queued",
                        and_(
                            model.status == "running",
                            or_(
                                model.lease_expires_at.is_(None),
                                model.lease_expires_at <= now,
                            ),
                        ),
                    ),
                )
                .order_by(model.requested_at, model.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = (await session.scalars(statement)).first()
            if job is None:
                return None
            job.status = "running"
            job.lease_owner = self._worker_id
            job.lease_expires_at = lease_until
            job.attempt += 1
            return job.id

    async def _process_export(self, job_id: UUID) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                job = await session.scalar(
                    select(DataExportJob).where(
                        DataExportJob.id == job_id,
                        DataExportJob.status == "running",
                        DataExportJob.lease_owner == self._worker_id,
                    )
                )
                if job is None:
                    return
                bundle, manifest, manifest_hash, _ = await self._service.build_export_payload(
                    session, job
                )
                now = self._now()
                job.status = "succeeded"
                job.lease_owner = None
                job.lease_expires_at = None
                job.completed_at = now
                job.expired_at = now + timedelta(days=7)
                job.manifest_version = manifest["manifest_version"]
                job.manifest = manifest
                job.manifest_hash = manifest_hash
                job.bundle = bundle
                job.last_error = None
                job.updated_at = now
        except Exception as exc:
            async with self._session_factory() as session, session.begin():
                await session.execute(
                    update(DataExportJob)
                    .where(
                        DataExportJob.id == job_id,
                        DataExportJob.status == "running",
                        DataExportJob.lease_owner == self._worker_id,
                    )
                    .values(
                        status="failed",
                        lease_owner=None,
                        lease_expires_at=None,
                        last_error=f"{type(exc).__name__}: lifecycle export failed"[:500],
                        updated_at=self._now(),
                    )
                )

    async def _process_deletion(self, job_id: UUID) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                job = await session.scalar(
                    select(DataDeletionJob).where(
                        DataDeletionJob.id == job_id,
                        DataDeletionJob.status == "running",
                        DataDeletionJob.lease_owner == self._worker_id,
                    )
                )
                if job is None:
                    return
                policy = await session.scalar(
                    select(DataLifecyclePolicy).where(
                        DataLifecyclePolicy.tenant_id == job.tenant_id,
                        DataLifecyclePolicy.workspace_id == job.workspace_id,
                        DataLifecyclePolicy.owner_user_id == job.owner_user_id,
                    )
                )
                now = self._now()
                if policy is not None and policy.legal_hold_active:
                    job.status = "blocked_legal_hold"
                    job.legal_hold_active = True
                    job.legal_hold_reason = policy.legal_hold_reason
                    job.system_status = {
                        system: "blocked_legal_hold" for system in DATA_LIFECYCLE_SYSTEMS
                    }
                    job.lease_owner = None
                    job.lease_expires_at = None
                    job.updated_at = now
                    return

                await delete_actor_product_rows(
                    session,
                    tenant_id=job.tenant_id,
                    workspace_id=job.workspace_id,
                    owner_user_id=job.owner_user_id,
                )
                # Keep the auditable job row, but scrub previously generated
                # bundles because an export is itself user data.
                await session.execute(
                    update(DataExportJob)
                    .where(
                        DataExportJob.tenant_id == job.tenant_id,
                        DataExportJob.workspace_id == job.workspace_id,
                        DataExportJob.owner_user_id == job.owner_user_id,
                    )
                    .values(
                        bundle={"deleted": True, "reason": "user_data_deletion"},
                        expired_at=now,
                        updated_at=now,
                    )
                )
                job.status = "pending_external"
                job.system_status = {
                    "product_db": "succeeded",
                    **{
                        system: "pending_external"
                        for system in DATA_LIFECYCLE_EXTERNAL_SYSTEMS
                    },
                }
                job.external_deletion_reference = {
                    system: None for system in DATA_LIFECYCLE_EXTERNAL_SYSTEMS
                }
                job.last_error = "external deletion adapters are not configured"
                job.lease_owner = None
                job.lease_expires_at = None
                job.updated_at = now
        except Exception as exc:
            async with self._session_factory() as session, session.begin():
                await session.execute(
                    update(DataDeletionJob)
                    .where(
                        DataDeletionJob.id == job_id,
                        DataDeletionJob.status == "running",
                        DataDeletionJob.lease_owner == self._worker_id,
                    )
                    .values(
                        status="failed",
                        lease_owner=None,
                        lease_expires_at=None,
                        last_error=f"{type(exc).__name__}: lifecycle deletion failed"[:500],
                        updated_at=self._now(),
                    )
                )

    async def dispatch_once(self) -> bool:
        export_id = await self._claim(DataExportJob)
        if export_id is not None:
            await self._process_export(export_id)
            return True
        deletion_id = await self._claim(DataDeletionJob)
        if deletion_id is not None:
            await self._process_deletion(deletion_id)
            return True
        return False

    async def release_owned_leases(self) -> None:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            for model in (DataExportJob, DataDeletionJob):
                await session.execute(
                    update(model)
                    .where(
                        model.status == "running",
                        model.lease_owner == self._worker_id,
                    )
                    .values(
                        status="queued",
                        lease_owner=None,
                        lease_expires_at=None,
                        available_at=now,
                        updated_at=now,
                    )
                )


__all__ = ["LifecycleWorker"]
