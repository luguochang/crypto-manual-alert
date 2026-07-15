from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    MarketSnapshot,
    Membership,
    Run,
    Task,
    TaskCommand,
    Tenant,
    Thread,
    User,
    WebEvidence,
    Workspace,
)


class ActorContext(Protocol):
    tenant_id: str
    workspace_id: str
    user_id: str
    identity_issuer: str
    context_id: UUID | None


class ScopedResourceNotFound(LookupError):
    """Raised without disclosing whether a resource exists outside the actor scope."""


@dataclass(frozen=True, slots=True)
class ResolvedActor:
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    membership_id: UUID
    role: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtifactCommit:
    artifact_version: ArtifactVersion
    decision: Decision


@dataclass(frozen=True, slots=True)
class TaskRunSourceRecords:
    market_snapshot: dict[str, Any] | None
    web_evidence: tuple[dict[str, Any], ...]


ModelT = TypeVar("ModelT", bound=Base)


class ActorScopedRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession, actor: ActorContext) -> None:
        if not actor.tenant_id or not actor.workspace_id or not actor.user_id:
            raise PermissionError("actor tenant, workspace and user identifiers are required")
        self.session = session
        self.actor = actor

    def _actor_scope(self, model: type[Any] | None = None) -> Any:
        resource = model or self.model
        return exists(
            select(1)
            .select_from(Tenant)
            .join(
                Workspace,
                and_(
                    Workspace.tenant_id == Tenant.id,
                    Workspace.id == resource.workspace_id,
                ),
            )
            .join(
                Membership,
                and_(
                    Membership.tenant_id == Tenant.id,
                    Membership.workspace_id == Workspace.id,
                    Membership.is_active.is_(True),
                ),
            )
            .join(
                User,
                and_(
                    Membership.user_id == User.id,
                    User.tenant_id == Tenant.id,
                    User.identity_issuer == self.actor.identity_issuer,
                ),
            )
            .where(
                Tenant.id == resource.tenant_id,
                Tenant.external_id == self.actor.tenant_id,
                Workspace.external_id == self.actor.workspace_id,
                User.external_subject == self.actor.user_id,
                *(
                    (Membership.id == self.actor.context_id,)
                    if self.actor.context_id is not None
                    else ()
                ),
            )
        )

    def _select(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self._actor_scope())

    async def get(self, resource_id: UUID) -> ModelT | None:
        statement = self._select().where(self.model.id == resource_id)
        return await self.session.scalar(statement)

    async def list(self, *, limit: int = 100) -> list[ModelT]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        statement = self._select().order_by(self.model.created_at.desc()).limit(limit)
        return list((await self.session.scalars(statement)).all())


class MembershipRepository(ActorScopedRepository[Membership]):
    model = Membership


class ThreadRepository(ActorScopedRepository[Thread]):
    model = Thread


class TaskRepository(ActorScopedRepository[Task]):
    model = Task


class RunRepository(ActorScopedRepository[Run]):
    model = Run


class MarketSnapshotRepository(ActorScopedRepository[MarketSnapshot]):
    model = MarketSnapshot


class WebEvidenceRepository(ActorScopedRepository[WebEvidence]):
    model = WebEvidence


class TaskRunProjectionRepository:
    def __init__(self, session: AsyncSession, actor: ResolvedActor) -> None:
        self.session = session
        self.actor = actor

    async def get_sources(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
    ) -> TaskRunSourceRecords:
        scope = (
            MarketSnapshot.tenant_id == self.actor.tenant_id,
            MarketSnapshot.workspace_id == self.actor.workspace_id,
            MarketSnapshot.owner_user_id == self.actor.user_id,
            MarketSnapshot.task_id == task_id,
            MarketSnapshot.run_id == run_id,
        )
        market_snapshot = await self.session.scalar(
            select(MarketSnapshot.snapshot)
            .where(*scope)
            .order_by(
                MarketSnapshot.fetched_at.desc(),
                MarketSnapshot.created_at.desc(),
                MarketSnapshot.id.desc(),
            )
            .limit(1)
        )
        web_evidence = tuple(
            (
                await self.session.scalars(
                    select(WebEvidence.payload)
                    .where(
                        WebEvidence.tenant_id == self.actor.tenant_id,
                        WebEvidence.workspace_id == self.actor.workspace_id,
                        WebEvidence.owner_user_id == self.actor.user_id,
                        WebEvidence.task_id == task_id,
                        WebEvidence.run_id == run_id,
                    )
                    .order_by(
                        WebEvidence.fetched_at.asc(),
                        WebEvidence.created_at.asc(),
                        WebEvidence.id.asc(),
                    )
                )
            ).all()
        )
        return TaskRunSourceRecords(
            market_snapshot=market_snapshot,
            web_evidence=web_evidence,
        )


