from __future__ import annotations

from typing import Any

from crypto_manual_alert.decision.pre_final_input_gate import evaluate_pre_final_input_gate


MISSING_POST_FINAL_GATES = [
    "decision_input_candidate",
    "replayable_input_candidate",
    "gate_candidate",
    "plan_semantic_candidate",
    "production_control_gate",
]


def build_pre_final_switch_readiness(pre_final_decision_input: dict[str, Any] | None) -> dict[str, Any]:
    """Build the pre-final switch audit envelope.

    This object only explains why the legacy final step must not switch to
    DecisionInput yet. It does not evaluate post-final candidate gates and must
    never mark the production final input as ready.
    """

    validation = pre_final_decision_input.get("validation") if isinstance(pre_final_decision_input, dict) else None
    validation_passed = isinstance(validation, dict) and validation.get("passed") is True
    has_pre_final_decision_input = isinstance(pre_final_decision_input, dict)
    input_gate = evaluate_pre_final_input_gate(pre_final_decision_input)
    input_gate_passed = input_gate.get("passed") is True

    reasons = ["candidate_audit_not_built_before_legacy_final"]
    if not validation_passed:
        reasons.append("pre_final_decision_input_invalid")
    if not input_gate_passed:
        reasons.append("pre_final_input_gate_failed")

    readiness: dict[str, Any] = {
        "ready": False,
        "stage": "pre_final",
        "decision_effect": "none",
        "blocking_reasons": reasons,
        "missing_post_final_gates": list(MISSING_POST_FINAL_GATES),
        "pre_final_checks": {
            "has_pre_final_decision_input": has_pre_final_decision_input,
            "pre_final_validation_passed": validation_passed,
            "pre_final_input_gate_passed": input_gate_passed,
        },
        "input_gate": input_gate,
    }
    if isinstance(pre_final_decision_input, dict):
        if pre_final_decision_input.get("input_ref") is not None:
            readiness["input_ref"] = pre_final_decision_input.get("input_ref")
        if pre_final_decision_input.get("input_hash") is not None:
            readiness["input_hash"] = pre_final_decision_input.get("input_hash")
    return readiness
