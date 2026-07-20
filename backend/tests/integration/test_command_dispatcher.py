from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import httpx
from langgraph_sdk.schema import StreamPart
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import AsyncIterator
from uuid import UUID, uuid4

from pydantic import SecretStr
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crypto_alert_v2.api.agent_server import (
    RemoteCancelResult,
    RemoteCheckpoint,
    RemoteForkIndeterminateError,
    RemoteInterrupt,
    RemoteInterruptSet,
    RemoteResumeIndeterminateError,
    RemoteRunHandle,
    RemoteRunState,
    RemoteSubmitIndeterminateError,
)
from crypto_alert_v2.api.schemas import (
    AnalysisSubmission,
    DeepResearchSubmission,
    ForkSubmission,
    InterruptResponseSubmission,
    InterruptResponsesSubmission,
    TerminalGraphOutput,
)
from crypto_alert_v2.api.service import ProductAnalysisService, TaskNotCancellableError
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.commands.dispatcher import CommandDispatcher
from crypto_alert_v2.domain.deep_research import (
    DeepResearchReport,
    DeepResearchSearchCoverage,
    materialize_deep_research_artifact,
)
from crypto_alert_v2.notifications.credentials import NotificationCredentialCipher
from crypto_alert_v2.notifications.resolver import DatabaseNotificationAdapterResolver
from crypto_alert_v2.persistence.base import Base
from crypto_alert_v2.persistence.models import (
    Artifact,
    ArtifactVersion,
    Decision,
    DomainEvent,
    InterruptPause,
    InterruptProjection,
    MarketSnapshot,
    Membership,
    NotificationAttempt,
    NotificationDestination,
    NotificationOutbox,
    ObservabilityDelivery,
    Run,
    Task,
    TaskCommand,
    Thread,
    WebEvidence,
    Workspace,
)
from crypto_alert_v2.observability.config import ObservabilityRuntimeConfig
from crypto_alert_v2.observability.planning import (
    plan_observability_delivery_intents,
)
from crypto_alert_v2.projections.domain_events import (
    DomainEventProjectionConflict,
    DomainEventProjectionWorker,
    append_progressive_events,
)
from crypto_alert_v2.testing.failure_injection import (
    FailureInjectionController,
    FailureInjectionScenario,
    install_database_failure_injection,
)
from crypto_alert_v2.workers.notification import OutboxWorker
from tests.fixtures.golden_cases import complete_market_snapshot, valid_market_analysis
from tests.integration.support.actor_cleanup import delete_actor_test_data
from crypto_alert_v2.providers.search import WebEvidence as DomainWebEvidence


DATABASE_URL = os.getenv("PRODUCT_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.getenv("REAL_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="requires REAL_DATABASE_TESTS=1 and PRODUCT_DATABASE_URL",
)


