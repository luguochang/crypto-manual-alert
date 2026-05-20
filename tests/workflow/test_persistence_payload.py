from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crypto_manual_alert.domain import DecisionPlan, RiskVerdict
from crypto_manual_alert.workflow.persistence_payload import build_plan_payload


def test_build_plan_payload_assembles_candidate_audit_and_run_context_without_prompt_pollution():
    now = datetime.now(timezone.utc)
    plan = DecisionPlan(
        plan_id="plan-1",
        instrument="ETH-USDT-SWAP",
        main_action="no trade",
        horizon="6h",
        manual_execution_required=True,
        generated_at=now,
        expires_at=now + timedelta(minutes=1),
        raw={"instrument": "ETH-USDT-SWAP", "main_action": "no trade"},
    )
    verdict = RiskVerdict(allowed=True, reasons=[])
    audit_payload = {
        "evidence_packets": [],
        "facts_gate": {"passed": True, "severity": "ok", "blocked_action_classes": []},
        "harness_validation": {"passed": True},
        "agent_contributions": [],
    }

    payload = build_plan_payload(
        trace_id="trace-1",
        plan=plan,
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        verdict=verdict,
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        shadow_swarm_audit=None,
        final_input_selection={"mode": "legacy_prompt"},
        run_context_summary={
            "run_id": "run-1",
            "run_type": "manual",
            "symbol": "ETH-USDT-SWAP",
            "query_text": "看 ETH",
            "horizon": "6h",
            "session_id": "session-1",
            "manual_only": True,
            "artifacts": {"evidence_count": 2, "has_lead_plan": True},
            "side_effect_policy": {"allow_production_journal_write": True},
            "version_lock": {
                "config_hash": "sha256:config",
                "skill_hashes": {"crypto-macro-decision": "sha256:skill"},
                "prompt_hashes": {"legacy_final_prompt": "sha256:prompt"},
                "model": "fixture",
                "rule_hashes": {"risk_gate": "sha256:risk-rules"},
                "redaction_policy_hash": "sha256:redaction",
            },
            "internal": "must not leak",
        },
        audit_payload=audit_payload,
        pre_final_decision_input={"input_ref": "trace:trace-1:pre_final_decision_input"},
        production_control_verdict=RiskVerdict(allowed=True, reasons=[]),
    )

    assert payload["trace_id"] == "trace-1"
    assert payload["skill"] == {"name": "crypto-macro-decision"}
    assert payload["evidence_packets"] == []
    assert payload["facts_gate"]["passed"] is True
    assert payload["pre_final_decision_input"] == {"input_ref": "trace:trace-1:pre_final_decision_input"}
    assert payload["final_input_selection"] == {"mode": "legacy_prompt"}
    assert payload["legacy_prompt_lifecycle"] == {
        "status": "legacy_primary_until_switch_review",
        "selected_as_final_input": True,
        "allowed_uses": [
            "production_primary_until_switch_review",
            "replay_baseline",
            "legacy_comparison",
        ],
        "replacement_target": "decision_input",
    }
    assert payload["audit_only"] == {
        "schema_version": 1,
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "mirrored_legacy_fields": [
            "evidence_packets",
            "facts_gate",
            "harness_validation",
            "agent_contributions",
            "shadow_swarm_audit",
            "pre_final_decision_input",
            "decision_input_candidate",
            "candidate_final_decision",
            "replayable_input_candidate",
            "lead_synthesis_artifact",
            "gate_candidate",
            "plan_semantic_candidate",
            "final_decision_switch_readiness",
        ],
        "evidence_packets": [],
        "facts_gate": {"passed": True, "severity": "ok", "blocked_action_classes": []},
        "harness_validation": {"passed": True},
        "agent_contributions": [],
        "shadow_swarm_audit": None,
        "pre_final_decision_input": {"input_ref": "trace:trace-1:pre_final_decision_input"},
        "decision_input_candidate": payload["decision_input_candidate"],
        "candidate_final_decision": None,
        "replayable_input_candidate": payload["replayable_input_candidate"],
        "lead_synthesis_artifact": payload["lead_synthesis_artifact"],
        "gate_candidate": payload["gate_candidate"],
        "plan_semantic_candidate": payload["plan_semantic_candidate"],
        "final_decision_switch_readiness": payload["final_decision_switch_readiness"],
    }
    assert payload["decision_input_candidate"]["decision_effect"] == "none"
    assert payload["replayable_input_candidate"]["decision_effect"] == "none"
    assert payload["replayable_input_candidate"]["artifact_refs"]["final_decision_output"]["output_hash"].startswith(
        "sha256:"
    )
    assert payload["replayable_input_candidate"]["artifact_refs"]["final_input_selection"]["mode"] == "legacy_prompt"
    assert payload["replayable_input_candidate"]["artifact_refs"]["parsed_plan"]["main_action"] == "no trade"
    assert payload["replayable_input_candidate"]["artifact_refs"]["risk_gate_result"]["allowed"] is True
    assert payload["replayable_input_candidate"]["artifact_refs"]["production_control_gate"]["allowed"] is True
    assert payload["replayable_input_candidate"]["artifact_refs"]["side_effect_policy"] == {
        "allow_production_journal_write": True,
        "policy_hash": payload["replayable_input_candidate"]["artifact_refs"]["side_effect_policy"]["policy_hash"],
    }
    assert payload["replayable_input_candidate"]["artifact_refs"]["version_lock"]["config_hash"] == "sha256:config"
    assert payload["gate_candidate"]["decision_effect"] == "none"
    assert payload["plan_semantic_candidate"]["decision_effect"] == "none"
    assert payload["final_decision_switch_readiness"]["decision_effect"] == "none"
    assert payload["run_context"] == {
        "horizon": "6h",
        "manual_only": True,
        "query_text": "看 ETH",
        "run_id": "run-1",
        "run_type": "manual",
        "session_id": "session-1",
        "artifacts": {"evidence_count": 2, "has_lead_plan": True},
        "side_effect_policy": {"allow_production_journal_write": True},
        "symbol": "ETH-USDT-SWAP",
    }


