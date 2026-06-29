from __future__ import annotations

import uuid
from typing import Any

from crypto_manual_alert.eval.schema import EvalCase, EvalScore


def parsed_plan(case: EvalCase) -> dict[str, Any]:
    parsed = case.input_summary.get("observed_output", {}).get("parsed_plan")
    return parsed if isinstance(parsed, dict) else {}


def observed_result(case: EvalCase) -> dict[str, Any]:
    trace = case.input_summary.get("trace") or {}
    verdict = case.input_summary.get("observed_output", {}).get("verdict") or {}
    return {
        "final_action": trace.get("final_action"),
        "allowed": trace.get("allowed") if trace.get("allowed") is not None else verdict.get("allowed"),
    }


def make_score(
    *,
    eval_run_id: str,
    case: EvalCase,
    judge_name: str,
    judge_type: str,
    passed: bool,
    severity: str,
    failure_category: str,
    reason_summary: str,
    evidence_refs: list[str],
    score: float | None = None,
    needs_human_review: bool = False,
    metadata: dict[str, Any] | None = None,
) -> EvalScore:
    return EvalScore(
        score_id=uuid.uuid4().hex,
        eval_run_id=eval_run_id,
        case_id=case.case_id,
        source_trace_id=case.source_trace_id,
        source_badcase_id=case.source_badcase_id,
        judge_name=judge_name,
        judge_type=judge_type,
        score=score,
        passed=passed,
        severity=severity,
        failure_category=failure_category,
        reason_summary=reason_summary,
        evidence_refs=evidence_refs,
        needs_human_review=needs_human_review,
        metadata=metadata or {},
    )
