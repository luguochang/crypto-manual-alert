import importlib
from typing import Any
import httpx
import pytest
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from openai import APITimeoutError

from crypto_alert_v2.domain.models import (
    MarketAnalysis,
    ModelExecutionAudit,
    MarketSnapshot,
    ResearchBundle,
)
from crypto_alert_v2.agents.deep_research import DeepResearchExecutionResult
from crypto_alert_v2.domain.deep_research import (
    DeepResearchReport,
    DeepResearchSearchCoverage,
    materialize_deep_research_artifact,
)
from crypto_alert_v2.graph.graph import create_graph
from crypto_alert_v2.graph.runtime import AnalysisRuntime, ResearchResult
from crypto_alert_v2.observability.callbacks import build_observability_config
from crypto_alert_v2.providers.errors import ProviderUnavailable, ResearchUnavailable
from crypto_alert_v2.providers.capability_probe import SearchReadinessError
from crypto_alert_v2.providers.search import WebEvidence
from crypto_alert_v2.providers.web_market import WebMarketResult
from tests.fixtures.golden_cases import (
    NOW,
    complete_market_snapshot,
    complete_research_bundle,
    valid_market_analysis,
)


graph = create_graph()


class FakeMarketProvider:
    def __init__(self, snapshot: MarketSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[str] = []
        self.horizons: list[str | None] = []
        self.correlation_ids: list[str] = []

    def fetch_snapshot(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        correlation_id: str,
    ) -> MarketSnapshot:
        self.calls.append(symbol)
        self.horizons.append(horizon)
        self.correlation_ids.append(correlation_id)
        return self.snapshot


class FailingMarketProvider:
    def fetch_snapshot(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        correlation_id: str,
    ) -> MarketSnapshot:
        del symbol, horizon
        raise ProviderUnavailable(
            "market offline",
            provider="okx",
            endpoint="ticker",
            retryable=True,
            correlation_id=correlation_id,
            attempt=3,
            retry_exhausted=True,
        )


class FakeMarketFallbackCollector:
    def __init__(self, result: WebMarketResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None]] = []
        self.configs: list[Any] = []

    def collect(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        config: Any = None,
    ) -> WebMarketResult:
        self.calls.append((symbol, horizon))
        self.configs.append(config)
        return self.result


class FakeResearchCollector:
    def __init__(self, bundle: ResearchBundle) -> None:
        self.bundle = bundle
        self.calls = 0
        self.queries: list[str] = []
        self.configs: list[Any] = []

    def collect(self, query: str, config: object = None) -> ResearchResult:
        self.calls += 1
        self.queries.append(query)
        self.configs.append(config)
        return ResearchResult(
            bundle=self.bundle,
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


class UnreadyResearchCollector:
    def collect(self, query: str, config: object = None) -> ResearchResult:
        del query, config
        raise SearchReadinessError("no verified search provider")


class TimedOutResearchCollector:
    def collect(self, query: str, config: object = None) -> ResearchResult:
        del query, config
        raise APITimeoutError(
            request=httpx.Request("POST", "https://model.example/v1/responses")
        )


class UnverifiedBuiltinSearchCollector:
    def collect(self, query: str, config: object = None) -> ResearchResult:
        del query, config
        raise ResearchUnavailable(
            "built-in search returned no completed server tool call",
            provider="builtin_web_search",
            retryable=True,
            error_type="UnverifiedServerToolCall",
            attempt=3,
        )


class RecordingAgent:
    def __init__(self, analysis: MarketAnalysis) -> None:
        self.analysis = analysis
        self.calls = 0
        self.configs: list[Any] = []
        self.payloads: list[dict[str, Any]] = []

    def invoke(self, payload: dict[str, Any], config: object = None) -> dict[str, Any]:
        self.calls += 1
        self.payloads.append(payload)
        self.configs.append(config)
        return {"structured_response": self.analysis}


class FakeDeepResearchExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def execute(
        self,
        request: object,
        config: object = None,
    ) -> DeepResearchExecutionResult:
        self.calls.append((request, config))
        evidence = WebEvidence(
            query="BTC institutional adoption",
            final_url="https://example.com/verified-btc-source",
            fetched_at=NOW,
            content_hash="b" * 64,
            title="Verified BTC source",
            source="test_search",
            excerpt="A verified source excerpt for the controlled graph contract.",
            evidence_relation="supports",
        )
        report = DeepResearchReport.model_validate(
            {
                "executive_summary": "BTC 的机构采用仍在推进。",
                "sections": [
                    {
                        "title": "机构采用",
                        "summary": "可验证来源支持该趋势。",
                        "findings": [
                            {
                                "claim": "机构采用仍在推进。",
                                "source_indexes": [1],
                            }
                        ],
                    }
                ],
            }
        )
        artifact = materialize_deep_research_artifact(
            report=report,
            evidence=(evidence,),
            harness_mode="deepagents",
            search_coverage=DeepResearchSearchCoverage(
                status="complete",
                attempted_queries=1,
                successful_queries=1,
            ),
            model_audits=(),
        )
        return DeepResearchExecutionResult(
            artifact=artifact,
            evidence=(evidence,),
            model_audits=(),
        )


class FailingDeepResearchExecutor:
    async def execute(
        self,
        request: object,
        config: object = None,
    ) -> DeepResearchExecutionResult:
        del request, config
        raise ResearchUnavailable(
            "verified search timed out",
            provider="builtin_web_search",
            retryable=True,
            error_type="APITimeoutError",
            attempt=3,
        )


class InvalidStructuredOutputAgent:
    def invoke(self, payload: dict[str, Any], config: object = None) -> dict[str, Any]:
        del payload, config
        raise StructuredOutputValidationError(
            "MarketAnalysis",
            ValueError("controlled invalid structured response"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "MarketAnalysis",
                        "args": {},
                        "id": "controlled-invalid-output",
                        "type": "tool_call",
                    }
                ],
            ),
        )


