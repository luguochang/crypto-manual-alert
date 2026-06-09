from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .contracts import EvidenceCandidate, SkillConstraints, SkillTaskContext, SkillToolResult, safe_evidence_text


def build_skill_result(
    context: SkillTaskContext,
    *,
    skill_name: str,
    result_type: str,
    source_type: str,
    can_satisfy_execution_fact: bool,
    evidence_candidates: Sequence[EvidenceCandidate] | None = None,
    fact_refs: dict[str, str] | None = None,
    constraints: SkillConstraints,
) -> SkillToolResult:
    return SkillToolResult(
        skill_name=skill_name,
        task_id=context.task_id,
        status="ok",
        result_type=result_type,
        source_type=source_type,
        can_satisfy_execution_fact=can_satisfy_execution_fact,
        evidence_candidates=evidence_candidates or (),
        fact_refs=fact_refs,
        constraints=constraints,
        missing_inputs=missing_inputs(context),
        trace_ref=context.trace_ref,
    )


def build_constraints(context: SkillTaskContext, **kwargs: Any) -> SkillConstraints:
    return SkillConstraints(max_depth=context.max_depth, timeout_seconds=context.timeout_seconds, **kwargs)


def sanitize_search_results(results: list[dict[str, Any]]) -> tuple[EvidenceCandidate, ...]:
    sanitized: list[EvidenceCandidate] = []
    for item in results:
        sanitized.append(
            EvidenceCandidate(
                title=safe_evidence_text(item.get("title")),
                url=safe_evidence_text(item.get("url")),
                snippet_ref=safe_evidence_text(item.get("snippet_ref")),
                source_type="search_derived",
            )
        )
    return tuple(sanitized)


def context_search_results(context: SkillTaskContext) -> list[dict[str, Any]]:
    results = context.input_view.get("search_results", [])
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


def missing_inputs(context: SkillTaskContext) -> tuple[str, ...]:
    missing: list[str] = []
    if not context.symbol:
        missing.append("symbol")
    if not context.query:
        missing.append("query")
    return tuple(missing)
