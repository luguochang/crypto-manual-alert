from __future__ import annotations

from typing import Any, Protocol

from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.research_pipeline.models import ResearchAudit, ResearchPlan, ResearchQuery, SearchResult


class ResearchPlanner(Protocol):
    def plan(self, snapshot: MarketSnapshot, skill_context: dict[str, Any] | None = None) -> ResearchPlan:
        """Build web-search tasks for missing market facts."""


class SearchAdapter(Protocol):
    def search(self, query: ResearchQuery) -> list[SearchResult]:
        """Run one controlled search query."""


class LeaderResearchSynthesizer(Protocol):
    def synthesize(self, snapshot: MarketSnapshot, audit: ResearchAudit) -> ResearchAudit:
        """Summarize parallel research and adversarial review."""
