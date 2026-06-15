from __future__ import annotations

from crypto_manual_alert.decision.gate_candidate import evaluate_gate_candidate


def test_gate_candidate_flags_legacy_action_outside_effective_allowed_actions_and_confidence_cap():
    result = evaluate_gate_candidate(
        decision_input_candidate={
            "effective_allowed_actions": ["hold long", "hold short", "no trade"],
            "confidence_policy": {
                "max_probability": 0.58,
                "cap_applied_by_gate": True,
                "cap_reasons": ["facts_gate:execution_facts_missing"],
            },
            "missing_facts": ["mark", "index", "order_book"],
        },
        legacy_plan={"main_action": "trigger long", "probability": 0.67},
    )

    public = result.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["passed"] is False
    assert public["severity"] == "hard_fail"
    assert {violation["rule_id"] for violation in public["violations"]} == {
        "candidate.action_not_allowed",
        "candidate.confidence_cap_exceeded",
    }
    assert public["blocked_actions"] == ["trigger long"]
    assert public["missing_facts"] == ["mark", "index", "order_book"]


def test_gate_candidate_passes_when_legacy_action_is_allowed_and_probability_within_cap():
    result = evaluate_gate_candidate(
        decision_input_candidate={
            "effective_allowed_actions": ["hold long", "no trade"],
            "confidence_policy": {"max_probability": 0.58, "cap_applied_by_gate": True},
            "missing_facts": [],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
    )

    public = result.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["passed"] is True
    assert public["severity"] == "ok"
    assert public["violations"] == []
