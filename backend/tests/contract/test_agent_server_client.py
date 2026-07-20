from typing import Any

import httpx
from langgraph_sdk.errors import (
    APIConnectionError,
    APITimeoutError,
    ConflictError,
    NotFoundError,
)
from langgraph_sdk.schema import StreamPart
import pytest

from crypto_alert_v2.api.agent_server import (
    AgentServerRunner,
    RemoteCheckpoint,
    RemoteForkIndeterminateError,
    RemoteInterruptSet,
    RemoteResumeIndeterminateError,
    RemoteRunHandle,
    RemoteSubmitIndeterminateError,
)
from crypto_alert_v2.api.request_identity import correlation_id_for_task
from crypto_alert_v2.api.schemas import AnalysisSubmission, DeepResearchSubmission
from crypto_alert_v2.auth.context import ActorContext


class RecordingThreads:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None
        self.state_result: dict[str, Any] = {
            "checkpoint": {
                "thread_id": "thread-1",
                "checkpoint_ns": "",
                "checkpoint_id": "checkpoint-1",
                "checkpoint_map": {},
            },
            "interrupts": [],
            "next": [],
            "tasks": [],
            "metadata": {"run_id": "run-1"},
        }
        self.get_state_args: tuple[Any, ...] | None = None
        self.get_state_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.kwargs = kwargs
        return {"thread_id": "thread-1"}

    async def get_state(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.get_state_args = args
        self.get_state_kwargs = kwargs
        return self.state_result


class RecordingRuns:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.list_results: list[dict[str, Any]] = []
        self.list_batches: list[list[dict[str, Any]]] | None = None
        self.list_pages: dict[int, list[dict[str, Any]]] | None = None
        self.list_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.list_args: tuple[Any, ...] | None = None
        self.list_kwargs: dict[str, Any] | None = None
        self.create_args: tuple[Any, ...] | None = None
        self.create_kwargs: dict[str, Any] | None = None
        self.create_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.create_error: Exception | None = None
        self.create_metadata_before_error = False
        self.get_args: tuple[Any, ...] | None = None
        self.get_kwargs: dict[str, Any] | None = None
        self.join_args: tuple[Any, ...] | None = None
        self.join_kwargs: dict[str, Any] | None = None
        self.join_stream_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.stream_parts: list[StreamPart] = []
        self.cancel_args: tuple[Any, ...] | None = None
        self.cancel_kwargs: dict[str, Any] | None = None
        self.get_status = "success"

    async def list(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.events.append("list")
        self.list_args = args
        self.list_kwargs = kwargs
        self.list_calls.append((args, kwargs))
        if self.list_pages is not None:
            return self.list_pages.get(int(kwargs.get("offset", 0)), [])
        if self.list_batches:
            return self.list_batches.pop(0)
        return self.list_results

    async def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.events.append("create")
        self.create_args = args
        self.create_kwargs = kwargs
        self.create_calls.append((args, kwargs))
        on_run_created = kwargs.get("on_run_created")
        if self.create_error is not None:
            if self.create_metadata_before_error and callable(on_run_created):
                on_run_created({"run_id": "accepted-run", "thread_id": args[0]})
            raise self.create_error
        if callable(on_run_created):
            on_run_created({"run_id": "run-1", "thread_id": args[0]})
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
            "status": self.get_status,
        }

    async def join(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.events.append("join")
        self.join_args = args
        self.join_kwargs = kwargs
        return {
            "terminal_status": "failed",
            "errors": [{"code": "provider_unavailable"}],
        }

    async def join_stream(self, *args: Any, **kwargs: Any):
        self.events.append("join_stream")
        self.join_stream_calls.append((args, kwargs))
        for part in self.stream_parts:
            yield part

    async def cancel(self, *args: Any, **kwargs: Any) -> None:
        self.events.append("cancel")
        self.cancel_args = args
        self.cancel_kwargs = kwargs


class RecordingClient:
    def __init__(self) -> None:
        self.threads = RecordingThreads()
        self.runs = RecordingRuns()


def _two_interrupt_state() -> dict[str, Any]:
    root_interrupt = {
        "id": "root-interrupt",
        "value": {"schema_version": "hitl.review.v1", "kind": "review"},
    }
    nested_interrupt = {
        "id": "nested-interrupt",
        "value": {
            "schema_version": "hitl.review.v1",
            "kind": "source_review",
        },
    }
    child_checkpoint_map = {
        "": "root-checkpoint",
        "research:child": "nested-checkpoint",
    }
    return {
        "checkpoint": {
            "thread_id": "thread-1",
            "checkpoint_ns": "",
            "checkpoint_id": "root-checkpoint",
        },
        "next": ["root-review", "research-subgraph"],
        "metadata": {"run_id": "run-1", "step": 0, "parents": {}},
        "interrupts": [root_interrupt, nested_interrupt],
        "tasks": [
            {
                "id": "root-task",
                "name": "root-review",
                "checkpoint": None,
                "state": None,
                "interrupts": [root_interrupt],
                "result": None,
            },
            {
                "id": "nested-task",
                "name": "research-subgraph",
                "checkpoint": None,
                "state": {
                    "checkpoint": {
                        "thread_id": "thread-1",
                        "checkpoint_ns": "research:child",
                        "checkpoint_id": "nested-checkpoint",
                        "checkpoint_map": child_checkpoint_map,
                    },
                    "next": ["source-review"],
                    "metadata": {
                        "run_id": "run-1",
                        "step": 0,
                        "parents": {"": "root-checkpoint"},
                    },
                    "interrupts": [nested_interrupt],
                    "tasks": [
                        {
                            "id": "nested-child-task",
                            "name": "source-review",
                            "checkpoint": None,
                            "state": None,
                            "interrupts": [nested_interrupt],
                            "result": None,
                        }
                    ],
                },
                "interrupts": [nested_interrupt],
                "result": None,
            },
        ],
    }


def _single_interrupt_state(*, run_id: str = "run-1") -> dict[str, Any]:
    interrupt = {
        "id": "interrupt-review",
        "value": {"kind": "artifact_review", "schema_version": "1.0"},
    }
    return {
        "checkpoint": {
            "thread_id": "thread-1",
            "checkpoint_ns": "",
            "checkpoint_id": "checkpoint-review",
        },
        "next": ["artifact-review"],
        "metadata": {"run_id": run_id, "step": 0, "parents": {}},
        "interrupts": [interrupt],
        "tasks": [
            {
                "id": "review-task",
                "name": "artifact-review",
                "checkpoint": None,
                "state": None,
                "interrupts": [interrupt],
                "result": None,
            }
        ],
    }


@pytest.mark.asyncio
async def test_runner_uses_official_thread_and_sync_durable_run() -> None:
    client = RecordingClient()
    request_ids = iter(
        (
            "00000000-0000-4000-8000-000000000101",
            "00000000-0000-4000-8000-000000000102",
        )
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        request_id_factory=lambda: next(request_ids),
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

    result = await runner.run(actor=actor, task_id="task-1", submission=submission)

    assert client.threads.kwargs == {
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "identity_issuer": "legacy",
            "task_id": "task-1",
            "task_type": "market_analysis",
            "product_run_id": "task-1",
            "correlation_id": correlation_id_for_task("task-1"),
            "request_id": "00000000-0000-4000-8000-000000000101",
            "lineage": {
                "operation": "submit",
                "product_run_id": "task-1",
            },
        },
        "graph_id": "crypto_analysis",
        "headers": {
            "x-request-id": "00000000-0000-4000-8000-000000000101",
        },
    }
    assert client.runs.create_args == ("thread-1", "crypto_analysis")
    assert client.runs.create_kwargs is not None
    create_kwargs = dict(client.runs.create_kwargs)
    assert callable(create_kwargs.pop("on_run_created"))
    assert create_kwargs == {
        "input": {
            "request": submission.model_dump(mode="json"),
            "review_policy": "bypass",
        },
        "durability": "sync",
        "stream_mode": ["updates", "custom"],
        "stream_resumable": True,
        "if_not_exists": "reject",
        "multitask_strategy": "reject",
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "identity_issuer": "legacy",
            "task_id": "task-1",
            "task_type": "market_analysis",
            "product_run_id": "task-1",
            "thread_id": "thread-1",
            "correlation_id": correlation_id_for_task("task-1"),
            "request_id": "00000000-0000-4000-8000-000000000102",
            "lineage": {
                "operation": "submit",
                "product_run_id": "task-1",
            },
        },
        "headers": {
            "x-request-id": "00000000-0000-4000-8000-000000000102",
        },
    }
    assert client.runs.join_args == ("thread-1", "run-1")
    assert result.thread_id == "thread-1"
    assert result.run_id == "run-1"
    assert result.output["terminal_status"] == "failed"


@pytest.mark.asyncio
async def test_runner_routes_deep_research_through_the_same_assistant() -> None:
    client = RecordingClient()
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    submission = DeepResearchSubmission(
        symbol="BTC-USDT-SWAP",
        horizon="7d",
        query_text="Research BTC institutional adoption and counter-evidence.",
    )

    await runner.start(
        actor=actor,
        task_id="research-task-1",
        product_thread_id="research-thread-1",
        product_run_id="research-run-1",
        submission=submission,
        task_type="deep_research",
    )

    assert client.runs.create_args == ("thread-1", "crypto_analysis")
    assert client.runs.create_kwargs is not None
    assert client.runs.create_kwargs["input"]["request"] == {
        "task_type": "deep_research",
        "symbol": "BTC-USDT-SWAP",
        "horizon": "7d",
        "query_text": "Research BTC institutional adoption and counter-evidence.",
    }
    assert client.runs.create_kwargs["metadata"]["task_type"] == "deep_research"
    assert client.threads.kwargs["metadata"]["task_type"] == "deep_research"


@pytest.mark.asyncio
async def test_runner_forwards_explicit_exit_durability_to_official_runs_api() -> None:
    client = RecordingClient()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )

    await runner.start(
        actor=actor,
        task_id="task-exit-durability",
        product_thread_id=None,
        product_run_id="product-run-exit-durability",
        submission=AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Prove exit durability serialization.",
            notify=False,
        ),
        durability="exit",
    )

    assert client.runs.create_kwargs is not None
    assert client.runs.create_kwargs["durability"] == "exit"


