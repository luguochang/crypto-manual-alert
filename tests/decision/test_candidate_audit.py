from __future__ import annotations

from crypto_manual_alert.decision.candidate_audit import build_candidate_audit_payload


def test_candidate_audit_payload_builds_all_candidate_sections_without_production_effect():
    lead_synthesis = {
        "decision_effect": "none",
        "included_contribution_ids": ["c-root"],
        "dropped_contributions": [],
        "supporting_thesis": [],
        "counter_thesis": [],
        "conflicts": [],
        "missing_facts": [],
    }
    payload = build_candidate_audit_payload(
        trace_id="trace-1",
        symbol="ETH-USDT-SWAP",
        legacy_plan={"main_action": "trigger long", "probability": 0.67},
        verdict={"allowed": False},
        frozen_input_hash="frozen-1",
        audit_payload={
            "evidence_packets": [
                {
                    "evidence_id": "ev-1",
                    "data_type": "mark",
                    "source_type": "search_derived",
                    "freshness_status": "unknown",
                    "can_satisfy_execution_fact": False,
                    "confidence_cap": 0.58,
                }
            ],
            "facts_gate": {
                "severity": "hard_fail",
                "missing_execution_facts": ["mark"],
                "blocked_action_classes": ["trigger"],
                "reasons": ["mark missing"],
            },
            "agent_contributions": [],
        },
        shadow_swarm_audit={
            "lead_plan": {"plan_id": "shadow:trace-1"},
            "lead_synthesis": lead_synthesis,
            "worker_results": [
                {
                    "task_id": "shadow:RootCauseAgent",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "contribution": {
                        "contribution_id": "c-root",
                        "agent_name": "RootCauseAgent",
                        "status": "ok",
                        "required": True,
                        "claims": [],
                        "conflicts": [],
                        "missing_facts": [],
                        "output_hash": "sha256:root",
                        "input_ref": "trace:trace-1:shadow_swarm_input",
                    },
                }
            ],
        },
    )

    assert set(payload) == {
        "decision_input_candidate",
        "replayable_input_candidate",
        "lead_synthesis_artifact",
        "gate_candidate",
        "plan_semantic_candidate",
        "final_decision_switch_readiness",
    }
    assert payload["decision_input_candidate"]["decision_effect"] == "none"
    assert payload["replayable_input_candidate"]["legacy_frozen_input_hash"] == "frozen-1"
    assert payload["lead_synthesis_artifact"]["artifact_ref"] == "candidate:lead_synthesis"
    assert payload["lead_synthesis_artifact"]["decision_effect"] == "none"
    assert payload["lead_synthesis_artifact"]["input_ref"] == "trace:trace-1:lead_synthesis"
    assert payload["lead_synthesis_artifact"]["included_contribution_refs"] == [
        {
            "contribution_id": "c-root",
            "output_hash": "sha256:root",
            "input_ref": "trace:trace-1:shadow_swarm_input",
        }
    ]
    assert payload["lead_synthesis_artifact"]["lead_plan_ref"] == "shadow:trace-1"
    assert payload["lead_synthesis_artifact"]["worker_manifest_hash"].startswith("sha256:")
    assert payload["gate_candidate"]["decision_effect"] == "none"
    assert payload["plan_semantic_candidate"]["decision_effect"] == "none"
    assert payload["final_decision_switch_readiness"]["decision_effect"] == "none"
    assert payload["final_decision_switch_readiness"]["ready"] is False


def test_candidate_audit_can_carry_candidate_final_sidecar_without_production_effect():
    sidecar = {
        "artifact_type": "candidate_final_decision",
        "mode": "candidate_final_sidecar",
        "decision_effect": "none",
        "production_final_input": False,
        "input_ref": "trace:trace-1:pre_final_decision_input",
        "input_hash": "sha256:pre-final",
        "input_gate_passed": True,
        "raw_candidate_decision": '{"main_action":"no trade"}',
        "error": None,
    }

    payload = build_candidate_audit_payload(
        trace_id="trace-1",
        symbol="ETH-USDT-SWAP",
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
        frozen_input_hash="frozen-1",
        audit_payload={"evidence_packets": [], "facts_gate": {}, "agent_contributions": []},
        shadow_swarm_audit={
            "lead_plan": {"tasks": []},
            "lead_synthesis": {"decision_effect": "none", "included_contribution_ids": []},
            "worker_results": [],
        },
        candidate_final_decision=sidecar,
    )

    assert payload["candidate_final_decision"] == sidecar
    assert payload["candidate_final_decision"]["decision_effect"] == "none"
    assert payload["candidate_final_decision"]["production_final_input"] is False


def test_candidate_audit_passes_lead_synthesis_as_single_source(monkeypatch):
    received: dict[str, object] = {}
    lead_synthesis = {"decision_effect": "none", "included_contribution_ids": ["c-root"]}

    class FakeDecisionInputCandidate:
        def to_public_dict(self):
            return {
                "decision_effect": "none",
                "effective_allowed_actions": ["no trade"],
                "confidence_policy": {},
                "missing_facts": [],
                "lead_synthesis": lead_synthesis,
                "validation": {"passed": True},
            }

    def fake_decision_input_builder(**kwargs):
        received.update(kwargs)
        return FakeDecisionInputCandidate()

    monkeypatch.setattr(
        "crypto_manual_alert.decision.candidate_audit.build_decision_input_candidate",
        fake_decision_input_builder,
    )

    build_candidate_audit_payload(
        trace_id="trace-1",
        symbol="ETH-USDT-SWAP",
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
        frozen_input_hash="frozen-1",
        audit_payload={"evidence_packets": [], "facts_gate": {}, "agent_contributions": []},
        shadow_swarm_audit={
            "lead_plan": {"tasks": [{"agent_name": "RootCauseAgent", "required": True}]},
            "lead_synthesis": lead_synthesis,
            "worker_results": [],
            "harness_validation": {"passed": True},
        },
    )

    assert received["lead_synthesis"] is lead_synthesis
    assert "lead_plan" not in received