@pytest_asyncio.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as migration_connection:
        await migration_connection.run_sync(Base.metadata.create_all)
    database_connection = await engine.connect()
    transaction = await database_connection.begin()
    try:
        yield database_connection
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await database_connection.close()
        await engine.dispose()


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 13, 6, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class InspectingRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        remote_run_id: str = "official-run",
        remote_thread_id: str = "official-thread",
    ) -> None:
        self._session_factory = session_factory
        self._remote_run_id = remote_run_id
        self._remote_thread_id = remote_thread_id
        self.events: list[str] = []
        self.cancelled: list[RemoteRunHandle] = []
        self.task_id: UUID | None = None
        self.registered_handle: tuple[str | None, str | None, str | None] | None = None
        self.remote_status = "success"
        self.start_requests: list[dict[str, object]] = []
        self.resume_requests: list[dict[str, object]] = []
        self.fork_requests: list[dict[str, object]] = []
        self.find_requests: list[dict[str, object]] = []

    async def start(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("start")
        self.start_requests.append(dict(kwargs))
        self.task_id = UUID(str(kwargs["task_id"]))
        return RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id=self._remote_thread_id,
            run_id=self._remote_run_id,
        )

    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        self.events.append("join")
        async with self._session_factory() as session:
            registered = (
                await session.execute(
                    select(
                        Run.task_id,
                        Run.official_assistant_id,
                        Thread.official_thread_id,
                        Run.official_run_id,
                    )
                    .join(Thread, Thread.id == Run.thread_id)
                    .where(Run.official_run_id == handle.run_id)
                )
            ).one()
        self.task_id = registered[0]
        self.registered_handle = tuple(registered[1:])
        return {
            "terminal_status": "failed",
            "errors": [{"code": "provider_unavailable", "retryable": True}],
        }

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState:
        del handle
        self.events.append("get")
        return RemoteRunState(status=self.remote_status)  # type: ignore[arg-type]

    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        self.cancelled.append(handle)
        return RemoteCancelResult(
            outcome="confirmed",
            state=RemoteRunState(status="interrupted"),
        )

    async def get_interrupts(
        self,
        handle: RemoteRunHandle,
    ) -> RemoteInterruptSet:
        self.events.append("get_interrupts")
        checkpoint_id = f"checkpoint-{handle.run_id}"
        async with self._session_factory() as session:
            task = await session.scalar(select(Task).where(Task.id == self.task_id))
        if task is not None and task.task_type == "deep_research":
            evidence = DomainWebEvidence(
                query="BTC institutional adoption",
                final_url="https://example.com/verified-btc-source",
                fetched_at=datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
                content_hash="f" * 64,
                title="Verified BTC source",
                source="test_search",
                excerpt="A verified source excerpt.",
                evidence_relation="supports",
            )
            report = DeepResearchReport.model_validate(
                {
                    "executive_summary": "Verified evidence supports a measured conclusion.",
                    "sections": [
                        {
                            "title": "Adoption",
                            "summary": "The source catalog supports the current finding.",
                            "findings": [
                                {
                                    "claim": "Institutional adoption remains active.",
                                    "source_indexes": [1],
                                }
                            ],
                        }
                    ],
                }
            )
            research_artifact = materialize_deep_research_artifact(
                report=report,
                evidence=(evidence,),
                harness_mode="deepagents",
                search_coverage=DeepResearchSearchCoverage(
                    status="complete",
                    attempted_queries=1,
                    successful_queries=1,
                ),
                model_audits=(),
            )
            payload = {
                "kind": "deep_research_review",
                "schema_version": "1.0",
                "allowed_actions": ["approve", "reject", "edit"],
                "symbol": "BTC-USDT-SWAP",
                "horizon": "7d",
                "review_iteration": 1,
                "artifact": research_artifact.model_dump(mode="json"),
            }
        else:
            payload = {
                "kind": "artifact_review",
                "schema_version": "1.0",
                "allowed_actions": ["approve", "reject", "edit"],
                "review_iteration": (2 if handle.run_id.startswith("resumed-") else 1),
                "artifact": {
                    **successful_terminal_output()["artifact"],
                    "status": "draft",
                },
            }
        return RemoteInterruptSet(
            checkpoint=RemoteCheckpoint(
                thread_id=handle.thread_id,
                checkpoint_ns="",
                checkpoint_id=checkpoint_id,
                checkpoint_map={},
            ),
            interrupts=(
                RemoteInterrupt(
                    interrupt_id=f"interrupt-{handle.run_id}",
                    namespace="",
                    checkpoint_id=checkpoint_id,
                    value=payload,
                ),
            ),
        )

    async def resume(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("resume")
        self.resume_requests.append(dict(kwargs))
        handle = kwargs["handle"]
        assert isinstance(handle, RemoteRunHandle)
        self.task_id = UUID(str(kwargs["task_id"]))
        return RemoteRunHandle(
            assistant_id=handle.assistant_id,
            thread_id=handle.thread_id,
            run_id=f"resumed-{kwargs['product_run_id']}",
        )

    async def fork(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("fork")
        self.fork_requests.append(dict(kwargs))
        handle = kwargs["handle"]
        assert isinstance(handle, RemoteRunHandle)
        self.task_id = UUID(str(kwargs["task_id"]))
        return RemoteRunHandle(
            assistant_id=handle.assistant_id,
            thread_id=handle.thread_id,
            run_id=f"forked-{kwargs['product_run_id']}",
        )

    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.find_requests.append(dict(kwargs))
        return None


class LeaseExpiringRunner(InspectingRunner):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: MutableClock,
    ) -> None:
        super().__init__(session_factory)
        self._clock = clock

    async def start(self, **kwargs: object) -> RemoteRunHandle:
        handle = await super().start(**kwargs)
        self._clock.now += timedelta(seconds=31)
        return handle


class SlowStartRunner(InspectingRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        await asyncio.sleep(1.1)
        return await super().start(**kwargs)


class TerminalJoinFailureRunner(InspectingRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.fail_join = True

    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        if self.fail_join:
            self.events.append("join")
            raise ConnectionError("terminal output temporarily unavailable")
        return await super().join(handle)


class DeadlineTerminalJoinFailureRunner(TerminalJoinFailureRunner):
    async def get(self, handle: RemoteRunHandle) -> RemoteRunState:
        del handle
        self.events.append("get")
        raise ConnectionError("state reconciliation temporarily unavailable")

    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        self.cancelled.append(handle)
        return RemoteCancelResult(
            outcome="terminal",
            state=RemoteRunState(status="success"),
        )


class HangingCancelRunner(InspectingRunner):
    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        self.cancelled.append(handle)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class SuccessfulJoinRunner(InspectingRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        await super().join(handle)
        return successful_terminal_output()


class HangingGetRunner(SuccessfulJoinRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.hang_get = True
        self.get_cancelled = False

    async def get(self, handle: RemoteRunHandle) -> RemoteRunState:
        del handle
        self.events.append("get")
        if self.hang_get:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.get_cancelled = True
                raise
        return RemoteRunState(status=self.remote_status)  # type: ignore[arg-type]


class ProgressiveLateFailureRunner(InspectingRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.remote_status = "error"
        output = successful_terminal_output()
        artifact = output["artifact"]
        assert isinstance(artifact, dict)
        self.stream_parts = [
            StreamPart(
                event="updates",
                data={
                    "collect_market_snapshot": {
                        "market_snapshot": output["market_snapshot"],
                        "lifecycle": "market_collected",
                    }
                },
                id="progress-market",
            ),
            StreamPart(
                event="updates",
                data={
                    "research_events": {
                        "web_evidence": output["web_evidence"],
                        "lifecycle": "research_collected",
                    }
                },
                id="progress-research",
            ),
            StreamPart(
                event="updates",
                data={
                    "analyze_market": {
                        "analysis": artifact["analysis"],
                        "lifecycle": "analysis_completed",
                    }
                },
                id="progress-analysis",
            ),
            StreamPart(
                event="updates",
                data={
                    "validate_evidence": {
                        "evidence_verdict": artifact["evidence_verdict"],
                        "lifecycle": "evidence_validated",
                    }
                },
                id="progress-evidence",
            ),
            StreamPart(
                event="updates",
                data={
                    "apply_risk_policy": {
                        "risk_verdict": artifact["risk_verdict"],
                        "lifecycle": "risk_validated",
                    }
                },
                id="progress-risk",
            ),
        ]
        self.join_stream_last_event_ids: list[str | None] = []

    async def join_stream(
        self,
        handle: RemoteRunHandle,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[StreamPart]:
        del handle
        self.events.append("join_stream")
        self.join_stream_last_event_ids.append(last_event_id)
        start_index = 0
        if last_event_id is not None:
            start_index = next(
                index + 1
                for index, part in enumerate(self.stream_parts)
                if part.id == last_event_id
            )
        for part in self.stream_parts[start_index:]:
            yield part


class ProgressiveReconnectRunner(ProgressiveLateFailureRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.remote_status = "running"


class ModelInvalidOutputRunner(InspectingRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        await super().join(handle)
        return model_invalid_terminal_output()


class WebFallbackBlockedRunner(InspectingRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        await super().join(handle)
        return web_fallback_blocked_terminal_output()


class ReviewAwareRunner(SuccessfulJoinRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        output = await super().join(handle)
        responses = (
            self.resume_requests[-1]["responses"] if self.resume_requests else None
        )
        response = (
            next(iter(responses.values())) if isinstance(responses, dict) else None
        )
        if isinstance(response, dict) and response.get("action") == "reject":
            return blocked_terminal_output()
        return output


class MultiInterruptRunner(SuccessfulJoinRunner):
    async def get_interrupts(
        self,
        handle: RemoteRunHandle,
    ) -> RemoteInterruptSet:
        single = await super().get_interrupts(handle)
        root = single.interrupts[0]
        return RemoteInterruptSet(
            checkpoint=single.checkpoint,
            interrupts=(
                root,
                RemoteInterrupt(
                    interrupt_id=f"nested-{handle.run_id}",
                    namespace="research:child",
                    checkpoint_id=f"nested-checkpoint-{handle.run_id}",
                    value=deepcopy(root.value),
                ),
            ),
        )


class MultiReviewAwareRunner(MultiInterruptRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        output = await super().join(handle)
        responses = (
            self.resume_requests[-1]["responses"] if self.resume_requests else None
        )
        if isinstance(responses, dict) and any(
            isinstance(response, dict) and response.get("action") == "reject"
            for response in responses.values()
        ):
            return blocked_terminal_output()
        return output


class FailingResumeMultiRunner(MultiReviewAwareRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.fail_resume = True

    async def resume(self, **kwargs: object) -> RemoteRunHandle:
        if self.fail_resume:
            self.events.append("resume")
            self.resume_requests.append(dict(kwargs))
            raise ConnectionError("resume temporarily unavailable")
        return await super().resume(**kwargs)


class IndeterminateResumeMultiRunner(MultiReviewAwareRunner):
    async def resume(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("resume")
        self.resume_requests.append(dict(kwargs))
        raise RemoteResumeIndeterminateError("resume acceptance is unknown")


class HangingResumeReconcileRunner(MultiReviewAwareRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.resume_cancelled = False
        self.find_cancelled = False
        self.find_calls = 0

    async def resume(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("resume")
        self.resume_requests.append(dict(kwargs))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.resume_cancelled = True
            raise
        raise AssertionError("unreachable")

    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.events.append("find")
        self.find_requests.append(dict(kwargs))
        self.find_calls += 1
        if self.find_calls == 1:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.find_cancelled = True
                raise
        return RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id=str(kwargs["product_thread_id"]),
            run_id=f"resumed-{kwargs['product_run_id']}",
        )


class IndeterminateForkRunner(SuccessfulJoinRunner):
    async def fork(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("fork")
        self.fork_requests.append(dict(kwargs))
        raise RemoteForkIndeterminateError("fork acceptance is unknown")


class HangingForkRunner(SuccessfulJoinRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.cancelled = False

    async def fork(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("fork")
        self.fork_requests.append(dict(kwargs))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


class HangingStartRunner(InspectingRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("start")
        self.start_requests.append(dict(kwargs))
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class ReconcileOnlyForkRunner(SuccessfulJoinRunner):
    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.find_requests.append(dict(kwargs))
        return RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id=str(kwargs["product_thread_id"]),
            run_id=f"forked-{kwargs['product_run_id']}",
        )


class IndeterminateSubmitRunner(InspectingRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("start")
        self.start_requests.append(dict(kwargs))
        raise RemoteSubmitIndeterminateError("submit acceptance is unknown")


class IntentObservingSubmitRunner(IndeterminateSubmitRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        task_id = UUID(str(kwargs["task_id"]))
        async with self._session_factory() as session:
            product_run = await session.scalar(
                select(Run).where(Run.task_id == task_id).order_by(Run.attempt.desc())
            )
        assert product_run is not None
        self.events.append(f"intent:{product_run.failure_code}")
        return await super().start(**kwargs)


class PreAcceptFailureSubmitRunner(InspectingRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.fail_once = True

    async def start(self, **kwargs: object) -> RemoteRunHandle:
        if self.fail_once:
            self.fail_once = False
            self.events.append("start-failed-before-accept")
            raise httpx.ConnectTimeout(
                "connect timeout",
                request=httpx.Request("POST", "http://agent.invalid/threads/runs"),
            )
        return await super().start(**kwargs)


class AlwaysPreAcceptFailureSubmitRunner(InspectingRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("start-failed-before-accept")
        self.start_requests.append(dict(kwargs))
        raise httpx.ConnectTimeout(
            "connect timeout",
            request=httpx.Request("POST", "http://agent.invalid/threads/runs"),
        )


class PermanentForkFailureRunner(SuccessfulJoinRunner):
    async def fork(self, **kwargs: object) -> RemoteRunHandle:
        self.events.append("fork")
        self.fork_requests.append(dict(kwargs))
        raise ConnectionError("fork permanently unavailable")


class ReconcileOnlySubmitRunner(SuccessfulJoinRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        raise AssertionError("durable indeterminate submit must never create again")

    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.find_requests.append(dict(kwargs))
        return RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id=str(kwargs["product_thread_id"]),
            run_id=f"submitted-{kwargs['product_run_id']}",
        )


class ReconcileMissingSubmitRunner(InspectingRunner):
    async def start(self, **kwargs: object) -> RemoteRunHandle:
        raise AssertionError("expired indeterminate submit must not create")

    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.find_requests.append(dict(kwargs))
        return None


class ReconcileOnlyResumeMultiRunner(MultiReviewAwareRunner):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        visible_after: int,
    ) -> None:
        super().__init__(session_factory)
        self.visible_after = visible_after
        self.find_calls = 0

    async def resume(self, **kwargs: object) -> RemoteRunHandle:
        self.resume_requests.append(dict(kwargs))
        raise AssertionError("durable indeterminate intent must never create again")

    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.events.append("find")
        self.find_calls += 1
        if self.find_calls < self.visible_after:
            return None
        return RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id=str(kwargs["product_thread_id"]),
            run_id=f"resumed-{kwargs['product_run_id']}",
        )


class TerminalResumeCancelRunner(MultiInterruptRunner):
    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        self.cancelled.append(handle)
        return RemoteCancelResult(
            outcome="terminal",
            state=RemoteRunState(status="success"),
        )


class OverLimitInterruptRunner(SuccessfulJoinRunner):
    async def get_interrupts(
        self,
        handle: RemoteRunHandle,
    ) -> RemoteInterruptSet:
        single = await super().get_interrupts(handle)
        root = single.interrupts[0]
        return RemoteInterruptSet(
            checkpoint=single.checkpoint,
            interrupts=tuple(
                RemoteInterrupt(
                    interrupt_id=f"interrupt-{index:02d}-{handle.run_id}",
                    namespace=f"review:{index}",
                    checkpoint_id=f"checkpoint-{index:02d}-{handle.run_id}",
                    value=deepcopy(root.value),
                )
                for index in range(65)
            ),
        )


class TerminalCancelRaceRunner(SuccessfulJoinRunner):
    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        self.cancelled.append(handle)
        return RemoteCancelResult(
            outcome="terminal",
            state=RemoteRunState(status="success"),
        )


class TerminalCancelJoinFailureRunner(TerminalCancelRaceRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        del handle
        self.events.append("join")
        raise ConnectionError("terminal output temporarily unavailable")


class TerminalThenUnconfirmedCancelRunner(TerminalCancelJoinFailureRunner):
    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        if self.cancelled:
            self.cancelled.append(handle)
            return RemoteCancelResult(
                outcome="unconfirmed",
                state=RemoteRunState(status="running"),
            )
        return await super().cancel(handle)


class UnconfirmedCancelRunner(InspectingRunner):
    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        self.cancelled.append(handle)
        return RemoteCancelResult(
            outcome="unconfirmed",
            state=RemoteRunState(status="running"),
        )


class ConflictingSuccessfulJoinRunner(SuccessfulJoinRunner):
    async def join(self, handle: RemoteRunHandle) -> dict[str, object]:
        output = await super().join(handle)
        artifact = output["artifact"]
        assert isinstance(artifact, dict)
        analysis = artifact["analysis"]
        assert isinstance(analysis, dict)
        analysis["probability"] = "0.61"
        return output


class RecoveringCancelRunner(InspectingRunner):
    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.events.append("find")
        self.task_id = UUID(str(kwargs["task_id"]))
        return RemoteRunHandle(
            assistant_id="recovered-assistant",
            thread_id=str(kwargs["product_thread_id"]),
            run_id="recovered-run",
        )


class DelayedVisibilityCancelRunner(InspectingRunner):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        visible_after: int,
    ) -> None:
        super().__init__(session_factory)
        self.visible_after = visible_after
        self.find_calls = 0

    async def find(self, **kwargs: object) -> RemoteRunHandle | None:
        self.events.append("find")
        self.find_calls += 1
        self.task_id = UUID(str(kwargs["task_id"]))
        if self.find_calls < self.visible_after:
            return None
        return RemoteRunHandle(
            assistant_id="delayed-assistant",
            thread_id=str(kwargs["product_thread_id"]),
            run_id="delayed-run",
        )


class CancelFailureRunner(InspectingRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.fail_cancel = True

    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        if self.fail_cancel:
            raise ConnectionError("cancel temporarily unavailable")
        return await super().cancel(handle)


class SourceCancelFailureRunner(InspectingRunner):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)
        self.cancel_attempts: list[RemoteRunHandle] = []

    async def cancel(self, handle: RemoteRunHandle) -> RemoteCancelResult:
        self.cancel_attempts.append(handle)
        raise ConnectionError("source Run cancellation permanently unavailable")


def actor() -> ActorContext:
    return ActorContext(
        tenant_id="dispatcher-tenant",
        workspace_id="dispatcher-workspace",
        user_id="oidc|dispatcher-user",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


async def queue_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: str = "dispatcher-analysis-1",
    notify: bool = False,
    task_type: str = "market_analysis",
) -> tuple[ProductAnalysisService, dict[str, object]]:
    service = ProductAnalysisService(session_factory=session_factory)
    await service.bootstrap_actor(actor())
    if task_type == "deep_research":
        queued = await service.create_deep_research(
            actor(),
            DeepResearchSubmission(
                symbol="BTC-USDT-SWAP",
                horizon="7d",
                query_text="Research BTC adoption and its strongest counterevidence.",
            ),
            idempotency_key=idempotency_key,
        )
    else:
        queued = await service.create_analysis(
            actor(),
            AnalysisSubmission(
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="Assess current BTC risk.",
                notify=notify,
            ),
            idempotency_key=idempotency_key,
        )
    return service, queued


@pytest.mark.asyncio
async def test_run_admission_persists_observability_intents_and_product_scope(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="observability-intent-admission",
    )
    runtime = ObservabilityRuntimeConfig(
        environment="test",
        release="test",
        langsmith_enabled=True,
        langsmith_api_key="langsmith-intent-canary",
        langsmith_project="crypto-alert-v2-test",
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        langfuse_secret_key="langfuse-intent-canary",
    )
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="observability-intent-worker",
        observability_intent_planner=lambda **kwargs: (
            plan_observability_delivery_intents(
                runtime=runtime,
                verification_deadline_seconds=3_600,
                **kwargs,
            )
        ),
    )

    assert await dispatcher.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(ObservabilityDelivery)
                    .where(ObservabilityDelivery.task_id == task_id)
                    .order_by(ObservabilityDelivery.provider)
                )
            ).all()
        )
    assert [row.provider for row in rows] == ["langfuse", "langsmith"]
    assert {row.status for row in rows} == {"planned"}
    assert rows[0].provider_trace_id is not None
    assert rows[1].provider_trace_id is None
    assert all(row.verification_deadline is not None for row in rows)
    assert all(row.attempt_count == 0 for row in rows)
    assert "langsmith-intent-canary" not in repr(rows)
    assert "langfuse-intent-canary" not in repr(rows)

    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "succeeded"
    assert view["artifact"]["status"] == "committed"
    assert view["completion_scope"]["observability"] == "pending"
    assert "observability_delivery_pending" in view["warnings"]


async def queue_checkpoint_fork(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: str,
) -> tuple[ProductAnalysisService, UUID, UUID, UUID, str]:
    service, queued = await queue_task(
        session_factory,
        idempotency_key=f"{idempotency_key}-source-task",
    )
    task_id = UUID(str(queued["task_id"]))
    source_run_id = uuid4()
    checkpoint_id = f"checkpoint-{idempotency_key}"
    async with session_factory() as session, session.begin():
        task = await session.scalar(select(Task).where(Task.id == task_id))
        assert task is not None
        thread = await session.scalar(select(Thread).where(Thread.id == task.thread_id))
        assert thread is not None
        submit_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task.id,
                TaskCommand.command_type == "submit",
            )
        )
        assert submit_command is not None
        submit_command.status = "dispatched"
        task.status = "succeeded"
        task.completed_at = datetime.now(UTC)
        thread.official_thread_id = "official-fork-thread"
        session.add(
            Run(
                id=source_run_id,
                tenant_id=task.tenant_id,
                workspace_id=task.workspace_id,
                owner_user_id=task.owner_user_id,
                thread_id=task.thread_id,
                task_id=task.id,
                attempt=1,
                status="succeeded",
                official_assistant_id="official-assistant",
                official_run_id="official-fork-source-run",
                checkpoint_id=checkpoint_id,
                input_payload=task.request_payload,
                finished_at=datetime.now(UTC),
            )
        )

    accepted = await service.fork_task(
        actor(),
        str(task_id),
        ForkSubmission(source_run_id=source_run_id),
        idempotency_key,
    )
    assert accepted is not None
    async with session_factory() as session:
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "fork",
            )
        )
    assert command is not None
    return (
        service,
        task_id,
        source_run_id,
        UUID(str(command.payload["fork_run_id"])),
        checkpoint_id,
    )


async def queue_review_response(
    session_factory: async_sessionmaker[AsyncSession],
    task_id: UUID,
    response: dict[str, object],
) -> tuple[UUID, UUID]:
    async with session_factory() as session:
        projection = await session.scalar(
            select(InterruptProjection).where(
                InterruptProjection.task_id == task_id,
                InterruptProjection.status == "pending",
            )
        )
        assert projection is not None
        projection_id = projection.id
        interrupt_id = projection.official_interrupt_id
        response_version = projection.response_version
    service = ProductAnalysisService(session_factory=session_factory)
    accepted = await service.respond_interrupt(
        actor(),
        str(task_id),
        interrupt_id,
        InterruptResponseSubmission.model_validate(
            {"response_version": response_version, **response}
        ),
        f"respond:{projection_id}",
    )
    assert accepted is not None
    async with session_factory() as session:
        resumed_run_id = await session.scalar(
            select(Run.id).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
    assert resumed_run_id is not None
    return resumed_run_id, projection_id


def successful_terminal_output() -> dict[str, object]:
    source_url = "https://www.reuters.com/markets/currencies/"
    return {
        "terminal_status": "succeeded",
        "market_snapshot": complete_market_snapshot(),
        "web_evidence": [
            {
                "query": "current Bitcoin macro news",
                "final_url": source_url,
                "fetched_at": datetime(2026, 7, 13, 5, 55, tzinfo=UTC),
                "content_hash": "d" * 64,
                "title": "Bitcoin macro update",
                "source": "openai_builtin_web_search",
                "excerpt": "Verified macro evidence for the recovery test.",
                "evidence_relation": "supports",
            }
        ],
        "artifact": {
            "content_version": 1,
            "status": "committed",
            "analysis": valid_market_analysis(),
            "evidence_verdict": {"sufficient": True},
            "risk_verdict": {"allowed": True},
            "source_references": [source_url],
        },
        "errors": [],
    }


def model_invalid_terminal_output() -> dict[str, object]:
    market_snapshot = complete_market_snapshot()
    market_snapshot["source_level"] = "controlled_dependency"
    return {
        "terminal_status": "failed",
        "market_snapshot": market_snapshot,
        "web_evidence": [
            {
                "query": "controlled model invalid output",
                "final_url": (
                    "https://controlled-dependency.invalid/model-invalid-output"
                ),
                "fetched_at": datetime(2026, 7, 13, 5, 55, tzinfo=UTC),
                "content_hash": "0" * 64,
                "parser_version": "controlled-dependency-v1",
                "title": "Controlled dependency evidence",
                "source": "controlled_dependency_test",
                "excerpt": "Controlled input for the canonical model boundary.",
                "evidence_relation": "controlled_dependency",
            }
        ],
        "artifact": None,
        "errors": [
            {
                "code": "model_invalid_output",
                "error_type": "StructuredOutputValidationError",
                "retryable": False,
            }
        ],
    }


def blocked_terminal_output() -> dict[str, object]:
    output = deepcopy(successful_terminal_output())
    output["terminal_status"] = "blocked"
    artifact = output["artifact"]
    assert isinstance(artifact, dict)
    artifact["status"] = "draft"
    risk_verdict = artifact["risk_verdict"]
    assert isinstance(risk_verdict, dict)
    risk_verdict["allowed"] = False
    risk_verdict["blocked_reasons"] = ["Rejected during required human review."]
    risk_verdict["confidence_cap"] = "0"
    return output


def web_fallback_blocked_terminal_output() -> dict[str, object]:
    output = blocked_terminal_output()
    market_url = "https://finance.yahoo.com/quote/BTC-USD/"
    macro_url = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    output["market_snapshot"] = {
        "symbol": "BTC-USDT-SWAP",
        "fetched_at": datetime(2026, 7, 17, 8, 0, tzinfo=UTC),
        "source_level": "web_search_verified",
        "ticker": {"last": "64169.21"},
        "mark_price": None,
        "index_price": None,
        "funding_rate": None,
        "open_interest": None,
        "order_book": None,
        "candles": [],
    }
    output["web_evidence"] = [
        {
            "query": "What is the current BTC price in USD?",
            "final_url": market_url,
            "fetched_at": datetime(2026, 7, 17, 8, 0, tzinfo=UTC),
            "content_hash": "a" * 64,
            "parser_version": "openai-responses-open-page-v1",
            "title": "finance.yahoo.com",
            "source": "openai_builtin_web_search",
            "excerpt": f"Bitcoin is $64,169.21 USD ({market_url}).",
            "evidence_relation": "market_snapshot",
        },
        {
            "query": "current BTC macro events",
            "final_url": macro_url,
            "fetched_at": datetime(2026, 7, 17, 8, 1, tzinfo=UTC),
            "content_hash": "b" * 64,
            "title": "Federal Reserve calendar",
            "source": "openai_builtin_web_search",
            "excerpt": "The Federal Reserve calendar was checked for event risk.",
            "evidence_relation": "supports",
        },
    ]
    artifact = output["artifact"]
    assert isinstance(artifact, dict)
    artifact["source_references"] = [market_url, macro_url]
    artifact["provenance"] = {
        "market_provider": "web_search_market",
        "search_provider": "openai_builtin_web_search",
        "search_parser_version": (
            "openai-responses-citation-v1, openai-responses-open-page-v1"
        ),
        "model_provider": "openai-compatible",
        "model_name": "gpt-5.5",
        "model_endpoint_host": "model.example",
        "model_audits": [
            {
                "prompt_version": "web-market-extraction-v1",
                "call_count": 1,
                "latency_ms": 500,
            },
            {
                "prompt_version": "research-extraction-v1",
                "call_count": 1,
                "latency_ms": 600,
            },
            {
                "prompt_version": "market-analysis-v1",
                "call_count": 1,
                "latency_ms": 700,
            },
        ],
    }
    evidence_verdict = artifact["evidence_verdict"]
    assert isinstance(evidence_verdict, dict)
    evidence_verdict.update(
        {
            "sufficient": False,
            "confidence_cap": 0,
            "missing_required": [
                "exchange_native_market_data",
                "mark_price",
                "index_price",
                "order_book",
                "candles",
            ],
            "missing_optional": ["funding_rate", "open_interest"],
            "warnings": ["evidence.market_source:web_search_verified"],
        }
    )
    risk_verdict = artifact["risk_verdict"]
    assert isinstance(risk_verdict, dict)
    risk_verdict.update(
        {
            "allowed": False,
            "blocked_reasons": [
                "evidence.insufficient:exchange_native_market_data,mark_price,"
                "index_price,order_book,candles"
            ],
            "warnings": ["evidence.market_source:web_search_verified"],
            "confidence_cap": 0,
        }
    )
    return output


async def persisted_output_counts(
    session_factory: async_sessionmaker[AsyncSession],
    task_id: UUID,
) -> dict[str, int]:
    async with session_factory() as session:
        return {
            model.__tablename__: int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.task_id == task_id)
                )
                or 0
            )
            for model in (
                MarketSnapshot,
                WebEvidence,
                Artifact,
                ArtifactVersion,
                Decision,
            )
        }


async def assert_canonical_terminal_event(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: UUID,
) -> None:
    async with session_factory() as session:
        product_run = await session.get(Run, run_id)
        terminal_event = await session.scalar(
            select(DomainEvent)
            .where(
                DomainEvent.run_id == run_id,
                DomainEvent.event_type == "run.terminal",
            )
            .order_by(DomainEvent.sequence.desc())
            .limit(1)
        )
    assert product_run is not None
    assert terminal_event is not None
    assert product_run.output_payload is not None
    assert product_run.terminal_output_hash == terminal_event.payload_hash
    assert product_run.output_payload == terminal_event.payload


@pytest.mark.asyncio
async def test_model_invalid_output_persists_inputs_without_business_side_effects(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="model-invalid-output-persistence",
        notify=True,
    )
    runner = ModelInvalidOutputRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="model-invalid-output-worker",
    )

    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "failed"
    assert view["artifact"] is None
    assert view["market_snapshot"].source_level == "controlled_dependency"
    assert view["web_evidence"][0].source == "controlled_dependency_test"
    assert view["errors"] == [
        {
            "code": "model_invalid_output",
            "message": "分析模型未返回有效结构化结果，当前未生成分析结果。",
            "retryable": False,
            "correlation_id": view["correlation_id"],
            "error_type": "StructuredOutputValidationError",
        }
    ]

    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
        market = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.task_id == task_id)
        )
        evidence = await session.scalar(
            select(WebEvidence).where(WebEvidence.task_id == task_id)
        )
        outbox_count = await session.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.task_id == task_id)
        )
        attempt_count = await session.scalar(
            select(func.count())
            .select_from(NotificationAttempt)
            .where(NotificationAttempt.task_id == task_id)
        )

    assert product_run is not None
    assert command is not None
    assert market is not None
    assert evidence is not None
    assert product_run.status == "failed"
    assert product_run.observed_terminal_status == "success"
    assert product_run.failure_code == "model_invalid_output"
    assert product_run.output_payload["terminal_status"] == "failed"
    assert product_run.output_payload["errors"] == [
        {
            "code": "model_invalid_output",
            "error_type": "StructuredOutputValidationError",
            "retryable": False,
        }
    ]
    assert product_run.output_payload.get("artifact") is None
    assert (
        product_run.output_payload["market_snapshot"]["source_level"]
        == "controlled_dependency"
    )
    assert (
        product_run.output_payload["web_evidence"][0]["source"]
        == "controlled_dependency_test"
    )
    assert command.status == "dispatched"
    assert command.attempt == 1
    assert command.official_run_id == product_run.official_run_id == "official-run"
    assert market.run_id == product_run.id
    assert market.snapshot["source_level"] == "controlled_dependency"
    assert evidence.run_id == product_run.id
    assert evidence.payload["parser_version"] == "controlled-dependency-v1"
    assert evidence.payload["content_hash"] == "0" * 64
    assert await persisted_output_counts(session_factory, task_id) == {
        "market_snapshots": 1,
        "web_evidence": 1,
        "artifacts": 0,
        "artifact_versions": 0,
        "decisions": 0,
    }
    assert outbox_count == 0
    assert attempt_count == 0
    assert await dispatcher.dispatch_once() is False


@pytest.mark.asyncio
async def test_web_market_fallback_persists_citations_and_projects_blocked_draft(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="web-market-fallback-product-projection",
        notify=False,
    )
    runner = WebFallbackBlockedRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="web-market-fallback-worker",
    )

    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    view = await service.get_task(actor(), str(task_id))

    assert view is not None
    assert view["status"] == "blocked"
    assert view["market_snapshot"].source_level == "web_search_verified"
    assert view["market_snapshot"].ticker is not None
    assert str(view["market_snapshot"].ticker.last) == "64169.21"
    assert [item.evidence_relation for item in view["web_evidence"]] == [
        "market_snapshot",
        "supports",
    ]
    assert len({str(item.final_url) for item in view["web_evidence"]}) == 2
    assert view["artifact"] is not None
    assert view["artifact"]["status"] == "draft"
    assert view["artifact"]["provenance"]["market_provider"] == "web_search_market"
    assert view["artifact"]["risk_verdict"]["allowed"] is False
    assert view["artifact"]["source_references"] == [
        "https://finance.yahoo.com/quote/BTC-USD/",
        "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    ]

    async with session_factory() as session:
        persisted_market = list(
            (
                await session.scalars(
                    select(MarketSnapshot).where(MarketSnapshot.task_id == task_id)
                )
            ).all()
        )
        persisted_evidence = list(
            (
                await session.scalars(
                    select(WebEvidence)
                    .where(WebEvidence.task_id == task_id)
                    .order_by(WebEvidence.fetched_at)
                )
            ).all()
        )
        persisted_artifacts = int(
            await session.scalar(
                select(func.count())
                .select_from(Artifact)
                .where(Artifact.task_id == task_id)
            )
            or 0
        )

    assert len(persisted_market) == 1
    assert persisted_market[0].snapshot["source_level"] == "web_search_verified"
    assert len(persisted_evidence) == 2
    assert [item.payload["evidence_relation"] for item in persisted_evidence] == [
        "market_snapshot",
        "supports",
    ]
    assert persisted_artifacts == 0
    assert await dispatcher.dispatch_once() is False


@pytest.mark.asyncio
async def test_database_rollback_recovers_without_partial_product_rows(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="database-rollback-recovery",
        notify=True,
    )
    task_id = UUID(str(queued["task_id"]))
    clock = MutableClock()
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="database-rollback-recovery-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
    )

    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        remove_injection = install_database_failure_injection(
            connection.engine,
            controller,
        )
        try:
            controller.set(FailureInjectionScenario.DATABASE_ROLLBACK)
            assert await dispatcher.dispatch_once() is False

            queued_after_rollback = await service.get_task(actor(), str(task_id))
            assert queued_after_rollback is not None
            assert queued_after_rollback["status"] == "queued"
            assert queued_after_rollback["artifact"] is None
            async with session_factory() as session:
                retrying_run = await session.scalar(
                    select(Run).where(Run.task_id == task_id)
                )
                retrying_command = await session.scalar(
                    select(TaskCommand).where(TaskCommand.task_id == task_id)
                )
                outbox_count = await session.scalar(
                    select(func.count())
                    .select_from(NotificationOutbox)
                    .where(NotificationOutbox.task_id == task_id)
                )
                attempt_count = await session.scalar(
                    select(func.count())
                    .select_from(NotificationAttempt)
                    .where(NotificationAttempt.task_id == task_id)
                )
            assert retrying_run is not None
            assert retrying_command is not None
            assert retrying_run.status == "queued"
            assert retrying_run.failure_code == "terminal_projection_unavailable"
            assert retrying_run.output_payload is None
            assert retrying_command.status == "pending"
            assert retrying_command.attempt == 1
            assert await persisted_output_counts(session_factory, task_id) == {
                "market_snapshots": 0,
                "web_evidence": 0,
                "artifacts": 0,
                "artifact_versions": 0,
                "decisions": 0,
            }
            assert outbox_count == 0
            assert attempt_count == 0

            controller.reset()
            clock.now += timedelta(seconds=2)
            assert await dispatcher.dispatch_once() is True
        finally:
            remove_injection()

    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["artifact"]["status"] == "committed"
    async with session_factory() as session:
        completed_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        completed_command = await session.scalar(
            select(TaskCommand).where(TaskCommand.task_id == task_id)
        )
        outboxes = list(
            (
                await session.scalars(
                    select(NotificationOutbox).where(
                        NotificationOutbox.task_id == task_id
                    )
                )
            ).all()
        )
    assert completed_run is not None
    assert completed_command is not None
    assert completed_run.status == "succeeded"
    assert completed_run.failure_code is None
    assert completed_run.failure_message is None
    assert completed_command.status == "dispatched"
    assert completed_command.attempt == 2
    assert await persisted_output_counts(session_factory, task_id) == {
        "market_snapshots": 1,
        "web_evidence": 1,
        "artifacts": 1,
        "artifact_versions": 1,
        "decisions": 1,
    }
    assert len(outboxes) == 1


@pytest.mark.asyncio
async def test_database_rollback_exhaustion_fails_cleanly_and_product_retry_recovers(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="database-rollback-exhaustion",
        notify=True,
    )
    task_id = UUID(str(queued["task_id"]))
    clock = MutableClock()
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="database-rollback-exhaustion-worker",
        clock=clock,
        max_attempts=2,
        reconciliation_interval_seconds=1,
    )

    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        remove_injection = install_database_failure_injection(
            connection.engine,
            controller,
        )
        try:
            controller.set(FailureInjectionScenario.DATABASE_ROLLBACK)
            assert await dispatcher.dispatch_once() is False
            clock.now += timedelta(seconds=2)
            assert await dispatcher.dispatch_once() is False

            failed = await service.get_task(actor(), str(task_id))
            assert failed is not None
            assert failed["status"] == "failed"
            assert failed["artifact"] is None
            assert failed["errors"] == [
                {
                    "code": "terminal_projection_unavailable",
                    "message": "官方执行已结束，但暂时无法读取最终结果。",
                    "retryable": True,
                    "correlation_id": failed["correlation_id"],
                    "error_type": "DatabaseOperationalError",
                    "attempt": 2,
                }
            ]
            async with session_factory() as session:
                failed_run = await session.scalar(
                    select(Run).where(Run.task_id == task_id)
                )
                failed_command = await session.scalar(
                    select(TaskCommand).where(TaskCommand.task_id == task_id)
                )
                outbox_count = await session.scalar(
                    select(func.count())
                    .select_from(NotificationOutbox)
                    .where(NotificationOutbox.task_id == task_id)
                )
                attempt_count = await session.scalar(
                    select(func.count())
                    .select_from(NotificationAttempt)
                    .where(NotificationAttempt.task_id == task_id)
                )
                terminal_events = list(
                    (
                        await session.scalars(
                            select(DomainEvent)
                            .where(
                                DomainEvent.task_id == task_id,
                                DomainEvent.event_type == "run.terminal",
                            )
                            .order_by(DomainEvent.sequence)
                        )
                    ).all()
                )
            assert failed_run is not None
            assert failed_command is not None
            assert failed_run.status == "failed"
            assert failed_run.observed_terminal_status == "success"
            assert failed_run.failure_code == "terminal_projection_unavailable"
            assert failed_run.output_payload["errors"][0] == {
                "code": "terminal_projection_unavailable",
                "error_type": "DatabaseOperationalError",
                "retryable": True,
                "attempt": 2,
            }
            assert failed_run.terminal_output_hash == terminal_events[-1].payload_hash
            assert terminal_events[-1].payload == failed_run.output_payload
            assert failed_command.status == "failed"
            assert failed_command.attempt == 2
            assert await persisted_output_counts(session_factory, task_id) == {
                "market_snapshots": 0,
                "web_evidence": 0,
                "artifacts": 0,
                "artifact_versions": 0,
                "decisions": 0,
            }
            assert outbox_count == 0
            assert attempt_count == 0

            controller.reset()
            retried = await service.retry_task(
                actor(),
                str(task_id),
                "database-rollback-product-retry",
            )
            assert retried is not None
            assert retried["status"] == "queued"
            recovered_dispatcher = CommandDispatcher(
                session_factory=session_factory,
                runner=SuccessfulJoinRunner(
                    session_factory,
                    remote_run_id="database-rollback-retry-official-run",
                ),
                worker_id="database-rollback-product-retry-worker",
                clock=clock,
            )
            assert await recovered_dispatcher.dispatch_once() is True
        finally:
            remove_injection()

    recovered = await service.get_task(actor(), str(task_id))
    assert recovered is not None
    assert recovered["status"] == "succeeded"
    assert recovered["artifact"]["status"] == "committed"
    async with session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.task_id == task_id).order_by(Run.attempt)
                )
            ).all()
        )
        outboxes = list(
            (
                await session.scalars(
                    select(NotificationOutbox).where(
                        NotificationOutbox.task_id == task_id
                    )
                )
            ).all()
        )
    assert [run.status for run in runs] == ["failed", "succeeded"]
    assert runs[1].retry_of_run_id == runs[0].id
    assert runs[1].failure_code is None
    assert await persisted_output_counts(session_factory, task_id) == {
        "market_snapshots": 1,
        "web_evidence": 1,
        "artifacts": 1,
        "artifact_versions": 1,
        "decisions": 1,
    }
    assert len(outboxes) == 1
    assert outboxes[0].run_id == runs[1].id