@pytest.mark.asyncio
async def test_runner_joins_the_official_resumable_update_stream() -> None:
    client = RecordingClient()
    client.runs.stream_parts = [
        StreamPart(
            event="updates",
            data={"collect_market_snapshot": {"market_snapshot": {"symbol": "BTC"}}},
            id="event-17",
        )
    ]
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer stream-token",
    )
    handle = runner.authorize(
        _remote_handle(),
        ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:read",),
        ),
    )

    parts = [
        part
        async for part in runner.join_stream(
            handle,
            last_event_id="event-16",
        )
    ]

    assert parts == client.runs.stream_parts
    assert client.runs.join_stream_calls == [
        (
            ("thread-1", "run-1"),
            {
                "cancel_on_disconnect": False,
                "stream_mode": ["updates"],
                "last_event_id": "event-16",
                "headers": {"authorization": "Bearer stream-token"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_runner_replays_a_resumable_stream_from_the_start_without_a_cursor() -> (
    None
):
    client = RecordingClient()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    assert [part async for part in runner.join_stream(_remote_handle())] == []

    assert client.runs.join_stream_calls == [
        (
            ("thread-1", "run-1"),
            {
                "cancel_on_disconnect": False,
                "stream_mode": ["updates"],
                "last_event_id": "0",
            },
        )
    ]


@pytest.mark.asyncio
async def test_runner_recovers_submit_id_from_official_response_headers() -> None:
    client = RecordingClient()
    client.runs.create_metadata_before_error = True
    client.runs.create_error = APITimeoutError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0,),
    )

    handle = await runner.start(
        actor=ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:write",),
        ),
        task_id="task-submit-header",
        product_thread_id="product-thread-submit-header",
        product_run_id="product-run-submit-header",
        submission=AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Assess submit recovery.",
            notify=False,
        ),
    )

    assert handle.run_id == "accepted-run"
    assert handle.assistant_id == "crypto_analysis"
    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_never_recreates_an_indeterminate_submit() -> None:
    client = RecordingClient()
    client.runs.create_error = APITimeoutError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0, 0),
    )
    kwargs = {
        "actor": ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:write",),
        ),
        "task_id": "task-submit-indeterminate",
        "product_thread_id": "product-thread-submit-indeterminate",
        "product_run_id": "product-run-submit-indeterminate",
        "submission": AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Assess indeterminate submit.",
            notify=False,
        ),
    }

    with pytest.raises(RemoteSubmitIndeterminateError, match="indeterminate"):
        await runner.start(**kwargs)
    with pytest.raises(RemoteSubmitIndeterminateError, match="indeterminate"):
        await runner.start(**kwargs)

    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_retries_submit_when_connection_was_never_established() -> None:
    client = RecordingClient()
    client.runs.create_error = httpx.ConnectTimeout(
        "connect timeout",
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs"),
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0,),
    )
    kwargs = {
        "actor": ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:write",),
        ),
        "task_id": "task-submit-connect-timeout",
        "product_thread_id": "product-thread-submit-connect-timeout",
        "product_run_id": "product-run-submit-connect-timeout",
        "submission": AnalysisSubmission(
            symbol="BTC-USDT-SWAP",
            horizon="4h",
            query_text="Assess pre-accept retry.",
            notify=False,
        ),
    }

    with pytest.raises(httpx.ConnectTimeout):
        await runner.start(**kwargs)
    client.runs.create_error = None
    handle = await runner.start(**kwargs)

    assert handle.run_id == "run-1"
    assert len(client.runs.create_calls) == 2


