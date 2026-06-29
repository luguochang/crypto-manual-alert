from __future__ import annotations

from crypto_manual_alert.eval.schema import EvalCase, EvalScore

from .common import make_score, observed_result, parsed_plan


OPENING_ACTIONS = {
    "open long",
    "open short",
    "trigger long",
    "trigger short",
    "flip long to short",
    "flip short to long",
}
OPENING_ACTION_HINTS = ("open", "trigger", "flip", "buy", "sell", "market")
ALLOWED_ACTIONS = {
    "open long",
    "open short",
    "hold long",
    "hold short",
    "close long",
    "close short",
    "flip long to short",
    "flip short to long",
    "trigger long",
    "trigger short",
    "no trade",
}


class RuleJudge:
    """确定性 eval 规则集合，负责首版 hard gate。"""

    def evaluate(self, eval_run_id: str, case: EvalCase) -> list[EvalScore]:
        scores = [
            self._action_enum(eval_run_id, case),
            self._expected_no_trade(eval_run_id, case),
            self._opening_requirements(eval_run_id, case),
            self._required_spans(eval_run_id, case),
            self._manual_only(eval_run_id, case),
        ]
        return [score for score in scores if score is not None]

    def _action_enum(self, eval_run_id: str, case: EvalCase) -> EvalScore:
        plan = parsed_plan(case)
        action = str(plan.get("main_action") or case.input_summary.get("trace", {}).get("final_action") or "")
        passed = action in ALLOWED_ACTIONS
        return make_score(
            eval_run_id=eval_run_id,
            case=case,
            judge_name="rule.action_enum",
            judge_type="rule",
            passed=passed,
            severity="critical" if not passed else "low",
            failure_category="schema_action_invalid" if not passed else "none",
            reason_summary=(
                "main_action is in the allowed action enum."
                if passed
                else f"main_action is outside the allowed action enum: {action}"
            ),
            evidence_refs=["observed_output.parsed_plan.main_action", "trace.final_action"],
        )

    def _expected_no_trade(self, eval_run_id: str, case: EvalCase) -> EvalScore | None:
        expected = case.expected_behavior.lower()
        if "no trade" not in expected and "禁止" not in expected and "不得" not in expected:
            return None
        observed = observed_result(case)
        final_action = str(observed.get("final_action") or "")
        allowed = observed.get("allowed")
        passed = final_action == "no trade" or allowed is False
        return make_score(
            eval_run_id=eval_run_id,
            case=case,
            judge_name="rule.expected_no_trade",
            judge_type="rule",
            passed=passed,
            severity="high" if not passed else "low",
            failure_category="expected_no_trade_violation" if not passed else "none",
            reason_summary=(
                "期望数据不足时 no trade 或 risk blocked，历史输出符合该边界。"
                if passed
                else f"期望 no trade/risk blocked，但历史输出 final_action={final_action}, allowed={allowed}。"
            ),
            evidence_refs=["expected.behavior", "trace.final_action", "observed_output.verdict.allowed"],
        )

    def _required_spans(self, eval_run_id: str, case: EvalCase) -> EvalScore:
        span_names = set(case.input_summary.get("trace_summary", {}).get("span_names") or [])
        missing = [name for name in ("decision.final", "risk.check") if name not in span_names]
        passed = not missing
        return make_score(
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
        plan = parsed_plan(case)
        manual_required = plan.get("manual_execution_required")
        passed = manual_required is not False
        return make_score(
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

    def _opening_requirements(self, eval_run_id: str, case: EvalCase) -> EvalScore:
        plan = parsed_plan(case)
        action = str(plan.get("main_action") or case.input_summary.get("trace", {}).get("final_action") or "")
        if not is_opening_intent(action):
            return make_score(
                eval_run_id=eval_run_id,
                case=case,
                judge_name="rule.opening_requirements",
                judge_type="rule",
                passed=True,
                severity="low",
                failure_category="none",
                reason_summary="action is not an opening/flip trigger, so entry/stop/invalidation are not required.",
                evidence_refs=["observed_output.parsed_plan.main_action"],
            )
        missing = [name for name in ("entry_trigger", "stop_price", "invalidation") if plan.get(name) in {None, ""}]
        passed = not missing
        return make_score(
            eval_run_id=eval_run_id,
            case=case,
            judge_name="rule.opening_requirements",
            judge_type="rule",
            passed=passed,
            severity="critical" if not passed else "low",
            failure_category="unsafe_entry_stop_plan" if not passed else "none",
            reason_summary=(
                "opening action has entry_trigger, stop_price and invalidation."
                if passed
                else f"opening action is missing required fields: {', '.join(missing)}"
            ),
            evidence_refs=[
                "observed_output.parsed_plan.entry_trigger",
                "observed_output.parsed_plan.stop_price",
                "observed_output.parsed_plan.invalidation",
            ],
        )


def is_opening_intent(action: str) -> bool:
    """非枚举但包含 market/buy/sell/open 等词时，仍按开仓意图做安全检查。"""

    normalized = action.strip().lower()
    return normalized in OPENING_ACTIONS or any(hint in normalized for hint in OPENING_ACTION_HINTS)