@pytest.mark.asyncio
async def test_dispatcher_registers_official_run_before_join(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )

    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert runner.events == ["start", "get", "join"]
    assert runner.registered_handle == (
        "official-assistant",
        "official-thread",
        "official-run",
    )
    async with session_factory() as session:
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == UUID(str(queued["task_id"]))
            )
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == UUID(str(queued["task_id"])))
        )
    assert command is not None
    assert product_run is not None
    assert command.status == "dispatched"
    assert command.official_run_id == "official-run"
    assert command.lease_owner is None
    assert command.lease_expires_at is None
    assert product_run.reconciliation_deadline_at is not None
    assert product_run.projection_fence == command.attempt
    assert product_run.terminal_output_hash is not None
    assert len(product_run.terminal_output_hash) == 64


@pytest.mark.asyncio
async def test_expired_command_lease_is_reclaimed_and_old_owner_is_fenced(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    first_runner = InspectingRunner(session_factory)
    first = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="worker-a",
        clock=clock,
        lease_seconds=30,
    )
    stale_lease = await first.claim_next()
    assert stale_lease is not None

    clock.now += timedelta(seconds=31)
    second_runner = ReconcileOnlySubmitRunner(session_factory)
    second = CommandDispatcher(
        session_factory=session_factory,
        runner=second_runner,
        worker_id="worker-b",
        clock=clock,
        lease_seconds=30,
    )
    assert await second.dispatch_once() is True
    assert await first.execute(stale_lease) is False

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "succeeded"
    assert first_runner.events == []
    assert second_runner.start_requests == []
    assert len(second_runner.find_requests) == 1


@pytest.mark.asyncio
async def test_lost_registration_lease_is_recovered_without_cancelling_remote(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = LeaseExpiringRunner(session_factory, clock)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        lease_seconds=30,
    )

    assert await dispatcher.dispatch_once() is False

    assert runner.events == ["start"]
    assert runner.cancelled == []

    recovery_runner = ReconcileOnlySubmitRunner(session_factory)
    recovery_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=recovery_runner,
        worker_id="worker-b",
        clock=clock,
        lease_seconds=30,
    )
    assert await recovery_dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "succeeded"
    assert recovery_runner.start_requests == []
    assert len(recovery_runner.find_requests) == 1
    assert recovery_runner.cancelled == []


@pytest.mark.asyncio
async def test_running_remote_releases_lease_and_is_reclaimed_without_duplicate_start(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    clock = MutableClock()
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        reconciliation_interval_seconds=2,
    )

    assert await dispatcher.dispatch_once() is True
    assert runner.events == ["start", "get"]
    assert runner.cancelled == []
    assert await dispatcher.claim_next() is None

    runner.remote_status = "success"
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    assert runner.events == ["start", "get", "get", "join"]


@pytest.mark.asyncio
async def test_hanging_remote_get_releases_lease_for_later_reconciliation(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-hanging-get-reconciliation",
    )
    clock = MutableClock()
    runner = HangingGetRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="hanging-get-worker",
        clock=clock,
        remote_operation_timeout_seconds=0.05,
        reconciliation_interval_seconds=1,
    )

    assert await asyncio.wait_for(dispatcher.dispatch_once(), timeout=2) is True
    assert runner.get_cancelled is True
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        task = await session.get(Task, task_id)
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        command = await session.scalar(
            select(TaskCommand).where(TaskCommand.task_id == task_id)
        )
    assert task is not None and product_run is not None and command is not None
    assert task.status == "running"
    assert product_run.status == "running"
    assert product_run.official_run_id == "official-run"
    assert command.status == "dispatching"
    assert command.attempt == 1
    assert command.lease_owner is None
    assert command.lease_expires_at == clock.now + timedelta(seconds=1)
    assert await dispatcher.claim_next() is None

    runner.hang_get = False
    runner.remote_status = "success"
    clock.now += timedelta(seconds=2)
    assert await dispatcher.dispatch_once() is True

    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert runner.events == ["start", "get", "get", "join"]
    async with session_factory() as session:
        command = await session.scalar(
            select(TaskCommand).where(TaskCommand.task_id == task_id)
        )
    assert command is not None
    assert command.status == "dispatched"
    assert command.attempt == 2
    assert command.lease_owner is None
    assert command.lease_expires_at is None


@pytest.mark.asyncio
async def test_terminal_join_transport_error_keeps_product_run_reconcilable(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = TerminalJoinFailureRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        reconciliation_interval_seconds=2,
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "running"

    runner.fail_join = False
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"


@pytest.mark.asyncio
async def test_terminal_join_replay_does_not_duplicate_persisted_output(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, queued = await queue_task(session_factory)
    first_runner = SuccessfulJoinRunner(session_factory)
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="worker-a",
    )

    assert await first_dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    expected_counts = {
        "market_snapshots": 1,
        "web_evidence": 1,
        "artifacts": 1,
        "artifact_versions": 1,
        "decisions": 1,
    }
    assert await persisted_output_counts(session_factory, task_id) == expected_counts

    async with session_factory() as session, session.begin():
        task = await session.scalar(
            select(Task).where(Task.id == task_id).with_for_update()
        )
        command = await session.scalar(
            select(TaskCommand)
            .where(TaskCommand.task_id == task_id, TaskCommand.command_type == "submit")
            .with_for_update()
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).with_for_update()
        )
        assert task is not None
        assert command is not None
        assert product_run is not None
        terminal_output_hash = product_run.terminal_output_hash
        projection_fence = product_run.projection_fence
        assert terminal_output_hash is not None

        task.status = "running"
        task.completed_at = None
        product_run.status = "running"
        product_run.finished_at = None
        command.status = "pending"
        command.lease_owner = None
        command.lease_expires_at = None

    replay_runner = SuccessfulJoinRunner(session_factory)
    restarted_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=replay_runner,
        worker_id="worker-after-restart",
    )

    assert await restarted_dispatcher.dispatch_once() is True
    assert replay_runner.events == ["join"]
    assert await persisted_output_counts(session_factory, task_id) == expected_counts
    async with session_factory() as session:
        replayed_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert replayed_run is not None
    assert replayed_run.projection_fence == projection_fence
    assert replayed_run.terminal_output_hash == terminal_output_hash
    async with session_factory() as session:
        replayed_task = await session.scalar(select(Task).where(Task.id == task_id))
        replayed_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
    assert replayed_task is not None
    assert replayed_task.status == "succeeded"
    assert replayed_task.completed_at is not None
    assert replayed_run.status == "succeeded"
    assert replayed_run.finished_at is not None
    assert replayed_command is not None
    assert replayed_command.status == "dispatched"
    assert replayed_command.lease_owner is None
    assert replayed_command.lease_expires_at is None