class ExhaustedStructuredOutputRepairAgent:
    def invoke(self, payload: dict[str, Any], config: object = None) -> dict[str, Any]:
        del payload, config
        raise ModelCallLimitExceededError(
            thread_count=3,
            run_count=3,
            thread_limit=None,
            run_limit=3,
        )


class AuditedResearchCollector(FakeResearchCollector):
    def collect(self, query: str, config: object = None) -> ResearchResult:
        result = super().collect(query, config=config)
        return ResearchResult(
            bundle=result.bundle,
            evidence=result.evidence,
            model_audit=ModelExecutionAudit(
                prompt_version="research-extraction-v1",
                call_count=1,
                input_tokens=100,
                output_tokens=25,
                total_tokens=125,
                latency_ms=12.5,
                observation_ids=["resp_research"],
            ),
        )


class AuditedAgent(RecordingAgent):
    def invoke(self, payload: dict[str, Any], config: object = None) -> dict[str, Any]:
        result = super().invoke(payload, config=config)
        return {
            **result,
            "messages": [
                {
                    "role": "assistant",
                    "usage_metadata": {
                        "input_tokens": 200,
                        "output_tokens": 40,
                        "total_tokens": 240,
                    },
                    "response_metadata": {"id": "resp_analysis"},
                }
            ],
        }


class RecordingObservabilityHandler(BaseCallbackHandler):
    def __init__(self, *, public_key: str | None = None) -> None:
        self.public_key = public_key


def valid_runtime() -> AnalysisRuntime:
    return AnalysisRuntime(
        market_provider=FakeMarketProvider(
            MarketSnapshot.model_validate(complete_market_snapshot())
        ),
        research_collector=FakeResearchCollector(
            ResearchBundle.model_validate(complete_research_bundle())
        ),
        analysis_agent=RecordingAgent(
            MarketAnalysis.model_validate(valid_market_analysis())
        ),
    )


def valid_input() -> dict[str, object]:
    return {
        "request": {
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "query_text": "Assess current BTC risk and opportunity.",
            "notify": False,
        }
    }


def test_canonical_graph_contains_the_vertical_analysis_path() -> None:
    nodes = set(graph.get_graph().nodes)

    assert {
        "validate_request",
        "collect_market_snapshot",
        "research_events",
        "analyze_market",
        "validate_evidence",
        "apply_risk_policy",
        "build_artifact",
        "complete",
        "complete_failed",
    } <= nodes


