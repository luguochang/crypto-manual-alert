from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

import crypto_alert_v2.api.service as service_module
from crypto_alert_v2.api.schemas import TaskView
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.domain.models import MarketSnapshot
from crypto_alert_v2.persistence import repositories as repository_module
from crypto_alert_v2.persistence.repositories import ResolvedActor
from crypto_alert_v2.providers.search import WebEvidence
from tests.fixtures.golden_cases import complete_market_snapshot


NOW = datetime(2026, 7, 13, 4, 0, tzinfo=UTC)


def _task_payload() -> dict[str, object]:
    return {
        "task_id": "task-1",
        "status": "running",
        "symbol": "BTC-USDT-SWAP",
        "horizon": "4h",
        "created_at": NOW,
        "artifact": None,
        "errors": [],
        "agent_stream": None,
    }


def _web_evidence_payload() -> dict[str, object]:
    return {
        "query": "BTC macro conditions",
        "final_url": "https://example.com/macro",
        "redirect_chain": [],
        "http_status": 200,
        "fetched_at": NOW,
        "published_at": None,
        "content_hash": "b" * 64,
        "parser_version": "test-parser-v1",
        "title": "Macro source",
        "author": None,
        "source": "test_search",
        "excerpt": "Macro evidence.",
        "evidence_relation": "supports",
    }


class _ScalarRows:
    def __init__(self, values: list[dict[str, Any]]) -> None:
        self._values = values

    def all(self) -> list[dict[str, Any]]:
        return self._values


class _RunSourceSession:
    def __init__(
        self,
        *,
        market_snapshot: dict[str, Any] | None,
        web_evidence: list[dict[str, Any]],
    ) -> None:
        self.market_snapshot = market_snapshot
        self.web_evidence = web_evidence
        self.scalar_statements: list[Any] = []
        self.scalars_statements: list[Any] = []

    async def scalar(self, statement: Any) -> dict[str, Any] | None:
        self.scalar_statements.append(statement)
        return self.market_snapshot

    async def scalars(self, statement: Any) -> _ScalarRows:
        self.scalars_statements.append(statement)
        return _ScalarRows(self.web_evidence)


class _TaskViewSession(_RunSourceSession):
    def __init__(
        self,
        *,
        task: SimpleNamespace,
        latest_run: SimpleNamespace | None,
        market_snapshot: dict[str, Any] | None,
        web_evidence: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            market_snapshot=market_snapshot,
            web_evidence=web_evidence,
        )
        self.task = task
        self.latest_run = latest_run
        self.execute_statements: list[Any] = []

    async def __aenter__(self) -> _TaskViewSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalar(self, statement: Any) -> Any:
        sql = str(statement)
        if "FROM app.tasks" in sql:
            return self.task
        if "app.artifact_versions" in sql:
            return None
        if "FROM app.task_commands" in sql:
            self.scalar_statements.append(statement)
            return None
        return await super().scalar(statement)

    async def execute(self, statement: Any) -> SimpleNamespace:
        self.execute_statements.append(statement)
        joined = (
            (self.latest_run, "official-thread-1")
            if self.latest_run is not None
            else None
        )
        return SimpleNamespace(one_or_none=lambda: joined)


def _resolved_actor() -> ResolvedActor:
    return ResolvedActor(
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        user_id=uuid4(),
        membership_id=uuid4(),
        role="member",
        permissions=("analysis:read",),
    )


def _actor_context() -> ActorContext:
    return ActorContext(
        tenant_id="tenant",
        workspace_id="workspace",
        user_id="user",
        roles=("member",),
        permissions=("analysis:read",),
    )


def _task(*, actor: ResolvedActor) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=actor.tenant_id,
        workspace_id=actor.workspace_id,
        owner_user_id=actor.user_id,
        thread_id=uuid4(),
        status="running",
        request_payload={"symbol": "BTC-USDT-SWAP", "horizon": "4h"},
        created_at=NOW,
        completed_at=None,
    )


def _assert_complete_scope(
    statement: Any,
    *,
    table_name: str,
    actor: ResolvedActor,
    task_id: UUID,
    run_id: UUID,
) -> None:
    sql = str(statement)
    params = statement.compile().params
    assert f"app.{table_name}.tenant_id =" in sql
    assert f"app.{table_name}.workspace_id =" in sql
    assert f"app.{table_name}.owner_user_id =" in sql
    assert f"app.{table_name}.task_id =" in sql
    assert f"app.{table_name}.run_id =" in sql
    assert actor.tenant_id in params.values()
    assert actor.workspace_id in params.values()
    assert actor.user_id in params.values()
    assert task_id in params.values()
    assert run_id in params.values()


def test_task_view_exposes_explicit_empty_run_sources() -> None:
    view = TaskView.model_validate(_task_payload())

    assert view.market_snapshot is None
    assert view.web_evidence == []
    assert view.model_dump(mode="json")["market_snapshot"] is None
    assert view.model_dump(mode="json")["web_evidence"] == []


def test_persistence_package_exports_task_run_projection_query() -> None:
    persistence_module = import_module("crypto_alert_v2.persistence")

    assert persistence_module.TaskRunProjectionRepository is not None
    assert persistence_module.TaskRunSourceRecords is not None


