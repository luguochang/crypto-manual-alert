from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Protocol

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from crypto_alert_v2.agents.security import secret_redaction_middleware
from crypto_alert_v2.agents.retry import AGENT_RETRYABLE_ERRORS
from crypto_alert_v2.agents.execution_audit import (
    build_model_execution_audit,
    start_model_timer,
)
from crypto_alert_v2.domain.models import ResearchBundle, ResearchFinding
from crypto_alert_v2.providers.capability_probe import (
    SearchProvider,
    SearchReadinessError,
)
from crypto_alert_v2.providers.errors import ResearchUnavailable
from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    DdgsMetasearchProvider,
    ResearchResult,
    TavilySearchProvider,
    WebEvidence,
)
from crypto_alert_v2.providers.model import as_chat_completions_model


RESEARCH_PROMPT = """Extract only facts supported by the supplied cited evidence.
Set VIX, US 10-year real yield, DXY, or macro_event_scan to null when the evidence
does not establish them. Every finding source_index must identify one supplied source.
Do not return source URLs or source timestamps; the application attaches those values
from verified provider evidence. Do not use unstated model knowledge and do not invent
a citation. Write human-readable structured findings and macro event descriptions in
concise Simplified Chinese, while preserving provider names, asset symbols, numeric
values, and cited source titles.
"""

RESEARCH_PROMPT_VERSION = "research-extraction-v1"


class ResearchFindingExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_index: int = Field(ge=1, le=8)


class ResearchExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vix: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    real_yield_10y: Decimal | None = Field(default=None, allow_inf_nan=False)
    dxy: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    macro_event_scan: list[ResearchFindingExtraction] | None = None
    findings: list[ResearchFindingExtraction] = Field(default_factory=list)
    source_conflicts: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ResearchEvidenceDecision:
    evidence: WebEvidence
    included: bool
    reason: str


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ASSET_ALIASES: dict[str, tuple[str, ...]] = {
    "BTC": ("btc", "bitcoin"),
    "ETH": ("eth", "ethereum", "ether"),
    "SOL": ("sol", "solana"),
}
_CRYPTO_CONTEXT_TERMS = (
    "crypto",
    "cryptocurrency",
    "blockchain",
    "digital asset",
    "digital assets",
    "defi",
    "stablecoin",
    "crypto exchange",
    "cryptocurrency exchange",
    "digital asset exchange",
    "crypto futures",
    "perpetual futures",
    "on chain",
    "onchain",
    "staking",
    "mining",
)
_MACRO_CONTEXT_TERMS = (
    "macro",
    "macroeconomic",
    "economic data",
    "federal reserve",
    "fed",
    "fomc",
    "cpi",
    "inflation",
    "ppi",
    "nonfarm payroll",
    "nfp",
    "jobs report",
    "unemployment",
    "interest rate",
    "policy rate",
    "treasury yield",
    "real yield",
    "10 year yield",
    "dxy",
    "dollar index",
    "vix",
    "volatility index",
    "central bank",
    "monetary policy",
    "fiscal policy",
    "tariff",
    "trade war",
    "geopolitical",
    "recession",
    "gdp",
    "consumer price",
    "producer price",
    "liquidity",
    "risk assets",
)


