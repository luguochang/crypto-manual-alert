from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import TypeAdapter

from crypto_alert_v2.agents.execution_audit import (
    build_model_execution_audit,
    start_model_timer,
)
from crypto_alert_v2.agents.market_analysis import (
    CitedMarketValue,
    WEB_MARKET_PROMPT_VERSION,
    WebMarketExtraction,
    create_web_market_extraction_agent,
)
from crypto_alert_v2.domain.models import (
    MarketSnapshot,
    ModelExecutionAudit,
    Symbol,
    Ticker,
)
from crypto_alert_v2.providers.errors import ResearchUnavailable
from crypto_alert_v2.providers.retry_policy import SearchRetryPolicy
from crypto_alert_v2.providers.search import BuiltinWebSearchProvider, WebEvidence


_SYMBOL_ADAPTER = TypeAdapter(Symbol)


@dataclass(frozen=True, slots=True)
class WebMarketResult:
    snapshot: MarketSnapshot
    evidence: tuple[WebEvidence, ...]
    model_audit: ModelExecutionAudit


class EvidenceSearch(Protocol):
    def search(
        self,
        query: str,
        config: RunnableConfig | None = None,
    ) -> list[WebEvidence]: ...


class ExtractionAgent(Protocol):
    def invoke(
        self,
        payload: dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]: ...


class WebSearchMarketCollector:
    """Cited, partial market fallback built on official search and agent APIs."""

    def __init__(
        self,
        model: ChatOpenAI,
        *,
        search: EvidenceSearch | None = None,
        agent: ExtractionAgent | None = None,
    ) -> None:
        self._search = search or BuiltinWebSearchProvider(
            model,
            retry_policy=SearchRetryPolicy(),
            result_requirements=(
                "State the exact current BTC, ETH, or SOL USD price as a numeric "
                "value in one sentence. Do not return a bare link or title. "
                "If a cited source also establishes mark price, index price, funding "
                "rate, or open interest, include those exact numeric values. Do not "
                "estimate or use uncited model knowledge."
            ),
            allow_completed_open_page_evidence=True,
            evidence_validator=require_usd_price_evidence,
        )
        self._agent = agent or create_web_market_extraction_agent(model=model)

    def collect(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        config: RunnableConfig | None = None,
    ) -> WebMarketResult:
        validated_symbol = _SYMBOL_ADAPTER.validate_python(symbol)
        asset = validated_symbol.partition("-")[0]
        query = f"current {asset} USD price market data live"
        evidence = tuple(
            item.model_copy(update={"evidence_relation": "market_snapshot"})
            for item in self._search.search(query, config=config)
        )
        require_usd_price_evidence(list(evidence))
        search_provider = _evidence_provider(evidence)
        evidence_text = "\n\n".join(
            f"URL: {item.final_url}\n"
            f"Title: {item.title}\n"
            f"Fetched at: {item.fetched_at.isoformat()}\n"
            f"Published at: "
            f"{item.published_at.isoformat() if item.published_at else 'unavailable'}\n"
            f"Excerpt: {item.excerpt}"
            for item in evidence
        )
        started_at = start_model_timer()
        result = self._agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Requested symbol: {validated_symbol}\n"
                            f"Analysis horizon: {horizon or 'current'}\n\n"
                            f"Provider-cited evidence:\n{evidence_text}"
                        ),
                    }
                ]
            },
            config=config,
        )
        model_audit = build_model_execution_audit(
            result,
            prompt_version=WEB_MARKET_PROMPT_VERSION,
            started_at=started_at,
        )
        extraction = result.get("structured_response")
        if not isinstance(extraction, WebMarketExtraction):
            raise TypeError("web market agent did not return WebMarketExtraction")
        if extraction.symbol != validated_symbol:
            raise _market_evidence_error("SymbolMismatch", provider=search_provider)

        evidence_by_url = {str(item.final_url): item for item in evidence}
        ticker_last = _validated_value(
            "ticker_last",
            extraction.ticker_last,
            evidence_by_url,
            provider=search_provider,
            positive=True,
        )
        if ticker_last is None:
            raise _market_evidence_error(
                "MissingCitedTicker",
                provider=search_provider,
                retryable=True,
            )
        mark_price = _validated_value(
            "mark_price",
            extraction.mark_price,
            evidence_by_url,
            provider=search_provider,
            positive=True,
        )
        index_price = _validated_value(
            "index_price",
            extraction.index_price,
            evidence_by_url,
            provider=search_provider,
            positive=True,
        )
        funding_rate = _validated_value(
            "funding_rate",
            extraction.funding_rate,
            evidence_by_url,
            provider=search_provider,
        )
        open_interest = _validated_value(
            "open_interest",
            extraction.open_interest,
            evidence_by_url,
            provider=search_provider,
            nonnegative=True,
        )
        fetched_at = max(item.fetched_at for item in evidence)
        snapshot = MarketSnapshot(
            symbol=validated_symbol,
            fetched_at=fetched_at,
            source_level="web_search_verified",
            ticker=Ticker(last=ticker_last),
            mark_price=mark_price,
            index_price=index_price,
            funding_rate=funding_rate,
            open_interest=open_interest,
            order_book=None,
            candles=[],
        )
        return WebMarketResult(
            snapshot=snapshot,
            evidence=evidence,
            model_audit=model_audit,
        )


