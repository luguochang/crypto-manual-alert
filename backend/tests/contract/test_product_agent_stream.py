from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError
import pytest

import crypto_alert_v2.api.service as service_module
from crypto_alert_v2.api.app import create_app
from crypto_alert_v2.api.schemas import AgentStreamBindingView, TaskView
from crypto_alert_v2.api.service import ProductAnalysisService
from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.config import Settings
from crypto_alert_v2.persistence.repositories import ResolvedActor


NOW = datetime(2026, 7, 13, tzinfo=UTC)
app_module = import_module("crypto_alert_v2.api.app")


def _development_app(service: object) -> object:
    settings = Settings(
        _env_file=None,
        app_environment="development",
        development_bootstrap_enabled=True,
        development_bootstrap_profile="local-proof",
        development_bootstrap_subject="compose-user",
        development_bootstrap_tenant_id="compose-tenant",
        development_bootstrap_workspace_id="compose-workspace",
        development_bootstrap_roles=("member",),
        development_bootstrap_permissions=("analysis:read", "analysis:write"),
    )
    return create_app(
        service=service,
        mode=settings.app_environment,
        settings=settings,
    )


class AgentStreamProductService:
    async def create_analysis(
        self,
        actor: ActorContext,
        submission: Any,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del actor, idempotency_key
        return {
            "task_id": "task-1",
            "status": "queued",
            "symbol": submission.symbol,
            "horizon": submission.horizon,
            "created_at": NOW,
            "artifact": None,
            "errors": [],
        }

    async def get_task(
        self,
        actor: ActorContext,
        task_id: str,
        *,
        run_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        del actor, run_id
        if task_id != "task-1":
            return None
        return {
            "task_id": task_id,
            "status": "running",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "created_at": NOW,
            "artifact": None,
            "errors": [],
            "agent_stream": {
                "protocol": "langgraph-v2",
                "assistant_id": "configured-assistant",
                "thread_id": "official-thread-1",
                "run_id": "official-run-1",
            },
        }


class ScalarSession:
    def __init__(
        self,
        *,
        task: object,
        latest_run: object,
        artifact_content: object = None,
        official_thread_id: str | None,
        joined_run_thread: tuple[object, str | None] | None = None,
    ) -> None:
        self.task = task
        self.latest_run = latest_run
        self.artifact_content = artifact_content
        self.official_thread_id = official_thread_id
        self.joined_run_thread = joined_run_thread
        self.scalar_statements: list[object] = []
        self.execute_statements: list[object] = []

    async def __aenter__(self) -> ScalarSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalar(self, statement: object) -> object:
        self.scalar_statements.append(statement)
        sql = str(statement)
        if "FROM app.tasks" in sql:
            return self.task
        if "FROM app.runs" in sql:
            return self.latest_run
        if "app.artifact_versions" in sql:
            return self.artifact_content
        if "FROM app.market_snapshots" in sql:
            return None
        if "FROM app.task_commands" in sql:
            return None
        if "FROM app.threads" in sql:
            return self.official_thread_id
        raise AssertionError(f"unexpected scalar query: {sql}")

    async def scalars(self, statement: object) -> SimpleNamespace:
        self.scalar_statements.append(statement)
        sql = str(statement)
        if "FROM app.web_evidence" in sql:
            return SimpleNamespace(all=lambda: [])
        if "FROM app.interrupt_inbox" in sql:
            return SimpleNamespace(all=lambda: [])
        raise AssertionError(f"unexpected scalars query: {sql}")

    async def execute(self, statement: object) -> SimpleNamespace:
        self.execute_statements.append(statement)
        return SimpleNamespace(one_or_none=lambda: self.joined_run_thread)


def _task() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        owner_user_id=uuid4(),
        thread_id=uuid4(),
        status="running",
        request_payload={"symbol": "BTC-USDT-SWAP", "horizon": "4h"},
        created_at=NOW,
        completed_at=None,
    )


def _resolved_actor(task: SimpleNamespace) -> ResolvedActor:
    return ResolvedActor(
        tenant_id=task.tenant_id,
        workspace_id=task.workspace_id,
        user_id=task.owner_user_id,
        membership_id=uuid4(),
        role="member",
        permissions=("analysis:read",),
    )


@pytest.mark.asyncio
async def test_queued_submission_does_not_accept_client_agent_stream() -> None:
    transport = httpx.ASGITransport(app=_development_app(AgentStreamProductService()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.post(
            "/api/v2/analysis",
            headers={"idempotency-key": "agent-stream-admission-1"},
            json={
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "query_text": "Assess current BTC risk.",
                "notify": False,
                "agent_stream": {
                    "protocol": "langgraph-v2",
                    "assistant_id": "attacker-assistant",
                    "thread_id": "attacker-thread",
                    "run_id": "attacker-run",
                },
            },
        )

    assert response.status_code == 202
    assert response.json()["agent_stream"] is None


@pytest.mark.asyncio
async def test_get_task_exposes_read_only_official_agent_stream_binding() -> None:
    transport = httpx.ASGITransport(app=_development_app(AgentStreamProductService()))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8011"
    ) as client:
        response = await client.get("/api/v2/tasks/task-1")

    assert response.status_code == 200
    assert response.json()["agent_stream"] == {
        "protocol": "langgraph-v2",
        "assistant_id": "configured-assistant",
        "thread_id": "official-thread-1",
        "run_id": "official-run-1",
    }


def test_agent_stream_protocol_is_fixed_to_langgraph_v2() -> None:
    with pytest.raises(ValidationError):
        TaskView.model_validate(
            {
                "task_id": "task-1",
                "status": "running",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "4h",
                "created_at": NOW,
                "agent_stream": {
                    "protocol": "custom-protocol",
                    "assistant_id": "configured-assistant",
                    "thread_id": "official-thread-1",
                    "run_id": "official-run-1",
                },
            }
        )


@pytest.mark.parametrize("field_name", ("assistant_id", "thread_id", "run_id"))
@pytest.mark.parametrize("invalid_value", ("   ", "x" * 256, 123))
def test_agent_stream_ids_are_stripped_strict_bounded_strings(
    field_name: str,
    invalid_value: object,
) -> None:
    payload: dict[str, object] = {
        "protocol": "langgraph-v2",
        "assistant_id": "assistant-1",
        "thread_id": "thread-1",
        "run_id": "run-1",
    }
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        AgentStreamBindingView.model_validate(payload)


def test_agent_stream_ids_strip_surrounding_whitespace() -> None:
    binding = AgentStreamBindingView.model_validate(
        {
            "protocol": "langgraph-v2",
            "assistant_id": " assistant-1 ",
            "thread_id": " thread-1 ",
            "run_id": " run-1 ",
        }
    )

    assert binding.assistant_id == "assistant-1"
    assert binding.thread_id == "thread-1"
    assert binding.run_id == "run-1"


@pytest.mark.asyncio
async def test_service_uses_persisted_official_ids_for_agent_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    latest_run = SimpleNamespace(
        id=uuid4(),
        status="running",
        finished_at=None,
        output_payload=None,
        official_assistant_id="persisted-assistant",
        official_run_id="official-run-latest",
    )
    session = ScalarSession(
        task=task,
        latest_run=latest_run,
        official_thread_id="official-thread-persisted",
        joined_run_thread=(latest_run, "official-thread-persisted"),
    )
    actor = ActorContext(
        tenant_id="tenant",
        workspace_id="workspace",
        user_id="user",
        roles=("member",),
        permissions=("analysis:read",),
    )
    resolved = _resolved_actor(task)

    async def resolve_actor_for_test(
        _: ScalarSession, __: ActorContext
    ) -> ResolvedActor:
        return resolved

    monkeypatch.setattr(service_module, "resolve_actor", resolve_actor_for_test)
    service = ProductAnalysisService(
        session_factory=lambda: session,
    )

    view = await service.get_task(actor, str(task.id))

    assert view is not None
    assert view["agent_stream"] == {
        "protocol": "langgraph-v2",
        "assistant_id": "persisted-assistant",
        "thread_id": "official-thread-persisted",
        "run_id": "official-run-latest",
    }
    assert len(session.execute_statements) == 1
    run_thread_query = str(session.execute_statements[0])
    artifact_query = next(
        str(statement)
        for statement in session.scalar_statements
        if "app.artifact_versions" in str(statement)
    )
    assert "JOIN app.threads ON" in run_thread_query
    assert "ORDER BY app.runs.attempt DESC" in run_thread_query
    assert "app.runs.owner_user_id = :owner_user_id_1" in run_thread_query
    assert ".thread_id = app.threads.id" in run_thread_query
    assert ".tenant_id = app.threads.tenant_id" in run_thread_query
    assert ".workspace_id = app.threads.workspace_id" in run_thread_query
    assert ".owner_user_id = app.threads.owner_user_id" in run_thread_query
    assert "app.threads.id = :id_1" in run_thread_query
    assert "app.artifacts.owner_user_id = :owner_user_id_1" in artifact_query


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("official_assistant_id", "official_thread_id", "official_run_id"),
    (
        (None, "official-thread", "official-run"),
        ("official-assistant", None, "official-run"),
        ("official-assistant", "official-thread", None),
    ),
)
async def test_service_requires_all_persisted_official_ids_for_agent_stream(
    monkeypatch: pytest.MonkeyPatch,
    official_assistant_id: str | None,
    official_thread_id: str | None,
    official_run_id: str | None,
) -> None:
    task = _task()
    latest_run = SimpleNamespace(
        id=uuid4(),
        status="running",
        finished_at=None,
        output_payload=None,
        official_assistant_id=official_assistant_id,
        official_run_id=official_run_id,
    )
    session = ScalarSession(
        task=task,
        latest_run=latest_run,
        official_thread_id=official_thread_id,
        joined_run_thread=(latest_run, official_thread_id),
    )
    actor = ActorContext(
        tenant_id="tenant",
        workspace_id="workspace",
        user_id="user",
        roles=("member",),
        permissions=("analysis:read",),
    )
    resolved = _resolved_actor(task)

    async def resolve_actor_for_test(
        _: ScalarSession, __: ActorContext
    ) -> ResolvedActor:
        return resolved

    monkeypatch.setattr(service_module, "resolve_actor", resolve_actor_for_test)
    service = ProductAnalysisService(
        session_factory=lambda: session,
    )

    view = await service.get_task(actor, str(task.id))

    assert view is not None
    assert view["agent_stream"] is None


def test_default_app_does_not_inject_current_agent_assistant_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    settings = SimpleNamespace(
        product_database_url="postgresql+asyncpg:///test",
        app_environment="local",
        agent_assistant_id="configured-assistant",
    )

    class CapturingProductAnalysisService:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def bootstrap_actor(self, _: ActorContext) -> None:
            return None

    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        app_module, "create_async_engine", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        app_module, "async_sessionmaker", lambda *_args, **_kwargs: "session-factory"
    )
    monkeypatch.setattr(
        app_module,
        "ProductAnalysisService",
        CapturingProductAnalysisService,
    )

    app_module.create_default_app()

    assert captured == {
        "session_factory": "session-factory",
        "inbox_cursor_key": None,
    }
