from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crypto_manual_alert.research_pipeline.redaction import redact_snippets_for_prompt


@dataclass(frozen=True)
class ResearchQuery:
    name: str
    query: str
    purpose: str
    required: bool = True


@dataclass(frozen=True)
class ResearchPlan:
    queries: list[ResearchQuery]
    reason: str
    planner: str = "static"

    def to_public_dict(self) -> dict[str, Any]:
        return {"planner": self.planner, "reason": self.reason, "queries": [query.__dict__ for query in self.queries]}


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "search-derived"

    def to_public_dict(self) -> dict[str, Any]:
        return self.__dict__

    def to_prompt_dict(self, *, snippet_ref: str) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "snippet_ref": snippet_ref,
        }


@dataclass(frozen=True)
class ResearchAudit:
    plan: ResearchPlan
    results: dict[str, list[SearchResult]] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)
    leader_summary: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_public_dict(),
            "results": {name: [result.to_public_dict() for result in results] for name, results in self.results.items()},
            "unavailable": list(self.unavailable),
            "leader_summary": self.leader_summary,
        }

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_public_dict(),
            "results": {
                name: [
                    result.to_prompt_dict(snippet_ref=f"research.results.{name}[{index}].snippet_redacted")
                    for index, result in enumerate(results)
                ]
                for name, results in self.results.items()
            },
            "unavailable": list(self.unavailable),
            "leader_summary": redact_snippets_for_prompt(self.leader_summary, path="research.leader_summary"),
        }
