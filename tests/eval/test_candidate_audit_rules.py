from __future__ import annotations

from crypto_manual_alert.eval.judges.rules import RuleJudge
from crypto_manual_alert.eval.schema import EvalCase


def test_rule_judge_scores_candidate_audit_gate_and_switch_readiness():
    case = EvalCase(
        case_id="case-1",
        dataset_name="default",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00Z",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="candidate_gate",
        severity="high",
        expected_behavior="candidate gate should flag unsafe trigger",
        actual_behavior="trigger long",
        summary="candidate audit",
        status="open",
        frozen_input_hash="hash",
        input_summary={
            "trace": {"final_action": "trigger long", "allowed": True},
            "observed_output": {
                "parsed_plan": {"main_action": "trigger long", "manual_execution_required": True},
                "verdict": {"allowed": True},
            },
            "trace_summary": {"span_names": ["decision.final", "risk.check"]},
            "candidate_audit": {
                "gate_candidate": {
                    "passed": False,
                    "violations": [{"rule_id": "candidate.action_not_allowed"}],
                },
                "plan_semantic_candidate": {
                    "passed": False,
                    "violations": [{"rule_id": "plan_semantic.long_stop_not_below_entry"}],
                },
                "final_decision_switch_readiness": {
                    "ready": False,
                    "blocking_reasons": ["candidate_gate_failed"],
                },
            },
        },
        metadata={},
    )

    scores = RuleJudge().evaluate("eval-run", case)
    by_name = {score.judge_name: score for score in scores}

    assert by_name["rule.candidate_gate"].passed is False
    assert by_name["rule.candidate_gate"].severity == "high"
    assert by_name["rule.candidate_gate"].failure_category == "candidate_gate_failed"
    assert by_name["rule.plan_semantic_candidate"].passed is False
    assert by_name["rule.plan_semantic_candidate"].severity == "high"
    assert by_name["rule.plan_semantic_candidate"].failure_category == "plan_semantic_candidate_failed"
    assert by_name["rule.final_switch_readiness"].passed is True
    assert by_name["rule.final_switch_readiness"].metadata["blocking_reasons"] == ["candidate_gate_failed"]