@pytest.mark.asyncio
async def test_runner_exposes_remote_ids_before_join_and_can_cancel() -> None:
    client = RecordingClient()
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda actor: f"Bearer token-for-{actor.user_id}",
        request_id_factory=iter(
            (
                "00000000-0000-4000-8000-000000000201",
                "00000000-0000-4000-8000-000000000202",
            )
        ).__next__,
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
            "identity_issuer": "legacy",
            "task_id": "task-1",
            "task_type": "market_analysis",
            "product_run_id": "product-run-1",
            "correlation_id": correlation_id_for_task("task-1"),
            "request_id": "00000000-0000-4000-8000-000000000201",
            "lineage": {
                "operation": "submit",
                "product_run_id": "product-run-1",
            },
        },
        "thread_id": "00000000-0000-0000-0000-000000000123",
        "if_exists": "do_nothing",
        "graph_id": "crypto_analysis",
        "headers": {
            "authorization": "Bearer token-for-user-1",
            "x-request-id": "00000000-0000-4000-8000-000000000201",
        },
    }
    assert client.runs.create_kwargs is not None
    assert client.runs.create_kwargs["headers"] == {
        "authorization": "Bearer token-for-user-1",
        "x-request-id": "00000000-0000-4000-8000-000000000202",
    }
    assert client.runs.create_kwargs["metadata"] == {
        **client.threads.kwargs["metadata"],
        "thread_id": "thread-1",
        "request_id": "00000000-0000-4000-8000-000000000202",
    }

    state = await runner.get(handle)
    assert state.status == "success"
    assert client.runs.get_args == ("thread-1", "run-1")
    assert client.runs.get_kwargs == {
        "headers": {"authorization": "Bearer token-for-user-1"}
    }
    assert client.threads.get_state_args == ("thread-1",)
    assert client.threads.get_state_kwargs == {
        "subgraphs": True,
        "headers": {"authorization": "Bearer token-for-user-1"},
    }

    output = await runner.join(handle)
    assert output["terminal_status"] == "failed"
    assert client.runs.events == ["list", "create", "get", "join"]
    assert client.runs.join_kwargs == {
        "headers": {"authorization": "Bearer token-for-user-1"}
    }

    client.runs.get_status = "interrupted"
    cancel_result = await runner.cancel(handle)
    assert cancel_result.outcome == "confirmed"
    assert cancel_result.state is not None
    assert cancel_result.state.status == "interrupted"
    assert client.runs.cancel_args == ("thread-1", "run-1")
    assert client.runs.cancel_kwargs == {
        "wait": True,
        "action": "interrupt",
        "headers": {"authorization": "Bearer token-for-user-1"},
    }
    assert client.runs.events == ["list", "create", "get", "join", "cancel", "get"]


