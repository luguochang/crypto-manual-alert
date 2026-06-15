from __future__ import annotations

from crypto_manual_alert.decision.plan_semantic_candidate import evaluate_plan_semantic_candidate


def test_plan_semantic_candidate_flags_long_plan_with_stop_above_entry_and_targets_out_of_order():
    result = evaluate_plan_semantic_candidate(
        legacy_plan={
            "main_action": "trigger long",
            "entry_trigger": 3500,
            "stop_price": 3510,
            "target_1": 3490,
            "target_2": 3480,
            "invalidation": "invalid below support",
        }
    )

    public = result.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["passed"] is False
    assert public["severity"] == "hard_fail"
    assert {violation["rule_id"] for violation in public["violations"]} == {
        "plan_semantic.long_stop_not_below_entry",
        "plan_semantic.long_target_not_above_entry",
        "plan_semantic.long_target_order_invalid",
    }
    assert public["checked_fields"] == ["main_action", "entry_trigger", "stop_price", "target_1", "target_2"]


def test_plan_semantic_candidate_passes_non_opening_action_without_entry_stop_targets():
    result = evaluate_plan_semantic_candidate(
        legacy_plan={
            "main_action": "no trade",
            "entry_trigger": None,
            "stop_price": None,
            "target_1": None,
            "target_2": None,
        }
    )

    public = result.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["passed"] is True
    assert public["severity"] == "ok"
    assert public["violations"] == []


def test_plan_semantic_candidate_flags_opening_plan_missing_required_execution_fields():
    result = evaluate_plan_semantic_candidate(
        legacy_plan={
            "main_action": "trigger long",
            "entry_trigger": None,
            "stop_price": None,
            "target_1": None,
            "target_2": None,
            "invalidation": "",
        }
    )

    public = result.to_public_dict()

    assert public["passed"] is False
    assert {violation["rule_id"] for violation in public["violations"]} == {
        "plan_semantic.opening_entry_required",
        "plan_semantic.opening_stop_required",
        "plan_semantic.opening_target_required",
        "plan_semantic.opening_invalidation_required",
    }
