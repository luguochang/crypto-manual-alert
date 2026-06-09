from __future__ import annotations

import time
from collections.abc import Callable

from .._shared import build_constraints, build_skill_result
from ..contracts import ALLOWED_FACTOR_TYPES, EvidenceCandidate, SkillTaskContext, SkillToolResult, safe_evidence_text
from .providers import RootCauseProvider, RootCauseSearchRequest


class RootCauseSearchSkill:
    skill_name = "root_cause_search"

    def __init__(
        self,
        *,
        provider: RootCauseProvider | None = None,
        max_branch_count: int = 2,
        max_expansion_calls: int = 8,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_branch_count < 1:
            raise ValueError("max_branch_count must be positive")
        if max_expansion_calls < 1:
            raise ValueError("max_expansion_calls must be positive")
        self.provider = provider
        self.max_branch_count = max_branch_count
        self.max_expansion_calls = max_expansion_calls
        self.clock = clock

    def run(self, context: SkillTaskContext) -> SkillToolResult:
        return build_skill_result(
            context,
            skill_name=self.skill_name,
            result_type="root_cause_factor_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            evidence_candidates=self._recursive_evidence(context),
            constraints=build_constraints(
                context,
                recursive_factor_search=True,
                allowed_factor_types=ALLOWED_FACTOR_TYPES,
            ),
        )

    def _recursive_evidence(self, context: SkillTaskContext) -> tuple[EvidenceCandidate, ...]:
        if self.provider is None:
            return ()

        evidence: list[EvidenceCandidate] = []
        queue: list[tuple[str, int]] = [(context.query, 1)]
        seen_queries = {context.query}
        deadline_at = self.clock() + float(context.timeout_seconds)
        expansion_calls = 0

        while queue:
            if self.clock() > deadline_at or expansion_calls >= self.max_expansion_calls:
                break
            query, depth = queue.pop(0)
            remaining_budget = self.max_expansion_calls - expansion_calls
            request = RootCauseSearchRequest(
                symbol=context.symbol,
                query=query,
                trace_id=context.trace_id,
                task_id=context.task_id,
                depth=depth,
                max_branch_count=self.max_branch_count,
                deadline_at=deadline_at,
                remaining_budget=remaining_budget,
            )
            expansion_calls += 1
            for factor in self.provider.expand(request)[: self.max_branch_count]:
                factor_type = str(factor.get("factor_type") or "")
                if factor_type not in ALLOWED_FACTOR_TYPES:
                    continue

                title = safe_evidence_text(f"depth {depth} {factor_type}: {factor.get('title') or ''}")
                evidence.append(
                    EvidenceCandidate(
                        title=title,
                        url=safe_evidence_text(factor.get("url")),
                        snippet_ref=safe_evidence_text(factor.get("snippet_ref")),
                        source_type="search_derived",
                    )
                )

                next_query = safe_evidence_text(factor.get("query") or factor.get("title"))
                if depth < context.max_depth and next_query and next_query not in seen_queries:
                    seen_queries.add(next_query)
                    queue.append((next_query, depth + 1))

        return tuple(evidence)