def test_build_plan_payload_marks_legacy_prompt_as_replay_only_when_decision_input_is_selected():
    now = datetime.now(timezone.utc)
    plan = DecisionPlan(
        plan_id="plan-1",
        instrument="ETH-USDT-SWAP",
        main_action="no trade",
        horizon="6h",
        manual_execution_required=True,
        generated_at=now,
        expires_at=now + timedelta(minutes=1),
        raw={"instrument": "ETH-USDT-SWAP", "main_action": "no trade"},
    )
    verdict = RiskVerdict(allowed=True, reasons=[])
    audit_payload = {
        "evidence_packets": [],
        "facts_gate": {"passed": True},
        "harness_validation": {"passed": True},
        "agent_contributions": [],
    }

    payload = build_plan_payload(
        trace_id="trace-1",
        plan=plan,
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        verdict=verdict,
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=audit_payload,
        final_input_selection={
            "mode": "decision_input",
            "source_ref": "trace:trace-1:decision_input_candidate",
            "decision_effect": "production_final_input",
            "readiness_ready": True,
        },
    )

    assert payload["legacy_prompt_lifecycle"] == {
        "status": "replay_and_comparison_only",
        "selected_as_final_input": False,
        "allowed_uses": ["replay_baseline", "legacy_comparison"],
        "replacement_target": "decision_input",
    }


def test_build_plan_payload_marks_legacy_prompt_as_decision_input_fallback():
    now = datetime.now(timezone.utc)
    plan = DecisionPlan(
        plan_id="plan-1",
        instrument="ETH-USDT-SWAP",
        main_action="no trade",
        horizon="6h",
        manual_execution_required=True,
        generated_at=now,
        expires_at=now + timedelta(minutes=1),
        raw={"instrument": "ETH-USDT-SWAP", "main_action": "no trade"},
    )
    verdict = RiskVerdict(allowed=True, reasons=[])
    audit_payload = {
        "evidence_packets": [],
        "facts_gate": {"passed": True},
        "harness_validation": {"passed": True},
        "agent_contributions": [],
    }

    payload = build_plan_payload(
        trace_id="trace-1",
        plan=plan,
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        verdict=verdict,
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=audit_payload,
        final_input_selection={
            "mode": "legacy_prompt",
            "source_ref": "legacy_prompt_packet",
            "fallback_from_mode": "decision_input",
            "fallback_reason": "decision_input_not_ready",
            "fallback_blocking_reasons": ["pre_final_input_gate_failed"],
        },
    )

    assert payload["legacy_prompt_lifecycle"] == {
        "status": "decision_input_fallback",
        "selected_as_final_input": True,
        "allowed_uses": ["decision_input_fallback", "replay_baseline", "legacy_comparison"],
        "replacement_target": "decision_input",
        "fallback_reason": "decision_input_not_ready",
        "fallback_blocking_reasons": ["pre_final_input_gate_failed"],
    }


def test_build_plan_payload_mirrors_candidate_final_sidecar_in_audit_only_namespace():
    now = datetime.now(timezone.utc)
    plan = DecisionPlan(
        plan_id="plan-1",
        instrument="ETH-USDT-SWAP",
        main_action="no trade",
        horizon="6h",
        manual_execution_required=True,
        generated_at=now,
        expires_at=now + timedelta(minutes=1),
        raw={"instrument": "ETH-USDT-SWAP", "main_action": "no trade"},
    )
    verdict = RiskVerdict(allowed=True, reasons=[])
    audit_payload = {
        "evidence_packets": [],
        "facts_gate": {"passed": True},
        "harness_validation": {"passed": True},
        "agent_contributions": [],
    }
    candidate_final_decision = {
        "artifact_type": "candidate_final_decision",
        "mode": "candidate_final_sidecar",
        "decision_effect": "none",
        "production_final_input": False,
        "input_ref": "trace:trace-1:pre_final_decision_input",
    }

    payload = build_plan_payload(
        trace_id="trace-1",
        plan=plan,
        snapshot=None,
        raw_decision='{"main_action":"no trade"}',
        verdict=verdict,
        prompt_packet={"skill": {"name": "crypto-macro-decision"}},
        research_audit=None,
        frozen_input=None,
        audit_payload=audit_payload,
        candidate_audit={"candidate_final_decision": candidate_final_decision},
    )

    assert payload["candidate_final_decision"] == candidate_final_decision
    assert "candidate_final_decision" in payload["audit_only"]["mirrored_legacy_fields"]
    assert payload["audit_only"]["candidate_final_decision"] == candidate_final_decision
