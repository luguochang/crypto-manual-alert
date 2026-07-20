from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt

from crypto_alert_v2.agents.deep_research import DeepResearchExecutionResult
from crypto_alert_v2.api.schemas import TerminalGraphOutput
from crypto_alert_v2.domain.deep_research import (
    DeepResearchReport,
    DeepResearchSearchCoverage,
    materialize_deep_research_artifact,
)
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

    def fetch_snapshot(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        correlation_id: str,
    ) -> MarketSnapshot:
        del symbol, horizon, correlation_id
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


class CountingDeepResearchExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        request: object,
        config: object = None,
    ) -> DeepResearchExecutionResult:
        del request, config
        self.calls += 1
        evidence = WebEvidence(
            query="BTC institutional adoption",
            final_url="https://example.com/verified-btc-source",
            fetched_at=NOW,
            content_hash="d" * 64,
            title="Verified BTC source",
            source="test_search",
            excerpt="A verified source excerpt for the research review contract.",
            evidence_relation="supports",
        )
        report = _deep_research_report(claim="Institutional adoption remains active.")
        return DeepResearchExecutionResult(
            artifact=materialize_deep_research_artifact(
                report=report,
                evidence=(evidence,),
                harness_mode="deepagents",
                search_coverage=DeepResearchSearchCoverage(
                    status="complete",
                    attempted_queries=1,
                    successful_queries=1,
                ),
                model_audits=(),
            ),
            evidence=(evidence,),
            model_audits=(),
        )


def _runtime() -> AnalysisRuntime:
    return AnalysisRuntime(
        market_provider=CountingMarketProvider(),
        research_collector=CountingResearchCollector(),
        analysis_agent=CountingAnalysisAgent(),
    )


def _deep_research_report(*, claim: str) -> DeepResearchReport:
    return DeepResearchReport.model_validate(
        {
            "executive_summary": "Verified evidence supports a measured conclusion.",
            "sections": [
                {
                    "title": "Adoption",
                    "summary": "The source catalog supports the current finding.",
                    "findings": [{"claim": claim, "source_indexes": [1]}],
                }
            ],
            "risk_notes": ["The conclusion may change as new filings arrive."],
            "evidence_gaps": [],
        }
    )


def _deep_runtime() -> tuple[AnalysisRuntime, CountingDeepResearchExecutor]:
    runtime = _runtime()
    executor = CountingDeepResearchExecutor()
    return (
        AnalysisRuntime(
            market_provider=runtime.market_provider,
            research_collector=runtime.research_collector,
            analysis_agent=runtime.analysis_agent,
            deep_research_executor=executor,
            deep_research_harness_mode="deepagents",
        ),
        executor,
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


def _deep_input(*, review_policy: str = "required") -> dict[str, object]:
    return {
        "request": {
            "task_type": "deep_research",
            "symbol": "BTC-USDT-SWAP",
            "horizon": "7d",
            "query_text": "Research BTC adoption and its strongest counterevidence.",
        },
        "review_policy": review_policy,
    }


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
    assert result["artifact"]["risk_verdict"]["allowed"] is False
    assert result["artifact"]["risk_verdict"]["blocked_reasons"] == [
        "Rejected during required human review."
    ]
    assert result["review_comment"] == "Entry risk is too high."
    assert TerminalGraphOutput.model_validate(result).terminal_status == "blocked"
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


@pytest.mark.asyncio
async def test_required_deep_research_review_approve_commits_without_replaying_executor() -> (
    None
):
    runtime, executor = _deep_runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()

    paused = await graph.ainvoke(_deep_input(), config=config, context=runtime)
    pending = _interrupt(paused)

    assert pending.value["kind"] == "deep_research_review"
    assert pending.value["symbol"] == "BTC-USDT-SWAP"
    assert pending.value["horizon"] == "7d"
    assert pending.value["review_iteration"] == 1
    assert pending.value["artifact"]["status"] == "draft"
    assert graph.get_state(config).next == ("interrupt_review",)
    assert executor.calls == 1

    result = await graph.ainvoke(Command(resume={"action": "approve"}), config=config)

    assert result["terminal_status"] == "succeeded"
    assert result["deep_research_artifact"]["status"] == "committed"
    assert result["review_action"] == "approve"
    assert TerminalGraphOutput.model_validate(result).terminal_status == "succeeded"
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_deep_research_edit_requires_re_review_and_preserves_source_provenance() -> (
    None
):
    runtime, executor = _deep_runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()
    first = _interrupt(
        await graph.ainvoke(_deep_input(), config=config, context=runtime)
    )
    original_sources = first.value["artifact"]["sources"]

    edited_report = _deep_research_report(
        claim="Institutional adoption remains active but uneven."
    )
    edited = await graph.ainvoke(
        Command(
            resume={
                "action": "edit",
                "edits": {"report": edited_report.model_dump(mode="json")},
                "comment": "Narrow the conclusion to match the evidence.",
            }
        ),
        config=config,
    )
    second = _interrupt(edited)

    assert second.id != first.id
    assert second.value["review_iteration"] == 2
    assert second.value["artifact"]["status"] == "draft"
    assert (
        second.value["artifact"]["report"]["sections"][0]["findings"][0]["claim"]
        == "Institutional adoption remains active but uneven."
    )
    assert second.value["artifact"]["sources"] == original_sources
    assert executor.calls == 1

    result = await graph.ainvoke(Command(resume={"action": "approve"}), config=config)

    assert result["terminal_status"] == "succeeded"
    assert result["deep_research_artifact"]["status"] == "committed"
    assert result["deep_research_artifact"]["sources"] == original_sources
    assert result["deep_research_artifact"]["search_coverage"] == {
        "status": "complete",
        "attempted_queries": 1,
        "successful_queries": 1,
        "failed_queries": [],
    }
    assert result["review_iteration"] == 2
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_rejected_deep_research_finishes_blocked_with_a_draft() -> None:
    runtime, executor = _deep_runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()
    _interrupt(await graph.ainvoke(_deep_input(), config=config, context=runtime))

    result = await graph.ainvoke(
        Command(
            resume={
                "action": "reject",
                "comment": "The source coverage is not sufficient for publication.",
            }
        ),
        config=config,
    )

    assert result["terminal_status"] == "blocked"
    assert result["lifecycle"] == "completed_rejected"
    assert result["deep_research_artifact"]["status"] == "draft"
    assert "artifact" not in result
    assert TerminalGraphOutput.model_validate(result).terminal_status == "blocked"
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_deep_research_review_rejects_analysis_edits_fail_closed() -> None:
    runtime, executor = _deep_runtime()
    graph = create_graph(checkpointer=MemorySaver())
    config = _config()
    _interrupt(await graph.ainvoke(_deep_input(), config=config, context=runtime))

    with pytest.raises(ValueError, match="deep research report edit"):
        await graph.ainvoke(
            Command(
                resume={
                    "action": "edit",
                    "edits": {"entry_trigger": "65200"},
                }
            ),
            config=config,
        )

    assert executor.calls == 1