@pytest.mark.asyncio
async def test_dispatcher_plans_notification_only_when_the_user_requested_it(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, silent = await queue_task(
        session_factory,
        idempotency_key="dispatcher-notify-disabled",
        notify=False,
    )
    silent_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="notification-disabled-worker",
    )
    assert await silent_dispatcher.dispatch_once() is True

    _, notified = await queue_task(
        session_factory,
        idempotency_key="dispatcher-notify-enabled",
        notify=True,
    )
    notified_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(
            session_factory,
            remote_run_id="official-run-notification-enabled",
            remote_thread_id="official-thread-notification-enabled",
        ),
        worker_id="notification-enabled-worker",
    )
    assert await notified_dispatcher.dispatch_once() is True

    async with session_factory() as session:
        silent_outbox = await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.task_id == UUID(str(silent["task_id"]))
            )
        )
        notified_outbox = await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.task_id == UUID(str(notified["task_id"]))
            )
        )
        silent_run_id = await session.scalar(
            select(Run.id).where(Run.task_id == UUID(str(silent["task_id"])))
        )
        notified_run_id = await session.scalar(
            select(Run.id).where(Run.task_id == UUID(str(notified["task_id"])))
        )
        silent_events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.run_id == silent_run_id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
        notified_events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.run_id == notified_run_id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
    assert silent_outbox is None
    assert notified_outbox is not None
    assert notified_outbox.status == "planned"
    assert notified_outbox.channel == "bark"
    assert notified_outbox.payload["task_id"] == notified["task_id"]
    assert [event.event_type for event in silent_events] == [
        "market.snapshot.committed",
        "research.evidence.committed",
        "agent.output.committed",
        "evidence.verdict.committed",
        "risk.verdict.committed",
        "artifact.committed",
        "run.terminal",
    ]
    assert [event.event_type for event in notified_events] == [
        "market.snapshot.committed",
        "research.evidence.committed",
        "agent.output.committed",
        "evidence.verdict.committed",
        "risk.verdict.committed",
        "artifact.committed",
        "notification.planned",
        "run.terminal",
    ]
    assert silent_run_id is not None
    assert notified_run_id is not None
    assert [event.sequence for event in silent_events] == list(
        range(silent_events[0].sequence, silent_events[0].sequence + 7)
    )
    assert [event.sequence for event in notified_events] == list(
        range(notified_events[0].sequence, notified_events[0].sequence + 8)
    )

    async with session_factory() as session, session.begin():
        await session.execute(
            delete(DomainEvent).where(DomainEvent.run_id == notified_run_id)
        )
    event_worker = DomainEventProjectionWorker(session_factory=session_factory)
    assert await event_worker.dispatch_once(run_id=notified_run_id) is True
    assert await event_worker.dispatch_once(run_id=notified_run_id) is False
    async with session_factory() as session:
        restored_events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.run_id == notified_run_id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
    assert [event.event_type for event in restored_events] == [
        event.event_type for event in notified_events
    ]


@pytest.mark.asyncio
async def test_progressive_updates_survive_a_later_official_run_failure(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, queued = await queue_task(
        session_factory,
        idempotency_key="progressive-late-failure",
        notify=False,
    )
    runner = ProgressiveLateFailureRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="progressive-late-failure-worker",
        stream_slice_seconds=2,
    )

    assert await dispatcher.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        assert product_run is not None
        events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.run_id == product_run.id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
        artifact_count = await session.scalar(
            select(func.count())
            .select_from(Artifact)
            .where(Artifact.task_id == task_id)
        )
        decision_count = await session.scalar(
            select(func.count())
            .select_from(Decision)
            .where(Decision.task_id == task_id)
        )

    assert product_run.status == "failed"
    assert product_run.official_stream_last_event_id == "progress-risk"
    assert product_run.official_stream_last_event_at is not None
    assert [event.event_type for event in events] == [
        "market.snapshot.committed",
        "research.evidence.committed",
        "agent.output.committed",
        "evidence.verdict.committed",
        "risk.verdict.committed",
        "run.terminal",
    ]
    assert [event.source_event_id for event in events[:-1]] == [
        "progress-market",
        "progress-research",
        "progress-analysis",
        "progress-evidence",
        "progress-risk",
    ]
    assert all(event.payload for event in events[:-1])
    assert all(event.payload_ref.endswith("/payload") for event in events)
    assert artifact_count == 0
    assert decision_count == 0
    assert runner.join_stream_last_event_ids == [None]

    market_part = runner.stream_parts[0]
    assert isinstance(market_part.data, dict)
    async with session_factory() as session, session.begin():
        task = await session.get(Task, task_id)
        replayed_run = await session.get(Run, product_run.id)
        assert task is not None
        assert replayed_run is not None
        assert (
            await append_progressive_events(
                session,
                task=task,
                run=replayed_run,
                updates=market_part.data,
                source_event_id="progress-market",
                checkpoint_id=None,
                created_at=datetime(2026, 7, 18, tzinfo=UTC),
            )
            == 0
        )

    changed_market_update = deepcopy(market_part.data)
    changed_market_update["collect_market_snapshot"]["market_snapshot"][
        "mark_price"
    ] = "64000"
    with pytest.raises(
        DomainEventProjectionConflict,
        match="immutable payload",
    ):
        async with session_factory() as session, session.begin():
            task = await session.get(Task, task_id)
            replayed_run = await session.get(Run, product_run.id)
            assert task is not None
            assert replayed_run is not None
            await append_progressive_events(
                session,
                task=task,
                run=replayed_run,
                updates=changed_market_update,
                source_event_id="progress-market",
                checkpoint_id=None,
                created_at=datetime(2026, 7, 18, tzinfo=UTC),
            )


@pytest.mark.asyncio
async def test_progressive_stream_resumes_from_the_committed_event_cursor(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, queued = await queue_task(
        session_factory,
        idempotency_key="progressive-cursor-resume",
        notify=False,
    )
    clock = MutableClock()
    runner = ProgressiveReconnectRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="progressive-cursor-worker",
        clock=clock,
        stream_slice_seconds=2,
        max_stream_events_per_slice=2,
    )

    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        first_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        assert first_run is not None
        first_event_types = list(
            (
                await session.scalars(
                    select(DomainEvent.event_type)
                    .where(DomainEvent.run_id == first_run.id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
    assert first_run.status == "running"
    assert first_run.official_stream_last_event_id == "progress-research"
    assert first_event_types == [
        "market.snapshot.committed",
        "research.evidence.committed",
    ]

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True

    clock.now += timedelta(seconds=3)
    runner.remote_status = "error"
    assert await dispatcher.dispatch_once() is True

    async with session_factory() as session:
        terminal_run = await session.get(Run, first_run.id)
        resumed_event_types = list(
            (
                await session.scalars(
                    select(DomainEvent.event_type)
                    .where(DomainEvent.run_id == first_run.id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
    assert terminal_run is not None
    assert terminal_run.status == "failed"
    assert terminal_run.official_stream_last_event_id == "progress-risk"
    assert resumed_event_types == [
        "market.snapshot.committed",
        "research.evidence.committed",
        "agent.output.committed",
        "evidence.verdict.committed",
        "risk.verdict.committed",
        "run.terminal",
    ]
    assert runner.join_stream_last_event_ids == [
        None,
        "progress-research",
        "progress-evidence",
    ]


@pytest.mark.asyncio
async def test_domain_event_sequence_is_atomic_across_runs_in_one_thread() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    actor = ActorContext(
        tenant_id=f"sequence-tenant-{suffix}",
        workspace_id=f"sequence-workspace-{suffix}",
        user_id=f"oidc|sequence-user-{suffix}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=session_factory)
    run_ids: tuple[UUID, UUID] | None = None
    try:
        await service.bootstrap_actor(actor)
        queued = await service.create_analysis(
            actor,
            AnalysisSubmission(
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="Verify concurrent event ordering.",
                notify=False,
            ),
            idempotency_key=f"sequence-first-{suffix}",
        )
        first_task_id = UUID(str(queued["task_id"]))
        second_task_id = uuid4()
        first_run_id = uuid4()
        second_run_id = uuid4()
        async with session_factory() as session, session.begin():
            first_task = await session.get(Task, first_task_id)
            assert first_task is not None
            first_task.status = "running"
            second_task = Task(
                id=second_task_id,
                tenant_id=first_task.tenant_id,
                workspace_id=first_task.workspace_id,
                owner_user_id=first_task.owner_user_id,
                thread_id=first_task.thread_id,
                task_type="analysis",
                status="running",
                idempotency_key=f"sequence-second-{suffix}",
                request_payload_hash="b" * 64,
                request_payload=deepcopy(first_task.request_payload),
            )
            session.add(second_task)
            await session.flush()
            session.add_all(
                [
                    Run(
                        id=first_run_id,
                        tenant_id=first_task.tenant_id,
                        workspace_id=first_task.workspace_id,
                        owner_user_id=first_task.owner_user_id,
                        thread_id=first_task.thread_id,
                        task_id=first_task.id,
                        attempt=1,
                        status="running",
                        official_run_id=f"sequence-run-a-{suffix}",
                        input_payload=deepcopy(first_task.request_payload),
                    ),
                    Run(
                        id=second_run_id,
                        tenant_id=first_task.tenant_id,
                        workspace_id=first_task.workspace_id,
                        owner_user_id=first_task.owner_user_id,
                        thread_id=first_task.thread_id,
                        task_id=second_task.id,
                        attempt=1,
                        status="running",
                        official_run_id=f"sequence-run-b-{suffix}",
                        input_payload=deepcopy(first_task.request_payload),
                    ),
                ]
            )
        run_ids = (first_run_id, second_run_id)

        async def append_one(task_id: UUID, run_id: UUID, event_id: str) -> None:
            async with session_factory() as session, session.begin():
                task = await session.get(Task, task_id)
                run = await session.get(Run, run_id)
                assert task is not None
                assert run is not None
                assert (
                    await append_progressive_events(
                        session,
                        task=task,
                        run=run,
                        updates={
                            "collect_market_snapshot": {
                                "market_snapshot": complete_market_snapshot(),
                                "lifecycle": "market_collected",
                            }
                        },
                        source_event_id=event_id,
                        checkpoint_id=None,
                        created_at=datetime(2026, 7, 18, tzinfo=UTC),
                    )
                    == 1
                )

        await asyncio.gather(
            append_one(first_task_id, first_run_id, "sequence-event-a"),
            append_one(second_task_id, second_run_id, "sequence-event-b"),
        )

        async with session_factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(DomainEvent)
                        .where(DomainEvent.run_id.in_(run_ids))
                        .order_by(DomainEvent.sequence)
                    )
                ).all()
            )
            thread = await session.get(Thread, events[0].thread_id)
        assert [event.sequence for event in events] == [1, 2]
        assert thread is not None
        assert thread.next_domain_event_sequence == 3
    finally:
        async with session_factory() as session, session.begin():
            await delete_actor_test_data(session, actor)
        await engine.dispose()


@pytest.mark.asyncio
async def test_retryable_notification_failure_preserves_complete_product_lineage(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="notification-failure-lineage",
        notify=True,
    )
    task_id = UUID(str(queued["task_id"]))
    destination_id = uuid4()
    cipher = NotificationCredentialCipher(
        key=b"n" * 32,
        key_version="controlled-notification-v1",
    )
    async with session_factory() as session, session.begin():
        task = await session.get(Task, task_id)
        assert task is not None
        session.add(
            NotificationDestination(
                id=destination_id,
                tenant_id=task.tenant_id,
                workspace_id=task.workspace_id,
                owner_user_id=task.owner_user_id,
                channel="bark",
                status="enabled",
                credential_ciphertext=cipher.encrypt(
                    SecretStr("controlled-device-key"),
                    destination_id=destination_id,
                    tenant_id=task.tenant_id,
                    workspace_id=task.workspace_id,
                    owner_user_id=task.owner_user_id,
                    channel="bark",
                ),
                credential_key_version=cipher.key_version,
            )
        )

    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="notification-failure-command-worker",
    )
    assert await dispatcher.dispatch_once() is True
    async with session_factory() as session, session.begin():
        planned = await session.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.task_id == task_id)
            .with_for_update()
        )
        assert planned is not None
        planned.available_at = datetime(1970, 1, 1, tzinfo=UTC)

    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(FailureInjectionScenario.NOTIFICATION_FAILURE)

        def unexpected_egress(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected Bark egress: {request.url.host}")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(unexpected_egress)
        ) as client:
            notification_worker = OutboxWorker(
                session_factory=session_factory,
                adapters={},
                adapter_resolver=DatabaseNotificationAdapterResolver(
                    session_factory=session_factory,
                    credential_cipher=cipher,
                    http_client=client,
                    failure_injection=controller,
                ),
                worker_id="notification-failure-outbox-worker",
            )
            assert await notification_worker.dispatch_once() is True

    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "succeeded"
    assert view["completion_scope"] == {
        "analysis": "complete",
        "notification": "retrying",
        "observability": "not_enabled",
    }
    assert view["warnings"] == ["notification_delivery_retrying"]
    assert view["artifact"]["status"] == "committed"

    async with session_factory() as session:
        tasks = list(
            (await session.scalars(select(Task).where(Task.id == task_id))).all()
        )
        runs = list(
            (await session.scalars(select(Run).where(Run.task_id == task_id))).all()
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand).where(TaskCommand.task_id == task_id)
                )
            ).all()
        )
        markets = list(
            (
                await session.scalars(
                    select(MarketSnapshot).where(MarketSnapshot.task_id == task_id)
                )
            ).all()
        )
        evidence = list(
            (
                await session.scalars(
                    select(WebEvidence).where(WebEvidence.task_id == task_id)
                )
            ).all()
        )
        artifacts = list(
            (
                await session.scalars(
                    select(Artifact).where(Artifact.task_id == task_id)
                )
            ).all()
        )
        versions = list(
            (
                await session.scalars(
                    select(ArtifactVersion).where(ArtifactVersion.task_id == task_id)
                )
            ).all()
        )
        decisions = list(
            (
                await session.scalars(
                    select(Decision).where(Decision.task_id == task_id)
                )
            ).all()
        )
        notifications = list(
            (
                await session.scalars(
                    select(NotificationOutbox).where(
                        NotificationOutbox.task_id == task_id
                    )
                )
            ).all()
        )
        attempts = list(
            (
                await session.scalars(
                    select(NotificationAttempt).where(
                        NotificationAttempt.task_id == task_id
                    )
                )
            ).all()
        )

    assert tuple(
        map(
            len,
            (
                tasks,
                runs,
                commands,
                markets,
                evidence,
                artifacts,
                versions,
                decisions,
                notifications,
                attempts,
            ),
        )
    ) == (1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
    task = tasks[0]
    run = runs[0]
    command = commands[0]
    artifact = artifacts[0]
    version = versions[0]
    decision = decisions[0]
    notification = notifications[0]
    attempt = attempts[0]
    assert task.status == run.status == "succeeded"
    assert task.request_payload["notify"] is True
    assert command.status == "dispatched"
    assert command.attempt == 1
    assert artifact.latest_version_number == 1
    assert version.status == "committed"
    assert version.version_number == decision.decision_version == 1
    assert version.artifact_id == decision.artifact_id == artifact.id
    assert version.id == decision.artifact_version_id
    assert version.run_id == decision.run_id == run.id
    assert notification.destination_id == destination_id
    assert notification.run_id == run.id
    assert notification.artifact_id == artifact.id
    assert notification.artifact_version_id == version.id
    assert notification.decision_id == decision.id
    assert notification.decision_version == decision.decision_version
    assert notification.status == "failed_retryable"
    assert notification.attempt_count == 1
    assert attempt.outbox_id == notification.id
    assert attempt.attempt_number == 1
    assert attempt.trigger == "automatic"
    assert attempt.result == "failed_retryable"
    assert attempt.reason == "injected_notification_failure"
    assert attempt.error_code == "injected_notification_failure"
    assert attempt.provider_receipt is None
    assert attempt.delay_seconds == 30


@pytest.mark.asyncio
async def test_conflicting_terminal_replay_is_failed_without_duplicate_output(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, queued = await queue_task(session_factory)
    first = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="first-worker",
    )
    assert await first.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    expected_counts = await persisted_output_counts(session_factory, task_id)
    async with session_factory() as session, session.begin():
        task = await session.scalar(
            select(Task).where(Task.id == task_id).with_for_update()
        )
        command = await session.scalar(
            select(TaskCommand)
            .where(TaskCommand.task_id == task_id, TaskCommand.command_type == "submit")
            .with_for_update()
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).with_for_update()
        )
        assert task is not None
        assert command is not None
        assert product_run is not None
        task.status = "running"
        task.completed_at = None
        product_run.status = "running"
        product_run.finished_at = None
        command.status = "pending"
        command.lease_owner = None
        command.lease_expires_at = None

    conflicting = CommandDispatcher(
        session_factory=session_factory,
        runner=ConflictingSuccessfulJoinRunner(session_factory),
        worker_id="conflicting-worker",
    )
    assert await conflicting.dispatch_once() is False

    async with session_factory() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id))
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        terminal_events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(
                        DomainEvent.task_id == task_id,
                        DomainEvent.event_type == "run.terminal",
                    )
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
    assert task is not None
    assert task.status == "failed"
    assert command is not None
    assert command.status == "failed"
    assert product_run is not None
    assert product_run.status == "failed"
    assert product_run.failure_code == "terminal_projection_conflict"
    assert len(terminal_events) == 2
    assert terminal_events[-1].payload == product_run.output_payload
    assert terminal_events[-1].payload_hash == product_run.terminal_output_hash
    assert await persisted_output_counts(session_factory, task_id) == expected_counts