def classify_research_evidence(
    query: str,
    evidence: tuple[WebEvidence, ...] | list[WebEvidence],
) -> tuple[ResearchEvidenceDecision, ...]:
    """Apply deterministic query-aware relevance before model extraction.

    The classifier deliberately uses token and phrase matches rather than fuzzy
    substring matching. This keeps ``SOL`` from matching words such as
    ``solution`` and makes every inclusion/exclusion reason stable and auditable.
    """

    query_tokens = _normalized_tokens(query)
    requested_assets = frozenset(
        asset
        for asset, aliases in _ASSET_ALIASES.items()
        if any(_contains_phrase(query_tokens, alias) for alias in aliases)
    )
    crypto_scoped = bool(
        requested_assets or _matches_any_term(query_tokens, _CRYPTO_CONTEXT_TERMS)
    )
    macro_scoped = _matches_any_term(query_tokens, _MACRO_CONTEXT_TERMS)
    scoped = crypto_scoped or macro_scoped

    decisions: list[ResearchEvidenceDecision] = []
    for item in evidence:
        item_tokens = _normalized_tokens(
            f"{item.final_url} {item.title} {item.excerpt}"
        )
        matched_assets = frozenset(
            asset
            for asset, aliases in _ASSET_ALIASES.items()
            if any(_contains_phrase(item_tokens, alias) for alias in aliases)
        )
        requested_asset_match = matched_assets & requested_assets
        macro_match = _matches_any_term(item_tokens, _MACRO_CONTEXT_TERMS)
        crypto_match = _matches_any_term(item_tokens, _CRYPTO_CONTEXT_TERMS)

        if not scoped:
            included = True
            reason = "scope_unfiltered"
        elif requested_asset_match:
            included = True
            reason = f"asset_match:{sorted(requested_asset_match)[0]}"
        elif not requested_assets and matched_assets:
            included = True
            reason = f"asset_match:{sorted(matched_assets)[0]}"
        elif macro_match:
            included = True
            reason = "macro_context"
        elif crypto_match and not (requested_assets and matched_assets):
            included = True
            reason = "crypto_context"
        else:
            included = False
            reason = "excluded:no_asset_crypto_or_macro_match"

        audited_item = (
            item
            if included
            else item.model_copy(update={"evidence_relation": "excluded"})
        )
        decisions.append(
            ResearchEvidenceDecision(
                evidence=audited_item,
                included=included,
                reason=reason,
            )
        )
    return tuple(decisions)


def _normalized_tokens(value: object) -> tuple[str, ...]:
    return tuple(_TOKEN_PATTERN.findall(str(value).casefold()))


def _contains_phrase(tokens: tuple[str, ...], phrase: str) -> bool:
    phrase_tokens = _normalized_tokens(phrase)
    width = len(phrase_tokens)
    return width > 0 and any(
        tokens[index : index + width] == phrase_tokens
        for index in range(len(tokens) - width + 1)
    )


def _matches_any_term(tokens: tuple[str, ...], terms: tuple[str, ...]) -> bool:
    return any(_contains_phrase(tokens, term) for term in terms)


class EvidenceSearch(Protocol):
    def search(
        self, query: str, config: RunnableConfig | None = None
    ) -> list[WebEvidence]: ...


class CitedResearchCollector:
    def __init__(self, model: ChatOpenAI, search: EvidenceSearch) -> None:
        self._search = search
        self._agent = create_agent(
            model=as_chat_completions_model(model),
            tools=[],
            middleware=list(secret_redaction_middleware()),
            system_prompt=RESEARCH_PROMPT,
            response_format=ToolStrategy(ResearchExtraction, handle_errors=False),
        ).with_retry(
            retry_if_exception_type=AGENT_RETRYABLE_ERRORS,
            stop_after_attempt=2,
        )

    def collect(
        self, query: str, config: RunnableConfig | None = None
    ) -> ResearchResult:
        provider_evidence = tuple(self._search.search(query, config=config))
        decisions = classify_research_evidence(query, provider_evidence)
        evidence = tuple(decision.evidence for decision in decisions)
        relevant_evidence = tuple(
            decision.evidence for decision in decisions if decision.included
        )
        if not relevant_evidence:
            excluded_count = sum(1 for decision in decisions if not decision.included)
            raise ResearchUnavailable(
                "research relevance filter excluded all provider results "
                f"(count={len(evidence)}, excluded={excluded_count}, "
                "reason=excluded:no_asset_crypto_or_macro_match)",
                provider=_research_provider_name(self._search, evidence),
                retryable=False,
                error_type="NoRelevantResearchEvidence",
            )
        evidence_text = "\n\n".join(
            f"Source index: {index}\n"
            f"URL: {item.final_url}\n"
            f"Title: {item.title}\n"
            f"Excerpt: {item.excerpt}"
            for index, item in enumerate(relevant_evidence, start=1)
        )
        started_at = start_model_timer()
        result = self._agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Research query: {query}\n\nCited evidence:\n{evidence_text}",
                    }
                ]
            },
            config=config,
        )
        model_audit = build_model_execution_audit(
            result,
            prompt_version=RESEARCH_PROMPT_VERSION,
            started_at=started_at,
        )
        extraction = result["structured_response"]
        if not isinstance(extraction, ResearchExtraction):
            raise TypeError("research agent did not return ResearchExtraction")
        bundle = _materialize_research_bundle(extraction, relevant_evidence)
        return ResearchResult(
            bundle=bundle,
            evidence=evidence,
            model_audit=model_audit,
        )


