from __future__ import annotations

from typing import Any

import pytest

from crypto_alert_v2.auth.context import ActorContext
from crypto_alert_v2.evaluation.review_runtime import CandidateReviewRuntime


class Threads:
    def __init__(self) -> None:
        self.create_kwargs: dict[str, Any] | None = None
        self.state = {
            "checkpoint": {
                "thread_id": "review-thread",
                "checkpoint_ns": "",
                "checkpoint_id": "checkpoint-1",
                "checkpoint_map": {},
            },
            "metadata": {"run_id": "review-run"},
            "next": ["request_candidate_review"],
            "interrupts": [],
            "tasks": [
                {
                    "name": "request_candidate_review",
                    "checkpoint": None,
                    "state": None,
                    "interrupts": [
                        {
                            "id": "interrupt-1",
                            "value": {
                                "kind": "candidate_review",
                                "candidate_id": "candidate-1",
                            },
                        }
                    ],
                    "result": None,
                }
            ],
        }

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.create_kwargs = kwargs
        return {"thread_id": "review-thread"}

    async def get_state(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.state


class Runs:
    def __init__(self) -> None:
        self.create_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.join_result: dict[str, Any] = {}

    async def list(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append((args, kwargs))
        if "command" in kwargs:
            return {"run_id": "resume-run", "assistant_id": "candidate_review"}
        return {"run_id": "review-run", "assistant_id": "candidate_review"}

    async def join(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.join_result


class Client:
    def __init__(self) -> None:
        self.threads = Threads()
        self.runs = Runs()


def _actor() -> ActorContext:
    return ActorContext(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        user_id="user-1",
        roles=("member",),
        permissions=("analysis:read", "analysis:write"),
    )


@pytest.mark.asyncio
async def test_review_runtime_uses_official_thread_run_and_interrupt_state() -> None:
    client = Client()
    runtime = CandidateReviewRuntime(
        client=client,
        authorization_provider=lambda _: "Bearer local",
    )

    receipt = await runtime.start(
        actor=_actor(),
        review_id="review-id",
        candidate_id="candidate-1",
        candidate_version="rule-v2",
        rationale="Require frozen replay gates.",
    )

    assert client.threads.create_kwargs is not None
    assert client.threads.create_kwargs["graph_id"] == "candidate_review"
    assert client.runs.create_calls[0][0] == ("review-thread", "candidate_review")
    run_options = client.runs.create_calls[0][1]
    assert run_options["durability"] == "sync"
    assert run_options["stream_resumable"] is True
    assert all(not isinstance(value, dict) for value in run_options["metadata"].values())
    assert receipt.interrupt.interrupt_id == "interrupt-1"
    assert receipt.checkpoint.checkpoint_id == "checkpoint-1"


@pytest.mark.asyncio
async def test_review_runtime_resumes_with_official_command_mapping() -> None:
    client = Client()
    runtime = CandidateReviewRuntime(client=client)
    receipt = await runtime.start(
        actor=_actor(),
        review_id="review-id",
        candidate_id="candidate-1",
        candidate_version="rule-v2",
        rationale="Require frozen replay gates.",
    )
    client.runs.join_result = {"status": "approved", "review": {"action": "approve"}}

    result = await runtime.decide(
        actor=_actor(),
        review_id="review-id",
        receipt=receipt,
        action="approve",
        comment="Ship to shadow.",
    )

    assert result["status"] == "approved"
    command = client.runs.create_calls[-1][1]["command"]
    assert command["resume"]["interrupt-1"] == {
        "action": "approve",
        "comment": "Ship to shadow.",
    }