@pytest.mark.asyncio
async def test_higher_command_sequence_fences_stale_terminal_projection(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
    )
    stale_submit_lease = await dispatcher.claim_next()
    assert stale_submit_lease is not None
    assert stale_submit_lease.command_sequence == 1
    assert await dispatcher.execute(stale_submit_lease) is True

    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-fences-stale-terminal",
    )
    assert await dispatcher.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session, session.begin():
        task = await session.scalar(
            select(Task).where(Task.id == task_id).with_for_update()
        )
        stale_command = await session.scalar(
            select(TaskCommand)
            .where(TaskCommand.id == stale_submit_lease.command_id)
            .with_for_update()
        )
        product_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).with_for_update()
        )
        assert task is not None
        assert stale_command is not None
        assert product_run is not None
        assert product_run.status == "cancelled"
        assert product_run.projection_fence == 2
        cancelled_output = product_run.output_payload
        cancelled_output_hash = product_run.terminal_output_hash

        task.status = "running"
        task.completed_at = None
        stale_command.status = "dispatching"
        stale_command.lease_owner = stale_submit_lease.worker_id
        stale_command.lease_expires_at = clock.now + timedelta(seconds=30)
        stale_command.attempt = stale_submit_lease.fence_token

    stale_terminal = TerminalGraphOutput.model_validate(successful_terminal_output())
    assert await dispatcher._finalize(stale_submit_lease, stale_terminal) is False

    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    assert product_run.status == "cancelled"
    assert product_run.projection_fence == 2
    assert product_run.output_payload == cancelled_output
    assert product_run.terminal_output_hash == cancelled_output_hash
    assert await persisted_output_counts(session_factory, task_id) == {
        "market_snapshots": 0,
        "web_evidence": 0,
        "artifacts": 0,
        "artifact_versions": 0,
        "decisions": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("persisted_winner", ("terminal_success", "cancel_intent"))
async def test_cancel_and_terminal_success_race_has_deterministic_owner(
    connection: AsyncConnection,
    persisted_winner: str,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key=f"race-{persisted_winner}",
    )
    runner: InspectingRunner
    if persisted_winner == "terminal_success":
        runner = SuccessfulJoinRunner(session_factory)
    else:
        runner = InspectingRunner(session_factory)
        runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="race-worker",
    )
    submit_lease = await dispatcher.claim_next()
    assert submit_lease is not None
    assert await dispatcher.execute(submit_lease) is True

    if persisted_winner == "terminal_success":
        with pytest.raises(TaskNotCancellableError):
            await service.cancel_task(
                actor(),
                str(queued["task_id"]),
                "cancel-after-terminal-success",
            )
        expected_status = "succeeded"
        expected_fence = 1
        expected_artifacts = 1
    else:
        await service.cancel_task(
            actor(),
            str(queued["task_id"]),
            "cancel-before-terminal-success",
        )
        late_success = TerminalGraphOutput.model_validate(successful_terminal_output())
        assert await dispatcher._finalize(submit_lease, late_success) is False
        runner.remote_status = "success"
        assert await dispatcher.dispatch_once() is True
        expected_status = "cancelled"
        expected_fence = 2
        expected_artifacts = 0

    task_id = UUID(str(queued["task_id"]))
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == expected_status
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    assert product_run.status == expected_status
    assert product_run.projection_fence == expected_fence
    counts = await persisted_output_counts(session_factory, task_id)
    assert counts["artifacts"] == expected_artifacts
    assert counts["artifact_versions"] == expected_artifacts


@pytest.mark.asyncio
async def test_worker_restart_uses_persisted_reconciliation_deadline(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    first_runner = InspectingRunner(session_factory)
    first_runner.remote_status = "running"
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="worker-before-restart",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_run_seconds=2,
    )

    assert await first_dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    persisted_deadline = product_run.reconciliation_deadline_at
    assert persisted_deadline == clock.now + timedelta(seconds=2)

    clock.now += timedelta(seconds=3)
    restarted_runner = InspectingRunner(session_factory)
    restarted_runner.remote_status = "running"
    restarted_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=restarted_runner,
        worker_id="worker-after-restart",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_run_seconds=3_600,
    )

    assert await restarted_dispatcher.dispatch_once() is True
    assert restarted_runner.events == ["get"]
    assert len(restarted_runner.cancelled) == 1
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_run_timeout"
    async with session_factory() as session:
        timed_out_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert timed_out_run is not None
    assert timed_out_run.reconciliation_deadline_at == persisted_deadline
    assert timed_out_run.output_payload is not None
    assert timed_out_run.output_payload["errors"][0]["error_type"] == (
        "OrphanDeadlineExceeded"
    )


@pytest.mark.asyncio
async def test_interrupted_remote_projects_waiting_human_without_join(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "waiting_human"
    assert runner.events == ["start", "get", "get_interrupts"]
    async with session_factory() as session:
        projection = await session.scalar(
            select(InterruptProjection).where(
                InterruptProjection.task_id == UUID(str(queued["task_id"]))
            )
        )
    assert projection is not None
    assert projection.status == "pending"
    assert projection.official_interrupt_id == "interrupt-official-run"
    assert projection.checkpoint_id == "checkpoint-official-run"
    assert projection.payload["kind"] == "artifact_review"
    assert projection.expires_at is not None


@pytest.mark.asyncio
async def test_deep_research_interrupt_projects_typed_scope_and_payload(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-deep-research-review",
        task_type="deep_research",
    )
    runner = InspectingRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-deep-research-review",
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["task_type"] == "deep_research"
    assert view["pending_interrupts"]["members"][0]["payload"]["kind"] == (
        "deep_research_review"
    )
    assert view["pending_interrupts"]["members"][0]["payload"]["symbol"] == (
        "BTC-USDT-SWAP"
    )
    assert (
        view["pending_interrupts"]["members"][0]["payload"]["artifact"]["status"]
        == "draft"
    )
    assert len(view["web_evidence"]) == 1
    assert view["web_evidence"][0].source == "test_search"
    assert str(view["web_evidence"][0].final_url) == (
        "https://example.com/verified-btc-source"
    )
    task_id = UUID(str(queued["task_id"]))
    assert await persisted_output_counts(session_factory, task_id) == {
        "market_snapshots": 0,
        "web_evidence": 1,
        "artifacts": 0,
        "artifact_versions": 0,
        "decisions": 0,
    }


@pytest.mark.asyncio
async def test_dispatcher_claims_checkpoint_fork_and_projects_terminal_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    (
        service,
        task_id,
        source_run_id,
        fork_run_id,
        checkpoint_id,
    ) = await queue_checkpoint_fork(
        session_factory,
        idempotency_key="dispatcher-fork",
    )
    runner = SuccessfulJoinRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="fork-worker",
    )

    lease = await dispatcher.claim_next()
    assert lease is not None
    assert lease.command_type == "fork"
    assert lease.product_run_id == fork_run_id
    assert lease.fork_payload is not None
    assert lease.fork_payload.source_run_id == source_run_id
    assert lease.fork_payload.checkpoint_id == checkpoint_id
    assert lease.fork_source_handle == RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id="official-fork-thread",
        run_id="official-fork-source-run",
    )
    assert await dispatcher.execute(lease) is True

    assert len(runner.fork_requests) == 1
    fork_request = runner.fork_requests[0]
    assert fork_request["product_run_id"] == str(fork_run_id)
    assert fork_request["checkpoint_id"] == checkpoint_id
    assert fork_request["handle"] == lease.fork_source_handle
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "succeeded"
    async with session_factory() as session:
        source_run = await session.get(Run, source_run_id)
        fork_run = await session.get(Run, fork_run_id)
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "fork",
            )
        )
    assert source_run is not None and fork_run is not None and command is not None
    assert fork_run.task_id == source_run.task_id == task_id
    assert fork_run.thread_id == source_run.thread_id
    assert fork_run.attempt == source_run.attempt + 1
    assert fork_run.forked_from_run_id == source_run.id
    assert fork_run.forked_from_checkpoint_id == checkpoint_id
    assert fork_run.official_run_id == f"forked-{fork_run_id}"
    assert fork_run.status == "succeeded"
    assert command.status == "dispatched"
    assert command.official_run_id == fork_run.official_run_id


@pytest.mark.asyncio
async def test_successful_fork_appends_artifact_and_decision_versions(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-versioned-fork-source",
    )
    runner = SuccessfulJoinRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="versioned-fork-worker",
    )

    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session, session.begin():
        source_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).with_for_update()
        )
        assert source_run is not None
        source_run.checkpoint_id = "checkpoint-version-1"
        source_run_id = source_run.id

    accepted = await service.fork_task(
        actor(),
        str(task_id),
        ForkSubmission(source_run_id=source_run_id),
        "dispatcher-versioned-fork",
    )
    assert accepted is not None
    assert await dispatcher.dispatch_once() is True

    async with session_factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(Artifact.task_id == task_id)
        )
        versions = list(
            (
                await session.scalars(
                    select(ArtifactVersion)
                    .where(ArtifactVersion.task_id == task_id)
                    .order_by(ArtifactVersion.version_number)
                )
            ).all()
        )
        decisions = list(
            (
                await session.scalars(
                    select(Decision)
                    .where(Decision.task_id == task_id)
                    .order_by(Decision.decision_version)
                )
            ).all()
        )
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.task_id == task_id).order_by(Run.attempt)
                )
            ).all()
        )

    assert artifact is not None
    assert artifact.latest_version_number == 2
    assert [version.version_number for version in versions] == [1, 2]
    assert [decision.decision_version for decision in decisions] == [1, 2]
    assert [version.run_id for version in versions] == [run.id for run in runs]
    assert [decision.run_id for decision in decisions] == [run.id for run in runs]
    assert all(version.artifact_id == artifact.id for version in versions)
    assert all(decision.artifact_id == artifact.id for decision in decisions)
    assert await persisted_output_counts(session_factory, task_id) == {
        "market_snapshots": 2,
        "web_evidence": 2,
        "artifacts": 1,
        "artifact_versions": 2,
        "decisions": 2,
    }


@pytest.mark.asyncio
async def test_retry_reuses_task_lineage_and_starts_a_new_official_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-retry-lineage",
    )
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=InspectingRunner(session_factory),
        worker_id="retry-worker-first",
    )
    assert await first_dispatcher.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        failed_run = await session.scalar(
            select(Run).where(Run.task_id == task_id).order_by(Run.attempt.desc())
        )
    assert failed_run is not None
    assert failed_run.status == "failed"

    retried = await service.retry_task(
        actor(),
        str(task_id),
        "retry-lineage-request",
    )
    assert retried is not None
    assert retried["status"] == "queued"

    second_runner = SuccessfulJoinRunner(
        session_factory,
        remote_run_id="retry-official-run",
    )
    second_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=second_runner,
        worker_id="retry-worker-second",
    )
    assert await second_dispatcher.dispatch_once() is True

    async with session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.task_id == task_id).order_by(Run.attempt)
                )
            ).all()
        )
        retry_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "retry",
            )
        )
    assert len(runs) == 2
    assert runs[0].status == "failed"
    assert runs[1].status == "succeeded"
    assert runs[1].retry_of_run_id == runs[0].id
    assert retry_command is not None
    assert retry_command.status == "dispatched"
    assert retry_command.payload["source_run_id"] == str(runs[0].id)
    assert retry_command.payload["retry_run_id"] == str(runs[1].id)
    replayed = await service.retry_task(
        actor(),
        str(task_id),
        "retry-lineage-request",
    )
    current = await service.get_task(actor(), str(task_id))
    assert replayed is not None
    assert current is not None
    current["projection_scope"] = {
        "mode": "selected_run",
        "selected_run_id": runs[1].id,
    }
    assert replayed == current


@pytest.mark.asyncio
async def test_fork_replacement_worker_reconciles_without_duplicate_create(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, task_id, _, fork_run_id, _ = await queue_checkpoint_fork(
        session_factory,
        idempotency_key="dispatcher-fork-reconcile",
    )
    clock = MutableClock()
    first_runner = IndeterminateForkRunner(session_factory)
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="fork-indeterminate-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
    )

    assert await first_dispatcher.dispatch_once() is False
    assert len(first_runner.fork_requests) == 1
    async with session_factory() as session:
        pending_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "fork",
            )
        )
        pending_run = await session.get(Run, fork_run_id)
    assert pending_command is not None and pending_run is not None
    assert pending_command.status == "pending"
    assert pending_run.status == "queued"
    assert pending_run.failure_code == "agent_fork_indeterminate"

    clock.now += timedelta(seconds=2)
    replacement_runner = ReconcileOnlyForkRunner(session_factory)
    replacement_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=replacement_runner,
        worker_id="fork-reconciliation-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
    )
    assert await replacement_dispatcher.dispatch_once() is True

    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert replacement_runner.fork_requests == []
    assert len(replacement_runner.find_requests) == 1
    assert replacement_runner.find_requests[0]["product_run_id"] == str(fork_run_id)
    async with session_factory() as session:
        fork_run = await session.get(Run, fork_run_id)
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "fork",
            )
        )
    assert fork_run is not None and command is not None
    assert fork_run.official_run_id == f"forked-{fork_run_id}"
    assert fork_run.failure_code is None
    assert command.status == "dispatched"
    assert command.attempt == 2


@pytest.mark.asyncio
async def test_submit_indeterminate_acceptance_reconciles_after_worker_restart(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-submit-indeterminate-restart",
    )
    clock = MutableClock()
    first_runner = IntentObservingSubmitRunner(session_factory)
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="submit-indeterminate-first-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )

    assert await first_dispatcher.dispatch_once() is False
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
    assert product_run is not None and command is not None
    assert product_run.failure_code == "agent_submit_indeterminate"
    assert product_run.official_run_id is None
    assert command.status == "pending"
    assert command.attempt == 1
    assert first_runner.events == [
        "intent:agent_submit_create_intent",
        "start",
    ]

    replacement_runner = ReconcileOnlySubmitRunner(session_factory)
    replacement_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=replacement_runner,
        worker_id="submit-indeterminate-replacement-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )
    clock.now += timedelta(seconds=2)
    assert await replacement_dispatcher.dispatch_once() is True

    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert replacement_runner.start_requests == []
    assert len(replacement_runner.find_requests) == 1
    async with session_factory() as session:
        persisted_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        persisted_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
    assert persisted_run is not None and persisted_command is not None
    assert persisted_run.official_run_id == f"submitted-{persisted_run.id}"
    assert persisted_run.failure_code is None
    assert persisted_command.status == "dispatched"
    assert persisted_command.attempt == 2


@pytest.mark.asyncio
async def test_expired_submit_uncertainty_fails_without_enabling_duplicate_create(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-submit-indeterminate-deadline",
    )
    clock = MutableClock()
    first_runner = IndeterminateSubmitRunner(session_factory)
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="submit-indeterminate-deadline-first",
        clock=clock,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )
    assert await first_dispatcher.dispatch_once() is False

    replacement_runner = ReconcileMissingSubmitRunner(session_factory)
    replacement_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=replacement_runner,
        worker_id="submit-indeterminate-deadline-replacement",
        clock=clock,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )
    clock.now += timedelta(seconds=31)
    assert await replacement_dispatcher.dispatch_once() is False

    task_id = UUID(str(queued["task_id"]))
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_submit_indeterminate"
    assert view["errors"][0]["retryable"] is False
    assert replacement_runner.find_requests
    assert replacement_runner.start_requests == []
    async with session_factory() as session:
        product_run_id = await session.scalar(
            select(Run.id).where(Run.task_id == task_id)
        )
    assert product_run_id is not None
    await assert_canonical_terminal_event(session_factory, product_run_id)


@pytest.mark.asyncio
async def test_pre_accept_failure_exhaustion_commits_canonical_terminal_event(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-submit-pre-accept-exhaustion",
    )
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=AlwaysPreAcceptFailureSubmitRunner(session_factory),
        worker_id="submit-pre-accept-exhaustion-worker",
        max_attempts=1,
    )

    assert await dispatcher.dispatch_once() is False

    task_id = UUID(str(queued["task_id"]))
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_server_unavailable"
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    assert product_run.projection_fence == 1
    await assert_canonical_terminal_event(session_factory, product_run.id)


@pytest.mark.asyncio
async def test_submit_remote_deadline_enters_reconcile_only_recovery(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-submit-operation-timeout",
    )
    runner = HangingStartRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="submit-timeout-worker",
        remote_operation_timeout_seconds=0.05,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )

    assert await asyncio.wait_for(dispatcher.dispatch_once(), timeout=2) is False
    assert runner.events == ["start"]
    task_id = UUID(str(queued["task_id"]))
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "queued"
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
    assert product_run is not None and command is not None
    assert product_run.failure_code == "agent_submit_indeterminate"
    assert command.status == "pending"


@pytest.mark.asyncio
async def test_submit_pre_accept_connection_failure_remains_retryable(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="dispatcher-submit-pre-accept-retry",
    )
    clock = MutableClock()
    runner = PreAcceptFailureSubmitRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="submit-pre-accept-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
    )

    assert await dispatcher.dispatch_once() is False
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        failed_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        failed_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "submit",
            )
        )
    assert failed_run is not None and failed_command is not None
    assert failed_run.failure_code == "agent_server_unavailable"
    assert failed_command.status == "dispatching"
    assert failed_command.lease_expires_at == clock.now

    assert await dispatcher.dispatch_once() is True
    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "failed"
    assert runner.events == ["start-failed-before-accept", "start", "get", "join"]


