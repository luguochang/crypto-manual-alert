from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt

from crypto_alert_v2.domain.models import MarketAnalysis, MarketSnapshot, ResearchBundle
from crypto_alert_v2.graph.graph import create_graph
from crypto_alert_v2.graph.runtime import AnalysisRuntime, ResearchResult
from crypto_alert_v2.providers.search import WebEvidence
from tests.fixtures.golden_cases import (
    NOW,
    complete_market_snapshot,
    complete_research_bundle,
    valid_market_analysis,
)


class CountingMarketProvider:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_snapshot(self, symbol: str, *, correlation_id: str) -> MarketSnapshot:
        del symbol, correlation_id
        self.calls += 1
        return MarketSnapshot.model_validate(complete_market_snapshot())


class CountingResearchCollector:
    def __init__(self) -> None:
        self.calls = 0

    def collect(self, query: str, config: object = None) -> ResearchResult:
        del config
        self.calls += 1
        return ResearchResult(
            bundle=ResearchBundle.model_validate(complete_research_bundle()),
            evidence=(
                WebEvidence(
                    query=query,
                    final_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                    fetched_at=NOW,
                    content_hash="a" * 64,
                    title="Fed calendar checked",
                    source="test_search",
                    excerpt="No FOMC decision falls inside the analysis horizon.",
                    evidence_relation="supports",
                ),
            ),
        )


class CountingAnalysisAgent:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(
        self,
        payload: dict[str, Any],
        config: object = None,
    ) -> dict[str, MarketAnalysis]:
        del payload, config
        self.calls += 1
        return {
            "structured_response": MarketAnalysis.model_validate(
                valid_market_analysis()
            )
        }


def _runtime() -> AnalysisRuntime:
    return AnalysisRuntime(
        market_provider=CountingMarketProvider(),
        research_collector=CountingResearchCollector(),
        analysis_agent=CountingAnalysisAgent(),
    )


def _input(*, review_policy: str | None = "required") -> dict[str, object]:
    payload: dict[str, object] = {
        "request": {
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "query_text": "Assess current BTC risk and opportunity.",
            "notify": False,
        },
    }
    if review_policy is not None:
        payload["review_policy"] = review_policy
    return payload


def _config(*, review_policy: str | None = None) -> dict[str, dict[str, str]]:
    configurable = {"thread_id": f"review-{uuid4()}"}
    if review_policy is not None:
        configurable["review_policy"] = review_policy
    return {"configurable": configurable}


def _interrupt(result: dict[str, Any]) -> Interrupt:
    interrupts = result.get("__interrupt__")
    assert isinstance(interrupts, list)
    assert len(interrupts) == 1
    interrupt_value = interrupts[0]
    assert isinstance(interrupt_value, Interrupt)
    return interrupt_value


def _assert_external_calls(runtime: AnalysisRuntime, expected: int) -> None:
    market = runtime.market_provider
    research = runtime.research_collector
    agent = runtime.analysis_agent
    assert isinstance(market, CountingMarketProvider)
    assert isinstance(research, CountingResearchCollector)
    assert isinstance(agent, CountingAnalysisAgent)
    assert (market.calls, research.calls, agent.calls) == (expected, expected, expected)


def test_default_review_policy_bypasses_interrupt() -> None:
    runtime = _runtime()
    graph = create_graph(checkpointer=MemorySaver())

    result = graph.invoke(_input(review_policy=None), config=_config(), context=runtime)

    assert result["terminal_status"] == "succeeded"
    assert result["artifact"]["status"] == "committed"
    assert result["review_policy"] == "bypass"
    assert "__interrupt__" not in result
    _assert_external_calls(runtime, 1)


