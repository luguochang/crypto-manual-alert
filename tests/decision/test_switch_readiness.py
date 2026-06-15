from __future__ import annotations

from crypto_manual_alert.decision.switch_readiness import evaluate_final_decision_switch_readiness


def test_switch_readiness_blocks_when_candidate_gate_or_worker_coverage_is_incomplete():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "lead_synthesis": {
                "included_contribution_ids": ["c-root"],
                "dropped_contributions": [
                    {
                        "contribution_id": None,
                        "agent_name": "ExecutionRiskAgent",
                        "reason": "missing_required_contribution",
                    }
                ],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 3,
            },
        },
        gate_candidate={
            "passed": False,
            "violations": [{"rule_id": "candidate.action_not_allowed"}],
        },
        plan_semantic_candidate={"passed": True, "violations": []},
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    public = result.to_public_dict()

    assert public["ready"] is False
    assert public["decision_effect"] == "none"
    assert set(public["blocking_reasons"]) == {
        "candidate_gate_failed",
        "required_worker_missing_or_failed",
        "worker_artifact_coverage_incomplete",
    }
    assert public["required_shadow_worker_count"] == 7


def test_switch_readiness_passes_only_when_candidate_audits_are_complete():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "lead_synthesis": {
                "included_contribution_ids": [
                    "c-live",
                    "c-derivatives",
                    "c-macro",
                    "c-root",
                    "c-sentiment",
                    "c-quality",
                    "c-risk",
                ],
                "dropped_contributions": [],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 7,
            },
        },
        gate_candidate={"passed": True, "violations": []},
        plan_semantic_candidate={"passed": True, "violations": []},
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    public = result.to_public_dict()

    assert public["ready"] is True
    assert public["decision_effect"] == "none"
    assert public["blocking_reasons"] == []


def test_switch_readiness_blocks_when_plan_semantic_candidate_fails():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "lead_synthesis": {
                "included_contribution_ids": [
                    "c-live",
                    "c-derivatives",
                    "c-macro",
                    "c-root",
                    "c-sentiment",
                    "c-quality",
                    "c-risk",
                ],
                "dropped_contributions": [],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 7,
            },
        },
        gate_candidate={"passed": True, "violations": []},
        plan_semantic_candidate={
            "passed": False,
            "violations": [{"rule_id": "plan_semantic.long_stop_not_below_entry"}],
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    public = result.to_public_dict()

    assert public["ready"] is False
    assert public["blocking_reasons"] == ["plan_semantic_candidate_failed"]


def test_switch_readiness_blocks_when_shadow_swarm_harness_fails():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "lead_synthesis": {
                "included_contribution_ids": [
                    "c-live",
                    "c-derivatives",
                    "c-macro",
                    "c-root",
                    "c-sentiment",
                    "c-quality",
                    "c-risk",
                ],
                "dropped_contributions": [],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 7,
            },
        },
        gate_candidate={"passed": True, "violations": []},
        plan_semantic_candidate={"passed": True, "violations": []},
        shadow_swarm_audit={
            "harness_validation": {
                "passed": False,
                "violations": [{"rule_id": "agent.non_final.executable_fields"}],
            }
        },
    )

    public = result.to_public_dict()

    assert public["ready"] is False
    assert public["blocking_reasons"] == ["shadow_swarm_harness_failed"]


def test_switch_readiness_does_not_block_for_optional_worker_drop():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "contribution_refs": [
                {
                    "contribution_id": "optional-failed",
                    "agent_name": "ScenarioForkAgent",
                    "required": False,
                }
            ],
            "lead_synthesis": {
                "included_contribution_ids": [
                    "c-live",
                    "c-derivatives",
                    "c-macro",
                    "c-root",
                    "c-sentiment",
                    "c-quality",
                    "c-risk",
                ],
                "dropped_contributions": [
                    {
                        "contribution_id": "optional-failed",
                        "agent_name": "ScenarioForkAgent",
                        "reason": "status=failed",
                    }
                ],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 7,
            },
        },
        gate_candidate={"passed": True, "violations": []},
        plan_semantic_candidate={"passed": True, "violations": []},
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    public = result.to_public_dict()

    assert public["ready"] is True
    assert public["blocking_reasons"] == []


def test_switch_readiness_blocks_required_drop_even_when_contribution_refs_are_missing():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "contribution_refs": [],
            "lead_synthesis": {
                "included_contribution_ids": [],
                "dropped_contributions": [
                    {
                        "contribution_id": "quality-failed",
                        "agent_name": "DataQualityAgent",
                        "reason": "status=failed",
                        "required": True,
                        "failure_policy_applied": "hard_block",
                    }
                ],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 7,
            },
        },
        gate_candidate={"passed": True, "violations": []},
        plan_semantic_candidate={"passed": True, "violations": []},
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    public = result.to_public_dict()

    assert public["ready"] is False
    assert public["blocking_reasons"] == ["required_worker_missing_or_failed"]


def test_switch_readiness_blocks_execution_risk_hard_block_drop():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "contribution_refs": [
                {
                    "contribution_id": "risk-failed",
                    "agent_name": "ExecutionRiskAgent",
                    "required": True,
                }
            ],
            "lead_synthesis": {
                "included_contribution_ids": ["c-live", "c-derivatives", "c-root", "c-sentiment", "c-quality"],
                "dropped_contributions": [
                    {
                        "contribution_id": "risk-failed",
                        "agent_name": "ExecutionRiskAgent",
                        "reason": "status=failed",
                        "required": True,
                        "failure_policy_applied": "hard_block",
                    }
                ],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 7,
            },
        },
        gate_candidate={"passed": True, "violations": []},
        plan_semantic_candidate={"passed": True, "violations": []},
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    public = result.to_public_dict()

    assert public["ready"] is False
    assert public["blocking_reasons"] == ["required_worker_missing_or_failed"]


def test_switch_readiness_blocks_worker_hard_block_constraint():
    result = evaluate_final_decision_switch_readiness(
        decision_input_candidate={
            "validation": {"passed": True},
            "contribution_refs": [
                {
                    "contribution_id": "risk-hard-block",
                    "agent_name": "ExecutionRiskAgent",
                    "required": True,
                    "hard_block": True,
                    "hard_block_reasons": ["facts_gate:execution_facts_missing"],
                }
            ],
            "lead_synthesis": {
                "included_contribution_ids": [
                    "c-live",
                    "c-derivatives",
                    "c-macro",
                    "c-root",
                    "c-sentiment",
                    "c-quality",
                    "risk-hard-block",
                ],
                "dropped_contributions": [],
            },
        },
        replayable_input_candidate={
            "validation": {"passed": True},
            "coverage": {
                "has_legacy_frozen_input": True,
                "has_decision_input_candidate": True,
                "worker_artifact_count": 7,
            },
        },
        gate_candidate={"passed": True, "violations": []},
        plan_semantic_candidate={"passed": True, "violations": []},
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    public = result.to_public_dict()

    assert public["ready"] is False
    assert public["blocking_reasons"] == ["worker_hard_block"]
