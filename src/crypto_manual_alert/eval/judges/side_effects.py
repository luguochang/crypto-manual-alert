from __future__ import annotations

import uuid

from crypto_manual_alert.eval.schema import EvalCase, EvalScore


def build_side_effect_score(
    *,
    eval_run_id: str,
    case: EvalCase,
    deltas: dict[str, int],
) -> EvalScore:
    """验证 eval 期间没有写生产表或触发通知副作用。"""

    passed = all(value == 0 for value in deltas.values())
    return EvalScore(
        score_id=uuid.uuid4().hex,
        eval_run_id=eval_run_id,
        case_id=case.case_id,
        source_trace_id=case.source_trace_id,
        source_badcase_id=case.source_badcase_id,
        judge_name="eval.side_effect_guard",
        judge_type="rule",
        score=1.0 if passed else 0.0,
        passed=passed,
        severity="critical" if not passed else "low",
        failure_category="eval_side_effect_violation" if not passed else "none",
        reason_summary=(
            "eval run 未新增生产 plan_runs、notifications、manual_outcomes。"
            if passed
            else f"eval run 发生生产副作用：{deltas}"
        ),
        evidence_refs=["prod_table_deltas"],
        needs_human_review=not passed,
        metadata={"prod_table_deltas": deltas},
    )