@pytest.mark.asyncio
async def test_fork_operation_deadline_enters_reconcile_only_recovery(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, task_id, _, fork_run_id, _ = await queue_checkpoint_fork(
        session_factory,
        idempotency_key="dispatcher-fork-operation-timeout",
    )
    runner = HangingForkRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="fork-timeout-worker",
        remote_operation_timeout_seconds=0.05,
        reconciliation_interval_seconds=1,
    )

    assert await asyncio.wait_for(dispatcher.dispatch_once(), timeout=2) is False
    assert len(runner.fork_requests) == 1
    assert runner.cancelled is True
    async with session_factory() as session:
        pending_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "fork",
            )
        )
        pending_run = await session.get(Run, fork_run_id)
    assert pending_command is not None and pending_run is not None
    assert pending_command.status == "pending"
    assert pending_run.status == "queued"
    assert pending_run.failure_code == "agent_fork_indeterminate"


@pytest.mark.asyncio
async def test_fork_failure_exhaustion_commits_canonical_terminal_event(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, task_id, _, fork_run_id, _ = await queue_checkpoint_fork(
        session_factory,
        idempotency_key="dispatcher-fork-failure-exhaustion",
    )
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=PermanentForkFailureRunner(session_factory),
        worker_id="fork-failure-exhaustion-worker",
        max_attempts=1,
    )

    assert await dispatcher.dispatch_once() is False

    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_fork_failed"
    await assert_canonical_terminal_event(session_factory, fork_run_id)


@pytest.mark.asyncio
async def test_invalid_persisted_fork_command_fails_with_canonical_safe_output(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, task_id, _, fork_run_id, _ = await queue_checkpoint_fork(
        session_factory,
        idempotency_key="dispatcher-invalid-fork-command",
    )
    async with session_factory() as session, session.begin():
        command = await session.scalar(
            select(TaskCommand)
            .where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "fork",
            )
            .with_for_update()
        )
        assert command is not None
        command.payload = {"source_run_id": "invalid-sensitive-looking-value"}
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=SuccessfulJoinRunner(session_factory),
        worker_id="invalid-fork-command-worker",
    )

    assert await dispatcher.dispatch_once() is False

    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "invalid_fork_command"
    async with session_factory() as session:
        fork_run = await session.get(Run, fork_run_id)
    assert fork_run is not None
    assert "invalid-sensitive-looking-value" not in (fork_run.failure_message or "")
    await assert_canonical_terminal_event(session_factory, fork_run_id)


@pytest.mark.asyncio
async def test_required_review_resumes_official_run_and_projects_approval(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    async with session_factory() as session, session.begin():
        task = await session.scalar(
            select(Task).where(Task.id == UUID(str(queued["task_id"])))
        )
        assert task is not None
        workspace = await session.scalar(
            select(Workspace).where(Workspace.id == task.workspace_id).with_for_update()
        )
        assert workspace is not None
        workspace.review_policy = "required"

    runner = ReviewAwareRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="review-approval-worker",
    )
    assert await dispatcher.dispatch_once() is True
    assert runner.start_requests[0]["review_policy"] == "required"

    task_id = UUID(str(queued["task_id"]))
    responding = await service.respond_interrupt(
        actor(),
        str(task_id),
        "interrupt-official-run",
        InterruptResponseSubmission(
            response_version=1,
            action="approve",
            comment="Evidence and risk are acceptable.",
        ),
        "approve-required-review",
    )
    assert responding is not None
    assert responding["status"] == "waiting_human"
    async with session_factory() as session:
        resumed_run_id = await session.scalar(
            select(Run.id).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
        projection_id = await session.scalar(
            select(InterruptProjection.id).where(InterruptProjection.task_id == task_id)
        )
    assert resumed_run_id is not None
    assert projection_id is not None
    runner.remote_status = "success"
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "succeeded"
    assert view["artifact"]["status"] == "committed"
    assert runner.events == [
        "start",
        "get",
        "get_interrupts",
        "resume",
        "get",
        "join",
    ]
    checkpoint = runner.resume_requests[0]["checkpoint"]
    assert isinstance(checkpoint, RemoteCheckpoint)
    assert checkpoint.checkpoint_id == "checkpoint-official-run"
    assert runner.resume_requests[0]["responses"] == {
        "interrupt-official-run": {
            "action": "approve",
            "comment": "Evidence and risk are acceptable.",
        }
    }
    async with session_factory() as session:
        resumed_run = await session.get(Run, resumed_run_id)
        projection = await session.get(InterruptProjection, projection_id)
    assert resumed_run is not None
    assert resumed_run.status == "succeeded"
    assert resumed_run.official_run_id == f"resumed-{resumed_run_id}"
    assert resumed_run.resume_of_run_id is not None
    assert projection is not None
    assert projection.status == "resolved"


@pytest.mark.asyncio
async def test_multi_interrupt_pause_resumes_once_and_resolves_atomically(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="multi-interrupt-dispatch",
    )
    runner = MultiInterruptRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="multi-interrupt-worker",
    )

    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    pause_view = waiting["pending_interrupts"]
    assert pause_view is not None
    assert pause_view["status"] == "pending"
    assert len(pause_view["members"]) == 2
    assert {member["interrupt_id"] for member in pause_view["members"]} == {
        "interrupt-official-run",
        "nested-official-run",
    }
    assert all(
        "namespace" not in member and "checkpoint_id" not in member
        for member in pause_view["members"]
    )

    submission = InterruptResponsesSubmission.model_validate(
        {
            "pause_id": pause_view["pause_id"],
            "pause_version": pause_view["pause_version"],
            "responses": [
                {
                    "interrupt_id": member["interrupt_id"],
                    "response_version": member["response_version"],
                    "response": {"action": "approve"},
                }
                for member in pause_view["members"]
            ],
        }
    )
    accepted = await service.respond_interrupts(
        actor(),
        str(task_id),
        submission,
        "multi-interrupt-approve",
    )
    assert accepted is not None
    assert accepted["pending_interrupts"]["status"] == "responding"

    resume_lease = await dispatcher.claim_next()
    assert resume_lease is not None
    assert resume_lease.command_type == "respond"
    resuming = await service.get_task(actor(), str(task_id))
    assert resuming is not None
    assert resuming["status"] == "waiting_human"
    assert resuming["pending_interrupts"]["status"] == "responding"

    runner.remote_status = "success"
    assert await dispatcher.execute(resume_lease) is True
    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["pending_interrupts"] is None

    assert runner.events.count("resume") == 1
    assert len(runner.resume_requests) == 1
    assert set(runner.resume_requests[0]["responses"]) == {
        "interrupt-official-run",
        "nested-official-run",
    }
    checkpoint = runner.resume_requests[0]["checkpoint"]
    assert isinstance(checkpoint, RemoteCheckpoint)
    assert checkpoint.checkpoint_ns == ""
    assert checkpoint.checkpoint_id == "checkpoint-official-run"
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        resume_run_count = await session.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.task_id == task_id, Run.resume_of_run_id.is_not(None))
        )
        respond_command_count = await session.scalar(
            select(func.count())
            .select_from(TaskCommand)
            .where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert pause is not None
    assert pause.status == "resolved"
    assert {projection.status for projection in projections} == {"resolved"}
    assert resume_run_count == 1
    assert respond_command_count == 1


@pytest.mark.asyncio
async def test_interrupt_set_over_public_limit_fails_before_pause_persistence(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="interrupt-set-over-public-limit",
    )
    runner = OverLimitInterruptRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="interrupt-set-over-public-limit-worker",
    )

    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    failed = await service.get_task(actor(), str(task_id))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["pending_interrupts"] is None
    assert failed["errors"][0]["code"] == "interrupt_member_limit_exceeded"
    async with session_factory() as session:
        pause_count = await session.scalar(
            select(func.count())
            .select_from(InterruptPause)
            .where(InterruptPause.task_id == task_id)
        )
        projection_count = await session.scalar(
            select(func.count())
            .select_from(InterruptProjection)
            .where(InterruptProjection.task_id == task_id)
        )
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        command = await session.scalar(
            select(TaskCommand).where(TaskCommand.task_id == task_id)
        )
    assert pause_count == 0
    assert projection_count == 0
    assert product_run is not None
    assert product_run.status == "failed"
    assert product_run.failure_code == "interrupt_member_limit_exceeded"
    assert product_run.finished_at is not None
    assert command is not None
    assert command.status == "dispatched"
    assert command.lease_owner is None
    assert command.lease_expires_at is None


@pytest.mark.asyncio
async def test_multi_interrupt_pause_expires_and_resumes_as_one_batch(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="multi-interrupt-expiry",
    )
    clock = MutableClock()
    runner = MultiReviewAwareRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="multi-interrupt-expiry-worker",
        clock=clock,
        interrupt_ttl_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert pause is not None
    assert pause.status == "expired"
    assert len(projections) == 2
    assert {projection.status for projection in projections} == {"expired"}
    assert command is not None
    assert command.payload["expired"] is True
    assert len(command.payload["responses"]) == 2

    runner.remote_status = "success"
    assert await dispatcher.dispatch_once() is True
    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "blocked"
    assert len(runner.resume_requests) == 1
    assert set(runner.resume_requests[0]["responses"]) == {
        "interrupt-official-run",
        "nested-official-run",
    }
    assert {
        response["action"]
        for response in runner.resume_requests[0]["responses"].values()
    } == {"reject"}


@pytest.mark.asyncio
async def test_expired_multi_resume_failure_retries_same_automatic_rejection(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="expired-multi-resume-retry",
    )
    clock = MutableClock()
    clock.now = datetime.now(UTC)
    runner = FailingResumeMultiRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="expired-multi-resume-retry-worker",
        clock=clock,
        max_attempts=1,
        reconciliation_interval_seconds=1,
        interrupt_ttl_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    async with session_factory() as session:
        original_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert original_command is not None
    original_payload = deepcopy(original_command.payload)
    original_hash = original_command.payload_hash

    assert await dispatcher.dispatch_once() is False
    assert await dispatcher.claim_next() is None
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
        resumed_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
    assert pause is not None
    assert pause.status == "expired"
    assert {projection.status for projection in projections} == {"expired"}
    assert command is not None
    assert command.status == "pending"
    assert command.attempt == 1
    assert command.lease_owner is None
    assert command.lease_expires_at is not None
    assert command.lease_expires_at > clock.now
    assert command.payload == original_payload
    assert command.payload_hash == original_hash
    assert resumed_run is not None
    assert resumed_run.status == "queued"

    runner.fail_resume = False
    runner.remote_status = "success"
    clock.now += timedelta(seconds=2)
    assert await dispatcher.dispatch_once() is True
    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "blocked"
    assert len(runner.resume_requests) == 2
    assert (
        runner.resume_requests[0]["responses"] == runner.resume_requests[1]["responses"]
    )


@pytest.mark.asyncio
async def test_expired_multi_resume_failure_exhausts_bounded_retry_budget(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="expired-multi-resume-exhaustion",
    )
    clock = MutableClock()
    clock.now = datetime.now(UTC)
    runner = FailingResumeMultiRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="expired-multi-resume-exhaustion-worker",
        clock=clock,
        max_attempts=1,
        max_cancel_attempts=2,
        reconciliation_interval_seconds=1,
        interrupt_ttl_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    assert await dispatcher.dispatch_once() is False
    assert await dispatcher.claim_next() is None

    clock.now += timedelta(seconds=2)
    assert await dispatcher.dispatch_once() is False

    failed = await service.get_task(actor(), str(task_id))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["pending_interrupts"] is None
    assert failed["errors"][0]["code"] == "agent_resume_failed"
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        resumed_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert pause is not None
    assert pause.status == "resume_failed"
    assert {projection.status for projection in projections} == {"expired"}
    assert resumed_run is not None
    assert resumed_run.status == "failed"
    assert resumed_run.failure_code == "agent_resume_failed"
    assert command is not None
    assert command.status == "failed"
    assert command.attempt == 2
    assert command.lease_owner is None
    assert command.lease_expires_at is None
    assert len(runner.resume_requests) == 2


@pytest.mark.asyncio
async def test_failed_multi_resume_retries_same_command_without_reopening_decisions(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="multi-interrupt-resume-retry",
    )
    runner = FailingResumeMultiRunner(session_factory)
    runner.remote_status = "interrupted"
    clock = MutableClock()
    clock.now = datetime.now(UTC)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="multi-interrupt-resume-retry-worker",
        clock=clock,
        max_attempts=2,
        reconciliation_interval_seconds=1,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    pause_view = waiting["pending_interrupts"]
    assert pause_view is not None
    accepted = await service.respond_interrupts(
        actor(),
        str(task_id),
        InterruptResponsesSubmission.model_validate(
            {
                "pause_id": pause_view["pause_id"],
                "pause_version": pause_view["pause_version"],
                "responses": [
                    {
                        "interrupt_id": member["interrupt_id"],
                        "response_version": member["response_version"],
                        "response": {"action": "approve"},
                    }
                    for member in pause_view["members"]
                ],
            }
        ),
        "multi-interrupt-resume-retry-response",
    )
    assert accepted is not None

    assert await dispatcher.dispatch_once() is False
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.task_id == task_id).order_by(Run.attempt)
                )
            ).all()
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand).where(
                        TaskCommand.task_id == task_id,
                        TaskCommand.command_type == "respond",
                    )
                )
            ).all()
        )
    assert pause is not None
    assert pause.status == "responding"
    assert {projection.status for projection in projections} == {"responding"}
    assert len(runs) == 2
    assert len(commands) == 1
    assert commands[0].status == "pending"
    assert runs[1].status == "queued"

    runner.fail_resume = False
    runner.remote_status = "success"
    clock.now += timedelta(seconds=2)
    assert await dispatcher.dispatch_once() is True
    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert runner.events.count("resume") == 2
    async with session_factory() as session:
        run_count = await session.scalar(
            select(func.count()).select_from(Run).where(Run.task_id == task_id)
        )
        command_count = await session.scalar(
            select(func.count())
            .select_from(TaskCommand)
            .where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert run_count == 2
    assert command_count == 1


@pytest.mark.asyncio
async def test_resume_create_intent_survives_worker_restart_without_second_create(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="resume-create-intent-restart",
    )
    clock = MutableClock()
    clock.now = datetime.now(UTC)
    first_runner = IndeterminateResumeMultiRunner(session_factory)
    first_runner.remote_status = "interrupted"
    first_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=first_runner,
        worker_id="resume-create-intent-first-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )
    assert await first_dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    pause_view = waiting["pending_interrupts"]
    assert pause_view is not None
    await service.respond_interrupts(
        actor(),
        str(task_id),
        InterruptResponsesSubmission.model_validate(
            {
                "pause_id": pause_view["pause_id"],
                "pause_version": pause_view["pause_version"],
                "responses": [
                    {
                        "interrupt_id": member["interrupt_id"],
                        "response_version": member["response_version"],
                        "response": {"action": "approve"},
                    }
                    for member in pause_view["members"]
                ],
            }
        ),
        "resume-create-intent-restart-response",
    )

    assert await first_dispatcher.dispatch_once() is False
    assert len(first_runner.resume_requests) == 1
    async with session_factory() as session:
        resume_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
    assert resume_run is not None
    assert resume_run.failure_code == "agent_resume_indeterminate"
    assert resume_run.official_run_id is None

    replacement_runner = ReconcileOnlyResumeMultiRunner(
        session_factory,
        visible_after=2,
    )
    replacement_runner.remote_status = "success"
    replacement_dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=replacement_runner,
        worker_id="resume-create-intent-replacement-worker",
        clock=clock,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )
    clock.now += timedelta(seconds=2)
    assert await replacement_dispatcher.dispatch_once() is False
    clock.now += timedelta(seconds=2)
    assert await replacement_dispatcher.dispatch_once() is True

    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert replacement_runner.resume_requests == []
    assert replacement_runner.find_calls == 2
    async with session_factory() as session:
        resume_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand).where(
                        TaskCommand.task_id == task_id,
                        TaskCommand.command_type == "respond",
                    )
                )
            ).all()
        )
    assert resume_run is not None
    assert resume_run.official_run_id == f"resumed-{resume_run.id}"
    assert resume_run.failure_code is None
    assert len(commands) == 1
    assert commands[0].official_run_id == resume_run.official_run_id


