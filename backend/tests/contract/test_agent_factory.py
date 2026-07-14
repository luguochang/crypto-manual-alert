from typing import Any

from langchain.agents.structured_output import ToolStrategy

from crypto_alert_v2.agents import market_analysis
from crypto_alert_v2.agents import research
from crypto_alert_v2.domain.models import MarketAnalysis
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

    model = object()
    result = market_analysis.create_market_analysis_agent(model=model)

    assert result is sentinel
    assert captured["model"] is model
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
    retry_options: dict[str, Any] = {}

    class Sentinel:
        def with_retry(self, **kwargs: Any) -> "Sentinel":
            retry_options.update(kwargs)
            return self

    monkeypatch.setattr(research, "create_agent", lambda **_: Sentinel())

    research.CitedResearchCollector(model=object(), search=object())  # type: ignore[arg-type]

    assert retry_options == {
        "retry_if_exception_type": TRANSIENT_MODEL_ERRORS,
        "stop_after_attempt": 2,
    }