@pytest.mark.asyncio
async def test_runner_forks_with_official_top_level_checkpoint_id() -> None:
    client = RecordingClient()
    client.threads.state_result["checkpoint"]["checkpoint_id"] = (
        "checkpoint-fork-source"
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer fork-token",
        request_id_factory=lambda: "00000000-0000-4000-8000-000000000301",
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    forked = await runner.fork(
        actor=actor,
        handle=_remote_handle(),
        task_id="task-1",
        product_run_id="product-fork-run-2",
        checkpoint_id="checkpoint-fork-source",
    )

    assert client.runs.create_args == (
        "thread-1",
        "11111111-1111-4111-8111-111111111111",
    )
    assert client.runs.create_kwargs is not None
    create_kwargs = dict(client.runs.create_kwargs)
    assert callable(create_kwargs.pop("on_run_created"))
    assert create_kwargs == {
        "input": None,
        "checkpoint_id": "checkpoint-fork-source",
        "durability": "sync",
        "stream_mode": ["updates", "custom"],
        "stream_resumable": True,
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "identity_issuer": "legacy",
            "task_id": "task-1",
            "product_run_id": "product-fork-run-2",
            "thread_id": "thread-1",
            "forked_from_official_run_id": "run-1",
            "forked_from_checkpoint_id": "checkpoint-fork-source",
            "correlation_id": correlation_id_for_task("task-1"),
            "request_id": "00000000-0000-4000-8000-000000000301",
            "lineage": {
                "operation": "fork",
                "product_run_id": "product-fork-run-2",
                "parent_official_run_id": "run-1",
                "checkpoint_id": "checkpoint-fork-source",
            },
        },
        "headers": {
            "authorization": "Bearer fork-token",
            "x-request-id": "00000000-0000-4000-8000-000000000301",
        },
    }
    assert "config" not in create_kwargs
    assert client.threads.get_state_args == ("thread-1",)
    assert client.threads.get_state_kwargs == {
        "checkpoint_id": "checkpoint-fork-source",
        "headers": {"authorization": "Bearer fork-token"},
    }
    assert forked == RemoteRunHandle(
        assistant_id="11111111-1111-4111-8111-111111111111",
        thread_id="thread-1",
        run_id="run-1",
    )
    assert forked.authorization == "Bearer fork-token"


