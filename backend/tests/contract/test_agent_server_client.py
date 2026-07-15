from typing import Any

import httpx
from langgraph_sdk.errors import APITimeoutError, ConflictError, NotFoundError
import pytest

from crypto_alert_v2.api.agent_server import (
    AgentServerRunner,
    RemoteCheckpoint,
    RemoteInterruptSet,
    RemoteResumeIndeterminateError,
    RemoteRunHandle,
)
from crypto_alert_v2.api.schemas import AnalysisSubmission
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
        "input": {
            "request": submission.model_dump(mode="json"),
            "review_policy": "bypass",
        },
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
        "multitask_strategy": "reject",
        "metadata": {
            "tenant_id": "tenant-1",
            "workspace_id": "workspace-1",
            "user_id": "user-1",
            "task_id": "task-1",
            "product_run_id": "product-run-2",
            "resume_of_official_run_id": "run-1",
        },
        "headers": {"authorization": "Bearer resume-token"},
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
