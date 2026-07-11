from __future__ import annotations

from crypto_manual_alert.decision.decision_input_policy import REQUIRED_SHADOW_WORKER_AGENTS
from crypto_manual_alert.workflow.candidate_sidecar_step import run_candidate_sidecar_step


class RecordingDecisionEngine:
    def __init__(self):
        self.calls = []

    def run(self, input_payload):
        self.calls.append(input_payload)
        return '{"main_action":"no trade","manual_execution_required":true}'


def test_candidate_sidecar_step_is_disabled_without_engine():
    result = run_candidate_sidecar_step(
        candidate_decision_engine=None,
        pre_final_decision_input={"input_ref": "trace:t1:pre_final", "input_hash": "sha256:abc"},
    )

    assert result is None


def test_candidate_sidecar_step_runs_gated_audit_only_candidate():
    engine = RecordingDecisionEngine()
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
    pre_final_decision_input = {
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

    result = run_candidate_sidecar_step(
        candidate_decision_engine=engine,
        pre_final_decision_input=pre_final_decision_input,
    )

    assert len(engine.calls) == 1
    assert result["artifact_type"] == "candidate_final_decision"
    assert result["mode"] == "candidate_final_sidecar"
    assert result["decision_effect"] == "none"
    assert result["production_final_input"] is False
    assert result["input_gate_passed"] is True
    assert result["raw_candidate_decision"] == '{"main_action":"no trade","manual_execution_required":true}'
    assert engine.calls[0]["mode"] == "candidate_final_input"
    assert engine.calls[0]["decision_effect"] == "none"