@pytest.mark.asyncio
async def test_canonical_graph_routes_deep_research_without_running_market_analysis() -> (
    None
):
    runtime = valid_runtime()
    market = runtime.market_provider
    research = runtime.research_collector
    analysis = runtime.analysis_agent
    deep_research = FakeDeepResearchExecutor()
    assert isinstance(market, FakeMarketProvider)
    assert isinstance(research, FakeResearchCollector)
    assert isinstance(analysis, RecordingAgent)

    result = await graph.ainvoke(
        {
            "request": {
                "task_type": "deep_research",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "7d",
                "query_text": "研究 BTC 机构采用及其主要反证。",
            }
        },
        context=AnalysisRuntime(
            market_provider=market,
            research_collector=research,
            analysis_agent=analysis,
            deep_research_executor=deep_research,
            deep_research_harness_mode="deepagents",
        ),
    )

    assert result["terminal_status"] == "succeeded"
    assert result["deep_research_artifact"]["artifact_type"] == ("deep_research_report")
    assert result["deep_research_artifact"]["report"]["sections"][0]["findings"][0][
        "source_indexes"
    ] == [1]
    assert result["research_harness_mode"] == "deepagents"
    assert len(deep_research.calls) == 1
    assert market.calls == []
    assert research.calls == 0
    assert analysis.calls == 0


@pytest.mark.asyncio
async def test_deep_research_failure_preserves_safe_provider_diagnostics() -> None:
    runtime = valid_runtime()
    result = await graph.ainvoke(
        {
            "request": {
                "task_type": "deep_research",
                "symbol": "BTC-USDT-SWAP",
                "horizon": "7d",
                "query_text": "研究 BTC 的宏观、监管和市场结构证据。",
            }
        },
        context=AnalysisRuntime(
            market_provider=runtime.market_provider,
            research_collector=runtime.research_collector,
            analysis_agent=runtime.analysis_agent,
            deep_research_executor=FailingDeepResearchExecutor(),
            deep_research_harness_mode="deepagents",
        ),
        config={"metadata": {"correlation_id": "deep-research-diagnostics"}},
    )

    assert result["terminal_status"] == "failed"
    assert result["errors"] == [
        {
            "code": "deep_research_unavailable",
            "provider": "builtin_web_search",
            "endpoint": "verified_web_search",
            "error_type": "APITimeoutError",
            "attempt": 3,
            "retryable": True,
            "correlation_id": "deep-research-diagnostics",
        }
    ]


def test_vertical_path_returns_committed_typed_artifact() -> None:
    result = graph.invoke(valid_input(), context=valid_runtime())

    assert result["terminal_status"] == "succeeded"
    assert result["artifact"]["status"] == "committed"
    assert result["artifact"]["analysis"]["main_action"] == "open_long"
    assert result["artifact"]["evidence_verdict"]["sufficient"] is True
    assert result["artifact"]["risk_verdict"]["allowed"] is True
    assert result["web_evidence"][0]["final_url"].startswith("https://")


