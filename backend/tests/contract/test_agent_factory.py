from typing import Any

from langchain.agents.structured_output import ToolStrategy
from langchain_openai import ChatOpenAI

from crypto_alert_v2.agents import market_analysis
from crypto_alert_v2.agents import research
from crypto_alert_v2.domain.models import MarketAnalysis, ResearchBundle
from crypto_alert_v2.providers.errors import TRANSIENT_MODEL_ERRORS


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
    result = market_analysis.create_market_analysis_agent(model=model)

    assert result is sentinel
    structured_model = captured["model"]
    assert structured_model is not model
    assert structured_model.use_responses_api is False
    assert structured_model.output_version is None
    assert model.use_responses_api is True
    assert model.output_version == "responses/v1"
    assert isinstance(captured["response_format"], ToolStrategy)
    assert captured["response_format"].schema is MarketAnalysis
    assert "tools" in captured
    assert isinstance(captured["system_prompt"], str)
    assert captured["system_prompt"]
    assert retry_options == {
        "retry_if_exception_type": TRANSIENT_MODEL_ERRORS,
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
    assert captured["response_format"].schema is ResearchBundle
    assert captured["tools"] == []
    assert retry_options == {
        "retry_if_exception_type": TRANSIENT_MODEL_ERRORS,
        "stop_after_attempt": 2,
    }


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
