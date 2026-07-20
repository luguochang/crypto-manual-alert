from __future__ import annotations

import asyncio
from collections.abc import Sequence
import json
from dataclasses import dataclass
from typing import Protocol, TYPE_CHECKING

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from crypto_alert_v2.agents.execution_audit import (
    build_model_execution_audit,
    start_model_timer,
)
from crypto_alert_v2.agents.research_harness_selection import (
    VERIFIED_SEARCH_TOOL_NAME,
    create_research_harness,
)
from crypto_alert_v2.domain.deep_research import (
    DeepResearchArtifact,
    DeepResearchReport,
    DeepResearchSearchCoverage,
    DeepResearchSearchErrorKind,
    DeepResearchSearchFailure,
    DeepResearchSearchProvider,
    MAX_RESEARCH_QUERIES,
    MAX_RESEARCH_SOURCES,
    ResearchHarnessMode,
    materialize_deep_research_artifact,
)
from crypto_alert_v2.domain.models import ModelExecutionAudit
from crypto_alert_v2.providers.model import as_chat_completions_model
from crypto_alert_v2.providers.search import (
    SearchEvidenceUnavailable,
    TavilySearchProvider,
    WebEvidence,
)

if TYPE_CHECKING:
    from crypto_alert_v2.graph.request import DeepResearchRequest


DEEP_RESEARCH_PROMPT_VERSION = "deep-research-v1"
MAX_SEARCH_QUERIES = 3
assert MAX_SEARCH_QUERIES == MAX_RESEARCH_QUERIES

_SEARCH_PROVIDERS: frozenset[str] = frozenset(
    {
        "builtin_web_search",
        "tavily",
        "ddgs_metasearch",
        "deep_research_search",
    }
)
_SEARCH_ERROR_KINDS: dict[str, DeepResearchSearchErrorKind] = {
    "APITimeoutError": "timeout",
    "TimeoutError": "timeout",
    "InternalServerError": "server_error",
    "RateLimitError": "rate_limited",
    "APIConnectionError": "connection_error",
    "UnverifiedServerToolCall": "unverified_server_tool_call",
    "MissingProviderCitation": "missing_provider_citation",
    "MissingVerifiedEvidence": "missing_verified_evidence",
    "InvalidProviderResponse": "invalid_provider_response",
    "InvalidProviderEvidence": "invalid_provider_response",
    "EmptyProviderResponse": "invalid_provider_response",
    "EmptyEvidence": "missing_verified_evidence",
}


class VerifiedEvidenceSearch(Protocol):
    def search(
        self,
        query: str,
        config: RunnableConfig | None = None,
    ) -> list[WebEvidence]: ...


class VerifiedSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    queries: list[str] = Field(
        min_length=1,
        max_length=MAX_SEARCH_QUERIES,
    )


@dataclass(frozen=True, slots=True)
class DeepResearchExecutionResult:
    artifact: DeepResearchArtifact
    evidence: tuple[WebEvidence, ...]
    model_audits: tuple[ModelExecutionAudit, ...]


class _VerifiedSourceLedger:
    def __init__(self, search: VerifiedEvidenceSearch) -> None:
        self._search = search
        self._evidence: list[WebEvidence] = []
        self._coverage: DeepResearchSearchCoverage | None = None
        self._tool_result: str | None = None
        self._seen: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    @property
    def evidence(self) -> tuple[WebEvidence, ...]:
        return tuple(self._evidence)

    @property
    def coverage(self) -> DeepResearchSearchCoverage:
        if self._coverage is None:
            raise RuntimeError("verified search has not completed successfully")
        return self._coverage

    async def collect(
        self,
        queries: Sequence[str],
        *,
        config: RunnableConfig | None,
    ) -> str:
        normalized_queries = list(
            dict.fromkeys(" ".join(query.split()) for query in queries)
        )
        if not 1 <= len(normalized_queries) <= MAX_SEARCH_QUERIES:
            raise ValueError(
                f"verified search requires 1 to {MAX_SEARCH_QUERIES} unique queries"
            )
        if any(not query or len(query) > 500 for query in normalized_queries):
            raise ValueError("verified search queries must contain 1 to 500 characters")

        async with self._lock:
            if self._tool_result is not None:
                return self._tool_result
            first_provider_failure: SearchEvidenceUnavailable | None = None
            first_missing_failure: SearchEvidenceUnavailable | None = None
            failures: list[DeepResearchSearchFailure] = []
            successful_result_sets: list[list[WebEvidence]] = []
            successful_queries = 0
            for query_index, query in enumerate(normalized_queries, start=1):
                try:
                    results = await _search_async(self._search, query, config=config)
                except SearchEvidenceUnavailable as exc:
                    first_provider_failure = first_provider_failure or exc
                    failures.append(
                        _query_failure_from_exception(
                            exc,
                            query_index=query_index,
                        )
                    )
                    continue
                if not results:
                    failure = SearchEvidenceUnavailable(
                        "verified search returned no evidence",
                        provider="deep_research_search",
                        retryable=True,
                        error_type="MissingVerifiedEvidence",
                    )
                    first_missing_failure = first_missing_failure or failure
                    failures.append(
                        _query_failure_from_exception(
                            failure,
                            query_index=query_index,
                        )
                    )
                    continue
                successful_queries += 1
                successful_result_sets.append(results)
            if successful_queries == 0:
                if first_provider_failure is not None:
                    raise first_provider_failure
                if first_missing_failure is not None:
                    raise first_missing_failure
                raise AssertionError("verified search completed without an outcome")

            result_offset = 0
            while len(self._evidence) < MAX_RESEARCH_SOURCES and any(
                result_offset < len(results) for results in successful_result_sets
            ):
                for results in successful_result_sets:
                    if (
                        result_offset >= len(results)
                        or len(self._evidence) >= MAX_RESEARCH_SOURCES
                    ):
                        continue
                    item = results[result_offset]
                    key = (str(item.final_url), item.content_hash)
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    self._evidence.append(item)
                result_offset += 1
            self._coverage = DeepResearchSearchCoverage(
                status="partial" if failures else "complete",
                attempted_queries=len(normalized_queries),
                successful_queries=successful_queries,
                failed_queries=failures,
            )
            safe_catalog = [
                {
                    "index": index,
                    "title": item.title,
                    "excerpt": item.excerpt,
                    "published_at": (
                        item.published_at.isoformat()
                        if item.published_at is not None
                        else None
                    ),
                }
                for index, item in enumerate(self._evidence, start=1)
            ]
            tool_result = {
                "sources": safe_catalog,
                "coverage": {
                    "status": self.coverage.status,
                    "attempted_queries": self.coverage.attempted_queries,
                    "successful_queries": self.coverage.successful_queries,
                    "failed_query_indexes": [
                        item.query_index for item in self.coverage.failed_queries
                    ],
                },
            }
            self._tool_result = json.dumps(
                tool_result,
                ensure_ascii=True,
                separators=(",", ":"),
            )
            return self._tool_result


