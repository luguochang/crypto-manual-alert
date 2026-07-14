import importlib
from typing import Any
import httpx
from langchain_core.callbacks import BaseCallbackHandler
from openai import APITimeoutError

from crypto_alert_v2.domain.models import (
    MarketAnalysis,
    MarketSnapshot,
    ResearchBundle,
)
from crypto_alert_v2.graph.graph import graph
from crypto_alert_v2.graph.runtime import AnalysisRuntime, ResearchResult
from crypto_alert_v2.observability.callbacks import build_observability_config
from crypto_alert_v2.providers.errors import ProviderUnavailable, ResearchUnavailable
from crypto_alert_v2.providers.capability_probe import SearchReadinessError
from crypto_alert_v2.providers.search import WebEvidence
from tests.fixtures.golden_cases import (
    NOW,
    complete_market_snapshot,
    complete_research_bundle,
    valid_market_analysis,
)


class FakeMarketProvider:
    def __init__(self, snapshot: MarketSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[str] = []

    def fetch_snapshot(self, symbol: str, *, correlation_id: str) -> MarketSnapshot:
        self.calls.append(symbol)
        return self.snapshot


class FailingMarketProvider:
    def fetch_snapshot(self, symbol: str, *, correlation_id: str) -> MarketSnapshot:
        raise ProviderUnavailable(
            "market offline",
            provider="okx",
            endpoint="ticker",
            retryable=True,
            correlation_id=correlation_id,
        )


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

    def invoke(self, payload: dict[str, Any], config: object = None) -> dict[str, Any]:
        del payload
        self.calls += 1
        self.configs.append(config)
        return {"structured_response": self.analysis}


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


def test_vertical_path_returns_committed_typed_artifact() -> None:
    result = graph.invoke(valid_input(), context=valid_runtime())

    assert result["terminal_status"] == "succeeded"
    assert result["artifact"]["status"] == "committed"
    assert result["artifact"]["analysis"]["main_action"] == "open_long"
    assert result["artifact"]["evidence_verdict"]["sufficient"] is True
    assert result["artifact"]["risk_verdict"]["allowed"] is True
    assert result["web_evidence"][0]["final_url"].startswith("https://")


def test_root_observability_config_propagates_to_both_external_calls() -> None:
    runtime = valid_runtime()
    research = runtime.research_collector
    agent = runtime.analysis_agent
    assert isinstance(research, FakeResearchCollector)
    assert isinstance(agent, RecordingAgent)
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
    expected_root_metadata = {
        **metadata,
        "langfuse_user_id": "anonymous-user-1",
        "langfuse_session_id": "thread-1",
        "nested": {"safe": "value"},
    }
    for key, value in expected_root_metadata.items():
        assert research_config["metadata"][key] == value
        assert agent_config["metadata"][key] == value
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
        "build_observability_config",
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
    assert "exactly one current public BTC macro news source" in research.queries[0]
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
            "provider": "builtin_web_search",
            "error_type": "UnverifiedServerToolCall",
            "attempt": 3,
            "retryable": True,
        }
    ]
    assert agent.calls == 0


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
