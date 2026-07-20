from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.api.schemas import (
    DATA_LIFECYCLE_DELETE_CONFIRMATION,
    DataDeletionSubmission,
    DataLifecyclePolicyUpdate,
    DataExportSubmission,
)
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    DATA_LIFECYCLE_SCOPE,
    DataDeletionJob,
    DataExportJob,
    DataLifecyclePolicy,
)
from crypto_alert_v2.persistence.repositories import ResolvedActor, resolve_actor


MANIFEST_VERSION = 1
EXPORT_EXPIRY_DAYS = 7
DEFAULT_POLICY = {
    "product_retention_days": 365,
    "artifact_retention_days": 365,
    "task_retention_days": 365,
    "run_retention_days": 365,
    "decision_retention_days": 365,
    "usage_retention_days": 365,
    "completed_checkpoint_retention_days": 30,
    "technical_projection_retention_days": 30,
    "log_retention_days": 30,
    "backup_retention_days": 35,
    "retain_raw_prompt": False,
    "retain_raw_response": False,
    "legal_hold_active": False,
    "legal_hold_reason": None,
}

DATA_LIFECYCLE_SYSTEMS = (
    "product_db",
    "object_storage",
    "checkpoint",
    "store",
    "search",
    "langsmith",
    "langfuse",
    "logs",
    "backups",
)
DATA_LIFECYCLE_EXTERNAL_SYSTEMS = tuple(
    system for system in DATA_LIFECYCLE_SYSTEMS if system != "product_db"
)

_SAFE_EXPORT_FIELDS = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "status",
        "task_type",
        "symbol",
        "horizon",
        "kind",
        "channel",
        "attempt",
        "attempt_count",
        "version",
        "version_number",
        "decision_version",
        "scope",
        "provider",
        "unit",
    }
)
_LIFECYCLE_TABLES = frozenset(
    {"data_lifecycle_policies", "data_export_jobs", "data_deletion_jobs"}
)


class LifecycleError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID) or value.__class__.__name__ == "UUID":
        return str(value)
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID) or value.__class__.__name__ == "UUID":
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    """Hash the exact canonical manifest representation stored in Product DB."""

    return _sha256(manifest)


def validate_manifest_hash(
    manifest: dict[str, Any], expected_hash: str, *, bundle: dict[str, Any] | None = None
) -> None:
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != MANIFEST_VERSION:
        raise LifecycleError("manifest_invalid", "manifest version is invalid")
    actual_hash = compute_manifest_hash(manifest)
    if hashlib.sha256(expected_hash.encode("ascii")).digest() != hashlib.sha256(
        actual_hash.encode("ascii")
    ).digest():
        raise LifecycleError("manifest_tampered", "manifest hash does not match")
    if bundle is not None and manifest.get("bundle_sha256") != _sha256(bundle):
        raise LifecycleError("bundle_tampered", "bundle hash does not match manifest")


def _scope_filter(model: Any, actor: ResolvedActor) -> Any:
    actor_column = getattr(model, "owner_user_id", None)
    if actor_column is None:
        actor_column = getattr(model, "actor_user_id", None)
    if actor_column is None:
        raise ValueError(f"{model.__tablename__} is not actor scoped")
    return and_(
        model.tenant_id == actor.tenant_id,
        model.workspace_id == actor.workspace_id,
        actor_column == actor.user_id,
    )


