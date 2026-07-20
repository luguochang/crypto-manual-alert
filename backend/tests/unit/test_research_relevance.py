from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_openai import ChatOpenAI

from crypto_alert_v2.agents import research
from crypto_alert_v2.providers.errors import ResearchUnavailable
from crypto_alert_v2.providers.search import WebEvidence


NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)


def make_evidence(
    slug: str,
    title: str,
    excerpt: str,
    *,
    relation: str = "supports",
) -> WebEvidence:
    return WebEvidence(
        query="research",
        final_url=f"https://news.example/{slug}",
        fetched_at=NOW,
        content_hash=(slug.replace("-", "") + "0" * 64)[:64],
        title=title,
        source="tavily",
        excerpt=excerpt,
        evidence_relation=relation,
    )


def test_relevance_filter_excludes_unrelated_enterprise_news_and_keeps_macro() -> None:
    query = (
        "Review BTC market structure. Asset: BTC. Market: cryptocurrency. "
        "Analysis horizon: 4h."
    )
    decisions = research.classify_research_evidence(
        query,
        [
            make_evidence(
                "bitcoin-price",
                "Bitcoin price and spot ETF flows",
                "Bitcoin market activity and spot ETF flows moved higher.",
            ),
            make_evidence(
                "btog-filing",
                "BTOG files annual report with corporate disclosures",
                "The company reported revenue, expenses, and its annual filing.",
            ),
            make_evidence(
                "fomc-calendar",
                "Federal Reserve FOMC rate decision calendar",
                "The Federal Reserve will publish its interest rate decision.",
            ),
        ],
    )

    assert [decision.included for decision in decisions] == [True, False, True]
    assert decisions[0].reason == "asset_match:BTC"
    assert decisions[1].reason == "excluded:no_asset_crypto_or_macro_match"
    assert decisions[1].evidence.evidence_relation == "excluded"
    assert decisions[2].reason == "macro_context"


@pytest.mark.parametrize(
    ("asset_query", "asset_title", "asset_excerpt"),
    [
        ("ETH", "Ethereum ETF flows", "Ethereum ETF flows increased this week."),
        ("SOL", "Solana network activity", "Solana staking activity increased."),
    ],
)
def test_relevance_filter_matches_requested_eth_and_sol(
    asset_query: str,
    asset_title: str,
    asset_excerpt: str,
) -> None:
    decisions = research.classify_research_evidence(
        f"Assess {asset_query} risk. Asset: {asset_query}. Market: cryptocurrency.",
        [
            make_evidence("asset", asset_title, asset_excerpt),
            make_evidence(
                "solution",
                "Enterprise solution results",
                "The company announced a new software solution and board changes.",
            ),
        ],
    )

    assert decisions[0].included is True
    assert decisions[0].reason == f"asset_match:{asset_query}"
    assert decisions[1].included is False
    assert decisions[1].evidence.evidence_relation == "excluded"


@pytest.mark.parametrize(
    ("title", "excerpt"),
    [
        ("BBVA reports quarterly earnings", "The bank discussed loan growth and fees."),
        (
            "Xponential Fitness board letter",
            "The fitness company announced board changes.",
        ),
        (
            "VAALCO Energy fiscal results",
            "The energy company reported production results.",
        ),
        ("Alstom fiscal year results", "The industrial company reported order intake."),
    ],
)
def test_obviously_unrelated_enterprise_results_are_excluded(
    title: str,
    excerpt: str,
) -> None:
    decisions = research.classify_research_evidence(
        "Assess BTC macro risk. Asset: BTC. Market: cryptocurrency.",
        [make_evidence("enterprise", title, excerpt)],
    )

    assert decisions[0].included is False
    assert decisions[0].reason == "excluded:no_asset_crypto_or_macro_match"
    assert decisions[0].evidence.evidence_relation == "excluded"


def test_collector_sends_only_relevant_sources_and_maps_indices_to_original_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    evidence = [
        make_evidence(
            "btc", "Bitcoin market structure", "Bitcoin price structure changed."
        ),
        make_evidence(
            "bbva",
            "BBVA earnings call",
            "The bank discussed loan growth and financial performance.",
        ),
        make_evidence(
            "dxy",
            "DXY dollar index rises",
            "The dollar index moved as markets assessed Federal Reserve policy.",
        ),
    ]

    class FakeAgent:
        invoked = False

        def with_retry(self, **_: Any) -> "FakeAgent":
            return self

        def invoke(self, payload: dict[str, Any], config: Any = None) -> dict[str, Any]:
            del config
            self.invoked = True
            captured["prompt"] = payload["messages"][0]["content"]
            return {
                "messages": [],
                "structured_response": research.ResearchExtraction(
                    findings=[
                        research.ResearchFindingExtraction(
                            title="Dollar index",
                            summary="美元指数影响风险资产定价。",
                            source_index=2,
                        )
                    ]
                ),
            }

    agent = FakeAgent()
    monkeypatch.setattr(research, "create_agent", lambda **_: agent)

    class FakeSearch:
        def search(self, query: str, config: Any = None) -> list[WebEvidence]:
            del query, config
            return evidence

    result = research.CitedResearchCollector(
        model=ChatOpenAI(
            model="research-relevance-test",
            api_key="test-key",
            base_url="https://model.example/v1",
        ),
        search=FakeSearch(),
    ).collect("Assess BTC macro risk. Asset: BTC. Market: cryptocurrency.")

    assert agent.invoked is True
    assert "Bitcoin market structure" in captured["prompt"]
    assert "DXY dollar index rises" in captured["prompt"]
    assert "BBVA earnings call" not in captured["prompt"]
    assert [item.evidence_relation for item in result.evidence] == [
        "supports",
        "excluded",
        "supports",
    ]
    assert result.bundle.findings[0].source_url == str(evidence[2].final_url)


def test_collector_fails_closed_before_structured_extraction_when_all_sources_are_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAgent:
        invoked = False

        def with_retry(self, **_: Any) -> "FakeAgent":
            return self

        def invoke(self, payload: dict[str, Any], config: Any = None) -> dict[str, Any]:
            del payload, config
            self.invoked = True
            raise AssertionError(
                "structured extraction must not receive excluded evidence"
            )

    agent = FakeAgent()
    monkeypatch.setattr(research, "create_agent", lambda **_: agent)

    class FakeSearch:
        def search(self, query: str, config: Any = None) -> list[WebEvidence]:
            del query, config
            return [
                make_evidence(
                    "btog", "BTOG annual report", "Corporate revenue and expenses."
                ),
                make_evidence(
                    "alstom", "Alstom fiscal results", "Industrial order intake."
                ),
            ]

    collector = research.CitedResearchCollector(
        model=ChatOpenAI(
            model="research-relevance-test",
            api_key="test-key",
            base_url="https://model.example/v1",
        ),
        search=FakeSearch(),
    )

    with pytest.raises(ResearchUnavailable) as caught:
        collector.collect("Assess BTC macro risk. Asset: BTC. Market: cryptocurrency.")

    assert agent.invoked is False
    assert caught.value.provider == "tavily"
    assert caught.value.retryable is False
    assert caught.value.error_type == "NoRelevantResearchEvidence"
    assert "count=2" in str(caught.value)
    assert "reason=excluded:no_asset_crypto_or_macro_match" in str(caught.value)


def test_generic_query_remains_compatible_with_existing_unscoped_research() -> None:
    decisions = research.classify_research_evidence(
        "bounded research",
        [make_evidence("generic", "Enterprise result", "A factual result.")],
    )

    assert decisions[0].included is True
    assert decisions[0].reason == "scope_unfiltered"
