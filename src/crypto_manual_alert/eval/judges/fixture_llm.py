from __future__ import annotations

from crypto_manual_alert.eval.schema import EvalCase, EvalScore

from .common import make_score, observed_result
from .rules import OPENING_ACTIONS


class FixtureLLMJudge:
    """可复现的 LLMJudge 替身，用于本地自测和 UI 闭环。"""

    def evaluate(self, eval_run_id: str, case: EvalCase) -> list[EvalScore]:
        observed = observed_result(case)
        final_action = str(observed.get("final_action") or "")
        data_gaps = case.input_summary.get("observed_output", {}).get("analysis", {}).get("data_gaps") or []
        has_opening_with_gap = final_action in OPENING_ACTIONS and bool(data_gaps)
        passed = not has_opening_with_gap
        return [
            make_score(
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
