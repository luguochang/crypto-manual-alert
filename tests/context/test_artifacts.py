from __future__ import annotations

from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.artifacts import record_orchestration_artifacts
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import RiskVerdict, RuleHit
from crypto_manual_alert.decision.frozen_input import stable_hash


def test_record_orchestration_artifacts_writes_only_controlled_context_sections():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    audit_payload = {
        "evidence_packets": [{"evidence_id": "ev-1"}, {"evidence_id": "ev-2"}],
        "facts_gate": {"passed": False},
        "agent_contributions": [{"contribution_id": "legacy-1", "agent_name": "data_quality_reviewer"}],
    }
    shadow_swarm_audit = {
        "lead_plan": {"plan_id": "lead-1"},
        "worker_results": [
            {
                "agent_name": "DataQualityAgent",
                "contribution": {"contribution_id": "worker-1", "agent_name": "DataQualityAgent"},
            }
        ],
    }
    pre_final_decision_input = {"input_ref": "trace:trace-1:pre_final_decision_input"}
    pre_final_bundle = {
        "artifact_ref": "trace:trace-1:pre_final_bundle",
        "decision_effect": "none",
    }
    candidate_audit = {
        "lead_synthesis_artifact": {
            "artifact_ref": "candidate:lead_synthesis",
            "input_ref": "trace:trace-1:lead_synthesis",
            "input_hash": "sha256:lead",
            "decision_effect": "none",
        },
        "candidate_final_decision": {
            "artifact_type": "candidate_final_decision",
            "decision_effect": "none",
            "production_final_input": False,
            "input_ref": "trace:trace-1:pre_final_decision_input",
        },
        "gate_candidate": {"passed": True},
        "plan_semantic_candidate": {"passed": True},
        "final_decision_switch_readiness": {"ready": False},
    }
    production_control_verdict = RiskVerdict(
        allowed=False,
        reasons=["blocked"],
        rule_hits=[
            RuleHit(
                rule_id="production_control.test",
                passed=False,
                severity="hard_fail",
                message="blocked",
                blocking=True,
            )
        ],
    )

    record_orchestration_artifacts(
        context,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        pre_final_decision_input=pre_final_decision_input,
        pre_final_bundle=pre_final_bundle,
        candidate_audit=candidate_audit,
        production_control_verdict=production_control_verdict,
    )

    summary = context.to_artifact_summary()

    assert summary == {
        "evidence_count": 2,
        "contribution_count": 2,
        "has_lead_plan": True,
        "has_decision_input": True,
        "gate_result_names": [
            "candidate_final_decision",
            "facts_gate",
            "final_decision_switch_readiness",
            "gate_candidate",
            "lead_synthesis_artifact",
            "plan_semantic_candidate",
            "pre_final_bundle",
            "production_control_gate",
        ],
        "reserved_sections": [],
        "evidence_refs": [
            {"evidence_id": "ev-1", "artifact_hash": stable_hash({"evidence_id": "ev-1"})},
            {"evidence_id": "ev-2", "artifact_hash": stable_hash({"evidence_id": "ev-2"})},
        ],
        "contribution_refs": [
            {
                "contribution_id": "legacy-1",
                "agent_name": "data_quality_reviewer",
                "confidence_cap": None,
                "confidence_cap_reasons": [],
                "blocked_actions": [],
                "hard_block": False,
                "hard_block_reasons": [],
                "manual_review_reminders": [],
                "allowed_action_class_reduction": {},
                "required_confirmations": [],
                "artifact_hash": stable_hash(
                    {"contribution_id": "legacy-1", "agent_name": "data_quality_reviewer"}
                ),
            },
            {
                "contribution_id": "worker-1",
                "agent_name": "DataQualityAgent",
                "confidence_cap": None,
                "confidence_cap_reasons": [],
                "blocked_actions": [],
                "hard_block": False,
                "hard_block_reasons": [],
                "manual_review_reminders": [],
                "allowed_action_class_reduction": {},
                "required_confirmations": [],
                "artifact_hash": stable_hash(
                    {"contribution_id": "worker-1", "agent_name": "DataQualityAgent"}
                ),
            },
        ],
        "lead_plan_ref": {"plan_id": "lead-1", "artifact_hash": stable_hash({"plan_id": "lead-1"})},
        "decision_input_ref": {
            "input_ref": "trace:trace-1:pre_final_decision_input",
            "artifact_hash": stable_hash(pre_final_decision_input),
        },
        "gate_result_refs": {
            "candidate_final_decision": {
                "input_ref": "trace:trace-1:pre_final_decision_input",
                "decision_effect": "none",
                "production_final_input": False,
                "artifact_hash": stable_hash(candidate_audit["candidate_final_decision"]),
            },
            "facts_gate": {"passed": False, "artifact_hash": stable_hash({"passed": False})},
            "final_decision_switch_readiness": {
                "ready": False,
                "artifact_hash": stable_hash({"ready": False}),
            },
            "gate_candidate": {"passed": True, "artifact_hash": stable_hash({"passed": True})},
            "lead_synthesis_artifact": {
                "artifact_ref": "candidate:lead_synthesis",
                "input_ref": "trace:trace-1:lead_synthesis",
                "input_hash": "sha256:lead",
                "decision_effect": "none",
                "artifact_hash": stable_hash(
                    {
                        "artifact_ref": "candidate:lead_synthesis",
                        "input_ref": "trace:trace-1:lead_synthesis",
                        "input_hash": "sha256:lead",
                        "decision_effect": "none",
                    }
                ),
            },
            "plan_semantic_candidate": {"passed": True, "artifact_hash": stable_hash({"passed": True})},
            "pre_final_bundle": {
                "artifact_ref": "trace:trace-1:pre_final_bundle",
                "decision_effect": "none",
                "artifact_hash": stable_hash(pre_final_bundle),
            },
            "production_control_gate": {
                "artifact_hash": stable_hash(production_control_verdict.to_public_dict())
            },
        },
    }
    assert context.lead_plan == {"plan_id": "lead-1"}
    assert context.decision_input == pre_final_decision_input
    assert context.gate_results["production_control_gate"]["allowed"] is False