@pytest.mark.asyncio
async def test_runner_never_recreates_an_indeterminate_checkpoint_fork() -> None:
    client = RecordingClient()
    client.threads.state_result["checkpoint"]["checkpoint_id"] = (
        "checkpoint-fork-indeterminate"
    )
    client.runs.create_error = APITimeoutError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0, 0),
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    fork_kwargs = {
        "actor": actor,
        "handle": _remote_handle(),
        "task_id": "task-1",
        "product_run_id": "product-fork-indeterminate",
        "checkpoint_id": "checkpoint-fork-indeterminate",
    }

    with pytest.raises(RemoteForkIndeterminateError, match="indeterminate"):
        await runner.fork(**fork_kwargs)
    with pytest.raises(RemoteForkIndeterminateError, match="indeterminate"):
        await runner.fork(**fork_kwargs)

    assert len(client.runs.create_calls) == 1
    assert client.runs.events.count("create") == 1
    assert client.runs.create_kwargs is not None
    assert client.runs.create_kwargs["checkpoint_id"] == (
        "checkpoint-fork-indeterminate"
    )


@pytest.mark.asyncio
async def test_runner_never_recreates_a_fork_after_a_connection_reset() -> None:
    client = RecordingClient()
    client.threads.state_result["checkpoint"]["checkpoint_id"] = (
        "checkpoint-fork-connection-reset"
    )
    client.runs.create_error = APIConnectionError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0, 0),
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    fork_kwargs = {
        "actor": actor,
        "handle": _remote_handle(),
        "task_id": "task-1",
        "product_run_id": "product-fork-connection-reset",
        "checkpoint_id": "checkpoint-fork-connection-reset",
    }

    with pytest.raises(RemoteForkIndeterminateError, match="indeterminate"):
        await runner.fork(**fork_kwargs)
    with pytest.raises(RemoteForkIndeterminateError, match="indeterminate"):
        await runner.fork(**fork_kwargs)

    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_rejects_fork_checkpoint_from_another_official_source_run() -> (
    None
):
    client = RecordingClient()
    client.threads.state_result["checkpoint"]["checkpoint_id"] = (
        "checkpoint-wrong-source"
    )
    client.threads.state_result["metadata"]["run_id"] = "another-official-run"
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    with pytest.raises(RuntimeError, match="selected source Run"):
        await runner.fork(
            actor=ActorContext(
                tenant_id="tenant-1",
                workspace_id="workspace-1",
                user_id="user-1",
                roles=("member",),
                permissions=("analysis:read", "analysis:write"),
            ),
            handle=_remote_handle(),
            task_id="task-1",
            product_run_id="product-fork-wrong-source",
            checkpoint_id="checkpoint-wrong-source",
        )

    assert client.runs.create_calls == []


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


@pytest.mark.asyncio
async def test_runner_normalizes_success_with_pending_interrupt() -> None:
    client = RecordingClient()
    client.runs.get_status = "success"
    client.threads.state_result = _single_interrupt_state()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    state = await runner.get(_remote_handle())

    assert state.status == "interrupted"
    assert client.threads.get_state_args == ("thread-1",)
    assert client.threads.get_state_kwargs == {"subgraphs": True}


@pytest.mark.asyncio
async def test_runner_does_not_bind_a_later_runs_interrupt_to_an_old_success() -> None:
    client = RecordingClient()
    client.runs.get_status = "success"
    client.threads.state_result = _single_interrupt_state(run_id="later-run")
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    state = await runner.get(_remote_handle())

    assert state.status == "success"


@pytest.mark.asyncio
async def test_runner_reads_official_root_and_nested_interrupt_identity() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    interrupts = await runner.get_interrupts(_remote_handle())

    assert isinstance(interrupts, RemoteInterruptSet)
    assert interrupts.checkpoint == RemoteCheckpoint(
        thread_id="thread-1",
        checkpoint_ns="",
        checkpoint_id="root-checkpoint",
        checkpoint_map={
            "": "root-checkpoint",
            "research:child": "nested-checkpoint",
        },
    )
    assert [
        (
            item.interrupt_id,
            item.namespace,
            item.checkpoint_id,
            item.value["kind"],
        )
        for item in interrupts
    ] == [
        ("root-interrupt", "", "root-checkpoint", "review"),
        (
            "nested-interrupt",
            "research:child",
            "nested-checkpoint",
            "source_review",
        ),
    ]
    assert client.threads.get_state_args == ("thread-1",)
    assert client.threads.get_state_kwargs == {"subgraphs": True}


