from datetime import UTC, datetime
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    PIIMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_openai import ChatOpenAI

from crypto_alert_v2.agents import market_analysis
from crypto_alert_v2.agents import research
from crypto_alert_v2.agents.retry import (
    AGENT_RETRYABLE_ERRORS,
    MODEL_TRANSPORT_RETRY_ERRORS,
)
from crypto_alert_v2.domain.models import MarketAnalysis
from crypto_alert_v2.providers.search import WebEvidence


def test_market_agent_factory_uses_official_structured_response(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    retry_options: dict[str, Any] = {}

    class Sentinel:
        def with_retry(self, **kwargs: Any) -> "Sentinel":
            retry_options.update(kwargs)
            return self

    sentinel = Sentinel()

    def fake_create_agent(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(market_analysis, "create_agent", fake_create_agent)

    model = ChatOpenAI(
        model="agent-factory-test",
        api_key="test-key",
        base_url="https://model.example/v1",
        use_responses_api=True,
        output_version="responses/v1",
    )
    test_middleware = AgentMiddleware()
    result = market_analysis.create_market_analysis_agent(
        model=model,
        additional_middleware=(test_middleware,),
    )

    assert result is sentinel
    structured_model = captured["model"]
    assert structured_model is not model
    assert structured_model.use_responses_api is False
    assert structured_model.output_version is None
    assert model.use_responses_api is True
    assert model.output_version == "responses/v1"
    assert isinstance(captured["response_format"], ToolStrategy)
    assert captured["response_format"].schema is MarketAnalysis
    assert captured["response_format"].handle_errors == (
        market_analysis.MARKET_ANALYSIS_STRUCTURED_OUTPUT_REPAIR
    )
    assert "tools" in captured
    assert captured["middleware"][-1] is test_middleware
    call_limit = captured["middleware"][0]
    assert isinstance(call_limit, ModelCallLimitMiddleware)
    assert call_limit.run_limit == 3
    assert call_limit.exit_behavior == "error"
    pii_middleware = captured["middleware"][1:-1]
    assert {item.pii_type for item in pii_middleware} == {
        "email",
        "credit_card",
        "ip",
        "mac_address",
        "phone",
        "secret",
    }
    assert all(isinstance(item, PIIMiddleware) for item in pii_middleware)
    assert all(item.apply_to_input for item in pii_middleware)
    assert all(item.apply_to_output for item in pii_middleware)
    assert all(item.apply_to_tool_results for item in pii_middleware)
    assert isinstance(captured["system_prompt"], str)
    assert "Simplified Chinese" in captured["system_prompt"]
    assert "root_cause_chain" in captured["system_prompt"]
    assert retry_options == {
        "retry_if_exception_type": MODEL_TRANSPORT_RETRY_ERRORS,
        "stop_after_attempt": 2,
    }


def test_research_extractor_uses_the_same_bounded_official_retry(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    retry_options: dict[str, Any] = {}

    class Sentinel:
        def with_retry(self, **kwargs: Any) -> "Sentinel":
            retry_options.update(kwargs)
            return self

    def fake_create_agent(**kwargs: Any) -> Sentinel:
        captured.update(kwargs)
        return Sentinel()

    monkeypatch.setattr(research, "create_agent", fake_create_agent)

    model = ChatOpenAI(
        model="agent-factory-test",
        api_key="test-key",
        base_url="https://model.example/v1",
        use_responses_api=True,
        output_version="responses/v1",
    )
    research.CitedResearchCollector(model=model, search=object())  # type: ignore[arg-type]

    structured_model = captured["model"]
    assert structured_model is not model
    assert structured_model.use_responses_api is False
    assert structured_model.output_version is None
    assert model.use_responses_api is True
    assert model.output_version == "responses/v1"
    assert isinstance(captured["response_format"], ToolStrategy)
    assert captured["response_format"].schema is research.ResearchExtraction
    assert captured["response_format"].handle_errors is False
    assert captured["tools"] == []
    assert {item.pii_type for item in captured["middleware"]} == {
        "email",
        "credit_card",
        "ip",
        "mac_address",
        "phone",
        "secret",
    }
    assert all(isinstance(item, PIIMiddleware) for item in captured["middleware"])
    assert all(item.apply_to_input for item in captured["middleware"])
    assert all(item.apply_to_output for item in captured["middleware"])
    assert all(item.apply_to_tool_results for item in captured["middleware"])
    assert "Simplified Chinese" in captured["system_prompt"]
    assert "source_index" in captured["system_prompt"]
    assert retry_options == {
        "retry_if_exception_type": AGENT_RETRYABLE_ERRORS,
        "stop_after_attempt": 2,
    }


def test_research_extractor_materializes_source_metadata_from_verified_evidence(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    fetched_at = datetime(2026, 7, 18, 7, 30, tzinfo=UTC)
    published_at = datetime(2026, 7, 18, 6, 45, tzinfo=UTC)
    evidence = WebEvidence(
        query="BTC macro",
        final_url="https://source.example/market/btc",
        fetched_at=fetched_at,
        published_at=published_at,
        content_hash="a" * 64,
        title="BTC macro update",
        source="test-search",
        excerpt="A verified macro update for Bitcoin.",
        evidence_relation="direct",
    )

    class FakeAgent:
        def with_retry(self, **_: Any) -> "FakeAgent":
            return self

        def invoke(self, payload: dict[str, Any], config: Any = None) -> dict[str, Any]:
            del config
            captured["prompt"] = payload["messages"][0]["content"]
            return {
                "messages": [],
                "structured_response": research.ResearchExtraction(
                    findings=[
                        research.ResearchFindingExtraction(
                            title="BTC macro update",
                            summary="宏观条件仍需谨慎。",
                            source_index=1,
                        )
                    ]
                ),
            }

    monkeypatch.setattr(research, "create_agent", lambda **_: FakeAgent())

    class FakeSearch:
        def search(self, query: str, config: Any = None) -> list[WebEvidence]:
            del query, config
            return [evidence]

    model = ChatOpenAI(
        model="agent-factory-test",
        api_key="test-key",
        base_url="https://model.example/v1",
    )
    result = research.CitedResearchCollector(
        model=model,
        search=FakeSearch(),
    ).collect("BTC macro")

    assert "Source index: 1" in captured["prompt"]
    assert result.bundle.findings[0].source_url == str(evidence.final_url)
    assert result.bundle.findings[0].fetched_at == fetched_at
    assert result.bundle.findings[0].published_at == published_at
    finding_schema = research.ResearchFindingExtraction.model_json_schema()
    assert "source_index" in finding_schema["properties"]
    assert "source_url" not in finding_schema["properties"]
    assert "fetched_at" not in finding_schema["properties"]


def test_builtin_research_keeps_responses_model_for_provider_search(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    class Sentinel:
        def with_retry(self, **_: Any) -> "Sentinel":
            return self

    class RecordingSearch:
        def __init__(self, model: ChatOpenAI) -> None:
            captured["search_model"] = model

    def fake_create_agent(**kwargs: Any) -> Sentinel:
        captured["structured_model"] = kwargs["model"]
        return Sentinel()

    monkeypatch.setattr(research, "BuiltinWebSearchProvider", RecordingSearch)
    monkeypatch.setattr(research, "create_agent", fake_create_agent)

    model = ChatOpenAI(
        model="agent-factory-test",
        api_key="test-key",
        base_url="https://model.example/v1",
        use_responses_api=True,
        output_version="responses/v1",
    )
    research.BuiltinResearchCollector(model)

    assert captured["search_model"] is model
    structured_model = captured["structured_model"]
    assert structured_model is not model
    assert structured_model.use_responses_api is False
    assert structured_model.output_version is None


def test_web_market_fallback_uses_official_search_and_structured_agent(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}
    retry_options: dict[str, Any] = {}

    class Sentinel:
        def with_retry(self, **kwargs: Any) -> "Sentinel":
            retry_options.update(kwargs)
            return self

    def fake_create_agent(**kwargs: Any) -> Sentinel:
        captured.update(kwargs)
        return Sentinel()

    monkeypatch.setattr(market_analysis, "create_agent", fake_create_agent)
    model = ChatOpenAI(
        model="agent-factory-test",
        api_key="test-key",
        base_url="https://model.example/v1",
        use_responses_api=True,
        output_version="responses/v1",
    )

    market_analysis.create_web_market_extraction_agent(model=model)

    structured_model = captured["model"]
    assert structured_model is not model
    assert structured_model.use_responses_api is False
    assert structured_model.output_version is None
    assert captured["tools"] == []
    strategy = captured["response_format"]
    assert isinstance(strategy, ToolStrategy)
    assert strategy.schema is market_analysis.WebMarketExtraction
    assert strategy.handle_errors is False
    assert "even if other cited prices differ" in captured["system_prompt"]
    assert "Never average or\nreconcile conflicting values" in captured["system_prompt"]
    assert {item.pii_type for item in captured["middleware"]} == {
        "email",
        "credit_card",
        "ip",
        "mac_address",
        "phone",
        "secret",
    }
    assert retry_options == {
        "retry_if_exception_type": AGENT_RETRYABLE_ERRORS,
        "stop_after_attempt": 2,
    }