def _query_failure_from_exception(
    exc: SearchEvidenceUnavailable,
    *,
    query_index: int,
) -> DeepResearchSearchFailure:
    attempt = getattr(exc, "attempt", None)
    if not (
        isinstance(attempt, int) and not isinstance(attempt, bool) and 1 <= attempt <= 3
    ):
        attempt = None
    raw_provider = getattr(exc, "provider", None)
    provider: DeepResearchSearchProvider = (
        raw_provider if raw_provider in _SEARCH_PROVIDERS else "search"
    )
    raw_error_type = getattr(exc, "error_type", None)
    error_kind = _SEARCH_ERROR_KINDS.get(raw_error_type, "provider_error")
    return DeepResearchSearchFailure(
        query_index=query_index,
        provider=provider,
        error_kind=error_kind,
        retryable=bool(getattr(exc, "retryable", False)),
        attempt=attempt,
    )


async def _search_async(
    search: VerifiedEvidenceSearch,
    query: str,
    *,
    config: RunnableConfig | None,
) -> list[WebEvidence]:
    if isinstance(search, TavilySearchProvider):
        return await search.asearch(query, config=config)
    return await asyncio.to_thread(search.search, query, config=config)


def _create_verified_search_tool(
    ledger: _VerifiedSourceLedger,
) -> BaseTool:
    async def verified_web_search(
        queries: list[str],
        config: RunnableConfig,
    ) -> str:
        return await ledger.collect(queries, config=config)

    return StructuredTool.from_function(
        coroutine=verified_web_search,
        name=VERIFIED_SEARCH_TOOL_NAME,
        description=(
            "Search one to three bounded cryptocurrency questions. Returns only "
            "application-assigned source indexes, titles, excerpts, and publication "
            "times. Call exactly once and cite only the returned indexes."
        ),
        args_schema=VerifiedSearchInput,
    )


class DeepResearchExecutor:
    def __init__(
        self,
        *,
        model: ChatOpenAI,
        search: VerifiedEvidenceSearch,
        harness_mode: ResearchHarnessMode,
    ) -> None:
        self._model = model
        self._search = search
        self._harness_mode = harness_mode

    async def execute(
        self,
        request: DeepResearchRequest,
        config: RunnableConfig | None = None,
    ) -> DeepResearchExecutionResult:
        ledger = _VerifiedSourceLedger(self._search)
        harness = create_research_harness(
            model=as_chat_completions_model(self._model),
            verified_search_tool=_create_verified_search_tool(ledger),
            mode=self._harness_mode,
        )
        started_at = start_model_timer()
        result = await harness.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Research request: {request.query_text}\n"
                            f"Asset: {request.symbol}\n"
                            f"Research horizon: {request.horizon}\n"
                            "Use only the verified-source-researcher and return the "
                            "typed report."
                        ),
                    }
                ]
            },
            config=config,
        )
        report = result.get("structured_response")
        if not isinstance(report, DeepResearchReport):
            raise TypeError("deep research harness did not return DeepResearchReport")
        model_audit = build_model_execution_audit(
            result,
            prompt_version=DEEP_RESEARCH_PROMPT_VERSION,
            started_at=started_at,
        )
        evidence = ledger.evidence
        artifact = materialize_deep_research_artifact(
            report=report,
            evidence=evidence,
            harness_mode=self._harness_mode,
            search_coverage=ledger.coverage,
            model_audits=(model_audit,),
        )
        return DeepResearchExecutionResult(
            artifact=artifact,
            evidence=evidence,
            model_audits=(model_audit,),
        )


__all__ = [
    "DEEP_RESEARCH_PROMPT_VERSION",
    "DeepResearchExecutionResult",
    "DeepResearchExecutor",
    "VerifiedEvidenceSearch",
]