@pytest.mark.asyncio
async def test_runner_excludes_a_consumed_task_from_the_pending_interrupt_set() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    client.threads.state_result["next"] = ["research-subgraph"]
    client.threads.state_result["tasks"][0]["result"] = {
        "root_review": {"action": "approve"}
    }
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    interrupts = await runner.get_interrupts(_remote_handle())

    assert [member.interrupt_id for member in interrupts] == ["nested-interrupt"]
    assert interrupts.checkpoint.checkpoint_map == {
        "": "root-checkpoint",
        "research:child": "nested-checkpoint",
    }


@pytest.mark.asyncio
async def test_runner_rejects_a_malformed_child_checkpoint_map() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    child_checkpoint = client.threads.state_result["tasks"][1]["state"]["checkpoint"]
    child_checkpoint["checkpoint_map"]["research:child"] = 42
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    with pytest.raises(RuntimeError, match="invalid checkpoint id"):
        await runner.get_interrupts(_remote_handle())


@pytest.mark.asyncio
async def test_runner_rejects_a_child_map_without_its_own_lineage() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    child_checkpoint = client.threads.state_result["tasks"][1]["state"]["checkpoint"]
    child_checkpoint["checkpoint_map"] = {"": "root-checkpoint"}
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    with pytest.raises(RuntimeError, match="omits its own checkpoint"):
        await runner.get_interrupts(_remote_handle())


@pytest.mark.asyncio
async def test_runner_rejects_interrupts_from_another_current_run() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    client.threads.state_result["metadata"]["run_id"] = "later-run"
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    with pytest.raises(RuntimeError, match="belongs to another Run"):
        await runner.get_interrupts(_remote_handle())


@pytest.mark.asyncio
async def test_runner_resumes_with_an_official_current_head_command() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        authorization_provider=lambda _: "Bearer resume-token",
        request_id_factory=lambda: "00000000-0000-4000-8000-000000000401",
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    interrupt_set = await runner.get_interrupts(_remote_handle())

    resumed = await runner.resume(
        actor=actor,
        handle=_remote_handle(),
        task_id="task-1",
        product_run_id="product-run-2",
        responses={
            "root-interrupt": {"action": "approve", "response_version": 1},
            "nested-interrupt": {"action": "reject", "response_version": 1},
        },
        checkpoint=interrupt_set.checkpoint,
    )

    assert client.runs.create_args == (
        "thread-1",
        "11111111-1111-4111-8111-111111111111",
    )
    assert client.runs.create_kwargs is not None
    create_kwargs = dict(client.runs.create_kwargs)
    assert callable(create_kwargs.pop("on_run_created"))
    assert create_kwargs == {
        "command": {
            "resume": {
                "root-interrupt": {
                    "action": "approve",
                    "response_version": 1,
                },
                "nested-interrupt": {
                    "action": "reject",
                    "response_version": 1,
                },
            }
        },
        "durability": "sync",
        "stream_mode": ["updates", "custom"],
        "stream_resumable": True,
        "multitask_strategy": "reject",
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "task_id": "task-1",
            "product_run_id": "product-run-2",
            "thread_id": "thread-1",
            "resume_of_official_run_id": "run-1",
            "correlation_id": correlation_id_for_task("task-1"),
            "request_id": "00000000-0000-4000-8000-000000000401",
            "lineage": {
                "operation": "resume",
                "product_run_id": "product-run-2",
                "parent_official_run_id": "run-1",
            },
        },
        "headers": {
            "authorization": "Bearer resume-token",
            "x-request-id": "00000000-0000-4000-8000-000000000401",
        },
    }
    assert resumed == RemoteRunHandle(
        assistant_id="11111111-1111-4111-8111-111111111111",
        thread_id="thread-1",
        run_id="run-1",
    )
    assert resumed.authorization == "Bearer resume-token"
    assert client.runs.events == ["list", "create"]
    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_rejects_a_stale_checkpoint_before_create() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")
    stale_interrupt_set = await runner.get_interrupts(_remote_handle())
    client.threads.state_result["checkpoint"]["checkpoint_id"] = "new-root"
    child_checkpoint = client.threads.state_result["tasks"][1]["state"]["checkpoint"]
    child_checkpoint["checkpoint_map"][""] = "new-root"

    with pytest.raises(RuntimeError, match="no longer current"):
        await runner.resume(
            actor=ActorContext(
                tenant_id="tenant-1",
                workspace_id="workspace-1",
                user_id="user-1",
                roles=("member",),
                permissions=("analysis:read", "analysis:write"),
            ),
            handle=_remote_handle(),
            task_id="task-1",
            product_run_id="product-run-stale",
            responses={
                "root-interrupt": {"action": "approve"},
                "nested-interrupt": {"action": "approve"},
            },
            checkpoint=stale_interrupt_set.checkpoint,
        )

    assert client.runs.create_calls == []


