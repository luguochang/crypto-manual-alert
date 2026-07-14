from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from crypto_alert_v2.persistence.repositories import (
    ActorContext,
    ArtifactRepository,
    ArtifactVersionRepository,
    DecisionRepository,
    MarketSnapshotRepository,
    MembershipRepository,
    RunRepository,
    TaskCommandRepository,
    TaskRepository,
    ThreadRepository,
    WebEvidenceRepository,
)


class ProductUnitOfWork:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        actor: ActorContext,
    ) -> None:
        self._session_factory = session_factory
        self.actor = actor
        self.session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> ProductUnitOfWork:
        if self.session is not None:
            raise RuntimeError("unit of work cannot be entered more than once")
        self.session = self._session_factory()
        await self.session.begin()
        self.memberships = MembershipRepository(self.session, self.actor)
        self.threads = ThreadRepository(self.session, self.actor)
        self.tasks = TaskRepository(self.session, self.actor)
        self.runs = RunRepository(self.session, self.actor)
        self.market_snapshots = MarketSnapshotRepository(self.session, self.actor)
        self.web_evidence = WebEvidenceRepository(self.session, self.actor)
        self.artifacts = ArtifactRepository(self.session, self.actor)
        self.artifact_versions = ArtifactVersionRepository(self.session, self.actor)
        self.decisions = DecisionRepository(self.session, self.actor)
        self.task_commands = TaskCommandRepository(self.session, self.actor)
        return self

    async def commit(self) -> None:
        session = self._require_session()
        await session.commit()
        self._committed = True

    async def rollback(self) -> None:
        session = self._require_session()
        await session.rollback()
        self._committed = False

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if not self._committed and session.in_transaction():
                await session.rollback()
        finally:
            await session.close()

    def _require_session(self) -> AsyncSession:
        if self.session is None:
            raise RuntimeError("unit of work has not been entered")
        return self.session


__all__ = ["ProductUnitOfWork"]