@pytest.mark.asyncio
async def test_hanging_resume_and_find_preserve_indeterminate_reconciliation(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="hanging-resume-reconciliation",
    )
    clock = MutableClock()
    clock.now = datetime.now(UTC)
    runner = HangingResumeReconcileRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="hanging-resume-worker",
        clock=clock,
        remote_operation_timeout_seconds=0.05,
        reconciliation_interval_seconds=1,
        max_run_seconds=30,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    pause_view = waiting["pending_interrupts"]
    assert pause_view is not None
    await service.respond_interrupts(
        actor(),
        str(task_id),
        InterruptResponsesSubmission.model_validate(
            {
                "pause_id": pause_view["pause_id"],
                "pause_version": pause_view["pause_version"],
                "responses": [
                    {
                        "interrupt_id": member["interrupt_id"],
                        "response_version": member["response_version"],
                        "response": {"action": "approve"},
                    }
                    for member in pause_view["members"]
                ],
            }
        ),
        "hanging-resume-response",
    )

    assert await asyncio.wait_for(dispatcher.dispatch_once(), timeout=2) is False
    assert runner.resume_cancelled is True
    async with session_factory() as session:
        task = await session.get(Task, task_id)
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        resume_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert task is not None and pause is not None
    assert resume_run is not None and command is not None
    assert task.status == "waiting_human"
    assert pause.status == "responding"
    assert {projection.status for projection in projections} == {"responding"}
    assert resume_run.status == "queued"
    assert resume_run.failure_code == "agent_resume_indeterminate"
    assert resume_run.official_run_id is None
    assert command.status == "pending"
    assert command.attempt == 1
    assert command.lease_owner is None
    assert command.lease_expires_at == clock.now + timedelta(seconds=1)

    runner.remote_status = "success"
    clock.now += timedelta(seconds=2)
    assert await asyncio.wait_for(dispatcher.dispatch_once(), timeout=2) is False
    assert runner.find_cancelled is True
    async with session_factory() as session:
        resume_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert resume_run is not None and command is not None
    assert resume_run.status == "queued"
    assert resume_run.failure_code == "agent_resume_indeterminate"
    assert resume_run.official_run_id is None
    assert command.status == "pending"
    assert command.attempt == 2
    assert command.lease_owner is None
    assert command.lease_expires_at == clock.now + timedelta(seconds=1)
    assert len(runner.resume_requests) == 1

    clock.now += timedelta(seconds=2)
    assert await dispatcher.dispatch_once() is True

    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert runner.find_calls == 2
    assert len(runner.resume_requests) == 1
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        resume_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
        command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert pause is not None and resume_run is not None and command is not None
    assert pause.status == "resolved"
    assert {projection.status for projection in projections} == {"resolved"}
    assert resume_run.status == "succeeded"
    assert resume_run.failure_code is None
    assert resume_run.official_run_id == f"resumed-{resume_run.id}"
    assert command.status == "dispatched"
    assert command.attempt == 3
    assert command.lease_owner is None
    assert command.lease_expires_at is None


@pytest.mark.asyncio
async def test_user_resume_permanent_failure_closes_accepted_batch_atomically(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="multi-interrupt-resume-exhaustion",
    )
    clock = MutableClock()
    clock.now = datetime.now(UTC)
    runner = FailingResumeMultiRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="multi-interrupt-resume-exhaustion-worker",
        clock=clock,
        max_attempts=2,
        reconciliation_interval_seconds=1,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    pause_view = waiting["pending_interrupts"]
    assert pause_view is not None
    responses = [
        {
            "interrupt_id": member["interrupt_id"],
            "response_version": member["response_version"],
            "response": {"action": "approve", "comment": "Accepted decision"},
        }
        for member in pause_view["members"]
    ]
    accepted = await service.respond_interrupts(
        actor(),
        str(task_id),
        InterruptResponsesSubmission.model_validate(
            {
                "pause_id": pause_view["pause_id"],
                "pause_version": pause_view["pause_version"],
                "responses": responses,
            }
        ),
        "multi-interrupt-resume-exhaustion-response",
    )
    assert accepted is not None

    assert await dispatcher.dispatch_once() is False
    clock.now += timedelta(seconds=2)
    assert await dispatcher.dispatch_once() is False

    failed = await service.get_task(actor(), str(task_id))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["pending_interrupts"] is None
    assert failed["errors"][0]["code"] == "agent_resume_failed"
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.task_id == task_id).order_by(Run.attempt)
                )
            ).all()
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand).where(
                        TaskCommand.task_id == task_id,
                        TaskCommand.command_type == "respond",
                    )
                )
            ).all()
        )
    async with session_factory() as session:
        terminal_events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(
                        DomainEvent.run_id == runs[-1].id,
                        DomainEvent.event_type == "run.terminal",
                    )
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
    assert pause is not None
    assert pause.status == "resume_failed"
    assert {projection.status for projection in projections} == {"responding"}
    assert {projection.response["action"] for projection in projections} == {"approve"}
    assert all(projection.responded_at is not None for projection in projections)
    assert len(runs) == 2
    assert runs[1].status == "failed"
    assert runs[1].failure_code == "agent_resume_failed"
    assert runs[1].finished_at is not None
    assert runs[1].terminal_output_hash == terminal_events[-1].payload_hash
    assert terminal_events[-1].payload == runs[1].output_payload
    assert len(commands) == 1
    assert commands[0].status == "failed"
    assert commands[0].attempt == 2
    assert commands[0].lease_owner is None
    assert commands[0].lease_expires_at is None
    assert len(runner.resume_requests) == 2


@pytest.mark.asyncio
async def test_cancelling_multi_interrupt_pause_removes_every_active_member(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="multi-interrupt-cancel",
    )
    runner = MultiInterruptRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="multi-interrupt-cancel-worker",
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))

    cancelled = await service.cancel_task(
        actor(),
        str(task_id),
        "cancel-multi-interrupt-pause",
    )
    assert cancelled is not None
    assert await dispatcher.dispatch_once() is True

    task_view = await service.get_task(actor(), str(task_id))
    assert task_view is not None
    assert task_view["status"] == "cancelled"
    assert task_view["pending_interrupts"] is None
    inbox = await service.list_inbox(
        actor(),
        status="active",
        limit=50,
        cursor=None,
    )
    assert all(item["task_id"] != str(task_id) for item in inbox["items"])
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        resume_run_count = await session.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.task_id == task_id, Run.resume_of_run_id.is_not(None))
        )
    assert pause is not None
    assert pause.status == "cancelled"
    assert {projection.status for projection in projections} == {"cancelled"}
    assert resume_run_count == 0


@pytest.mark.asyncio
async def test_cancel_after_accepted_response_targets_source_official_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="cancel-accepted-response-before-resume",
    )
    runner = MultiInterruptRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="cancel-accepted-response-before-resume-worker",
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    pause_view = waiting["pending_interrupts"]
    assert pause_view is not None
    accepted = await service.respond_interrupts(
        actor(),
        str(task_id),
        InterruptResponsesSubmission.model_validate(
            {
                "pause_id": pause_view["pause_id"],
                "pause_version": pause_view["pause_version"],
                "responses": [
                    {
                        "interrupt_id": member["interrupt_id"],
                        "response_version": member["response_version"],
                        "response": {"action": "approve"},
                    }
                    for member in pause_view["members"]
                ],
            }
        ),
        "cancel-accepted-response-batch",
    )
    assert accepted is not None
    requested = await service.cancel_task(
        actor(),
        str(task_id),
        "cancel-before-official-resume-created",
    )
    assert requested is not None

    assert await dispatcher.dispatch_once() is True
    cancelled = await service.get_task(actor(), str(task_id))
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert cancelled["pending_interrupts"] is None
    assert runner.resume_requests == []
    assert runner.cancelled == [
        RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id="official-thread",
            run_id="official-run",
        )
    ]
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
        resume_runs = list(
            (
                await session.scalars(
                    select(Run).where(
                        Run.task_id == task_id,
                        Run.resume_of_run_id.is_not(None),
                    )
                )
            ).all()
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand)
                    .where(TaskCommand.task_id == task_id)
                    .order_by(TaskCommand.sequence)
                )
            ).all()
        )
    assert pause is not None
    assert pause.status == "cancelled"
    assert {projection.status for projection in projections} == {"cancelled"}
    assert len(resume_runs) == 1
    assert resume_runs[0].status == "cancelled"
    assert [
        command.status for command in commands if command.command_type == "respond"
    ] == ["cancelled"]
    assert [
        command.status for command in commands if command.command_type == "cancel_task"
    ] == ["dispatched"]


@pytest.mark.asyncio
async def test_cancel_terminal_winner_resolves_responding_interrupt_lineage(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="cancel-terminal-wins-responding-pause",
    )
    runner = TerminalResumeCancelRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="cancel-terminal-wins-responding-pause-worker",
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    pause_view = waiting["pending_interrupts"]
    assert pause_view is not None
    accepted = await service.respond_interrupts(
        actor(),
        str(task_id),
        InterruptResponsesSubmission.model_validate(
            {
                "pause_id": pause_view["pause_id"],
                "pause_version": pause_view["pause_version"],
                "responses": [
                    {
                        "interrupt_id": member["interrupt_id"],
                        "response_version": member["response_version"],
                        "response": {"action": "approve"},
                    }
                    for member in pause_view["members"]
                ],
            }
        ),
        "cancel-terminal-wins-response",
    )
    assert accepted is not None
    await service.cancel_task(
        actor(),
        str(task_id),
        "cancel-terminal-wins-request",
    )

    assert await dispatcher.dispatch_once() is True
    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["pending_interrupts"] is None
    assert runner.resume_requests == []
    assert runner.cancelled == [
        RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id="official-thread",
            run_id="official-run",
        )
    ]
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
    assert pause is not None
    assert pause.status == "resolved"
    assert {projection.status for projection in projections} == {"resolved"}
    assert {projection.response["action"] for projection in projections} == {"approve"}


@pytest.mark.asyncio
async def test_cancel_terminal_winner_cancels_unanswered_interrupt_lineage(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="cancel-terminal-wins-pending-pause",
    )
    runner = TerminalResumeCancelRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="cancel-terminal-wins-pending-pause-worker",
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    waiting = await service.get_task(actor(), str(task_id))
    assert waiting is not None
    assert waiting["pending_interrupts"] is not None

    await service.cancel_task(
        actor(),
        str(task_id),
        "cancel-terminal-wins-pending-request",
    )

    assert await dispatcher.dispatch_once() is True
    completed = await service.get_task(actor(), str(task_id))
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["pending_interrupts"] is None
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
    assert pause is not None
    assert pause.status == "cancelled"
    assert {projection.status for projection in projections} == {"cancelled"}
    assert {projection.response for projection in projections} == {None}


@pytest.mark.asyncio
async def test_permanent_cancel_failure_closes_responding_interrupt_lineage(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(
        session_factory,
        idempotency_key="cancel-failure-responding-pause",
    )
    runner = SourceCancelFailureRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="cancel-failure-responding-pause-worker",
        max_cancel_attempts=1,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    await queue_review_response(
        session_factory,
        task_id,
        {"action": "approve", "comment": "Keep this accepted response"},
    )
    await service.cancel_task(
        actor(),
        str(task_id),
        "cancel-failure-after-response",
    )

    assert await dispatcher.dispatch_once() is True
    failed = await service.get_task(actor(), str(task_id))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["pending_interrupts"] is None
    assert failed["errors"][0]["code"] == "agent_cancel_failed"
    assert runner.cancel_attempts == [
        RemoteRunHandle(
            assistant_id="official-assistant",
            thread_id="official-thread",
            run_id="official-run",
        )
    ]
    async with session_factory() as session:
        pause = await session.scalar(
            select(InterruptPause).where(InterruptPause.task_id == task_id)
        )
        projection = await session.scalar(
            select(InterruptProjection).where(InterruptProjection.task_id == task_id)
        )
        resumed_run = await session.scalar(
            select(Run).where(
                Run.task_id == task_id,
                Run.resume_of_run_id.is_not(None),
            )
        )
    assert pause is not None
    assert pause.status == "cancelled"
    assert projection is not None
    assert projection.status == "cancelled"
    assert projection.response == {
        "action": "approve",
        "comment": "Keep this accepted response",
    }
    assert projection.responded_at is not None
    assert resumed_run is not None
    assert resumed_run.status == "failed"
    assert resumed_run.failure_code == "agent_cancel_failed"


@pytest.mark.asyncio
async def test_review_edit_resumes_then_projects_a_new_interrupt(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = ReviewAwareRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="review-edit-worker",
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    resumed_run_id, first_projection_id = await queue_review_response(
        session_factory,
        task_id,
        {
            "action": "edit",
            "comment": "Use the confirmed trigger.",
            "edits": {"entry_trigger": "65200"},
        },
    )

    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "waiting_human"
    async with session_factory() as session:
        projections = list(
            (
                await session.scalars(
                    select(InterruptProjection).where(
                        InterruptProjection.task_id == task_id
                    )
                )
            ).all()
        )
    assert len(projections) == 2
    first_projection = next(
        projection for projection in projections if projection.id == first_projection_id
    )
    next_projection = next(
        projection for projection in projections if projection.id != first_projection_id
    )
    assert first_projection.status == "resolved"
    assert next_projection.status == "pending"
    assert next_projection.run_id == resumed_run_id
    assert next_projection.payload["review_iteration"] == 2
    assert runner.events.count("start") == 1
    assert runner.events.count("resume") == 1
    assert runner.events.count("get_interrupts") == 2


@pytest.mark.asyncio
async def test_expired_review_creates_durable_rejection_and_finishes_blocked(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = ReviewAwareRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="review-expiry-worker",
        clock=clock,
        interrupt_ttl_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))

    clock.now += timedelta(seconds=3)
    runner.remote_status = "success"
    assert await dispatcher.dispatch_once() is True
    async with session_factory() as session:
        projection = await session.scalar(
            select(InterruptProjection).where(InterruptProjection.task_id == task_id)
        )
        respond_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert projection is not None
    assert projection.status == "expired"
    assert projection.response == {
        "action": "reject",
        "comment": "The review window expired before a decision was submitted.",
    }
    assert respond_command is not None
    assert respond_command.status == "pending"
    assert respond_command.payload["expired"] is True

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(task_id))
    assert view is not None
    assert view["status"] == "blocked"
    assert view["artifact"]["status"] == "draft"
    assert runner.resume_requests[0]["responses"] == {
        projection.official_interrupt_id: projection.response
    }
    async with session_factory() as session:
        persisted_projection = await session.get(InterruptProjection, projection.id)
    assert persisted_projection is not None
    assert persisted_projection.status == "expired"


@pytest.mark.asyncio
async def test_admitted_review_response_survives_write_permission_revocation(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = ReviewAwareRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="revoked-member-response-worker",
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    accepted = await service.respond_interrupt(
        actor(),
        str(task_id),
        "interrupt-official-run",
        InterruptResponseSubmission(response_version=1, action="approve"),
        "accepted-before-membership-revocation",
    )
    assert accepted is not None

    async with session_factory() as session, session.begin():
        task = await session.get(Task, task_id)
        assert task is not None
        membership = await session.scalar(
            select(Membership)
            .where(
                Membership.workspace_id == task.workspace_id,
                Membership.user_id == task.owner_user_id,
            )
            .with_for_update()
        )
        assert membership is not None
        membership.permissions = ["analysis:read"]

    runner.remote_status = "success"
    assert await dispatcher.dispatch_once() is True

    async with session_factory() as session:
        task = await session.get(Task, task_id)
        resumed_run = await session.scalar(
            select(Run)
            .where(Run.task_id == task_id)
            .order_by(Run.attempt.desc())
            .limit(1)
        )
        projection = await session.scalar(
            select(InterruptProjection).where(InterruptProjection.task_id == task_id)
        )
        respond_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert task is not None
    assert task.status == "succeeded"
    assert resumed_run is not None
    assert resumed_run.status == "succeeded"
    assert projection is not None
    assert projection.status == "resolved"
    assert respond_command is not None
    assert respond_command.status == "dispatched"


@pytest.mark.asyncio
async def test_expiry_rejection_survives_membership_deactivation(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    _, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = ReviewAwareRunner(session_factory)
    runner.remote_status = "interrupted"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="revoked-member-expiry-worker",
        clock=clock,
        interrupt_ttl_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session, session.begin():
        task = await session.get(Task, task_id)
        assert task is not None
        membership = await session.scalar(
            select(Membership)
            .where(
                Membership.workspace_id == task.workspace_id,
                Membership.user_id == task.owner_user_id,
            )
            .with_for_update()
        )
        assert membership is not None
        membership.is_active = False

    clock.now += timedelta(seconds=3)
    runner.remote_status = "success"
    assert await dispatcher.dispatch_once() is True
    assert await dispatcher.dispatch_once() is True

    async with session_factory() as session:
        task = await session.get(Task, task_id)
        projection = await session.scalar(
            select(InterruptProjection).where(InterruptProjection.task_id == task_id)
        )
        respond_command = await session.scalar(
            select(TaskCommand).where(
                TaskCommand.task_id == task_id,
                TaskCommand.command_type == "respond",
            )
        )
    assert task is not None
    assert task.status == "blocked"
    assert projection is not None
    assert projection.status == "expired"
    assert respond_command is not None
    assert respond_command.status == "dispatched"


@pytest.mark.asyncio
async def test_running_remote_is_cancelled_only_after_orphan_deadline(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        max_run_seconds=2,
    )
    lease = await dispatcher.claim_next()
    assert lease is not None
    clock.now += timedelta(seconds=3)

    assert await dispatcher.execute(lease) is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert runner.cancelled


@pytest.mark.asyncio
async def test_orphan_deadline_cancel_failure_keeps_cleanup_reconcilable(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = CancelFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="orphan-cleanup-worker",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_run_seconds=2,
    )

    assert await dispatcher.dispatch_once() is True
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "running"

    runner.fail_cancel = False
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_run_timeout"


@pytest.mark.asyncio
async def test_orphan_cleanup_failure_has_a_persisted_terminal_deadline(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = CancelFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="bounded-orphan-cleanup-worker",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_run_seconds=2,
        max_cancel_seconds=4,
    )

    assert await dispatcher.dispatch_once() is True
    clock.now += timedelta(seconds=3)
    cleanup_started_at = clock.now
    assert await dispatcher.dispatch_once() is True

    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        product_run = await session.scalar(select(Run).where(Run.task_id == task_id))
    assert product_run is not None
    assert product_run.cancel_requested_at == cleanup_started_at
    pending = await service.get_task(actor(), str(task_id))
    assert pending is not None
    assert pending["status"] == "running"
    assert pending["cancel_requested_at"] is None

    clock.now += timedelta(seconds=5)
    assert await dispatcher.dispatch_once() is True
    failed = await service.get_task(actor(), str(task_id))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["errors"][0]["code"] == "orphan_cancel_unconfirmed"
    assert failed["errors"][0]["error_type"] == "ConnectionError"
    assert failed["errors"][0]["retryable"] is False


@pytest.mark.asyncio
async def test_queued_task_cancel_is_durable_without_creating_remote_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )

    requested = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-queued-1",
    )
    assert requested is not None
    assert requested["cancel_requested_at"] is not None
    replayed = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-queued-with-a-different-key",
    )
    assert replayed is not None
    assert replayed["cancel_requested_at"] == requested["cancel_requested_at"]
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.events == []
    async with session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(Run).where(Run.task_id == UUID(str(queued["task_id"])))
                )
            ).all()
        )
        commands = list(
            (
                await session.scalars(
                    select(TaskCommand)
                    .where(TaskCommand.task_id == UUID(str(queued["task_id"])))
                    .order_by(TaskCommand.sequence)
                )
            ).all()
        )
    assert runs == []
    assert [(item.command_type, item.status) for item in commands] == [
        ("submit", "cancelled"),
        ("cancel_task", "dispatched"),
    ]


