from typing import Any

import pytest
from langchain_openai import ChatOpenAI

from crypto_alert_v2.agents import research
from crypto_alert_v2.providers.retry_policy import SearchRetryPolicy
from crypto_alert_v2.providers.search import TavilySearchProvider


def test_tavily_collector_boundary_excludes_unrelated_result_before_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class InMemoryTavilyTool:
        def invoke(self, input: dict[str, str], config: Any = None) -> dict[str, Any]:
            del config
            captured["provider_query"] = input["query"]
            return {
                "results": [
                    {
                        "url": "https://www.reuters.com/markets/bitcoin-contract",
                        "title": "Bitcoin market structure",
                        "content": "Bitcoin liquidity improved as crypto trading rose.",
                    },
                    {
                        "url": "https://www.bbva.com/en/earnings-contract",
                        "title": "BBVA quarterly earnings",
                        "content": "The bank discussed loan growth and operating income.",
                    },
                ]
            }

    class FakeAgent:
        def with_retry(self, **_: Any) -> "FakeAgent":
            return self

        def invoke(self, payload: dict[str, Any], config: Any = None) -> dict[str, Any]:
            del config
            captured["model_prompt"] = payload["messages"][0]["content"]
            return {
                "messages": [],
                "structured_response": research.ResearchExtraction(
                    findings=[
                        research.ResearchFindingExtraction(
                            title="Bitcoin market structure",
                            summary="比特币市场流动性改善。",
                            source_index=1,
                        )
                    ]
                ),
            }

    monkeypatch.setattr(research, "create_agent", lambda **_: FakeAgent())
    provider = TavilySearchProvider(
        tool=InMemoryTavilyTool(),
        retry_policy=SearchRetryPolicy(max_attempts=1),
    )
    collector = research.CitedResearchCollector(
        model=ChatOpenAI(
            model="research-relevance-contract",
            api_key="test-key",
            base_url="https://model.example/v1",
        ),
        search=provider,
    )
    query = "Assess BTC risk. Asset: BTC. Market: cryptocurrency."

    result = collector.collect(query)

    assert captured["provider_query"] == query
    assert "Bitcoin market structure" in captured["model_prompt"]
    assert "BBVA quarterly earnings" not in captured["model_prompt"]
    assert [item.evidence_relation for item in result.evidence] == [
        "supports",
        "excluded",
    ]
    assert result.bundle.findings[0].source_url == str(result.evidence[0].final_url)
