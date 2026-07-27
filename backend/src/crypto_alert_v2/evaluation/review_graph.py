"""Official LangGraph interrupt boundary for controlled-improvement approval."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class CandidateReviewState(TypedDict, total=False):
    candidate_id: str
    candidate_version: str
    rationale: str
    review: dict[str, Any]
    status: str


def request_candidate_review(state: CandidateReviewState) -> CandidateReviewState:
    response = interrupt(
        {
            "kind": "candidate_review",
            "schema_version": "1.0",
            "candidate_id": state["candidate_id"],
            "candidate_version": state["candidate_version"],
            "rationale": state["rationale"],
            "allowed_actions": ["approve", "reject"],
        }
    )
    if not isinstance(response, dict) or response.get("action") not in {
        "approve",
        "reject",
    }:
        raise ValueError("candidate review response must approve or reject")
    return {
        "review": dict(response),
        "status": "approved" if response["action"] == "approve" else "rejected",
    }


builder = StateGraph(CandidateReviewState)
builder.add_node("request_candidate_review", request_candidate_review)
builder.add_edge(START, "request_candidate_review")
builder.add_edge("request_candidate_review", END)
graph = builder.compile()


def graph_factory() -> Any:
    return graph


__all__ = [
    "CandidateReviewState",
    "graph",
    "graph_factory",
    "request_candidate_review",
]