def test_record_orchestration_artifacts_is_idempotent_for_repeated_candidate_writes():
    context = DecisionRunContext.create(DecisionRequest(symbol="ETH-USDT-SWAP"))
    candidate_audit = {
        "gate_candidate": {"passed": False},
        "plan_semantic_candidate": {"passed": True},
        "final_decision_switch_readiness": {"ready": False},
        "replayable_input_candidate": {
            "input_ref": "trace:trace-1:replayable_input_candidate",
            "input_hash": "sha256:replayable",
        },
    }
    verdict = RiskVerdict(allowed=False, reasons=["blocked"])

    record_orchestration_artifacts(
        context,
        candidate_audit=candidate_audit,
        production_control_verdict=verdict,
    )
    record_orchestration_artifacts(
        context,
        candidate_audit=candidate_audit,
        production_control_verdict=verdict,
    )

    summary = context.to_artifact_summary()

    assert summary == {
        "evidence_count": 0,
        "contribution_count": 0,
        "has_lead_plan": False,
        "has_decision_input": False,
        "gate_result_names": [
            "final_decision_switch_readiness",
            "gate_candidate",
            "plan_semantic_candidate",
            "production_control_gate",
            "replayable_input_candidate",
        ],
        "reserved_sections": [],
        "evidence_refs": [],
        "contribution_refs": [],
        "lead_plan_ref": None,
        "decision_input_ref": None,
        "gate_result_refs": {
            "final_decision_switch_readiness": {
                "ready": False,
                "artifact_hash": stable_hash({"ready": False}),
            },
            "gate_candidate": {
                "passed": False,
                "artifact_hash": stable_hash({"passed": False}),
            },
            "plan_semantic_candidate": {
                "passed": True,
                "artifact_hash": stable_hash({"passed": True}),
            },
            "production_control_gate": {
                "artifact_hash": stable_hash(verdict.to_public_dict())
            },
            "replayable_input_candidate": {
                "input_ref": "trace:trace-1:replayable_input_candidate",
                "input_hash": "sha256:replayable",
                "artifact_hash": stable_hash(
                    {
                        "input_ref": "trace:trace-1:replayable_input_candidate",
                        "input_hash": "sha256:replayable",
                    }
                ),
            },
        },
    }
    assert context.gate_results["replayable_input_candidate"] == {
        "input_ref": "trace:trace-1:replayable_input_candidate",
        "input_hash": "sha256:replayable",
    }


def test_record_orchestration_artifacts_ignores_missing_context():
    record_orchestration_artifacts(
        None,
        audit_payload={"evidence_packets": [{"evidence_id": "ev-1"}]},
        shadow_swarm_audit={"lead_plan": {"plan_id": "lead-1"}},
        pre_final_decision_input={"input_ref": "trace:trace-1:pre_final_decision_input"},
        candidate_audit={"gate_candidate": {"passed": True}},
        production_control_verdict=RiskVerdict(allowed=True, reasons=[]),
    )