def _policy_view(policy: DataLifecyclePolicy) -> dict[str, Any]:
    return {
        "id": policy.id,
        "tenant_id": policy.tenant_id,
        "workspace_id": policy.workspace_id,
        "owner_user_id": policy.owner_user_id,
        **{
            name: getattr(policy, name)
            for name in DEFAULT_POLICY
        },
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


def _export_view(job: DataExportJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "tenant_id": job.tenant_id,
        "workspace_id": job.workspace_id,
        "owner_user_id": job.owner_user_id,
        "scope": job.scope,
        "idempotency_key": job.idempotency_key,
        "status": job.status,
        "attempt": job.attempt,
        "lease_expires_at": job.lease_expires_at,
        "requested_at": job.requested_at,
        "completed_at": job.completed_at,
        "expired_at": job.expired_at,
        "manifest_version": job.manifest_version,
        "manifest_hash": job.manifest_hash,
        "last_error": job.last_error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _deletion_view(job: DataDeletionJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "tenant_id": job.tenant_id,
        "workspace_id": job.workspace_id,
        "owner_user_id": job.owner_user_id,
        "scope": job.scope,
        "idempotency_key": job.idempotency_key,
        "status": job.status,
        "attempt": job.attempt,
        "lease_expires_at": job.lease_expires_at,
        "requested_at": job.requested_at,
        "completed_at": job.completed_at,
        "expired_at": job.expired_at,
        "legal_hold_active": job.legal_hold_active,
        "legal_hold_reason": job.legal_hold_reason,
        "system_status": dict(job.system_status),
        "external_deletion_reference": dict(job.external_deletion_reference),
        "last_error": job.last_error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


class LifecycleService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("lifecycle clock must be timezone-aware")
        return value

    @staticmethod
    def _require_permission(actor: ResolvedActor, *, write: bool = False) -> None:
        permissions = set(actor.permissions)
        accepted = (
            {"data_lifecycle:write", "data_lifecycle:delete", "analysis:write", "admin"}
            if write
            else {"data_lifecycle:read", "data_lifecycle:write", "analysis:read", "analysis:write", "admin"}
        )
        if not permissions.intersection(accepted):
            required = "data_lifecycle:write" if write else "data_lifecycle:read"
            raise PermissionError(f"{required} permission is required")

    async def _resolved(
        self, session: AsyncSession, actor: ActorContext, *, write: bool = False
    ) -> ResolvedActor:
        resolved = await resolve_actor(session, actor)
        self._require_permission(resolved, write=write)
        return resolved

    @staticmethod
    def _find_policy_statement(actor: ResolvedActor) -> Any:
        return select(DataLifecyclePolicy).where(
            DataLifecyclePolicy.tenant_id == actor.tenant_id,
            DataLifecyclePolicy.workspace_id == actor.workspace_id,
            DataLifecyclePolicy.owner_user_id == actor.user_id,
        )

    async def _ensure_policy(
        self, session: AsyncSession, actor: ResolvedActor
    ) -> DataLifecyclePolicy:
        policy = await session.scalar(self._find_policy_statement(actor))
        if policy is None:
            policy = DataLifecyclePolicy(
                id=uuid4(),
                tenant_id=actor.tenant_id,
                workspace_id=actor.workspace_id,
                owner_user_id=actor.user_id,
                **DEFAULT_POLICY,
            )
            session.add(policy)
            await session.flush()
        return policy

    async def get_policy(self, actor: ActorContext) -> dict[str, Any]:
        async with self._session_factory() as session, session.begin():
            resolved = await self._resolved(session, actor)
            return _policy_view(await self._ensure_policy(session, resolved))

    async def update_policy(
        self, actor: ActorContext, submission: DataLifecyclePolicyUpdate
    ) -> dict[str, Any]:
        async with self._session_factory() as session, session.begin():
            resolved = await self._resolved(session, actor, write=True)
            policy = await self._ensure_policy(session, resolved)
            for name, value in submission.model_dump(exclude_none=True).items():
                setattr(policy, name, value)
            if policy.legal_hold_active and not policy.legal_hold_reason:
                raise LifecycleError(
                    "legal_hold_reason_required",
                    "legal_hold_reason is required for an active legal hold",
                )
            if not policy.legal_hold_active:
                policy.legal_hold_reason = None
            policy.updated_at = self._now()
            await session.flush()
            return _policy_view(policy)

    async def create_export(
        self,
        actor: ActorContext,
        submission: DataExportSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload_hash = _sha256(submission.model_dump(mode="json"))
        async with self._session_factory() as session, session.begin():
            resolved = await self._resolved(session, actor, write=True)
            existing = await session.scalar(
                select(DataExportJob).where(
                    _scope_filter(DataExportJob, resolved),
                    DataExportJob.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_payload_hash != payload_hash:
                    raise LifecycleError(
                        "idempotency_conflict",
                        "Idempotency-Key was already used with a different export payload.",
                    )
                return _export_view(existing)
            now = self._now()
            job = DataExportJob(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                scope=submission.scope,
                idempotency_key=idempotency_key,
                request_payload_hash=payload_hash,
                status="queued",
                available_at=now,
                requested_at=now,
            )
            session.add(job)
            await session.flush()
            return _export_view(job)

    async def get_export(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            resolved = await self._resolved(session, actor)
            job = await session.scalar(
                select(DataExportJob).where(
                    DataExportJob.id == export_id,
                    _scope_filter(DataExportJob, resolved),
                )
            )
            return _export_view(job) if job is not None else None

    async def get_export_manifest(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            resolved = await self._resolved(session, actor)
            job = await session.scalar(
                select(DataExportJob).where(
                    DataExportJob.id == export_id,
                    _scope_filter(DataExportJob, resolved),
                )
            )
            if job is None:
                return None
            return {
                "export_id": job.id,
                "status": job.status,
                "manifest_version": job.manifest_version,
                "manifest_hash": job.manifest_hash,
                "manifest": job.manifest,
            }

    async def get_export_bundle(
        self, actor: ActorContext, export_id: UUID
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            resolved = await self._resolved(session, actor)
            job = await session.scalar(
                select(DataExportJob).where(
                    DataExportJob.id == export_id,
                    _scope_filter(DataExportJob, resolved),
                )
            )
            if job is None:
                return None
            if job.status == "succeeded" and job.manifest and job.manifest_hash:
                validate_manifest_hash(job.manifest, job.manifest_hash, bundle=job.bundle)
            return {
                "export_id": job.id,
                "status": job.status,
                "manifest_version": job.manifest_version,
                "manifest_hash": job.manifest_hash,
                "bundle": job.bundle,
            }

    async def create_deletion(
        self,
        actor: ActorContext,
        submission: DataDeletionSubmission,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if submission.confirmation != DATA_LIFECYCLE_DELETE_CONFIRMATION:
            raise LifecycleError(
                "invalid_deletion_confirmation",
                "The deletion confirmation string is invalid.",
            )
        payload_hash = _sha256({"scope": submission.scope})
        confirmation_hash = hashlib.sha256(
            submission.confirmation.encode("utf-8")
        ).hexdigest()
        async with self._session_factory() as session, session.begin():
            resolved = await self._resolved(session, actor, write=True)
            existing = await session.scalar(
                select(DataDeletionJob).where(
                    _scope_filter(DataDeletionJob, resolved),
                    DataDeletionJob.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_payload_hash != payload_hash:
                    raise LifecycleError(
                        "idempotency_conflict",
                        "Idempotency-Key was already used with a different deletion payload.",
                    )
                return _deletion_view(existing)
            policy = await self._ensure_policy(session, resolved)
            now = self._now()
            held = policy.legal_hold_active
            system_status = {
                system: "blocked_legal_hold" if held else "pending"
                for system in DATA_LIFECYCLE_SYSTEMS
            }
            job = DataDeletionJob(
                id=uuid4(),
                tenant_id=resolved.tenant_id,
                workspace_id=resolved.workspace_id,
                owner_user_id=resolved.user_id,
                scope=submission.scope,
                idempotency_key=idempotency_key,
                request_payload_hash=payload_hash,
                confirmation_hash=confirmation_hash,
                status="blocked_legal_hold" if held else "queued",
                available_at=now,
                requested_at=now,
                legal_hold_active=held,
                legal_hold_reason=policy.legal_hold_reason,
                system_status=system_status,
                external_deletion_reference={
                    system: None for system in DATA_LIFECYCLE_EXTERNAL_SYSTEMS
                },
            )
            session.add(job)
            await session.flush()
            return _deletion_view(job)

    async def get_deletion(
        self, actor: ActorContext, deletion_id: UUID
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            resolved = await self._resolved(session, actor)
            job = await session.scalar(
                select(DataDeletionJob).where(
                    DataDeletionJob.id == deletion_id,
                    _scope_filter(DataDeletionJob, resolved),
                )
            )
            return _deletion_view(job) if job is not None else None

    async def build_export_payload(
        self, session: AsyncSession, job: DataExportJob
    ) -> tuple[dict[str, Any], dict[str, Any], str, str]:
        actor = ResolvedActor(
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            user_id=job.owner_user_id,
            membership_id=UUID(int=0),
            role="worker",
            permissions=(),
        )
        tables: dict[str, list[dict[str, Any]]] = {}
        for table in Base.metadata.sorted_tables:
            if table.name in _LIFECYCLE_TABLES:
                continue
            actor_column = table.c.get("owner_user_id")
            if actor_column is None:
                actor_column = table.c.get("actor_user_id")
            if actor_column is None or "tenant_id" not in table.c or "workspace_id" not in table.c:
                continue
            rows = (
                await session.execute(
                    select(table).where(
                        table.c.tenant_id == actor.tenant_id,
                        table.c.workspace_id == actor.workspace_id,
                        actor_column == actor.user_id,
                    )
                )
            ).mappings().all()
            safe_rows: list[dict[str, Any]] = []
            for row in rows:
                safe_row: dict[str, Any] = {}
                for name in _SAFE_EXPORT_FIELDS:
                    if name not in row or row[name] is None:
                        continue
                    value = row[name]
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    elif isinstance(value, UUID) or value.__class__.__name__ == "UUID":
                        # asyncpg can return its own UUID wrapper when a
                        # connection is created outside SQLAlchemy's codec.
                        value = str(value)
                    safe_row[name] = value
                safe_rows.append(safe_row)
            tables[table.name] = safe_rows

        bundle = _json_safe({
            "bundle_version": 1,
            "export_id": job.id,
            "scope": DATA_LIFECYCLE_SCOPE,
            "generated_at": self._now(),
            "records": tables,
        })
        # The policy is intentionally explicit and contains no prompt, response,
        # credential or provider payload.  It explains the retention decision
        # without copying user data into the export.
        policy = await session.scalar(
            select(DataLifecyclePolicy).where(
                DataLifecyclePolicy.tenant_id == job.tenant_id,
                DataLifecyclePolicy.workspace_id == job.workspace_id,
                DataLifecyclePolicy.owner_user_id == job.owner_user_id,
            )
        )
        assert isinstance(bundle, dict)
        bundle["policy"] = _json_safe(
            _policy_view(policy) if policy is not None else dict(DEFAULT_POLICY)
        )
        bundle_hash = _sha256(bundle)
        manifest = _json_safe({
            "manifest_version": MANIFEST_VERSION,
            "export_id": job.id,
            "scope": DATA_LIFECYCLE_SCOPE,
            "generated_at": bundle["generated_at"],
            "bundle_sha256": bundle_hash,
            "tables": {
                name: {
                    "row_count": len(rows),
                    "records_sha256": _sha256(rows),
                }
                for name, rows in sorted(tables.items())
            },
        })
        assert isinstance(manifest, dict)
        manifest_hash = compute_manifest_hash(manifest)
        validate_manifest_hash(manifest, manifest_hash, bundle=bundle)
        return bundle, manifest, manifest_hash, bundle_hash


async def delete_actor_product_rows(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    owner_user_id: UUID,
) -> None:
    """Delete actor-owned Product rows in metadata dependency order.

    Lifecycle jobs remain as the audit record.  Tenant, workspace, user and
    membership identity rows are shared authorization state and are never
    removed by the user-data scope.
    """

    for table in reversed(Base.metadata.sorted_tables):
        if table.name in _LIFECYCLE_TABLES:
            continue
        actor_column = table.c.get("owner_user_id")
        if actor_column is None:
            actor_column = table.c.get("actor_user_id")
        if actor_column is None or "tenant_id" not in table.c or "workspace_id" not in table.c:
            continue
        await session.execute(
            delete(table).where(
                table.c.tenant_id == tenant_id,
                table.c.workspace_id == workspace_id,
                actor_column == owner_user_id,
            )
        )


__all__ = [
    "DATA_LIFECYCLE_EXTERNAL_SYSTEMS",
    "DATA_LIFECYCLE_SYSTEMS",
    "LifecycleError",
    "LifecycleService",
    "compute_manifest_hash",
    "delete_actor_product_rows",
    "validate_manifest_hash",
]
