from __future__ import annotations

from copy import deepcopy

from crypto_manual_alert.decision.candidate_final_decision import run_candidate_final_decision_sidecar
from crypto_manual_alert.decision.decision_input_policy import REQUIRED_SHADOW_WORKER_AGENTS
from crypto_manual_alert.decision.pre_final_input_gate import evaluate_pre_final_input_gate


class CapturingCandidateEngine:
    def __init__(self):
        self.input_payload = None

    def run(self, input_payload):
        self.input_payload = input_payload
        return '{"main_action":"no trade","manual_execution_required":true}'


def test_candidate_final_decision_sidecar_consumes_gate_passed_decision_input_without_production_effect():
    engine = CapturingCandidateEngine()
    decision_input = _complete_pre_final_input()
    gate = evaluate_pre_final_input_gate(decision_input)

    result = run_candidate_final_decision_sidecar(
        decision_engine=engine,
        pre_final_decision_input=decision_input,
        input_gate=gate,
    )

    assert engine.input_payload["mode"] == "candidate_final_input"
    assert engine.input_payload["decision_effect"] == "none"
    assert engine.input_payload["source_candidate_ref"] == decision_input["input_ref"]
    assert decision_input["mode"] == "pre_final_candidate"
    assert decision_input["decision_effect"] == "none"
    assert result == {
        "artifact_type": "candidate_final_decision",
        "mode": "candidate_final_sidecar",
        "decision_effect": "none",
        "production_final_input": False,
        "input_ref": decision_input["input_ref"],
        "input_hash": decision_input["input_hash"],
        "input_gate_passed": True,
        "raw_candidate_decision": '{"main_action":"no trade","manual_execution_required":true}',
        "error": None,
    }


def test_candidate_final_decision_sidecar_strips_legacy_raw_and_frozen_fields_before_engine():
    engine = CapturingCandidateEngine()
    decision_input = _complete_pre_final_input()
    decision_input.update(
        {
            "legacy_prompt": "raw legacy prompt must not reach candidate final",
            "prompt_packet": {"messages": ["raw prompt packet must not reach candidate final"]},
            "raw_decision": "legacy raw decision must not reach candidate final",
            "frozen_input": {"full_prompt": "frozen prompt must not reach candidate final"},
            "frozen_input_hash": "sha256:legacy-frozen",
        }
    )
    gate = evaluate_pre_final_input_gate(decision_input)

    result = run_candidate_final_decision_sidecar(
        decision_engine=engine,
        pre_final_decision_input=decision_input,
        input_gate=gate,
    )

    assert result["error"] is None
    assert engine.input_payload is not None
    rendered = str(engine.input_payload)
    assert "raw legacy prompt must not reach candidate final" not in rendered
    assert "raw prompt packet must not reach candidate final" not in rendered
    assert "legacy raw decision must not reach candidate final" not in rendered
    assert "frozen prompt must not reach candidate final" not in rendered
    assert "legacy_prompt" not in engine.input_payload
    assert "prompt_packet" not in engine.input_payload
    assert "raw_decision" not in engine.input_payload
    assert "frozen_input" not in engine.input_payload
    assert "frozen_input_hash" not in engine.input_payload


def test_candidate_final_decision_sidecar_skips_engine_when_input_gate_fails():
    engine = CapturingCandidateEngine()
    decision_input = _complete_pre_final_input()
    decision_input["contribution_refs"] = []
    gate = evaluate_pre_final_input_gate(decision_input)

    result = run_candidate_final_decision_sidecar(
        decision_engine=engine,
        pre_final_decision_input=decision_input,
        input_gate=gate,
    )

    assert engine.input_payload is None
    assert result["decision_effect"] == "none"
    assert result["production_final_input"] is False
    assert result["input_gate_passed"] is False
    assert result["raw_candidate_decision"] is None
    assert result["error"]["type"] == "input_gate_failed"
    assert result["diagnosis"] == {
        "summary": "candidate final sidecar blocked by input gate",
        "blocking_reasons": [violation["rule_id"] for violation in gate["violations"]],
    }


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
