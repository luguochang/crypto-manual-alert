from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.stream import CheckpointsTransformer
from langgraph.types import interrupt

from crypto_alert_v2.domain.models import (
    Artifact,
    EvidenceVerdict,
    MarketAnalysis,
    RiskVerdict,
)
from crypto_alert_v2.graph.request import ArtifactReviewPayload, ReviewResponse


class MultiInterruptFixtureState(TypedDict, total=False):
    root_review: dict[str, Any]
    nested_review: dict[str, Any]
    artifact: dict[str, Any]
    completion_count: int
    terminal_status: str
    errors: list[dict[str, Any]]


def _draft_artifact() -> Artifact:
    analysis = MarketAnalysis(
        regime="risk_on",
        factor_scores={
            "market_structure": 1,
            "macro": 0,
            "derivatives": 1,
        },
        total_score=2,
        main_action="open_long",
        instrument="BTC-USDT-SWAP",
        horizon="4h",
        reference_price="65000.25",
        entry_trigger="65100",
        stop_price="64500",
        target_1="66000",
        target_2="67000",
        probability=0.65,
        position_size_class="light",
        max_leverage=2,
        risk_pct="0.10",
        root_cause_chain=[
            "Price reclaimed resistance",
            "Liquidity supports continuation",
        ],
        why_not_opposite="The bearish invalidation has not triggered.",
        invalidation="Close below 64500.",
        manual_execution_required=True,
        expires_in_seconds=90,
    )
    return Artifact(
        content_version=1,
        status="draft",
        analysis=analysis,
        evidence_verdict=EvidenceVerdict(sufficient=True),
        risk_verdict=RiskVerdict(allowed=True),
        source_references=["https://example.com/review-source"],
    )


def _review_payload() -> dict[str, Any]:
    return ArtifactReviewPayload(
        review_iteration=1,
        artifact=_draft_artifact(),
    ).model_dump(mode="json")


def _root_interrupt(_: MultiInterruptFixtureState) -> MultiInterruptFixtureState:
    decision = ReviewResponse.model_validate(interrupt(_review_payload()))
    return {"root_review": decision.model_dump(mode="json")}


def _nested_interrupt(_: MultiInterruptFixtureState) -> MultiInterruptFixtureState:
    decision = ReviewResponse.model_validate(interrupt(_review_payload()))
    return {"nested_review": decision.model_dump(mode="json")}


def _finish(state: MultiInterruptFixtureState) -> MultiInterruptFixtureState:
    decisions = (
        ReviewResponse.model_validate(state["root_review"]),
        ReviewResponse.model_validate(state["nested_review"]),
    )
    if any(decision.action != "approve" for decision in decisions):
        raise ValueError("the multi-interrupt fixture commits only approved reviews")

    artifact = Artifact.model_validate(
        {
            **_draft_artifact().model_dump(mode="json"),
            "status": "committed",
        }
    )
    return {
        "artifact": artifact.model_dump(mode="json"),
        "completion_count": state.get("completion_count", 0) + 1,
        "terminal_status": "succeeded",
        "errors": [],
    }


_nested_builder = StateGraph(MultiInterruptFixtureState)
_nested_builder.add_node("nested_interrupt", _nested_interrupt)
_nested_builder.add_edge(START, "nested_interrupt")
_nested_builder.add_edge("nested_interrupt", END)
_nested_graph = _nested_builder.compile()

builder = StateGraph(MultiInterruptFixtureState)
builder.add_node("root_interrupt", _root_interrupt)
builder.add_node("nested_review", _nested_graph)
builder.add_node("finish", _finish)
builder.add_edge(START, "root_interrupt")
builder.add_edge(START, "nested_review")
builder.add_edge("root_interrupt", "finish")
builder.add_edge("nested_review", "finish")
builder.add_edge("finish", END)


def create_graph(*, checkpointer: Any = None) -> Any:
    return builder.compile(
        checkpointer=checkpointer,
        transformers=[CheckpointsTransformer],
    )


graph = create_graph()


__all__ = ["create_graph", "graph"]
