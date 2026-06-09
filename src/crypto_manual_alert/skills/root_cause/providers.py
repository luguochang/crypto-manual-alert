from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from crypto_manual_alert.skills.realtime_search.providers import SearchProvider, SearchProviderRequest


@dataclass(frozen=True)
class RootCauseSearchRequest:
    symbol: str
    query: str
    trace_id: str
    task_id: str
    depth: int
    max_branch_count: int
    deadline_at: float | None = field(default=None, compare=False)
    remaining_budget: int | None = field(default=None, compare=False)


class RootCauseProvider(Protocol):
    def expand(self, request: RootCauseSearchRequest) -> list[dict[str, str]]:
        """Return redacted factor candidates for one root-cause expansion step."""


@dataclass(frozen=True)
class FixtureRootCauseProvider:
    def expand(self, request: RootCauseSearchRequest) -> list[dict[str, str]]:
        factor_type = "macro_event" if request.depth == 1 else "flow"
        return [
            {
                "factor_type": factor_type,
                "title": f"fixture {factor_type}: {request.query}",
                "query": f"fixture child factor for {request.query}",
                "url": f"fixture://root_cause/{request.symbol}/{request.depth}",
                "snippet_ref": f"fixture.root_cause.depth{request.depth}[0].snippet_redacted",
            }
        ]


@dataclass(frozen=True)
class RealtimeBackedRootCauseProvider:
    search_provider: SearchProvider
    factor_type: str = "flow"

    def expand(self, request: RootCauseSearchRequest) -> list[dict[str, str]]:
        results = self.search_provider.search(
            SearchProviderRequest(
                symbol=request.symbol,
                query=request.query,
                trace_id=request.trace_id,
                task_id=request.task_id,
                max_results=request.max_branch_count,
            )
        )
        factors: list[dict[str, str]] = []
        for item in results[: request.max_branch_count]:
            title = str(item.get("title") or "")
            factors.append(
                {
                    "factor_type": self.factor_type,
                    "title": title,
                    "query": title,
                    "url": str(item.get("url") or ""),
                    "snippet_ref": str(item.get("snippet_ref") or ""),
                }
            )
        return factors