@pytest.mark.asyncio
async def test_runner_rejects_a_partial_aggregate_resume_before_create() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    interrupt_set = await runner.get_interrupts(_remote_handle())

    with pytest.raises(RuntimeError, match="exactly match"):
        await runner.resume(
            actor=actor,
            handle=_remote_handle(),
            task_id="task-1",
            product_run_id="product-run-partial",
            responses={"root-interrupt": {"action": "approve"}},
            checkpoint=interrupt_set.checkpoint,
        )

    assert client.runs.create_calls == []


@pytest.mark.asyncio
async def test_runner_normalizes_legacy_single_interrupt_resume() -> None:
    client = RecordingClient()
    client.threads.state_result = _single_interrupt_state()
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    await runner.resume(
        actor=ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:read", "analysis:write"),
        ),
        handle=_remote_handle(),
        task_id="task-1",
        product_run_id="product-run-2",
        response={"action": "approve", "response_version": 1},
        checkpoint_id="checkpoint-review",
    )

    assert client.runs.create_kwargs is not None
    assert client.runs.create_kwargs["command"] == {
        "resume": {"interrupt-review": {"action": "approve", "response_version": 1}}
    }
    assert "checkpoint" not in client.runs.create_kwargs
    assert "checkpoint_id" not in client.runs.create_kwargs
    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_recovers_the_run_id_from_timeout_response_headers() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    client.runs.create_metadata_before_error = True
    client.runs.create_error = APITimeoutError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0,),
    )
    interrupt_set = await runner.get_interrupts(_remote_handle())

    resumed = await runner.resume(
        actor=ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:read", "analysis:write"),
        ),
        handle=_remote_handle(),
        task_id="task-1",
        product_run_id="product-run-header-recovery",
        responses={
            "root-interrupt": {"action": "approve"},
            "nested-interrupt": {"action": "approve"},
        },
        checkpoint=interrupt_set.checkpoint,
    )

    assert resumed.run_id == "accepted-run"
    assert client.runs.events == ["list", "create"]
    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_recovers_an_accepted_resume_after_an_sdk_timeout() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    accepted_run = {
        "run_id": "accepted-resume-run",
        "assistant_id": "11111111-1111-4111-8111-111111111111",
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "task_id": "task-1",
            "product_run_id": "product-run-2",
        },
    }
    client.runs.list_batches = [
        [],
        [],
        [],
        [accepted_run],
    ]
    client.runs.create_error = APITimeoutError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0, 0, 0),
    )
    interrupt_set = await runner.get_interrupts(_remote_handle())

    resumed = await runner.resume(
        actor=ActorContext(
            tenant_id="tenant-1",
            workspace_id="workspace-1",
            user_id="user-1",
            roles=("member",),
            permissions=("analysis:read", "analysis:write"),
        ),
        handle=_remote_handle(),
        task_id="task-1",
        product_run_id="product-run-2",
        responses={
            "root-interrupt": {"action": "approve", "response_version": 1},
            "nested-interrupt": {"action": "reject", "response_version": 1},
        },
        checkpoint=interrupt_set.checkpoint,
    )

    assert resumed.run_id == "accepted-resume-run"
    assert client.runs.events == ["list", "create", "list", "list", "list"]
    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_rejects_an_ambiguous_lookup_after_an_sdk_timeout() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    metadata = {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "user-1",
        "task_id": "task-1",
        "product_run_id": "product-run-2",
    }
    client.runs.list_batches = [
        [],
        [
            {
                "run_id": f"ambiguous-resume-run-{index}",
                "assistant_id": "11111111-1111-4111-8111-111111111111",
                "metadata": metadata,
            }
            for index in range(2)
        ],
    ]
    client.runs.create_error = APITimeoutError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0,),
    )
    interrupt_set = await runner.get_interrupts(_remote_handle())

    with pytest.raises(RuntimeError, match="Multiple Agent Server Runs"):
        await runner.resume(
            actor=ActorContext(
                tenant_id="tenant-1",
                workspace_id="workspace-1",
                user_id="user-1",
                roles=("member",),
                permissions=("analysis:read", "analysis:write"),
            ),
            handle=_remote_handle(),
            task_id="task-1",
            product_run_id="product-run-2",
            responses={
                "root-interrupt": {"action": "approve", "response_version": 1},
                "nested-interrupt": {"action": "reject", "response_version": 1},
            },
            checkpoint=interrupt_set.checkpoint,
        )

    assert client.runs.events == ["list", "create", "list"]
    assert len(client.runs.create_calls) == 1


