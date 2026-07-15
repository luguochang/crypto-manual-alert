from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, StateSnapshot
from langgraph_api.state import state_snapshot_to_thread_state

from crypto_alert_v2.api.agent_server import _collect_remote_interrupts
from crypto_alert_v2.domain.models import Artifact
from crypto_alert_v2.graph.request import ArtifactReviewPayload, ReviewResponse
from crypto_alert_v2.testing.multi_interrupt_fixture import create_graph, graph


def _checkpoint_namespace(task_state: StateSnapshot | None) -> str:
    if task_state is None:
        return ""
    namespace = task_state.config["configurable"]["checkpoint_ns"]
    assert isinstance(namespace, str)
    return namespace


def test_official_runtime_resumes_root_and_nested_interrupts_together() -> None:
    assert graph.checkpointer is None

    checkpointer = InMemorySaver()
    fixture = create_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": f"multi-interrupt-{uuid4()}"}}

    paused = fixture.invoke({"completion_count": 0}, config=config)
    snapshot = fixture.get_state(config, subgraphs=True)

    assert snapshot.metadata["step"] == 0
    assert set(snapshot.next) == {"root_interrupt", "nested_review"}
    assert len(paused["__interrupt__"]) == 2
    assert len(snapshot.interrupts) == 2

    logical_interrupts: list[tuple[str, str, dict[str, Any]]] = []
    for task in snapshot.tasks:
        assert task.name in {"root_interrupt", "nested_review"}
        assert len(task.interrupts) == 1
        task_state = task.state
        assert task_state is None or isinstance(task_state, StateSnapshot)
        namespace = _checkpoint_namespace(task_state)
        pending = task.interrupts[0]
        payload = ArtifactReviewPayload.model_validate(pending.value)
        assert payload.artifact.status == "draft"
        logical_interrupts.append((namespace, pending.id, pending.value))

    logical_ids = {
        (namespace, interrupt_id) for namespace, interrupt_id, _ in logical_interrupts
    }
    assert len(logical_ids) == 2
    assert len({interrupt_id for _, interrupt_id in logical_ids}) == 2
    assert {interrupt_id for _, interrupt_id in logical_ids} == {
        pending.id for pending in snapshot.interrupts
    }

    namespaces = {namespace for namespace, _, _ in logical_interrupts}
    assert "" in namespaces
    nested_namespaces = namespaces - {""}
    assert len(nested_namespaces) == 1
    nested_namespace = nested_namespaces.pop()
    assert nested_namespace.startswith("nested_review:")

    root_checkpoint = snapshot.config
    assert root_checkpoint["configurable"]["checkpoint_ns"] == ""
    official_state = state_snapshot_to_thread_state(snapshot)
    interrupt_set = _collect_remote_interrupts(
        official_state,
        expected_thread_id=config["configurable"]["thread_id"],
    )
    expected_checkpoint_map = {
        "": root_checkpoint["configurable"]["checkpoint_id"],
    }
    for task in snapshot.tasks:
        if isinstance(task.state, StateSnapshot):
            child_config = task.state.config["configurable"]
            expected_checkpoint_map[child_config["checkpoint_ns"]] = child_config[
                "checkpoint_id"
            ]
    assert interrupt_set.checkpoint.checkpoint_map == expected_checkpoint_map
    assert {member.interrupt_id for member in interrupt_set} == {
        interrupt_id for _, interrupt_id, _ in logical_interrupts
    }
    resume = {
        interrupt_id: ReviewResponse(action="approve").model_dump(mode="json")
        for _, interrupt_id, _ in logical_interrupts
    }

    result = fixture.invoke(Command(resume=resume), config=config)

    assert result["root_review"] == {
        "action": "approve",
        "edits": None,
        "comment": None,
    }
    assert result["nested_review"] == {
        "action": "approve",
        "edits": None,
        "comment": None,
    }
    assert result["completion_count"] == 1
    assert Artifact.model_validate(result["artifact"]).status == "committed"

    completed = fixture.get_state(config, subgraphs=True)
    assert completed.next == ()
    assert completed.interrupts == ()


def test_official_state_shape_excludes_a_partially_resumed_task() -> None:
    checkpointer = InMemorySaver()
    fixture = create_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": f"partial-interrupt-{uuid4()}"}}

    fixture.invoke({"completion_count": 0}, config=config)
    paused = fixture.get_state(config, subgraphs=True)
    root_task = next(task for task in paused.tasks if task.name == "root_interrupt")
    nested_task = next(task for task in paused.tasks if task.name == "nested_review")
    root_interrupt_id = root_task.interrupts[0].id
    nested_interrupt_id = nested_task.interrupts[0].id

    fixture.invoke(
        Command(
            resume={
                root_interrupt_id: ReviewResponse(action="approve").model_dump(
                    mode="json"
                )
            }
        ),
        config=config,
    )
    partially_resumed = fixture.get_state(config, subgraphs=True)

    assert partially_resumed.next == ("nested_review",)
    completed_root_task = next(
        task for task in partially_resumed.tasks if task.name == "root_interrupt"
    )
    assert completed_root_task.result is not None
    assert completed_root_task.interrupts[0].id == root_interrupt_id
    assert {interrupt.id for interrupt in partially_resumed.interrupts} == {
        root_interrupt_id,
        nested_interrupt_id,
    }

    official_state = state_snapshot_to_thread_state(partially_resumed)
    interrupt_set = _collect_remote_interrupts(
        official_state,
        expected_thread_id=config["configurable"]["thread_id"],
    )

    assert [member.interrupt_id for member in interrupt_set] == [nested_interrupt_id]
    assert len(interrupt_set.checkpoint.checkpoint_map) == 2
    assert (
        interrupt_set.checkpoint.checkpoint_map[""]
        == partially_resumed.config["configurable"]["checkpoint_id"]
    )

    result = fixture.invoke(
        Command(
            resume={
                nested_interrupt_id: ReviewResponse(action="approve").model_dump(
                    mode="json"
                )
            }
        ),
        config=config,
    )
    assert result["completion_count"] == 1
    assert Artifact.model_validate(result["artifact"]).status == "committed"


def test_dedicated_langgraph_config_registers_fixture_and_canonical_graph() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    dedicated = json.loads(
        (backend_root / "langgraph.multi-interrupt.json").read_text(encoding="utf-8")
    )
    canonical = json.loads(
        (backend_root / "langgraph.json").read_text(encoding="utf-8")
    )

    assert dedicated["graphs"] == {
        "crypto_analysis": canonical["graphs"]["crypto_analysis"],
        "multi_interrupt_fixture": (
            "./src/crypto_alert_v2/testing/multi_interrupt_fixture.py:graph"
        ),
    }
