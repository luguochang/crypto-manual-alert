from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.lifecycle.service import (
    DATA_LIFECYCLE_EXTERNAL_SYSTEMS,
    DATA_LIFECYCLE_SYSTEMS,
    LifecycleService,
    count_actor_product_rows,
    delete_actor_product_rows,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.lifecycle.adapters import (
    LifecycleAdapterResult,
    LifecycleSystemAdapter,
)
from crypto_alert_v2.persistence.models import (
    DataDeletionReceipt,
    DataDeletionJob,
    DataExportJob,
    DataLifecyclePolicy,
    Membership,
    Tenant,
    User,
    Workspace,
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
        deletion_adapters: Sequence[LifecycleSystemAdapter] = (),
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
        adapters = {adapter.system: adapter for adapter in deletion_adapters}
        if len(adapters) != len(deletion_adapters):
            raise ValueError("lifecycle deletion adapters must have unique systems")
        if any(system in {"logs", "backups"} for system in adapters):
            raise ValueError("logs and backups are owned by retention receipts")
        self._deletion_adapters = adapters

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

    async def _actor_for_job(
        self, session: AsyncSession, job: DataDeletionJob
    ) -> ActorContext:
        row = (
            await session.execute(
                select(
                    Tenant.external_id,
                    Workspace.external_id,
                    User.identity_issuer,
                    User.external_subject,
                    Membership.id,
                    Membership.role,
                    Membership.permissions,
                )
                .select_from(Membership)
                .join(Tenant, Tenant.id == Membership.tenant_id)
                .join(Workspace, Workspace.id == Membership.workspace_id)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.tenant_id == job.tenant_id,
                    Membership.workspace_id == job.workspace_id,
                    Membership.user_id == job.owner_user_id,
                )
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("lifecycle actor membership is missing")
        return ActorContext(
            tenant_id=row[0],
            workspace_id=row[1],
            identity_issuer=row[2],
            user_id=row[3],
            context_id=row[4],
            roles=(row[5],),
            permissions=tuple(row[6]),
        )

    async def _append_receipt(
        self,
        session: AsyncSession,
        *,
        job: DataDeletionJob,
        system: str,
        phase: str,
        result: LifecycleAdapterResult,
        observed_at: datetime,
    ) -> str:
        existing = await session.scalar(
            select(DataDeletionReceipt).where(
                DataDeletionReceipt.deletion_job_id == job.id,
                DataDeletionReceipt.system == system,
                DataDeletionReceipt.phase == phase,
                DataDeletionReceipt.attempt == job.attempt,
            )
        )
        if existing is not None:
            return existing.receipt_hash
        payload = {
            "deletion_job_id": str(job.id),
            "tenant_id": str(job.tenant_id),
            "workspace_id": str(job.workspace_id),
            "owner_user_id": str(job.owner_user_id),
            "system": system,
            "phase": phase,
            "attempt": job.attempt,
            "outcome": result.outcome,
            "affected_count": result.affected_count,
            "survivor_count": result.survivor_count,
            "observed_at": observed_at.isoformat(),
            "reference": result.reference,
            "evidence": result.evidence,
        }
        receipt_hash = sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        session.add(
            DataDeletionReceipt(
                id=uuid4(),
                deletion_job_id=job.id,
                tenant_id=job.tenant_id,
                workspace_id=job.workspace_id,
                owner_user_id=job.owner_user_id,
                system=system,
                phase=phase,
                attempt=job.attempt,
                outcome=result.outcome,
                affected_count=result.affected_count,
                survivor_count=result.survivor_count,
                observed_at=observed_at,
                reference=result.reference,
                evidence=result.evidence,
                receipt_hash=receipt_hash,
            )
        )
        return receipt_hash

    @staticmethod
    def _system_outcome(
        deletion: LifecycleAdapterResult, scan: LifecycleAdapterResult
    ) -> str:
        if deletion.outcome == "failed" or scan.outcome == "failed":
            return "failed"
        if deletion.outcome in {"pending_external", "pending_expiry"}:
            return deletion.outcome
        if scan.outcome in {"pending_external", "pending_expiry"}:
            return scan.outcome
        if deletion.outcome == "not_applicable" and scan.outcome == "not_applicable":
            return "not_applicable"
        return "succeeded"

    async def _record_adapter_result(
        self,
        *,
        job_id: UUID,
        system: str,
        deletion: LifecycleAdapterResult,
        scan: LifecycleAdapterResult,
        delete_phase: str = "delete",
    ) -> None:
        now = self._now()
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
            delete_hash = await self._append_receipt(
                session,
                job=job,
                system=system,
                phase=delete_phase,
                result=deletion,
                observed_at=now,
            )
            scan_hash = await self._append_receipt(
                session,
                job=job,
                system=system,
                phase="survivor_scan",
                result=scan,
                observed_at=now,
            )
            system_status = dict(job.system_status)
            system_status[system] = self._system_outcome(deletion, scan)
            job.system_status = system_status
            references = dict(job.external_deletion_reference)
            references[system] = {
                "delete_receipt_hash": delete_hash,
                "survivor_scan_receipt_hash": scan_hash,
            }
            job.external_deletion_reference = references
            job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            job.updated_at = now

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

                actor = await self._actor_for_job(session, job)
                deleted_count = await delete_actor_product_rows(
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
                product_survivors = await count_actor_product_rows(
                    session,
                    tenant_id=job.tenant_id,
                    workspace_id=job.workspace_id,
                    owner_user_id=job.owner_user_id,
                )
                product_delete = LifecycleAdapterResult(
                    outcome="succeeded",
                    affected_count=deleted_count,
                    evidence={"owner": "product_postgresql"},
                )
                product_scan = LifecycleAdapterResult(
                    outcome="succeeded" if product_survivors == 0 else "failed",
                    survivor_count=product_survivors,
                    evidence={"scan": "actor_scoped_tables"},
                )
                product_delete_hash = await self._append_receipt(
                    session,
                    job=job,
                    system="product_db",
                    phase="delete",
                    result=product_delete,
                    observed_at=now,
                )
                product_scan_hash = await self._append_receipt(
                    session,
                    job=job,
                    system="product_db",
                    phase="survivor_scan",
                    result=product_scan,
                    observed_at=now,
                )
                job.system_status = {
                    "product_db": self._system_outcome(product_delete, product_scan),
                    **{
                        system: "pending"
                        for system in DATA_LIFECYCLE_EXTERNAL_SYSTEMS
                    },
                }
                job.external_deletion_reference = {
                    "product_db": {
                        "delete_receipt_hash": product_delete_hash,
                        "survivor_scan_receipt_hash": product_scan_hash,
                    }
                }
                job.last_error = None
                job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
                job.updated_at = now
                log_retention_days = policy.log_retention_days if policy is not None else 30
                backup_retention_days = (
                    policy.backup_retention_days if policy is not None else 35
                )
                if product_survivors:
                    job.status = "failed"
                    job.last_error = "Product survivor scan found actor-owned rows"
                    job.lease_owner = None
                    job.lease_expires_at = None
                    return

            for system in DATA_LIFECYCLE_EXTERNAL_SYSTEMS:
                if system in {"logs", "backups"}:
                    retention_days = (
                        log_retention_days if system == "logs" else backup_retention_days
                    )
                    delete_after = self._now() + timedelta(days=retention_days)
                    pending = LifecycleAdapterResult(
                        outcome="pending_expiry",
                        reference={"delete_after": delete_after.isoformat()},
                        evidence={
                            "owner": "deployment_retention",
                            "retention_days": retention_days,
                        },
                    )
                    await self._record_adapter_result(
                        job_id=job_id,
                        system=system,
                        deletion=pending,
                        scan=LifecycleAdapterResult(
                            outcome="pending_expiry",
                            survivor_count=1,
                            reference={"next_scan_at": delete_after.isoformat()},
                            evidence={"queue": "data_deletion_receipt"},
                        ),
                        delete_phase="retention_queue",
                    )
                    continue
                adapter = self._deletion_adapters.get(system)
                if adapter is None:
                    unresolved = LifecycleAdapterResult(
                        outcome="pending_external",
                        evidence={"reason": "lifecycle adapter is not configured"},
                    )
                    await self._record_adapter_result(
                        job_id=job_id,
                        system=system,
                        deletion=unresolved,
                        scan=unresolved,
                    )
                    continue
                try:
                    deletion_result = await adapter.delete(actor)
                    scan_result = await adapter.survivor_scan(actor)
                except Exception as exc:
                    failure = LifecycleAdapterResult(
                        outcome="failed",
                        evidence={"error_type": type(exc).__name__},
                    )
                    deletion_result = failure
                    scan_result = failure
                await self._record_adapter_result(
                    job_id=job_id,
                    system=system,
                    deletion=deletion_result,
                    scan=scan_result,
                )

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
                outcomes = set(job.system_status.values())
                now = self._now()
                if "failed" in outcomes:
                    job.status = "failed"
                    job.last_error = "one or more lifecycle survivor scans failed"
                elif outcomes.intersection({"pending_external", "pending_expiry", "pending"}):
                    job.status = "pending_external"
                    unresolved = sorted(
                        system
                        for system, outcome in job.system_status.items()
                        if outcome in {"pending_external", "pending_expiry", "pending"}
                    )
                    job.last_error = f"unresolved lifecycle systems: {', '.join(unresolved)}"[:500]
                else:
                    job.status = "succeeded"
                    job.completed_at = now
                    job.last_error = None
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
