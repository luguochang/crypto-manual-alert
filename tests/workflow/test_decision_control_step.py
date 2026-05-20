from __future__ import annotations

from datetime import datetime, timezone

from crypto_manual_alert.config import load_config
from crypto_manual_alert.decision.decision_input_policy import REQUIRED_SHADOW_WORKER_AGENTS
from crypto_manual_alert.domain import DataPoint, DecisionPlan, MarketSnapshot
from crypto_manual_alert.workflow.decision_control_step import run_decision_control_step


class CandidateDecisionEngine:
    def __init__(self):
        self.calls = []

    def run(self, input_payload):
        self.calls.append(input_payload)
        return '{"main_action":"no trade","manual_execution_required":true}'


def test_decision_control_step_builds_candidate_audit_and_merges_with_legacy_risk():
    plan = DecisionPlan.from_payload(
        {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "reference_price": 3500,
            "entry_trigger": 3501,
            "stop_price": 3400,
            "target_1": 3700,
            "probability": 0.67,
            "manual_execution_required": True,
            "expires_in_seconds": 90,
            "why_not_opposite": "counter thesis",
            "invalidation": "invalid below stop",
        },
        generated_at=datetime.now(timezone.utc),
    )
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={
            "mark": DataPoint("mark", 3500, None, "fixture"),
            "index": DataPoint("index", 3499, None, "fixture"),
            "order_book": DataPoint("order_book", {"bid": 3498, "ask": 3501}, None, "fixture"),
        },
        unavailable=[],
    )
    audit_payload = {
        "evidence_packets": [
            {
                "evidence_id": "ev-mark",
                "data_type": "mark",
                "source_type": "fixture",
                "freshness_status": "unknown",
                "can_satisfy_execution_fact": False,
                "confidence_cap": 0.58,
            }
        ],
        "facts_gate": {
            "passed": False,
            "severity": "hard_fail",
            "missing_execution_facts": ["mark"],
            "blocked_action_classes": ["trigger"],
            "reasons": ["mark missing"],
        },
        "agent_contributions": [],
    }
    shadow_swarm_audit = {
        "harness_validation": {"passed": True},
        "worker_results": [],
        "lead_synthesis": {
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
    }

    result = run_decision_control_step(
        trace_id="trace-1",
        plan=plan,
        snapshot=snapshot,
        config=load_config("config/default.yaml"),
        frozen_input_hash="frozen-1",
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        raw_decision="{\"notes\":\"raw final output must not be copied\"}",
        final_input_selection={
            "mode": "legacy_prompt",
            "source_ref": "legacy_prompt_packet",
            "decision_effect": "production_final_input",
            "readiness_ready": False,
        },
        run_context_summary={
            "side_effect_policy": {
                "allow_production_journal_write": True,
                "allow_notification_intent": True,
            },
            "artifacts": {
                "evidence_count": 1,
                "contribution_count": 0,
                "lead_plan_ref": {"plan_id": "shadow:trace-1"},
            },
            "version_lock": {
                "config_hash": "sha256:config",
                "skill_hashes": {"crypto-macro-decision": "sha256:skill"},
                "prompt_hashes": {"legacy_final_prompt": "sha256:prompt"},
                "model": "fixture",
                "rule_hashes": {"risk_gate": "sha256:risk-rules"},
                "redaction_policy_hash": "sha256:redaction",
                "raw_prompt": "raw prompt must not leak",
            },
        },
    )

    assert result.production_control_verdict.allowed is False
    assert result.final_verdict.allowed is False
    assert result.production_control_summary == result.production_control_verdict.to_public_dict()
    assert result.risk_summary == result.final_verdict.to_public_dict()
    assert "production_control.candidate.action_not_allowed" in {
        hit.rule_id for hit in result.final_verdict.rule_hits if hit.blocking
    }
    assert result.candidate_audit["decision_input_candidate"]["legacy_decision_ref"] == {
        "main_action": "trigger long",
        "probability": 0.67,
        "allowed": False,
    }
    assert result.candidate_audit["final_decision_switch_readiness"]["decision_effect"] == "none"
    replayable_refs = result.candidate_audit["replayable_input_candidate"]["artifact_refs"]
    assert replayable_refs["final_decision_output"]["output_hash"].startswith("sha256:")
    assert replayable_refs["final_input_selection"]["mode"] == "legacy_prompt"
    assert replayable_refs["parsed_plan"]["main_action"] == "trigger long"
    assert replayable_refs["production_control_gate"]["allowed"] is False
    assert replayable_refs["risk_gate_result"]["allowed"] is False
    assert replayable_refs["side_effect_policy"]["allow_notification_intent"] is True
    assert replayable_refs["context_artifact_summary"]["evidence_count"] == 1
    assert replayable_refs["version_lock"]["config_hash"] == "sha256:config"
    assert replayable_refs["version_lock"]["skill_hashes"] == {"crypto-macro-decision": "sha256:skill"}
    assert replayable_refs["version_lock"]["prompt_hashes"] == {"legacy_final_prompt": "sha256:prompt"}
    assert replayable_refs["version_lock"]["model"] == "fixture"
    assert "raw final output must not be copied" not in str(result.candidate_audit["replayable_input_candidate"])
    assert "raw prompt must not leak" not in str(result.candidate_audit["replayable_input_candidate"])


def test_decision_control_step_runs_candidate_final_sidecar_into_candidate_audit():
    engine = CandidateDecisionEngine()
    plan = _trigger_long_plan()
    snapshot = _snapshot()
    audit_payload = _audit_payload()
    shadow_swarm_audit = _shadow_swarm_audit()
    pre_final_decision_input = _complete_pre_final_input()

    result = run_decision_control_step(
        trace_id="trace-1",
        plan=plan,
        snapshot=snapshot,
        config=load_config("config/default.yaml"),
        frozen_input_hash="frozen-1",
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        raw_decision="{\"main_action\":\"trigger long\"}",
        final_input_selection={"mode": "legacy_prompt", "decision_effect": "production_final_input"},
        candidate_decision_engine=engine,
        pre_final_decision_input=pre_final_decision_input,
    )

    assert len(engine.calls) == 1
    sidecar = result.candidate_audit["candidate_final_decision"]
    assert sidecar["artifact_type"] == "candidate_final_decision"
    assert sidecar["decision_effect"] == "none"
    assert sidecar["production_final_input"] is False
    assert sidecar["input_ref"] == pre_final_decision_input["input_ref"]
    assert sidecar["input_hash"] == pre_final_decision_input["input_hash"]
    assert sidecar["raw_candidate_decision"] == '{"main_action":"no trade","manual_execution_required":true}'


def test_decision_control_step_blocks_request_snapshot_plan_symbol_mismatch():
    engine = CandidateDecisionEngine()
    plan = _trigger_long_plan()
    snapshot = MarketSnapshot(
        symbol="BTC-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={
            "mark": DataPoint("mark", 65000, None, "fixture"),
            "index": DataPoint("index", 64990, None, "fixture"),
            "order_book": DataPoint("order_book", {"bid": 64980, "ask": 65010}, None, "fixture"),
        },
        unavailable=[],
    )

    result = run_decision_control_step(
        trace_id="trace-symbol-mismatch",
        plan=plan,
        snapshot=snapshot,
        config=load_config("config/default.yaml"),
        frozen_input_hash="frozen-1",
        audit_payload=_audit_payload(),
        shadow_swarm_audit=_shadow_swarm_audit(),
        final_input_selection={"mode": "legacy_prompt", "decision_effect": "production_final_input"},
        candidate_decision_engine=engine,
        pre_final_decision_input=_complete_pre_final_input(),
        run_context_summary={"symbol": "BTC-USDT-SWAP"},
    )

    blocking_rule_ids = {hit.rule_id for hit in result.final_verdict.rule_hits if hit.blocking}
    assert "production_control.symbol_consistency.mismatch" in blocking_rule_ids
    assert result.final_verdict.allowed is False
    assert result.candidate_audit["symbol_consistency"] == {
        "request_symbol": "BTC-USDT-SWAP",
        "snapshot_symbol": "BTC-USDT-SWAP",
        "plan_instrument": "ETH-USDT-SWAP",
        "consistent": False,
    }