class ArtifactVersionRepository(ActorScopedRepository[ArtifactVersion]):
    model = ArtifactVersion


class DecisionRepository(ActorScopedRepository[Decision]):
    model = Decision


class TaskCommandRepository(ActorScopedRepository[TaskCommand]):
    model = TaskCommand


class ArtifactRepository(ActorScopedRepository[Artifact]):
    model = Artifact

    async def commit_version_and_decision(
        self,
        *,
        artifact_id: UUID,
        run_id: UUID,
        content: dict[str, Any],
        decision: dict[str, Any],
        evidence_verdict: dict[str, Any],
        risk_verdict: dict[str, Any],
        schema_version: str = "1.0",
    ) -> ArtifactCommit:
        artifact_run_statement = (
            select(Artifact, Run)
            .join(
                Run,
                and_(
                    Run.id == run_id,
                    Run.task_id == Artifact.task_id,
                    Run.tenant_id == Artifact.tenant_id,
                    Run.workspace_id == Artifact.workspace_id,
                ),
            )
            .where(Artifact.id == artifact_id, self._actor_scope(Artifact))
            .with_for_update(of=Artifact)
        )
        artifact_run = (await self.session.execute(artifact_run_statement)).one_or_none()
        if artifact_run is None:
            raise ScopedResourceNotFound("artifact and run lineage not found")

        artifact, run = artifact_run
        version_statement = select(
            func.coalesce(func.max(ArtifactVersion.version_number), 0)
        ).where(
            ArtifactVersion.artifact_id == artifact.id,
            self._actor_scope(ArtifactVersion),
        )
        version_number = int((await self.session.scalar(version_statement)) or 0) + 1

        artifact_version = ArtifactVersion(
            id=uuid4(),
            tenant_id=artifact.tenant_id,
            workspace_id=artifact.workspace_id,
            owner_user_id=artifact.owner_user_id,
            artifact_id=artifact.id,
            task_id=artifact.task_id,
            run_id=run.id,
            version_number=version_number,
            schema_version=schema_version,
            status="committed",
            content=content,
        )
        final_decision = Decision(
            id=uuid4(),
            tenant_id=artifact.tenant_id,
            workspace_id=artifact.workspace_id,
            owner_user_id=artifact.owner_user_id,
            artifact_id=artifact.id,
            artifact_version_id=artifact_version.id,
            task_id=artifact.task_id,
            run_id=run.id,
            decision_version=version_number,
            decision=decision,
            evidence_verdict=evidence_verdict,
            risk_verdict=risk_verdict,
        )
        artifact.latest_version_number = version_number
        self.session.add_all([artifact_version, final_decision])
        await self.session.flush()
        return ArtifactCommit(artifact_version=artifact_version, decision=final_decision)


async def resolve_actor(session: AsyncSession, actor: ActorContext) -> ResolvedActor:
    if not actor.tenant_id or not actor.workspace_id or not actor.user_id:
        raise PermissionError("actor tenant, workspace and user identifiers are required")

    statement = (
        select(
            Tenant.id,
            Workspace.id,
            User.id,
            Membership.id,
            Membership.role,
            Membership.permissions,
        )
        .select_from(Tenant)
        .join(
            Workspace,
            and_(
                Workspace.tenant_id == Tenant.id,
                Workspace.external_id == actor.workspace_id,
            ),
        )
        .join(
            Membership,
            and_(
                Membership.tenant_id == Tenant.id,
                Membership.workspace_id == Workspace.id,
                Membership.is_active.is_(True),
            ),
        )
        .join(
            User,
            and_(
                Membership.user_id == User.id,
                User.tenant_id == Tenant.id,
                User.identity_issuer == actor.identity_issuer,
                User.external_subject == actor.user_id,
            ),
        )
        .where(
            Tenant.external_id == actor.tenant_id,
            *(
                (Membership.id == actor.context_id,)
                if actor.context_id is not None
                else ()
            ),
        )
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise PermissionError("actor is not an active member of the workspace")
    return ResolvedActor(
        tenant_id=row[0],
        workspace_id=row[1],
        user_id=row[2],
        membership_id=row[3],
        role=row[4],
        permissions=tuple(row[5]),
    )


__all__ = [
    "ActorContext",
    "ActorScopedRepository",
    "ArtifactCommit",
    "ArtifactRepository",
    "ArtifactVersionRepository",
    "DecisionRepository",
    "MarketSnapshotRepository",
    "MembershipRepository",
    "ResolvedActor",
    "RunRepository",
    "ScopedResourceNotFound",
    "TaskCommandRepository",
    "TaskRunProjectionRepository",
    "TaskRunSourceRecords",
    "TaskRepository",
    "ThreadRepository",
    "WebEvidenceRepository",
    "resolve_actor",
]
