from typing import Any

import httpx
from langgraph_sdk.errors import ConflictError, NotFoundError
import pytest

from crypto_alert_v2.api.agent_server import AgentServerRunner, RemoteRunHandle
from crypto_alert_v2.api.schemas import AnalysisSubmission
from crypto_alert_v2.auth.context import ActorContext


class RecordingThreads:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.kwargs = kwargs
        return {"thread_id": "thread-1"}


class RecordingRuns:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.list_results: list[dict[str, Any]] = []
        self.list_args: tuple[Any, ...] | None = None
        self.list_kwargs: dict[str, Any] | None = None
        self.create_args: tuple[Any, ...] | None = None
        self.create_kwargs: dict[str, Any] | None = None
        self.get_args: tuple[Any, ...] | None = None
        self.get_kwargs: dict[str, Any] | None = None
        self.join_args: tuple[Any, ...] | None = None
        self.join_kwargs: dict[str, Any] | None = None
        self.cancel_args: tuple[Any, ...] | None = None
        self.cancel_kwargs: dict[str, Any] | None = None

    async def list(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.events.append("list")
        self.list_args = args
        self.list_kwargs = kwargs
        return self.list_results

    async def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.events.append("create")
        self.create_args = args
        self.create_kwargs = kwargs
        return {
            "run_id": "run-1",
            "assistant_id": "11111111-1111-4111-8111-111111111111",
        }

    async def get(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.events.append("get")
        self.get_args = args
        self.get_kwargs = kwargs
        return {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "assistant_id": "11111111-1111-4111-8111-111111111111",
            "status": "success",
        }

    async def join(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.events.append("join")
        self.join_args = args
        self.join_kwargs = kwargs
        return {"terminal_status": "failed", "errors": [{"code": "provider_unavailable"}]}

    async def cancel(self, *args: Any, **kwargs: Any) -> None:
        self.events.append("cancel")
        self.cancel_args = args
        self.cancel_kwargs = kwargs


class RecordingClient:
    def __init__(self) -> None:
        self.threads = RecordingThreads()
        self.runs = RecordingRuns()


@pytest.mark.asyncio
async def test_runner_uses_official_thread_and_sync_durable_run() -> None:
    client = RecordingClient()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    submission = AnalysisSubmission(
        symbol="BTC-USDT-SWAP",
        horizon="4h",
        query_text="Assess current BTC risk.",
        notify=False,
    )

    result = await runner.run(actor=actor, task_id="task-1", submission=submission)

    assert client.threads.kwargs == {
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "task_id": "task-1",
            "product_run_id": "task-1",
        },
        "graph_id": "crypto_analysis",
    }
    assert client.runs.create_args == ("thread-1", "crypto_analysis")
    assert client.runs.create_kwargs == {
        "input": {"request": submission.model_dump(mode="json")},
        "durability": "sync",
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "task_id": "task-1",
            "product_run_id": "task-1",
        },
    }
    assert client.runs.join_args == ("thread-1", "run-1")
    assert result.thread_id == "thread-1"
    assert result.run_id == "run-1"
    assert result.output["terminal_status"] == "failed"


@pytest.mark.asyncio
async def test_runner_exposes_remote_ids_before_join_and_can_cancel() -> None:
    client = RecordingClient()
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda actor: f"Bearer token-for-{actor.user_id}",
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    submission = AnalysisSubmission(
        symbol="BTC-USDT-SWAP",
        horizon="4h",
        query_text="Assess current BTC risk.",
        notify=False,
    )

    handle = await runner.start(
        actor=actor,
        task_id="task-1",
        product_thread_id="00000000-0000-0000-0000-000000000123",
        product_run_id="product-run-1",
        submission=submission,
    )

    assert handle.thread_id == "thread-1"
    assert handle.run_id == "run-1"
    assert handle.assistant_id == "11111111-1111-4111-8111-111111111111"
    assert client.runs.events == ["list", "create"]
    assert client.threads.kwargs == {
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "task_id": "task-1",
            "product_run_id": "product-run-1",
        },
        "thread_id": "00000000-0000-0000-0000-000000000123",
        "if_exists": "do_nothing",
        "graph_id": "crypto_analysis",
        "headers": {"authorization": "Bearer token-for-user-1"},
    }
    assert client.runs.create_kwargs is not None
    assert client.runs.create_kwargs["headers"] == {
        "authorization": "Bearer token-for-user-1"
    }

    state = await runner.get(handle)
    assert state.status == "success"
    assert client.runs.get_args == ("thread-1", "run-1")
    assert client.runs.get_kwargs == {
        "headers": {"authorization": "Bearer token-for-user-1"}
    }

    output = await runner.join(handle)
    assert output["terminal_status"] == "failed"
    assert client.runs.events == ["list", "create", "get", "join"]
    assert client.runs.join_kwargs == {
        "headers": {"authorization": "Bearer token-for-user-1"}
    }

    await runner.cancel(handle)
    assert client.runs.cancel_args == ("thread-1", "run-1")
    assert client.runs.cancel_kwargs == {
        "wait": True,
        "action": "interrupt",
        "headers": {"authorization": "Bearer token-for-user-1"}
    }
    assert client.runs.events == ["list", "create", "get", "join", "cancel"]