def _research_provider_name(
    search: EvidenceSearch,
    evidence: tuple[WebEvidence, ...],
) -> str:
    if evidence:
        source = evidence[0].source.strip().lower()
        if source:
            return re.sub(r"[^a-z0-9._-]+", "_", source)[:64]
    class_name = type(search).__name__
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).casefold()
    return normalized[:64] or "research_search"


def _materialize_research_bundle(
    extraction: ResearchExtraction,
    evidence: tuple[WebEvidence, ...],
) -> ResearchBundle:
    def materialize(finding: ResearchFindingExtraction) -> ResearchFinding:
        try:
            source = evidence[finding.source_index - 1]
        except IndexError as exc:
            raise ValueError(
                "research agent returned an unknown evidence source index"
            ) from exc
        return ResearchFinding(
            title=finding.title,
            summary=finding.summary,
            source_url=str(source.final_url),
            fetched_at=source.fetched_at,
            published_at=source.published_at,
        )

    return ResearchBundle(
        vix=extraction.vix,
        real_yield_10y=extraction.real_yield_10y,
        dxy=extraction.dxy,
        macro_event_scan=(
            [materialize(finding) for finding in extraction.macro_event_scan]
            if extraction.macro_event_scan is not None
            else None
        ),
        findings=[materialize(finding) for finding in extraction.findings],
        source_conflicts=extraction.source_conflicts,
        evidence_gaps=extraction.evidence_gaps,
    )


class BuiltinResearchCollector(CitedResearchCollector):
    def __init__(self, model: ChatOpenAI) -> None:
        super().__init__(model, BuiltinWebSearchProvider(model))


class TavilyResearchCollector(CitedResearchCollector):
    def __init__(self, model: ChatOpenAI, *, api_key: str) -> None:
        super().__init__(model, TavilySearchProvider(api_key=api_key))


class DdgsMetasearchResearchCollector(CitedResearchCollector):
    def __init__(self, model: ChatOpenAI, *, proxy: str | None = None) -> None:
        super().__init__(model, DdgsMetasearchProvider(proxy=proxy))


class CapabilityAwareResearchCollector:
    def __init__(
        self,
        model: ChatOpenAI,
        *,
        tavily_api_key: str | None,
        provider: SearchProvider,
        search_http_proxy: str | None = None,
    ) -> None:
        self._model = model
        self._tavily_api_key = tavily_api_key
        self._provider = provider
        self._search_http_proxy = search_http_proxy
        self._selected: CitedResearchCollector | None = None

    def collect(
        self, query: str, config: RunnableConfig | None = None
    ) -> ResearchResult:
        if self._selected is None:
            if self._provider is SearchProvider.BUILTIN:
                self._selected = BuiltinResearchCollector(self._model)
            elif self._provider is SearchProvider.DDGS_METASEARCH:
                self._selected = DdgsMetasearchResearchCollector(
                    self._model,
                    proxy=self._search_http_proxy,
                )
            else:
                if self._tavily_api_key is None:
                    raise SearchReadinessError(
                        "Tavily was selected but TAVILY_API_KEY is not configured"
                    )
                self._selected = TavilyResearchCollector(
                    self._model,
                    api_key=self._tavily_api_key,
                )
        return self._selected.collect(query, config=config)
