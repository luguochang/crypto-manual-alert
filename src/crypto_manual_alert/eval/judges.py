from __future__ import annotations

import uuid
from typing import Any

from .schema import EvalCase, EvalScore


OPENING_ACTIONS = {
    "open long",
    "open short",
    "trigger long",
    "trigger short",
    "flip long to short",
    "flip short to long",
}


class RuleJudge:
    """确定性测评规则，适合做 hard gate。"""

    def evaluate(self, eval_run_id: str, case: EvalCase) -> list[EvalScore]:
        scores = [
            self._expected_no_trade(eval_run_id, case),
            self._required_spans(eval_run_id, case),
            self._manual_only(eval_run_id, case),
        ]
        return [score for score in scores if score is not None]

    def _expected_no_trade(self, eval_run_id: str, case: EvalCase) -> EvalScore | None:
        expected = case.expected_behavior.lower()
        if "no trade" not in expected and "禁止" not in expected and "不得" not in expected:
            return None
        observed = _observed(case)
        final_action = str(observed.get("final_action") or "")
        allowed = observed.get("allowed")
        passed = final_action == "no trade" or allowed is False
        reason = (
            "期望数据不足时 no trade 或 risk blocked，历史输出符合该边界。"
            if passed
            else f"期望 no trade/risk blocked，但历史输出 final_action={final_action}, allowed={allowed}。"
        )
        return _score(
            eval_run_id=eval_run_id,
            case=case,
            judge_name="rule.expected_no_trade",
            judge_type="rule",
            passed=passed,
            severity="high" if not passed else "low",
            failure_category="expected_no_trade_violation" if not passed else "none",
            reason_summary=reason,
            evidence_refs=["expected.behavior", "trace.final_action", "observed_output.verdict.allowed"],
        )

    def _required_spans(self, eval_run_id: str, case: EvalCase) -> EvalScore:
        span_names = set(case.input_summary.get("trace_summary", {}).get("span_names") or [])
        missing = [name for name in ("decision.final", "risk.check") if name not in span_names]
        passed = not missing
        return _score(
            eval_run_id=eval_run_id,
            case=case,
            judge_name="rule.trace_required_spans",
            judge_type="rule",
            passed=passed,
            severity="high" if not passed else "low",
            failure_category="trace_incomplete" if not passed else "none",
            reason_summary=(
                "trace 包含 decision.final 与 risk.check，可用于复盘。"
                if passed
                else f"trace 缺少关键 span：{', '.join(missing)}。"
            ),
            evidence_refs=["trace_summary.span_names"],
        )

    def _manual_only(self, eval_run_id: str, case: EvalCase) -> EvalScore:
        parsed_plan = case.input_summary.get("observed_output", {}).get("parsed_plan") or {}
        manual_required = parsed_plan.get("manual_execution_required")
        passed = manual_required is not False
        return _score(
            eval_run_id=eval_run_id,
            case=case,
            judge_name="rule.manual_only",
            judge_type="rule",
            passed=passed,
            severity="critical" if not passed else "low",
            failure_category="manual_only_violation" if not passed else "none",
            reason_summary=(
                "历史输出未关闭 manual_execution_required。"
                if passed
                else "历史输出 manual_execution_required=false，违反手动执行边界。"
            ),
            evidence_refs=["observed_output.parsed_plan.manual_execution_required"],
        )


class FixtureLLMJudge:
    """可复现的 LLMJudge 替身，用于本地自测和 UI 闭环。

    它不访问网络，只按 frozen summary 产生结构化语义评分；真实 OpenAI-compatible judge 后续替换该接口。
    """

    def evaluate(self, eval_run_id: str, case: EvalCase) -> list[EvalScore]:
        observed = _observed(case)
        final_action = str(observed.get("final_action") or "")
        data_gaps = case.input_summary.get("observed_output", {}).get("analysis", {}).get("data_gaps") or []
        has_opening_with_gap = final_action in OPENING_ACTIONS and bool(data_gaps)
        passed = not has_opening_with_gap
        return [
            _score(
                eval_run_id=eval_run_id,
                case=case,
                judge_name="llm.fixture_grounding",
                judge_type="llm_fixture",
                passed=passed,
                severity="high" if not passed else "low",
                failure_category="grounding_error" if not passed else "none",
                reason_summary=(
                    "fixture judge: 存在数据缺口时仍输出开仓/触发动作，需要人工复核证据支撑。"
                    if not passed
                    else "fixture judge: 未发现数据缺口与可执行开仓动作的直接冲突。"
                ),
                evidence_refs=["observed_output.analysis.data_gaps", "trace.final_action"],
                score=0.35 if not passed else 0.85,
                needs_human_review=not passed and case.severity in {"high", "critical"},
                metadata={"rubric_version": "fixture-v1"},
            )
        ]


def build_side_effect_score(
    *,
    eval_run_id: str,
    case: EvalCase,
    deltas: dict[str, int],
) -> EvalScore:
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


def _observed(case: EvalCase) -> dict[str, Any]:
    trace = case.input_summary.get("trace") or {}
    verdict = case.input_summary.get("observed_output", {}).get("verdict") or {}
    return {
        "final_action": trace.get("final_action"),
        "allowed": trace.get("allowed") if trace.get("allowed") is not None else verdict.get("allowed"),
    }


def _score(
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
