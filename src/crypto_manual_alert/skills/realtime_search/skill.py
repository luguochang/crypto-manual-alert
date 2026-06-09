from __future__ import annotations

from .._shared import build_constraints, build_skill_result, context_search_results, sanitize_search_results
from ..contracts import SkillTaskContext, SkillToolResult
from .providers import SearchProvider, SearchProviderRequest


class RealtimeSearchSkill:
    skill_name = "realtime_search"

    def __init__(self, *, provider: SearchProvider | None = None, max_results: int = 5) -> None:
        self.provider = provider
        self.max_results = max_results

    def run(self, context: SkillTaskContext) -> SkillToolResult:
        return build_skill_result(
            context,
            skill_name=self.skill_name,
            result_type="evidence_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            evidence_candidates=sanitize_search_results(self._search_results(context)),
            constraints=build_constraints(context, raw_snippets_redacted=True),
        )

    def _search_results(self, context: SkillTaskContext) -> list[dict[str, str]]:
        if self.provider is None:
            return context_search_results(context)
        return self.provider.search(
            SearchProviderRequest(
                symbol=context.symbol,
                query=context.query,
                trace_id=context.trace_id,
                task_id=context.task_id,
                max_results=self.max_results,
            )
        )
