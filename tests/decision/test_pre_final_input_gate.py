from __future__ import annotations

from copy import deepcopy

from crypto_manual_alert.decision.decision_input_policy import REQUIRED_SHADOW_WORKER_AGENTS
from crypto_manual_alert.decision.pre_final_input_gate import evaluate_pre_final_input_gate
from crypto_manual_alert.decision.pre_final_switch_readiness import build_pre_final_switch_readiness


def test_pre_final_input_gate_accepts_minimum_candidate_schema_without_enabling_switch():
    payload = _complete_pre_final_input()

    gate = evaluate_pre_final_input_gate(payload)

    assert gate == {
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
    }

    readiness = build_pre_final_switch_readiness(payload)

    assert readiness["ready"] is False
    assert readiness["decision_effect"] == "none"
    assert readiness["pre_final_checks"]["pre_final_input_gate_passed"] is True
    assert readiness["input_gate"] == gate


def test_pre_final_input_gate_rejects_missing_required_worker_ref():
    payload = _complete_pre_final_input()
    payload["contribution_refs"] = [
        ref for ref in payload["contribution_refs"] if ref["agent_name"] != "ExecutionRiskAgent"
    ]

    gate = evaluate_pre_final_input_gate(payload)

    assert gate["passed"] is False
    assert {
        violation["rule_id"] for violation in gate["violations"]
    } >= {"pre_final_input.required_worker_refs_missing"}
    missing = next(
        violation
        for violation in gate["violations"]
        if violation["rule_id"] == "pre_final_input.required_worker_refs_missing"
    )
    assert missing["missing_required_agents"] == ["ExecutionRiskAgent"]


def test_pre_final_input_gate_rejects_execution_fact_source_hard_block_and_side_effects():
    payload = _complete_pre_final_input()
    payload["evidence_refs"].append(
        {
            "evidence_id": "ev-order-book-search",
            "data_type": "order_book",
            "source_type": "search_derived",
            "can_satisfy_execution_fact": True,
        }
    )
    payload["contribution_refs"][-1]["hard_block"] = True
    payload["contribution_refs"][-1]["hard_block_reasons"] = ["facts_gate:execution_facts_missing"]
    payload["notification_input"] = True

    gate = evaluate_pre_final_input_gate(payload)

    assert gate["passed"] is False
    assert {
        violation["rule_id"] for violation in gate["violations"]
    } >= {
        "pre_final_input.execution_fact_source_invalid",
        "pre_final_input.worker_hard_block",
        "pre_final_input.side_effect_field_present",
    }

    readiness = build_pre_final_switch_readiness(payload)

    assert readiness["ready"] is False
    assert "pre_final_input_gate_failed" in readiness["blocking_reasons"]
    assert readiness["pre_final_checks"]["pre_final_input_gate_passed"] is False


def test_pre_final_input_gate_rejects_tool_artifact_execution_fact_from_search_source():
    payload = _complete_pre_final_input()
    payload["contribution_refs"][0]["tool_call_artifact_refs"] = [
        {
            "tool_call_id": "tool:trace-1:LiveFactAgent:realtime_search:1",
            "skill_name": "realtime_search",
            "status": "ok",
            "source_type": "search_derived",
            "source_tier": "search",
            "retrieved_at": "2026-07-04T10:00:00+00:00",
            "freshness_status": "fresh",
            "result_ref": "skill_result:trace-1:LiveFactAgent:realtime_search:1",
            "output_hash": "sha256:tool",
            "can_satisfy_execution_fact": True,
        }
    ]

    gate = evaluate_pre_final_input_gate(payload)

    assert gate["passed"] is False
    violation = next(
        violation
        for violation in gate["violations"]
        if violation["rule_id"] == "pre_final_input.tool_artifact_execution_fact_source_invalid"
    )
    assert violation["invalid_refs"] == [
        {
            "agent_name": "LiveFactAgent",
            "tool_call_id": "tool:trace-1:LiveFactAgent:realtime_search:1",
            "skill_name": "realtime_search",
            "source_type": "search_derived",
            "freshness_status": "fresh",
        }
    ]


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
    payload = {
        "schema_version": 1,
        "mode": "pre_final_candidate",
        "decision_effect": "none",
        "trace_id": "trace-1",
        "symbol": "ETH-USDT-SWAP",
        "input_ref": "trace:trace-1:pre_final_decision_input",
        "input_hash": "sha256:pre-final",
        "evidence_refs": [
            {
                "evidence_id": "ev-mark",
                "data_type": "mark",
                "source_type": "exchange_native",
                "can_satisfy_execution_fact": True,
            }
        ],
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
    return deepcopy(payload)
