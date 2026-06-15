from __future__ import annotations

from copy import deepcopy

from crypto_manual_alert.decision.decision_input_policy import REQUIRED_SHADOW_WORKER_AGENTS
from crypto_manual_alert.decision.pre_final_switch_readiness import build_pre_final_switch_readiness


def test_pre_final_switch_readiness_is_a_structured_audit_envelope():
    payload = _complete_pre_final_input()

    readiness = build_pre_final_switch_readiness(payload)

    assert readiness == {
        "ready": False,
        "stage": "pre_final",
        "decision_effect": "none",
        "blocking_reasons": ["candidate_audit_not_built_before_legacy_final"],
        "missing_post_final_gates": [
            "decision_input_candidate",
            "replayable_input_candidate",
            "gate_candidate",
            "plan_semantic_candidate",
            "production_control_gate",
        ],
        "pre_final_checks": {
            "has_pre_final_decision_input": True,
            "pre_final_validation_passed": True,
            "pre_final_input_gate_passed": True,
        },
        "input_gate": {
            "passed": True,
            "severity": "ok",
            "decision_effect": "none",
            "violations": [],
            "checks": {
                "schema_version": 1,
                "mode": "pre_final_candidate",
                "required_worker_ref_count": 7,
                "validation_passed": True,
                "side_effect_safe": True,
            },
        },
        "input_ref": "trace:trace-1:pre_final_decision_input",
        "input_hash": "sha256:pre-final",
    }


def test_pre_final_switch_readiness_keeps_invalid_pre_final_input_blocked():
    readiness = build_pre_final_switch_readiness(
        {
            "input_ref": "trace:trace-1:pre_final_decision_input",
            "input_hash": "sha256:pre-final",
            "decision_effect": "none",
            "validation": {"passed": False, "violations": [{"rule_id": "missing_required_worker"}]},
        }
    )

    assert readiness["ready"] is False
    assert readiness["decision_effect"] == "none"
    assert readiness["stage"] == "pre_final"
    assert readiness["blocking_reasons"] == [
        "candidate_audit_not_built_before_legacy_final",
        "pre_final_decision_input_invalid",
        "pre_final_input_gate_failed",
    ]
    assert readiness["pre_final_checks"] == {
        "has_pre_final_decision_input": True,
        "pre_final_validation_passed": False,
        "pre_final_input_gate_passed": False,
    }
    assert readiness["input_gate"]["passed"] is False


def test_pre_final_switch_readiness_handles_missing_pre_final_input_without_refs():
    readiness = build_pre_final_switch_readiness(None)

    assert readiness["ready"] is False
    assert readiness["stage"] == "pre_final"
    assert readiness["decision_effect"] == "none"
    assert readiness["blocking_reasons"] == [
        "candidate_audit_not_built_before_legacy_final",
        "pre_final_decision_input_invalid",
        "pre_final_input_gate_failed",
    ]
    assert readiness["pre_final_checks"] == {
        "has_pre_final_decision_input": False,
        "pre_final_validation_passed": False,
        "pre_final_input_gate_passed": False,
    }
    assert readiness["input_gate"]["passed"] is False
    assert "input_ref" not in readiness
    assert "input_hash" not in readiness


def _complete_pre_final_input() -> dict[str, object]:
    contribution_refs = [
        {
            "contribution_id": f"shadow_swarm:shadow:{agent_name}",
            "agent_name": agent_name,
            "task_id": f"shadow:{agent_name}",
            "status": "ok",
            "required": True,
            "input_ref": "trace:trace-1:shadow_swarm_input",
            "output_hash": f"sha256:{agent_name}",
            "trace_ref": f"trace-1:shadow:{agent_name}",
            "evidence_ids": [f"ev:{agent_name}"],
            "confidence_cap": None,
            "confidence_cap_reasons": [],
            "blocked_actions": [],
            "hard_block": False,
            "hard_block_reasons": [],
            "manual_review_reminders": [],
            "allowed_action_class_reduction": {},
            "required_confirmations": [],
        }
        for agent_name in REQUIRED_SHADOW_WORKER_AGENTS
    ]
    return deepcopy(
        {
            "schema_version": 1,
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "trace_id": "trace-1",
            "symbol": "ETH-USDT-SWAP",
            "input_ref": "trace:trace-1:pre_final_decision_input",
            "input_hash": "sha256:pre-final",
            "evidence_refs": [],
            "facts_gate": {"passed": True, "severity": "ok"},
            "contribution_refs": contribution_refs,
            "lead_synthesis": {
                "decision_effect": "none",
                "included_contribution_ids": [ref["contribution_id"] for ref in contribution_refs],
                "dropped_contributions": [],
            },
            "effective_allowed_actions": ["no trade"],
            "blocked_actions": [],
            "execution_mode": "executable",
            "confidence_policy": {"max_probability": None, "cap_reasons": [], "cap_applied_by_gate": False},
            "missing_facts": [],
            "conflicts": [],
            "validation": {"passed": True, "severity": "ok", "violations": []},
        }
    )