def test_typed_sources_replace_model_claims_about_unavailable_data() -> None:
    payload = valid_market_analysis()
    payload["unavailable_data"] = [
        "Web Search is unavailable even though verified evidence exists."
    ]
    runtime = valid_runtime()
    runtime = AnalysisRuntime(
        market_provider=runtime.market_provider,
        research_collector=runtime.research_collector,
        analysis_agent=RecordingAgent(MarketAnalysis.model_validate(payload)),
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "succeeded"
    assert result["analysis"]["unavailable_data"] == []
    assert result["artifact"]["analysis"]["unavailable_data"] == []


def test_controlled_dependency_artifact_provenance_cannot_claim_real_providers() -> (
    None
):
    snapshot = complete_market_snapshot()
    snapshot["source_level"] = "controlled_dependency"
    runtime = valid_runtime()
    controlled_runtime = AnalysisRuntime(
        market_provider=FakeMarketProvider(MarketSnapshot.model_validate(snapshot)),
        research_collector=runtime.research_collector,
        analysis_agent=runtime.analysis_agent,
    )

    result = graph.invoke(valid_input(), context=controlled_runtime)

    provenance = result["artifact"]["provenance"]
    assert provenance["market_provider"] == "controlled_dependency"
    assert provenance["model_provider"] == "controlled_dependency"
    assert provenance["model_name"] == "controlled-dependency-test"
    assert provenance["model_endpoint_host"] is None


def test_model_execution_audits_are_ordered_and_persisted_in_artifact_provenance() -> (
    None
):
    runtime = AnalysisRuntime(
        market_provider=FakeMarketProvider(
            MarketSnapshot.model_validate(complete_market_snapshot())
        ),
        research_collector=AuditedResearchCollector(
            ResearchBundle.model_validate(complete_research_bundle())
        ),
        analysis_agent=AuditedAgent(
            MarketAnalysis.model_validate(valid_market_analysis())
        ),
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["artifact"]["provenance"]["model_audits"] == [
        {
            "prompt_version": "research-extraction-v1",
            "call_count": 1,
            "input_tokens": 100,
            "output_tokens": 25,
            "total_tokens": 125,
            "latency_ms": 12.5,
            "observation_ids": ["resp_research"],
        },
        {
            "prompt_version": "market-analysis-v2",
            "call_count": 1,
            "input_tokens": 200,
            "output_tokens": 40,
            "total_tokens": 240,
            "latency_ms": result["artifact"]["provenance"]["model_audits"][1][
                "latency_ms"
            ],
            "observation_ids": ["resp_analysis"],
        },
    ]


def test_root_observability_config_propagates_to_both_external_calls() -> None:
    runtime = valid_runtime()
    research = runtime.research_collector
    agent = runtime.analysis_agent
    market = runtime.market_provider
    assert isinstance(research, FakeResearchCollector)
    assert isinstance(agent, RecordingAgent)
    assert isinstance(market, FakeMarketProvider)
    metadata = {
        "tenant_id": "tenant-1",
        "user_id": "anonymous-user-1",
        "thread_id": "thread-1",
        "task_id": "task-1",
        "product_run_id": "product-run-1",
        "official_run_id": "official-run-1",
        "correlation_id": "correlation-1",
        "environment": "test",
        "version": "2.0.0-test",
        "nested": {"authorization": "Bearer secret", "safe": "value"},
    }
    root_config = build_observability_config(
        {"metadata": metadata},
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        handler_factory=RecordingObservabilityHandler,
    )

    result = graph.with_config(root_config).invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "succeeded"
    assert len(research.configs) == 1
    assert len(agent.configs) == 1
    research_config = research.configs[0]
    agent_config = agent.configs[0]
    expected_root_metadata = root_config["metadata"]
    for key, value in expected_root_metadata.items():
        assert research_config["metadata"][key] == value
        assert agent_config["metadata"][key] == value
    assert "user_id" not in expected_root_metadata
    assert expected_root_metadata["actor_ref"].startswith("anon-")
    assert market.correlation_ids == ["correlation-1"]
    assert market.horizons == ["4h"]
    research_handlers = research_config["callbacks"].handlers
    agent_handlers = agent_config["callbacks"].handlers
    research_handler = next(
        item
        for item in research_handlers
        if isinstance(item, RecordingObservabilityHandler)
    )
    agent_handler = next(
        item
        for item in agent_handlers
        if isinstance(item, RecordingObservabilityHandler)
    )
    assert research_handler is agent_handler


def test_graph_nodes_do_not_reassemble_observability_during_a_run(
    monkeypatch: Any,
) -> None:
    graph_module = importlib.import_module("crypto_alert_v2.graph.graph")

    def unexpected_assembly(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise AssertionError("observability must be assembled at the graph root")

    monkeypatch.setattr(
        graph_module,
        "_root_observability_config",
        unexpected_assembly,
    )

    result = graph.invoke(valid_input(), context=valid_runtime())

    assert result["terminal_status"] == "succeeded"


def test_provider_failure_stops_before_research_and_model() -> None:
    research = FakeResearchCollector(
        ResearchBundle.model_validate(complete_research_bundle())
    )
    agent = RecordingAgent(MarketAnalysis.model_validate(valid_market_analysis()))
    runtime = AnalysisRuntime(
        market_provider=FailingMarketProvider(),
        research_collector=research,
        analysis_agent=agent,
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"][0]["code"] == "provider_unavailable"
    assert result.get("artifact") is None
    assert research.calls == 0
    assert agent.calls == 0


def test_okx_failure_uses_cited_web_market_fallback_and_blocks_opening() -> None:
    market_url = "https://www.kraken.com/features/futures/bitcoin"
    fallback = FakeMarketFallbackCollector(
        WebMarketResult(
            snapshot=MarketSnapshot.model_validate(
                {
                    "symbol": "BTC-USDT-SWAP",
                    "fetched_at": NOW,
                    "source_level": "web_search_verified",
                    "ticker": {"last": "65000.25"},
                    "mark_price": "65001.00",
                    "index_price": "64999.50",
                    "funding_rate": "0.0001",
                    "open_interest": "1200000000",
                    "order_book": None,
                    "candles": [],
                }
            ),
            evidence=(
                WebEvidence(
                    query="current BTC futures market data",
                    final_url=market_url,
                    fetched_at=NOW,
                    content_hash="b" * 64,
                    title="Bitcoin futures market",
                    source="openai_builtin_web_search",
                    excerpt="Cited partial market data.",
                    evidence_relation="market_snapshot",
                ),
            ),
            model_audit=ModelExecutionAudit(
                prompt_version="web-market-extraction-v1",
                call_count=1,
                latency_ms=10,
            ),
        )
    )
    research = FakeResearchCollector(
        ResearchBundle.model_validate(complete_research_bundle())
    )
    agent = RecordingAgent(MarketAnalysis.model_validate(valid_market_analysis()))
    runtime = AnalysisRuntime(
        market_provider=FailingMarketProvider(),
        market_fallback_collector=fallback,
        research_collector=research,
        analysis_agent=agent,
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "blocked"
    assert result["market_snapshot"]["source_level"] == "web_search_verified"
    assert result["artifact"]["provenance"]["market_provider"] == "web_search_market"
    assert result["artifact"]["risk_verdict"]["allowed"] is False
    assert result["artifact"]["evidence_verdict"]["missing_required"] == [
        "exchange_native_market_data",
        "order_book",
        "candles",
    ]
    assert [item["evidence_relation"] for item in result["web_evidence"]] == [
        "market_snapshot",
        "supports",
    ]
    assert result["artifact"]["source_references"][0] == market_url
    assert len(result["artifact"]["source_references"]) == 2
    assert fallback.calls == [("BTC-USDT-SWAP", "4h")]
    assert fallback.configs[0] is not None
    assert research.calls == 1
    assert agent.calls == 1


def test_excluded_research_evidence_is_audited_but_cannot_influence_analysis() -> None:
    class MixedResearchCollector:
        def collect(self, query: str, config: object = None) -> ResearchResult:
            del config
            return ResearchResult(
                bundle=ResearchBundle.model_validate(complete_research_bundle()),
                evidence=(
                    WebEvidence(
                        query=query,
                        final_url="https://www.reuters.com/markets/bitcoin",
                        fetched_at=NOW,
                        content_hash="d" * 64,
                        title="Bitcoin market structure",
                        source="tavily",
                        excerpt="Bitcoin liquidity and spot market activity.",
                        evidence_relation="supports",
                    ),
                    WebEvidence(
                        query=query,
                        final_url="https://www.bbva.com/en/earnings",
                        fetched_at=NOW,
                        content_hash="e" * 64,
                        title="BBVA quarterly earnings",
                        source="tavily",
                        excerpt="The bank discussed loan growth and operating income.",
                        evidence_relation="excluded",
                    ),
                ),
            )

    agent = RecordingAgent(MarketAnalysis.model_validate(valid_market_analysis()))
    result = graph.invoke(
        valid_input(),
        context=AnalysisRuntime(
            market_provider=FakeMarketProvider(
                MarketSnapshot.model_validate(complete_market_snapshot())
            ),
            research_collector=MixedResearchCollector(),
            analysis_agent=agent,
        ),
    )

    assert result["terminal_status"] == "succeeded"
    assert [item["evidence_relation"] for item in result["web_evidence"]] == [
        "supports",
        "excluded",
    ]
    payload = agent.payloads[0]
    submitted_evidence = payload["messages"][0]["content"]
    assert "https://www.reuters.com/markets/bitcoin" in submitted_evidence
    assert "https://www.bbva.com/en/earnings" not in submitted_evidence
    assert result["artifact"]["source_references"] == [
        "https://www.reuters.com/markets/bitcoin"
    ]


def test_later_research_failure_preserves_verified_web_market_evidence() -> None:
    market_url = "https://www.kraken.com/features/futures/bitcoin"
    fallback = FakeMarketFallbackCollector(
        WebMarketResult(
            snapshot=MarketSnapshot.model_validate(
                {
                    **complete_market_snapshot(),
                    "source_level": "web_search_verified",
                    "ticker": {"last": "65000"},
                    "order_book": None,
                    "candles": [],
                }
            ),
            evidence=(
                WebEvidence(
                    query="current BTC futures market data",
                    final_url=market_url,
                    fetched_at=NOW,
                    content_hash="c" * 64,
                    title="Bitcoin futures market",
                    source="openai_builtin_web_search",
                    excerpt="Cited partial market data.",
                    evidence_relation="market_snapshot",
                ),
            ),
            model_audit=ModelExecutionAudit(
                prompt_version="web-market-extraction-v1",
                call_count=1,
                latency_ms=10,
            ),
        )
    )
    agent = RecordingAgent(MarketAnalysis.model_validate(valid_market_analysis()))
    runtime = AnalysisRuntime(
        market_provider=FailingMarketProvider(),
        market_fallback_collector=fallback,
        research_collector=UnreadyResearchCollector(),
        analysis_agent=agent,
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"][0]["code"] == "research_unavailable"
    assert result["errors"][0]["endpoint"] == "research_events"
    assert len(result["web_evidence"]) == 1
    assert result["web_evidence"][0]["final_url"] == market_url
    assert result["web_evidence"][0]["evidence_relation"] == "market_snapshot"
    assert agent.calls == 0


def test_non_retryable_okx_failure_never_uses_web_market_fallback() -> None:
    class InvalidOkxPayload:
        def fetch_snapshot(
            self,
            symbol: str,
            *,
            horizon: str | None = None,
            correlation_id: str,
        ) -> MarketSnapshot:
            del symbol, horizon
            raise ProviderUnavailable(
                "invalid OKX payload",
                provider="okx",
                endpoint="ticker",
                retryable=False,
                correlation_id=correlation_id,
                attempt=1,
                retry_exhausted=False,
            )

    fallback = FakeMarketFallbackCollector(
        WebMarketResult(
            snapshot=MarketSnapshot.model_validate(complete_market_snapshot()),
            evidence=(),
            model_audit=ModelExecutionAudit(
                prompt_version="web-market-extraction-v1",
                call_count=0,
                latency_ms=0,
            ),
        )
    )
    runtime = valid_runtime()
    result = graph.invoke(
        valid_input(),
        context=AnalysisRuntime(
            market_provider=InvalidOkxPayload(),
            market_fallback_collector=fallback,
            research_collector=runtime.research_collector,
            analysis_agent=runtime.analysis_agent,
        ),
    )

    assert result["terminal_status"] == "failed"
    assert result["errors"][0]["provider"] == "okx"
    assert fallback.calls == []


def test_search_readiness_failure_stops_before_analysis_model() -> None:
    agent = RecordingAgent(MarketAnalysis.model_validate(valid_market_analysis()))
    runtime = AnalysisRuntime(
        market_provider=FakeMarketProvider(
            MarketSnapshot.model_validate(complete_market_snapshot())
        ),
        research_collector=UnreadyResearchCollector(),
        analysis_agent=agent,
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"][0]["code"] == "research_unavailable"
    assert agent.calls == 0


def test_research_query_has_a_bounded_source_budget() -> None:
    runtime = valid_runtime()
    research = runtime.research_collector
    assert isinstance(research, FakeResearchCollector)

    graph.invoke(valid_input(), context=runtime)

    assert len(research.queries) == 1
    assert research.queries[0] == (
        "Assess current BTC risk and opportunity.\n"
        "Asset: BTC\n"
        "Market: cryptocurrency\n"
        "Analysis horizon: 4h"
    )
    assert "BTC-USDT-SWAP" not in research.queries[0]


def test_research_timeout_is_a_retryable_product_failure() -> None:
    agent = RecordingAgent(MarketAnalysis.model_validate(valid_market_analysis()))
    runtime = AnalysisRuntime(
        market_provider=FakeMarketProvider(
            MarketSnapshot.model_validate(complete_market_snapshot())
        ),
        research_collector=TimedOutResearchCollector(),
        analysis_agent=agent,
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"][0] == {
        "code": "research_unavailable",
        "endpoint": "research_events",
        "error_type": "APITimeoutError",
        "retryable": True,
    }
    assert agent.calls == 0


def test_research_failure_preserves_safe_provider_diagnostics() -> None:
    agent = RecordingAgent(MarketAnalysis.model_validate(valid_market_analysis()))
    runtime = AnalysisRuntime(
        market_provider=FakeMarketProvider(
            MarketSnapshot.model_validate(complete_market_snapshot())
        ),
        research_collector=UnverifiedBuiltinSearchCollector(),
        analysis_agent=agent,
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"] == [
        {
            "code": "research_unavailable",
            "endpoint": "research_events",
            "provider": "builtin_web_search",
            "error_type": "UnverifiedServerToolCall",
            "attempt": 3,
            "retryable": True,
        }
    ]
    assert agent.calls == 0


def test_structured_model_validation_failure_is_typed_and_non_retryable() -> None:
    runtime = valid_runtime()
    runtime = AnalysisRuntime(
        market_provider=runtime.market_provider,
        research_collector=runtime.research_collector,
        analysis_agent=InvalidStructuredOutputAgent(),
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"] == [
        {
            "code": "model_invalid_output",
            "error_type": "StructuredOutputValidationError",
            "retryable": False,
        }
    ]
    assert result.get("artifact") is None
    assert result["market_snapshot"]["symbol"] == "BTC-USDT-SWAP"
    assert len(result["web_evidence"]) == 1


def test_exhausted_structured_output_repair_is_typed_and_non_retryable() -> None:
    runtime = valid_runtime()
    runtime = AnalysisRuntime(
        market_provider=runtime.market_provider,
        research_collector=runtime.research_collector,
        analysis_agent=ExhaustedStructuredOutputRepairAgent(),
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"] == [
        {
            "code": "model_invalid_output",
            "error_type": "ModelCallLimitExceededError",
            "retryable": False,
        }
    ]
    assert result.get("artifact") is None


def test_model_output_for_different_symbol_fails_closed() -> None:
    payload = valid_market_analysis()
    payload["instrument"] = "ETH-USDT-SWAP"
    runtime = valid_runtime()
    runtime = AnalysisRuntime(
        market_provider=runtime.market_provider,
        research_collector=runtime.research_collector,
        analysis_agent=RecordingAgent(MarketAnalysis.model_validate(payload)),
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"] == [
        {
            "code": "model_output_mismatch",
            "field": "instrument",
            "expected": "BTC-USDT-SWAP",
            "actual": "ETH-USDT-SWAP",
            "retryable": False,
        }
    ]
    assert result.get("artifact") is None


def test_model_output_for_different_horizon_fails_closed() -> None:
    payload = valid_market_analysis()
    payload["horizon"] = "1d"
    runtime = valid_runtime()
    runtime = AnalysisRuntime(
        market_provider=runtime.market_provider,
        research_collector=runtime.research_collector,
        analysis_agent=RecordingAgent(MarketAnalysis.model_validate(payload)),
    )

    result = graph.invoke(valid_input(), context=runtime)

    assert result["terminal_status"] == "failed"
    assert result["errors"][0] == {
        "code": "model_output_mismatch",
        "field": "horizon",
        "expected": "4h",
        "actual": "1d",
        "retryable": False,
    }
    assert result.get("artifact") is None