def _trigger_long_plan() -> DecisionPlan:
    return DecisionPlan.from_payload(
        {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "reference_price": 3500,
            "entry_trigger": 3501,
            "stop_price": 3400,
            "target_1": 3700,
            "probability": 0.67,
            "manual_execution_required": True,
            "expires_in_seconds": 90,
            "why_not_opposite": "counter thesis",
            "invalidation": "invalid below stop",
        },
        generated_at=datetime.now(timezone.utc),
    )


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={
            "mark": DataPoint("mark", 3500, None, "fixture"),
            "index": DataPoint("index", 3499, None, "fixture"),
            "order_book": DataPoint("order_book", {"bid": 3498, "ask": 3501}, None, "fixture"),
        },
        unavailable=[],
    )


def _audit_payload() -> dict[str, object]:
    return {
        "evidence_packets": [
            {
                "evidence_id": "ev-mark",
                "data_type": "mark",
                "source_type": "fixture",
                "freshness_status": "unknown",
                "can_satisfy_execution_fact": False,
                "confidence_cap": 0.58,
            }
        ],
        "facts_gate": {
            "passed": False,
            "severity": "hard_fail",
            "missing_execution_facts": ["mark"],
            "blocked_action_classes": ["trigger"],
            "reasons": ["mark missing"],
        },
        "agent_contributions": [],
    }


def _shadow_swarm_audit() -> dict[str, object]:
    return {
        "harness_validation": {"passed": True},
        "worker_results": [],
        "lead_synthesis": {
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
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
    return {
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