def test_required_review_approve_resumes_without_replaying_external_calls() -> None:
    runtime = _runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()

    paused = graph.invoke(_input(), config=config, context=runtime)
    pending = _interrupt(paused)

    assert pending.value["kind"] == "artifact_review"
    assert pending.value["allowed_actions"] == ["approve", "reject", "edit"]
    assert pending.value["review_iteration"] == 1
    assert pending.value["artifact"]["status"] == "draft"
    assert graph.get_state(config).next == ("interrupt_review",)
    _assert_external_calls(runtime, 1)

    result = graph.invoke(Command(resume={"action": "approve"}), config=config)

    assert result["terminal_status"] == "succeeded"
    assert result["artifact"]["status"] == "committed"
    assert result["review_action"] == "approve"
    assert result["review_iteration"] == 1
    assert graph.get_state(config).next == ()
    _assert_external_calls(runtime, 1)


def test_server_required_review_cannot_be_downgraded_by_input() -> None:
    runtime = _runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config(review_policy="required")

    paused = graph.invoke(
        _input(review_policy="bypass"),
        config=config,
        context=runtime,
    )

    pending = _interrupt(paused)
    assert paused["review_policy"] == "required"
    assert pending.value["kind"] == "artifact_review"
    _assert_external_calls(runtime, 1)


def test_required_review_reject_finishes_blocked_with_draft_artifact() -> None:
    runtime = _runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()
    _interrupt(graph.invoke(_input(), config=config, context=runtime))

    result = graph.invoke(
        Command(resume={"action": "reject", "comment": "Entry risk is too high."}),
        config=config,
    )

    assert result["terminal_status"] == "blocked"
    assert result["lifecycle"] == "completed_rejected"
    assert result["artifact"]["status"] == "draft"
    assert result["review_comment"] == "Entry risk is too high."
    _assert_external_calls(runtime, 1)


def test_edit_revalidates_then_interrupts_again_before_approval() -> None:
    runtime = _runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()
    first = _interrupt(graph.invoke(_input(), config=config, context=runtime))

    edited = graph.invoke(
        Command(
            resume={
                "action": "edit",
                "edits": {"entry_trigger": "65200"},
                "comment": "Use the confirmed breakout level.",
            }
        ),
        config=config,
    )
    second = _interrupt(edited)

    assert second.id != first.id
    assert second.value["review_iteration"] == 2
    assert second.value["artifact"]["analysis"]["entry_trigger"] == "65200"
    assert second.value["artifact"]["evidence_verdict"]["sufficient"] is True
    assert second.value["artifact"]["risk_verdict"]["allowed"] is True
    assert edited["artifact"]["status"] == "draft"
    assert graph.get_state(config).next == ("interrupt_review",)
    _assert_external_calls(runtime, 1)

    result = graph.invoke(Command(resume={"action": "approve"}), config=config)

    assert result["terminal_status"] == "succeeded"
    assert result["artifact"]["status"] == "committed"
    assert result["artifact"]["analysis"]["entry_trigger"] == "65200"
    assert result["review_iteration"] == 2
    _assert_external_calls(runtime, 1)


def test_risk_blocking_edit_is_revalidated_and_cannot_be_approved() -> None:
    runtime = _runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()
    _interrupt(graph.invoke(_input(), config=config, context=runtime))

    edited = graph.invoke(
        Command(resume={"action": "edit", "edits": {"max_leverage": 3}}),
        config=config,
    )
    second = _interrupt(edited)

    assert second.value["review_iteration"] == 2
    assert second.value["artifact"]["risk_verdict"]["allowed"] is False
    assert second.value["artifact"]["risk_verdict"]["blocked_reasons"] == [
        "budget.max_leverage_exceeded:actual=3,limit=2"
    ]
    _assert_external_calls(runtime, 1)

    result = graph.invoke(Command(resume={"action": "approve"}), config=config)

    assert result["terminal_status"] == "blocked"
    assert result["artifact"]["status"] == "draft"
    assert result["review_action"] == "approve"
    _assert_external_calls(runtime, 1)


@pytest.mark.parametrize(
    "response",
    (
        {"action": "edit"},
        {"action": "approve", "edits": {"entry_trigger": "65200"}},
        {"action": "unknown"},
    ),
)
def test_invalid_review_response_fails_closed(response: dict[str, object]) -> None:
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()
    _interrupt(graph.invoke(_input(), config=config, context=_runtime()))

    with pytest.raises(ValueError):
        graph.invoke(Command(resume=response), config=config)