@pytest.mark.asyncio
async def test_runner_never_recreates_an_indeterminate_resume() -> None:
    client = RecordingClient()
    client.threads.state_result = _two_interrupt_state()
    client.runs.create_error = APITimeoutError(
        request=httpx.Request("POST", "http://agent.invalid/threads/thread-1/runs")
    )
    runner = AgentServerRunner(
        client=client,
        assistant_id="crypto_analysis",
        resume_reconciliation_delays=(0, 0),
    )
    actor = ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )
    interrupt_set = await runner.get_interrupts(_remote_handle())
    resume_kwargs = {
        "actor": actor,
        "handle": _remote_handle(),
        "task_id": "task-1",
        "product_run_id": "product-run-indeterminate",
        "responses": {
            "root-interrupt": {"action": "approve"},
            "nested-interrupt": {"action": "reject"},
        },
        "checkpoint": interrupt_set.checkpoint,
    }

    with pytest.raises(RemoteResumeIndeterminateError, match="indeterminate"):
        await runner.resume(**resume_kwargs)
    with pytest.raises(RemoteResumeIndeterminateError, match="indeterminate"):
        await runner.resume(**resume_kwargs)

    assert len(client.runs.create_calls) == 1
    assert client.runs.events.count("create") == 1
    assert client.runs.events.count("list") == 6


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
                "identity_issuer": "legacy",
                "task_id": "task-1",
                "task_type": "market_analysis",
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
async def test_runner_injects_server_owned_required_review_policy() -> None:
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
        query_text="Require an explicit review.",
        notify=False,
    )

    await runner.start(
        actor=actor,
        task_id="task-required-review",
        product_thread_id="00000000-0000-0000-0000-000000000456",
        product_run_id="product-run-required-review",
        submission=submission,
        review_policy="required",
    )

    assert client.runs.create_kwargs is not None
    assert client.runs.create_kwargs["input"] == {
        "request": submission.model_dump(mode="json"),
        "review_policy": "required",
    }


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
                "identity_issuer": "legacy",
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
        "offset": 0,
        "headers": {"authorization": "Bearer recovery-token"},
    }


@pytest.mark.asyncio
async def test_runner_searches_all_run_pages_before_reporting_missing() -> None:
    client = RecordingClient()
    matching_run = {
        "run_id": "second-page-run",
        "assistant_id": "22222222-2222-4222-8222-222222222222",
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "task_id": "task-1",
            "product_run_id": "product-run-1",
        },
    }
    client.runs.list_pages = {
        0: [{"metadata": {}} for _ in range(100)],
        100: [matching_run],
    }
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

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

    assert handle is not None
    assert handle.run_id == "second-page-run"
    assert [call[1]["offset"] for call in client.runs.list_calls] == [0, 100]


@pytest.mark.asyncio
async def test_runner_rejects_duplicate_runs_for_one_product_run() -> None:
    client = RecordingClient()
    metadata = {
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "user_id": "user-1",
        "task_id": "task-1",
        "product_run_id": "product-run-1",
    }
    client.runs.list_results = [
        {
            "run_id": f"duplicate-run-{index}",
            "assistant_id": "22222222-2222-4222-8222-222222222222",
            "metadata": metadata,
        }
        for index in range(2)
    ]
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    with pytest.raises(RuntimeError, match="Multiple Agent Server Runs"):
        await runner.find(
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


@pytest.mark.asyncio
async def test_runner_reports_a_missing_cancel_target_as_unconfirmed() -> None:
    client = RecordingClient()
    response = httpx.Response(
        404,
        request=httpx.Request("POST", "http://agent.invalid/runs/cancel"),
    )
    error = NotFoundError("cancel target unavailable", response=response, body=None)
    client.runs.cancel = lambda *_, **__: _async_raise(error)  # type: ignore[method-assign]
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    result = await runner.cancel(_remote_handle())

    assert result.outcome == "unconfirmed"
    assert result.state is None


@pytest.mark.asyncio
async def test_runner_preserves_a_terminal_run_that_won_the_cancel_race() -> None:
    client = RecordingClient()
    response = httpx.Response(
        409,
        request=httpx.Request("POST", "http://agent.invalid/runs/cancel"),
    )
    error = ConflictError("cancel target is terminal", response=response, body=None)
    client.runs.cancel = lambda *_, **__: _async_raise(error)  # type: ignore[method-assign]
    client.runs.get_status = "success"
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    result = await runner.cancel(_remote_handle())

    assert result.outcome == "terminal"
    assert result.state is not None
    assert result.state.status == "success"


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
    client.runs.get_status = "running"
    runner = AgentServerRunner(client=client, assistant_id="crypto_analysis")

    result = await runner.cancel(_remote_handle())

    assert result.outcome == "unconfirmed"
    assert result.state is not None
    assert result.state.status == "running"
