from __future__ import annotations

import asyncio
import operator
from typing import Annotated, Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph


class AegraDurabilityFixtureState(TypedDict, total=False):
    proof_id: str
    sleep_seconds: float
    prepared_count: Annotated[int, operator.add]
    completion_count: Annotated[int, operator.add]
    stage: str
    terminal_status: str


def _prepare(_: AegraDurabilityFixtureState) -> AegraDurabilityFixtureState:
    return {
        "prepared_count": 1,
        "stage": "checkpoint_committed",
    }


async def _wait_for_worker_restart(
    state: AegraDurabilityFixtureState,
) -> AegraDurabilityFixtureState:
    delay = float(state.get("sleep_seconds", 90.0))
    if not 5.0 <= delay <= 300.0:
        raise ValueError("sleep_seconds must be between 5 and 300")
    get_stream_writer()(
        {
            "schema_version": 1,
            "type": "aegra_durability_fixture.waiting",
            "proof_id": state.get("proof_id", ""),
        }
    )
    await asyncio.sleep(delay)
    return {"stage": "worker_recovered"}


def _finish(_: AegraDurabilityFixtureState) -> AegraDurabilityFixtureState:
    return {
        "completion_count": 1,
        "stage": "completed",
        "terminal_status": "succeeded",
    }


builder = StateGraph(AegraDurabilityFixtureState)
builder.add_node("prepare", _prepare)
builder.add_node("wait_for_worker_restart", _wait_for_worker_restart)
builder.add_node("finish", _finish)
builder.add_edge(START, "prepare")
builder.add_edge("prepare", "wait_for_worker_restart")
builder.add_edge("wait_for_worker_restart", "finish")
builder.add_edge("finish", END)


def create_graph(*, checkpointer: Any = None) -> Any:
    return builder.compile(checkpointer=checkpointer)


graph = create_graph()


__all__ = ["create_graph", "graph"]