@pytest.mark.asyncio
async def test_running_task_cancel_stops_registered_official_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
    )
    assert await dispatcher.dispatch_once() is True

    requested = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-running-1",
    )
    assert requested is not None
    assert requested["cancel_requested_at"] is not None
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.events == ["start", "get"]
    assert len(runner.cancelled) == 1
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        product_run_id = await session.scalar(
            select(Run.id).where(Run.task_id == task_id)
        )
    assert product_run_id is not None
    await assert_canonical_terminal_event(session_factory, product_run_id)


@pytest.mark.asyncio
async def test_terminal_success_wins_a_concurrent_cancel_request(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = TerminalCancelRaceRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="terminal-cancel-race-worker",
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-after-official-terminal",
    )

    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "succeeded"
    assert view["artifact"] is not None
    assert view["artifact"]["analysis"]["main_action"] == "open_long"
    assert len(runner.cancelled) == 1


@pytest.mark.asyncio
async def test_terminal_output_failure_does_not_consume_cancel_failure_semantics(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = TerminalCancelJoinFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="terminal-output-cancel-race-worker",
        max_cancel_attempts=1,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-after-terminal-with-unavailable-output",
    )

    assert await dispatcher.dispatch_once() is True

    failed = await service.get_task(actor(), str(queued["task_id"]))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["errors"][0]["code"] == "terminal_projection_unavailable"
    assert failed["errors"][0]["error_type"] == "ConnectionError"
    assert failed["errors"][0]["code"] != "agent_cancel_failed"
    assert len(runner.cancelled) == 1


@pytest.mark.asyncio
async def test_observed_terminal_survives_lease_retry_without_recancelling(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = TerminalThenUnconfirmedCancelRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="durable-terminal-observation-worker",
        clock=clock,
        max_cancel_attempts=2,
        reconciliation_interval_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-after-durable-terminal-observation",
    )

    assert await dispatcher.dispatch_once() is True
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        observed_status = await session.scalar(
            select(Run.observed_terminal_status).where(Run.task_id == task_id)
        )
    assert observed_status == "success"
    assert len(runner.cancelled) == 1

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True

    failed = await service.get_task(actor(), str(task_id))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["errors"][0]["code"] == "terminal_projection_unavailable"
    assert failed["errors"][0]["code"] != "agent_cancel_failed"
    assert runner.events.count("join") == 2
    assert len(runner.cancelled) == 1


@pytest.mark.asyncio
async def test_unconfirmed_registered_cancel_never_projects_cancelled(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = UnconfirmedCancelRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="unconfirmed-cancel-worker",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_cancel_attempts=2,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-that-remains-unconfirmed",
    )

    assert await dispatcher.dispatch_once() is True
    pending = await service.get_task(actor(), str(queued["task_id"]))
    assert pending is not None
    assert pending["status"] == "running"

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    failed = await service.get_task(actor(), str(queued["task_id"]))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["errors"][0]["code"] == "agent_cancel_failed"
    assert "cancelled" not in {pending["status"], failed["status"]}


@pytest.mark.asyncio
async def test_cancel_requested_during_start_registers_then_cancels_remote_run(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = InspectingRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="start-cancel-race-worker",
    )
    submit_lease = await dispatcher.claim_next()
    assert submit_lease is not None

    requested = await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-during-start",
    )
    assert requested is not None
    assert requested["cancel_requested_at"] is not None
    async with session_factory() as session:
        submit = await session.scalar(
            select(TaskCommand).where(TaskCommand.id == submit_lease.command_id)
        )
    assert submit is not None
    assert submit.status == "dispatching"

    handle = RemoteRunHandle(
        assistant_id="official-assistant",
        thread_id="official-thread",
        run_id="official-run",
    )
    assert await dispatcher._register_remote(submit_lease, handle) == (
        "cancel_requested"
    )
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.cancelled == [handle]


@pytest.mark.asyncio
async def test_remote_registration_and_product_cancel_share_one_lock_order() -> None:
    assert DATABASE_URL is not None
    suffix = uuid4().hex[:12]
    registration_app = f"registration-{suffix}"
    cancellation_app = f"cancellation-{suffix}"
    observer_app = f"observer-{suffix}"
    registration_engine = create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"application_name": registration_app}},
    )
    cancellation_engine = create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"application_name": cancellation_app}},
    )
    observer_engine = create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"application_name": observer_app}},
    )
    registration_sessions = async_sessionmaker(
        registration_engine,
        expire_on_commit=False,
    )
    cancellation_sessions = async_sessionmaker(
        cancellation_engine,
        expire_on_commit=False,
    )
    concurrent_actor = ActorContext(
        tenant_id=f"lock-order-tenant-{suffix}",
        workspace_id=f"lock-order-workspace-{suffix}",
        user_id=f"oidc|lock-order-user-{suffix}",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    service = ProductAnalysisService(session_factory=cancellation_sessions)
    runner = InspectingRunner(registration_sessions)
    dispatcher = CommandDispatcher(
        session_factory=registration_sessions,
        runner=runner,
        worker_id="lock-order-worker",
    )
    release_registration = asyncio.Event()
    registration_holds_locks = asyncio.Event()
    original_locked_command = dispatcher._locked_command
    pause_once = True

    async def pause_after_locking_command(
        *args: object, **kwargs: object
    ) -> TaskCommand | None:
        nonlocal pause_once
        command = await original_locked_command(*args, **kwargs)  # type: ignore[arg-type]
        if pause_once:
            pause_once = False
            registration_holds_locks.set()
            await release_registration.wait()
        return command

    dispatcher._locked_command = pause_after_locking_command  # type: ignore[method-assign]
    try:
        await service.bootstrap_actor(concurrent_actor)
        queued = await service.create_analysis(
            concurrent_actor,
            AnalysisSubmission(
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="Exercise registration and cancellation lock order.",
                notify=False,
            ),
            idempotency_key=f"lock-order-{suffix}",
        )
        lease = await dispatcher.claim_next()
        assert lease is not None
        handle = RemoteRunHandle(
            assistant_id="lock-order-assistant",
            thread_id="lock-order-thread",
            run_id="lock-order-run",
        )

        registration = asyncio.create_task(dispatcher._register_remote(lease, handle))
        await asyncio.wait_for(registration_holds_locks.wait(), timeout=2)
        cancellation = asyncio.create_task(
            service.cancel_task(
                concurrent_actor,
                str(queued["task_id"]),
                "concurrent-lock-order-cancel",
            )
        )
        blocking_pair: tuple[int, int] | None = None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 3
        while loop.time() < deadline:
            async with observer_engine.connect() as observer:
                blocking_pair = (
                    await observer.execute(
                        text(
                            """
                            SELECT blocked.pid, blocker.pid
                            FROM pg_stat_activity AS blocked
                            JOIN pg_stat_activity AS blocker
                              ON blocker.pid = ANY(pg_blocking_pids(blocked.pid))
                            WHERE blocked.application_name = :cancellation_app
                              AND blocker.application_name = :registration_app
                            """
                        ),
                        {
                            "cancellation_app": cancellation_app,
                            "registration_app": registration_app,
                        },
                    )
                ).one_or_none()
            if blocking_pair is not None:
                break
            if cancellation.done():
                await cancellation
                pytest.fail(
                    "Product cancellation completed before observing its lock wait"
                )
            await asyncio.sleep(0.02)
        assert blocking_pair is not None
        assert blocking_pair[0] != blocking_pair[1]
        release_registration.set()

        registration_result, cancellation_result = await asyncio.wait_for(
            asyncio.gather(registration, cancellation),
            timeout=5,
        )
        assert registration_result == "registered"
        assert cancellation_result is not None
        assert cancellation_result["cancel_requested_at"] is not None
        assert await dispatcher.dispatch_once() is True
        cancelled = await service.get_task(
            concurrent_actor,
            str(queued["task_id"]),
        )
        assert cancelled is not None
        assert cancelled["status"] == "cancelled"
        async with cancellation_sessions() as session:
            commands = list(
                (
                    await session.scalars(
                        select(TaskCommand)
                        .where(TaskCommand.task_id == UUID(str(queued["task_id"])))
                        .order_by(TaskCommand.sequence)
                    )
                ).all()
            )
            product_run = await session.scalar(
                select(Run).where(Run.task_id == UUID(str(queued["task_id"])))
            )
            thread = await session.scalar(
                select(Thread).where(Thread.id == commands[0].thread_id)
            )
        assert [(command.command_type, command.status) for command in commands] == [
            ("submit", "cancelled"),
            ("cancel_task", "dispatched"),
        ]
        assert product_run is not None
        assert product_run.official_run_id == handle.run_id
        assert product_run.cancel_requested_at is not None
        assert thread is not None
        assert thread.official_thread_id == handle.thread_id
    finally:
        release_registration.set()
        async with cancellation_sessions() as session, session.begin():
            await delete_actor_test_data(session, concurrent_actor)
        await registration_engine.dispose()
        await cancellation_engine.dispose()
        await observer_engine.dispose()


@pytest.mark.asyncio
async def test_cancel_recovers_unregistered_remote_run_after_worker_restart(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = RecoveringCancelRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="recovery-worker",
        clock=clock,
    )
    submit_lease = await dispatcher.claim_next()
    assert submit_lease is not None
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-after-ambiguous-start",
    )

    clock.now += timedelta(seconds=31)
    assert await dispatcher.claim_next() is None
    assert await dispatcher.dispatch_once() is True

    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"
    assert runner.events == ["find"]
    assert runner.cancelled == [
        RemoteRunHandle(
            assistant_id="recovered-assistant",
            thread_id=str(submit_lease.product_thread_id),
            run_id="recovered-run",
        )
    ]
    async with session_factory() as session:
        product_run = await session.scalar(
            select(Run).where(Run.id == submit_lease.product_run_id)
        )
    assert product_run is not None
    assert product_run.official_run_id == "recovered-run"
    assert product_run.official_assistant_id == "recovered-assistant"


@pytest.mark.asyncio
async def test_cancel_retries_until_unregistered_remote_run_becomes_visible(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = DelayedVisibilityCancelRunner(session_factory, visible_after=2)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="delayed-visibility-worker",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_cancel_attempts=3,
    )
    submit_lease = await dispatcher.claim_next()
    assert submit_lease is not None
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-before-delayed-discovery",
    )

    clock.now += timedelta(seconds=31)
    assert await dispatcher.claim_next() is None
    assert await dispatcher.dispatch_once() is True
    pending = await service.get_task(actor(), str(queued["task_id"]))
    assert pending is not None
    assert pending["status"] == "running"
    assert runner.find_calls == 1
    assert runner.cancelled == []

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    cancelled = await service.get_task(actor(), str(queued["task_id"]))
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert runner.find_calls == 2
    assert runner.cancelled == [
        RemoteRunHandle(
            assistant_id="delayed-assistant",
            thread_id=str(submit_lease.product_thread_id),
            run_id="delayed-run",
        )
    ]


@pytest.mark.asyncio
async def test_cancel_fails_explicitly_when_unregistered_run_never_becomes_visible(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = DelayedVisibilityCancelRunner(session_factory, visible_after=100)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="missing-run-worker",
        clock=clock,
        reconciliation_interval_seconds=2,
        max_cancel_attempts=2,
    )
    assert await dispatcher.claim_next() is not None
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-run-that-never-appears",
    )

    clock.now += timedelta(seconds=31)
    assert await dispatcher.claim_next() is None
    assert await dispatcher.dispatch_once() is True
    pending = await service.get_task(actor(), str(queued["task_id"]))
    assert pending is not None
    assert pending["status"] == "running"

    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    failed = await service.get_task(actor(), str(queued["task_id"]))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["errors"][0]["code"] == "agent_cancel_failed"
    assert failed["errors"][0]["error_type"] == "RunDiscoveryTimeout"
    assert runner.find_calls == 2
    assert runner.cancelled == []


@pytest.mark.asyncio
async def test_cancel_transport_error_is_retried_without_losing_intent(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = CancelFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        clock=clock,
        reconciliation_interval_seconds=2,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-retry-1",
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "running"

    runner.fail_cancel = False
    clock.now += timedelta(seconds=3)
    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "cancelled"


@pytest.mark.asyncio
async def test_permanent_cancel_failure_becomes_an_explicit_product_failure(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = CancelFailureRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="permanent-cancel-failure-worker",
        max_cancel_attempts=1,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-permanent-failure",
    )

    assert await dispatcher.dispatch_once() is True
    view = await service.get_task(actor(), str(queued["task_id"]))
    assert view is not None
    assert view["status"] == "failed"
    assert view["errors"][0]["code"] == "agent_cancel_failed"
    assert view["errors"][0]["retryable"] is False
    task_id = UUID(str(queued["task_id"]))
    async with session_factory() as session:
        failed_run = await session.scalar(select(Run).where(Run.task_id == task_id))
        terminal_events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(
                        DomainEvent.task_id == task_id,
                        DomainEvent.event_type == "run.terminal",
                    )
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
    assert failed_run is not None
    assert failed_run.terminal_output_hash == terminal_events[-1].payload_hash
    assert terminal_events[-1].payload == failed_run.output_payload


@pytest.mark.asyncio
async def test_terminal_join_failure_after_deadline_retries_without_recursion(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    clock = MutableClock()
    runner = DeadlineTerminalJoinFailureRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="terminal-projection-failure-worker",
        clock=clock,
        max_attempts=1,
        max_run_seconds=1,
        remote_operation_timeout_seconds=0.2,
    )
    lease = await dispatcher.claim_next()
    assert lease is not None
    clock.now += timedelta(seconds=2)

    assert await asyncio.wait_for(dispatcher.execute(lease), timeout=2) is True

    failed = await service.get_task(actor(), str(queued["task_id"]))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["errors"][0]["code"] == "terminal_projection_unavailable"
    assert failed["errors"][0]["error_type"] == "ConnectionError"
    assert len(runner.cancelled) == 1
    assert runner.events.count("join") == 1


@pytest.mark.asyncio
async def test_hanging_remote_cancel_is_bounded_by_local_timeout(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    service, queued = await queue_task(session_factory)
    runner = HangingCancelRunner(session_factory)
    runner.remote_status = "running"
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="hanging-cancel-worker",
        max_cancel_attempts=1,
        remote_operation_timeout_seconds=0.05,
    )
    assert await dispatcher.dispatch_once() is True
    await service.cancel_task(
        actor(),
        str(queued["task_id"]),
        "cancel-with-hanging-transport",
    )

    assert await asyncio.wait_for(dispatcher.dispatch_once(), timeout=2) is True

    failed = await service.get_task(actor(), str(queued["task_id"]))
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["errors"][0]["code"] == "agent_cancel_failed"
    assert failed["errors"][0]["error_type"] == "TimeoutError"
    assert len(runner.cancelled) == 1


@pytest.mark.asyncio
async def test_remote_start_renews_the_command_lease_before_join(
    connection: AsyncConnection,
) -> None:
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    await queue_task(session_factory)
    runner = SlowStartRunner(session_factory)
    dispatcher = CommandDispatcher(
        session_factory=session_factory,
        runner=runner,
        worker_id="worker-a",
        lease_seconds=3,
    )
    renew_calls = 0
    renew_lease = dispatcher._renew_lease

    async def recording_renewal(lease: object) -> bool:
        nonlocal renew_calls
        renew_calls += 1
        return await renew_lease(lease)  # type: ignore[arg-type]

    dispatcher._renew_lease = recording_renewal  # type: ignore[method-assign]

    assert await dispatcher.dispatch_once() is True
    assert renew_calls >= 1