def test_task_view_validates_run_sources_as_typed_models() -> None:
    payload = _task_payload()
    payload["market_snapshot"] = complete_market_snapshot()
    payload["web_evidence"] = [_web_evidence_payload()]

    view = TaskView.model_validate(payload)

    assert isinstance(view.market_snapshot, MarketSnapshot)
    assert isinstance(view.web_evidence[0], WebEvidence)
    assert view.market_snapshot.ticker is not None
    assert view.market_snapshot.ticker.last > 0
    assert str(view.web_evidence[0].final_url) == "https://example.com/macro"


@pytest.mark.asyncio
async def test_run_source_query_is_scoped_to_actor_task_and_product_run() -> None:
    repository_type = getattr(
        repository_module,
        "TaskRunProjectionRepository",
        None,
    )
    assert repository_type is not None
    actor = _resolved_actor()
    task_id = uuid4()
    run_id = uuid4()
    market_snapshot = complete_market_snapshot()
    web_evidence = [_web_evidence_payload()]
    session = _RunSourceSession(
        market_snapshot=market_snapshot,
        web_evidence=web_evidence,
    )

    records = await repository_type(session, actor).get_sources(
        task_id=task_id,
        run_id=run_id,
    )

    assert records.market_snapshot == market_snapshot
    assert records.web_evidence == tuple(web_evidence)
    assert len(session.scalar_statements) == 1
    assert len(session.scalars_statements) == 1
    market_statement = session.scalar_statements[0]
    evidence_statement = session.scalars_statements[0]
    _assert_complete_scope(
        market_statement,
        table_name="market_snapshots",
        actor=actor,
        task_id=task_id,
        run_id=run_id,
    )
    _assert_complete_scope(
        evidence_statement,
        table_name="web_evidence",
        actor=actor,
        task_id=task_id,
        run_id=run_id,
    )
    assert "ORDER BY app.market_snapshots.fetched_at DESC" in str(market_statement)
    assert "LIMIT" in str(market_statement)
    assert "ORDER BY app.web_evidence.fetched_at ASC" in str(evidence_statement)


def test_run_source_projection_validates_persisted_payloads_as_typed_models() -> None:
    projection_module = import_module("crypto_alert_v2.projections.task")
    records = SimpleNamespace(
        market_snapshot=complete_market_snapshot(),
        web_evidence=(_web_evidence_payload(),),
    )

    projection = projection_module.project_task_run_sources(records)

    assert isinstance(projection.market_snapshot, MarketSnapshot)
    assert isinstance(projection.web_evidence[0], WebEvidence)


@pytest.mark.asyncio
async def test_service_projects_sources_from_current_product_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolved_actor()
    task = _task(actor=resolved)
    latest_run = SimpleNamespace(
        id=uuid4(),
        status="running",
        finished_at=None,
        output_payload=None,
        official_assistant_id=None,
        official_run_id=None,
    )
    session = _TaskViewSession(
        task=task,
        latest_run=latest_run,
        market_snapshot=complete_market_snapshot(),
        web_evidence=[_web_evidence_payload()],
    )

    async def resolve_actor_for_test(*_: object) -> ResolvedActor:
        return resolved

    monkeypatch.setattr(service_module, "resolve_actor", resolve_actor_for_test)
    service = ProductAnalysisService(session_factory=lambda: session)

    view = await service.get_task(_actor_context(), str(task.id))

    assert view is not None
    assert isinstance(view["market_snapshot"], MarketSnapshot)
    assert isinstance(view["web_evidence"][0], WebEvidence)
    source_statements = [
        statement
        for statement in (*session.scalar_statements, *session.scalars_statements)
        if "app.task_commands" not in str(statement)
    ]
    for statement in source_statements:
        assert latest_run.id in statement.compile().params.values()
    cancel_statement = next(
        statement
        for statement in session.scalar_statements
        if "app.task_commands" in str(statement)
    )
    cancel_params = cancel_statement.compile().params.values()
    assert task.id in cancel_params
    assert resolved.tenant_id in cancel_params
    assert resolved.workspace_id in cancel_params
    assert resolved.user_id in cancel_params


@pytest.mark.asyncio
async def test_service_returns_explicit_empty_sources_when_task_has_no_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolved_actor()
    task = _task(actor=resolved)
    session = _TaskViewSession(
        task=task,
        latest_run=None,
        market_snapshot=complete_market_snapshot(),
        web_evidence=[_web_evidence_payload()],
    )

    async def resolve_actor_for_test(*_: object) -> ResolvedActor:
        return resolved

    monkeypatch.setattr(service_module, "resolve_actor", resolve_actor_for_test)
    service = ProductAnalysisService(session_factory=lambda: session)

    view = await service.get_task(_actor_context(), str(task.id))

    assert view is not None
    assert view["market_snapshot"] is None
    assert view["web_evidence"] == []
    assert len(session.scalar_statements) == 1
    assert "app.task_commands" in str(session.scalar_statements[0])
    assert session.scalars_statements == []