@pytest.mark.asyncio
async def test_runner_rejects_an_unknown_official_run_status() -> None:
    client = RecordingClient()
    client.runs.get = lambda *_, **__: _async_value(  # type: ignore[method-assign]
        {"status": "mystery"}
    )
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    with pytest.raises(RuntimeError, match="unknown status"):
        await runner.get(
            runner.authorize(
                handle=_remote_handle(),
                actor=ActorContext(
                    tenant_id="tenant-1",
                    workspace_id="workspace-1",
                    user_id="user-1",
                    roles=("member",),
                    permissions=("analysis:read",),
                ),
            )
        )


async def _async_value(value: Any) -> Any:
    return value


async def _async_raise(error: Exception) -> Any:
    raise error


def _remote_handle():
    return RemoteRunHandle(
        assistant_id="11111111-1111-4111-8111-111111111111",
        thread_id="thread-1",
        run_id="run-1",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_status", ["running", "interrupted"])
async def test_runner_recovers_an_existing_product_run_without_creating_another(
    existing_status: str,
) -> None:
    client = RecordingClient()
    client.runs.list_results = [
        {
            "run_id": "existing-run",
            "assistant_id": "22222222-2222-4222-8222-222222222222",
            "thread_id": "00000000-0000-0000-0000-000000000123",
            "metadata": {
                "tenant_id": "tenant-1",
                "workspace_id": "workspace-1",
                "user_id": "user-1",
                "task_id": "task-1",
                "product_run_id": "product-run-1",
            },
            "status": existing_status,
        }
    ]
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    submission = AnalysisSubmission(
        symbol="BTC-USDT-SWAP",
        horizon="4h",
        query_text="Assess current BTC risk.",
        notify=False,
    )

    handle = await runner.start(
        actor=actor,
        task_id="task-1",
        product_thread_id="00000000-0000-0000-0000-000000000123",
        product_run_id="product-run-1",
        submission=submission,
    )

    assert handle.run_id == "existing-run"
    assert handle.assistant_id == "22222222-2222-4222-8222-222222222222"
    assert client.runs.events == ["list"]
    assert client.runs.create_args is None


@pytest.mark.asyncio
async def test_runner_finds_an_unregistered_run_by_product_metadata() -> None:
    client = RecordingClient()
    client.runs.list_results = [
        {
            "run_id": "recovered-run",
            "assistant_id": "22222222-2222-4222-8222-222222222222",
            "metadata": {
                "tenant_id": "tenant-1",
                "workspace_id": "workspace-1",
                "user_id": "user-1",
                "task_id": "task-1",
                "product_run_id": "product-run-1",
            },
        }
    ]
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer recovery-token",
    )

    handle = await runner.find(
        actor=ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:write",),
        ),
        task_id="task-1",
        product_thread_id="product-thread-1",
        product_run_id="product-run-1",
    )

    assert handle == RemoteRunHandle(
        assistant_id="22222222-2222-4222-8222-222222222222",
        thread_id="product-thread-1",
        run_id="recovered-run",
    )
    assert handle is not None
    assert handle.authorization == "Bearer recovery-token"
    assert client.runs.list_args == ("product-thread-1",)
    assert client.runs.list_kwargs == {
        "limit": 100,
        "headers": {"authorization": "Bearer recovery-token"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [NotFoundError, ConflictError])
async def test_runner_treats_missing_or_terminal_cancel_target_as_stopped(
    error_type: type[Exception],
) -> None:
    client = RecordingClient()
    response = httpx.Response(
        404 if error_type is NotFoundError else 409,
        request=httpx.Request("POST", "http://agent.invalid/runs/cancel"),
    )
    error = error_type("cancel target unavailable", response=response, body=None)
    client.runs.cancel = lambda *_, **__: _async_raise(error)  # type: ignore[method-assign]
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    await runner.cancel(_remote_handle())


@pytest.mark.asyncio
async def test_runner_does_not_hide_a_cancel_conflict_for_an_active_run() -> None:
    client = RecordingClient()
    response = httpx.Response(
        409,
        request=httpx.Request("POST", "http://agent.invalid/runs/cancel"),
    )
    error = ConflictError(
        "active run cancellation conflicted",
        response=response,
        body=None,
    )
    client.runs.cancel = lambda *_, **__: _async_raise(error)  # type: ignore[method-assign]
    client.runs.get = lambda *_, **__: _async_value(  # type: ignore[method-assign]
        {"status": "running"}
    )
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    with pytest.raises(ConflictError):
        await runner.cancel(_remote_handle())
