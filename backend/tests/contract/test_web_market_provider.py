from datetime import UTC, datetime
from typing import Any, cast

import pytest
from langchain_openai import ChatOpenAI

from crypto_alert_v2.providers.errors import ResearchUnavailable
from crypto_alert_v2.providers.search import WebEvidence
from crypto_alert_v2.providers.web_market import (
    CitedMarketValue,
    WebMarketExtraction,
    WebSearchMarketCollector,
)


NOW = datetime(2026, 7, 17, 8, 0, tzinfo=UTC)
SOURCE_URL = "https://www.kraken.com/features/futures/bitcoin"


def cited_evidence(*, source: str = "openai_builtin_web_search") -> WebEvidence:
    return WebEvidence(
        query="current BTC futures market data",
        final_url=SOURCE_URL,
        fetched_at=NOW,
        content_hash="a" * 64,
        title="Bitcoin futures market",
        source=source,
        excerpt=(
            "BTC last price is $65,000.25, mark price is $65,001.00, "
            "funding is 0.01%, and open interest is 1.2 billion USD."
        ),
        evidence_relation="supports",
    )


class RecordingSearch:
    def __init__(self, evidence: list[WebEvidence]) -> None:
        self.evidence = evidence
        self.queries: list[str] = []
        self.configs: list[Any] = []

    def search(self, query: str, config: Any = None) -> list[WebEvidence]:
        self.queries.append(query)
        self.configs.append(config)
        return self.evidence


class RecordingAgent:
    def __init__(self, extraction: WebMarketExtraction) -> None:
        self.extraction = extraction
        self.payloads: list[dict[str, Any]] = []
        self.configs: list[Any] = []

    def invoke(self, payload: dict[str, Any], config: Any = None) -> dict[str, Any]:
        self.payloads.append(payload)
        self.configs.append(config)
        return {
            "structured_response": self.extraction,
            "messages": [
                {
                    "role": "assistant",
                    "usage_metadata": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                    },
                    "response_metadata": {"id": "response-web-market"},
                }
            ],
        }


def cited_value(value: str, quote: str, *, url: str = SOURCE_URL) -> CitedMarketValue:
    return CitedMarketValue(value=value, source_url=url, quote=quote)


def valid_extraction() -> WebMarketExtraction:
    return WebMarketExtraction(
        symbol="BTC-USDT-SWAP",
        ticker_last=cited_value("65000.25", "$65,000.25"),
        mark_price=cited_value("65001.00", "$65,001.00"),
        index_price=None,
        funding_rate=cited_value("0.0001", "0.01%"),
        open_interest=cited_value("1200000000", "1.2 billion"),
    )


def collector(
    extraction: WebMarketExtraction,
    *,
    evidence: list[WebEvidence] | None = None,
) -> tuple[WebSearchMarketCollector, RecordingSearch, RecordingAgent]:
    search = RecordingSearch(evidence or [cited_evidence()])
    agent = RecordingAgent(extraction)
    instance = WebSearchMarketCollector(
        cast(ChatOpenAI, object()),
        search=search,
        agent=agent,
    )
    return instance, search, agent


def test_web_market_fallback_returns_only_cited_partial_typed_data() -> None:
    instance, search, agent = collector(valid_extraction())
    config = {"metadata": {"correlation_id": "corr-1"}}

    result = instance.collect(
        "BTC-USDT-SWAP",
        horizon="4h",
        config=config,
    )

    assert result.snapshot.source_level == "web_search_verified"
    assert result.snapshot.ticker is not None
    assert str(result.snapshot.ticker.last) == "65000.25"
    assert str(result.snapshot.mark_price) == "65001.00"
    assert result.snapshot.index_price is None
    assert str(result.snapshot.funding_rate) == "0.0001"
    assert str(result.snapshot.open_interest) == "1200000000"
    assert result.snapshot.order_book is None
    assert result.snapshot.candles == []
    assert result.evidence[0].evidence_relation == "market_snapshot"
    assert result.model_audit.prompt_version == "web-market-extraction-v2"
    assert result.model_audit.call_count == 1
    assert result.model_audit.observation_ids == ["response-web-market"]
    assert search.configs == [config]
    assert agent.configs == [config]
    assert search.queries[0] == "current BTC USD price market data live"
    assert "Fetched at: 2026-07-17T08:00:00+00:00" in str(agent.payloads[0])


@pytest.mark.parametrize(
    ("field", "replacement", "error_type"),
    [
        (
            "ticker_last",
            cited_value("65000.25", "a quote that is not in the evidence"),
            "UnsupportedQuote:ticker_last",
        ),
        (
            "ticker_last",
            cited_value("99999", "$65,000.25"),
            "UnsupportedValue:ticker_last",
        ),
        (
            "mark_price",
            cited_value(
                "65001.00",
                "$65,001.00",
                url="https://unsupported.example.invalid/market",
            ),
            "UnsupportedSource:mark_price",
        ),
    ],
)
def test_web_market_fallback_rejects_uncited_agent_values(
    field: str,
    replacement: CitedMarketValue,
    error_type: str,
) -> None:
    extraction = valid_extraction().model_copy(update={field: replacement})
    instance, _, _ = collector(extraction)

    with pytest.raises(ResearchUnavailable) as caught:
        instance.collect("BTC-USDT-SWAP", horizon="4h")

    assert caught.value.provider == "builtin_web_search"
    assert caught.value.error_type == error_type


def test_web_market_fallback_requires_a_cited_ticker_for_analysis() -> None:
    extraction = valid_extraction().model_copy(update={"ticker_last": None})
    instance, _, _ = collector(extraction)

    with pytest.raises(ResearchUnavailable) as caught:
        instance.collect("BTC-USDT-SWAP", horizon="4h")

    assert caught.value.error_type == "MissingCitedTicker"
    assert caught.value.retryable is True


def test_web_market_fallback_preserves_selected_search_provider_in_errors() -> None:
    extraction = valid_extraction().model_copy(update={"ticker_last": None})
    instance, _, _ = collector(
        extraction,
        evidence=[cited_evidence(source="ddgs_metasearch")],
    )

    with pytest.raises(ResearchUnavailable) as caught:
        instance.collect("BTC-USDT-SWAP", horizon="4h")

    assert caught.value.provider == "ddgs_metasearch"
    assert caught.value.error_type == "MissingCitedTicker"


def test_web_market_fallback_rejects_symbol_drift() -> None:
    extraction = valid_extraction().model_copy(update={"symbol": "ETH-USDT-SWAP"})
    instance, _, _ = collector(extraction)

    with pytest.raises(ResearchUnavailable) as caught:
        instance.collect("BTC-USDT-SWAP", horizon="4h")

    assert caught.value.error_type == "SymbolMismatch"