_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])([-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s*(%|k|m|b|thousand|million|billion)?",
    flags=re.IGNORECASE,
)
_SCALES = {
    "": Decimal("1"),
    "k": Decimal("1000"),
    "thousand": Decimal("1000"),
    "m": Decimal("1000000"),
    "million": Decimal("1000000"),
    "b": Decimal("1000000000"),
    "billion": Decimal("1000000000"),
}


def _evidence_provider(evidence: tuple[WebEvidence, ...] | list[WebEvidence]) -> str:
    sources = {item.source for item in evidence}
    if sources and sources <= {
        "builtin_web_search",
        "openai_builtin_web_search",
        "openai_web_search",
    }:
        return "builtin_web_search"
    if len(sources) == 1:
        return next(iter(sources))
    return "web_search"


def require_usd_price_evidence(evidence: list[WebEvidence]) -> None:
    for item in evidence:
        excerpt = item.excerpt
        if not ("$" in excerpt or re.search(r"\bUSD\b", excerpt, re.IGNORECASE)):
            continue
        for match in _NUMBER_PATTERN.finditer(excerpt):
            value = Decimal(match.group(1).replace(",", ""))
            if value > 0:
                return
    raise ResearchUnavailable(
        "Web Search returned no cited USD price value",
        provider=_evidence_provider(evidence),
        retryable=True,
        error_type="MissingCitedTickerCandidate",
    )


def _validated_value(
    field: str,
    cited: CitedMarketValue | None,
    evidence_by_url: Mapping[str, WebEvidence],
    *,
    provider: str,
    positive: bool = False,
    nonnegative: bool = False,
) -> Decimal | None:
    if cited is None:
        return None
    evidence = evidence_by_url.get(str(cited.source_url))
    if evidence is None:
        raise _market_evidence_error(f"UnsupportedSource:{field}", provider=provider)
    quote = " ".join(cited.quote.split())
    excerpt = " ".join(evidence.excerpt.split())
    if quote not in excerpt:
        raise _market_evidence_error(f"UnsupportedQuote:{field}", provider=provider)
    if not _quote_supports_value(cited.value, quote):
        raise _market_evidence_error(f"UnsupportedValue:{field}", provider=provider)
    if positive and cited.value <= 0:
        raise _market_evidence_error(f"NonPositiveValue:{field}", provider=provider)
    if nonnegative and cited.value < 0:
        raise _market_evidence_error(f"NegativeValue:{field}", provider=provider)
    return cited.value


def _quote_supports_value(value: Decimal, quote: str) -> bool:
    for match in _NUMBER_PATTERN.finditer(quote):
        number = Decimal(match.group(1).replace(",", ""))
        suffix = (match.group(2) or "").lower()
        candidate = number / 100 if suffix == "%" else number * _SCALES[suffix]
        if candidate == value:
            return True
    return False


def _market_evidence_error(
    error_type: str,
    *,
    provider: str,
    retryable: bool = False,
) -> ResearchUnavailable:
    return ResearchUnavailable(
        "Web Search market evidence did not satisfy the cited value contract",
        provider=provider,
        retryable=retryable,
        error_type=error_type,
    )


__all__ = [
    "CitedMarketValue",
    "WEB_MARKET_PROMPT_VERSION",
    "WebMarketExtraction",
    "WebMarketResult",
    "WebSearchMarketCollector",
    "require_usd_price_evidence",
]
