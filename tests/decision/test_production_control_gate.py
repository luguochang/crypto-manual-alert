from __future__ import annotations

from datetime import datetime, timezone

from crypto_manual_alert.decision.production_control_gate import check_production_control_gate, merge_risk_verdicts
from crypto_manual_alert.domain import DecisionPlan, RiskVerdict


def _plan(payload: dict) -> DecisionPlan:
    return DecisionPlan.from_payload(payload, generated_at=datetime.now(timezone.utc))


def test_production_control_gate_blocks_executable_action_clipped_by_candidate_gate():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "horizon": "6h",
                "entry_trigger": 3500,
                "stop_price": 3400,
                "target_1": 3600,
                "probability": 0.67,
                "manual_execution_required": True,
                "invalidation": "invalid below stop",
            }
        ),
        candidate_audit={
            "decision_input_candidate": {
                "confidence_policy": {
                    "max_probability": 0.58,
                    "cap_reasons": ["facts_gate:execution_facts_missing"],
                },
                "lead_synthesis": {"dropped_contributions": []},
            },
            "gate_candidate": {
                "passed": False,
                "violations": [
                    {"rule_id": "candidate.action_not_allowed", "message": "trigger long not allowed"},
                    {"rule_id": "candidate.confidence_cap_exceeded", "message": "probability too high"},
                ],
                "blocked_actions": ["trigger long"],
                "missing_facts": ["mark", "index", "order_book"],
            },
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    rule_ids = {hit.rule_id for hit in verdict.rule_hits}

    assert verdict.allowed is False
    assert "production_control.candidate.action_not_allowed" in rule_ids
    assert "production_control.candidate.confidence_cap_exceeded" in rule_ids
    assert verdict.rule_hits[0].evidence_refs == ["gate_candidate", "decision_input_candidate"]


def test_production_control_gate_blocks_semantic_failure_for_executable_action():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "horizon": "6h",
                "entry_trigger": 3500,
                "stop_price": 3510,
                "target_1": 3600,
                "probability": 0.55,
                "manual_execution_required": True,
                "invalidation": "invalid below stop",
            }
        ),
        candidate_audit={
            "decision_input_candidate": {"lead_synthesis": {"dropped_contributions": []}},
            "gate_candidate": {"passed": True, "violations": []},
            "plan_semantic_candidate": {
                "passed": False,
                "violations": [
                    {
                        "rule_id": "plan_semantic.long_stop_not_below_entry",
                        "message": "long stop_price must be below entry_trigger",
                    }
                ],
            },
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    assert verdict.allowed is False
    assert {hit.rule_id for hit in verdict.rule_hits} == {
        "production_control.plan_semantic.long_stop_not_below_entry"
    }


def test_production_control_gate_warns_but_does_not_block_no_trade_on_worker_failures():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "no trade",
                "horizon": "6h",
                "probability": 0.51,
                "manual_execution_required": True,
            }
        ),
        candidate_audit={
            "decision_input_candidate": {
                "lead_synthesis": {
                    "dropped_contributions": [
                        {"agent_name": "DataQualityAgent", "reason": "missing_required_contribution"}
                    ]
                }
            },
            "gate_candidate": {
                "passed": False,
                "violations": [{"rule_id": "candidate.action_not_allowed", "message": "no trade not listed"}],
            },
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": False}},
    )

    assert verdict.allowed is True
    assert verdict.reasons == []
    assert "shadow swarm harness validation failed; kept as warning because action is no trade" in verdict.warnings
    assert all(hit.blocking is False for hit in verdict.rule_hits)


def test_production_control_gate_warns_but_does_not_block_no_trade_candidate_gate_failures():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "no trade",
                "horizon": "6h",
                "probability": 0.72,
                "manual_execution_required": True,
            }
        ),
        candidate_audit={
            "decision_input_candidate": {
                "confidence_policy": {
                    "max_probability": 0.58,
                    "cap_reasons": ["facts_gate:execution_facts_missing"],
                },
                "lead_synthesis": {"dropped_contributions": []},
            },
            "gate_candidate": {
                "passed": False,
                "violations": [
                    {"rule_id": "candidate.action_not_allowed", "message": "no trade missing from candidate list"},
                    {"rule_id": "candidate.confidence_cap_exceeded", "message": "probability too high"},
                ],
                "blocked_actions": ["no trade"],
                "missing_facts": ["mark"],
            },
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    assert verdict.allowed is True
    assert verdict.reasons == []
    assert {
        hit.rule_id
        for hit in verdict.rule_hits
    } == {
        "production_control.candidate.action_not_allowed",
        "production_control.candidate.confidence_cap_exceeded",
    }
    assert all(hit.blocking is False for hit in verdict.rule_hits)


def test_production_control_gate_does_not_block_executable_action_for_optional_worker_drop():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "horizon": "6h",
                "entry_trigger": 3500,
                "stop_price": 3400,
                "target_1": 3600,
                "probability": 0.55,
                "manual_execution_required": True,
                "invalidation": "invalid below stop",
            }
        ),
        candidate_audit={
            "final_input_selection": {
                "mode": "legacy_prompt",
                "source_ref": "legacy_prompt_packet",
                "fallback_from_mode": "decision_input",
                "fallback_reason": "decision_input_not_ready",
                "fallback_blocking_reasons": ["worker_hard_block"],
            },
            "decision_input_candidate": {
                "contribution_refs": [
                    {
                        "contribution_id": "optional-failed",
                        "agent_name": "ScenarioForkAgent",
                        "required": False,
                    }
                ],
                "lead_synthesis": {
                    "dropped_contributions": [
                        {
                            "contribution_id": "optional-failed",
                            "agent_name": "ScenarioForkAgent",
                            "reason": "status=failed",
                        }
                    ]
                },
            },
            "gate_candidate": {"passed": True, "violations": []},
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    assert verdict.allowed is True
    assert "production_control.required_worker_missing_or_failed" not in {
        hit.rule_id for hit in verdict.rule_hits
    }


def test_production_control_gate_blocks_executable_action_for_data_quality_hard_block():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "horizon": "6h",
                "entry_trigger": 3500,
                "stop_price": 3400,
                "target_1": 3600,
                "probability": 0.55,
                "manual_execution_required": True,
                "invalidation": "invalid below stop",
            }
        ),
        candidate_audit={
            "decision_input_candidate": {
                "contribution_refs": [
                    {
                        "contribution_id": "quality-failed",
                        "agent_name": "DataQualityAgent",
                        "required": True,
                    }
                ],
                "lead_synthesis": {
                    "dropped_contributions": [
                        {
                            "contribution_id": "quality-failed",
                            "agent_name": "DataQualityAgent",
                            "reason": "status=failed",
                            "required": True,
                            "failure_policy_applied": "hard_block",
                        }
                    ]
                },
            },
            "gate_candidate": {"passed": True, "violations": []},
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    assert verdict.allowed is False
    assert verdict.reasons == ["required worker contribution missing or failed"]
    hit = next(hit for hit in verdict.rule_hits if hit.rule_id == "production_control.required_worker_missing_or_failed")
    assert hit.blocking is True
    assert hit.details["dropped_contributions"] == [
        {
            "contribution_id": "quality-failed",
            "agent_name": "DataQualityAgent",
            "reason": "status=failed",
            "required": True,
            "failure_policy_applied": "hard_block",
        }
    ]


def test_production_control_gate_blocks_executable_action_for_execution_risk_hard_block():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "open short",
                "horizon": "6h",
                "entry_price": 3500,
                "stop_price": 3600,
                "target_1": 3300,
                "probability": 0.56,
                "manual_execution_required": True,
                "invalidation": "invalid above stop",
            }
        ),
        candidate_audit={
            "decision_input_candidate": {
                "contribution_refs": [
                    {
                        "contribution_id": "risk-failed",
                        "agent_name": "ExecutionRiskAgent",
                        "required": True,
                    }
                ],
                "lead_synthesis": {
                    "dropped_contributions": [
                        {
                            "contribution_id": "risk-failed",
                            "agent_name": "ExecutionRiskAgent",
                            "reason": "status=failed",
                            "required": True,
                            "failure_policy_applied": "hard_block",
                        }
                    ]
                },
            },
            "gate_candidate": {"passed": True, "violations": []},
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    assert verdict.allowed is False
    assert {hit.rule_id for hit in verdict.rule_hits if hit.blocking} == {
        "production_control.required_worker_missing_or_failed"
    }


def test_production_control_gate_blocks_executable_action_for_worker_hard_block_constraint():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "open short",
                "horizon": "6h",
                "entry_price": 3500,
                "stop_price": 3600,
                "target_1": 3300,
                "probability": 0.56,
                "manual_execution_required": True,
                "invalidation": "invalid above stop",
            }
        ),
        candidate_audit={
            "decision_input_candidate": {
                "contribution_refs": [
                    {
                        "contribution_id": "risk-hard-block",
                        "agent_name": "ExecutionRiskAgent",
                        "required": True,
                        "hard_block": True,
                        "hard_block_reasons": ["facts_gate:execution_facts_missing"],
                    }
                ],
                "lead_synthesis": {"dropped_contributions": []},
            },
            "gate_candidate": {"passed": True, "violations": []},
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    assert verdict.allowed is False
    hit = next(hit for hit in verdict.rule_hits if hit.rule_id == "production_control.worker_hard_block")
    assert hit.blocking is True
    assert hit.details["worker_hard_blocks"] == [
        {
            "contribution_id": "risk-hard-block",
            "agent_name": "ExecutionRiskAgent",
            "reasons": ["facts_gate:execution_facts_missing"],
        }
    ]


def test_production_control_gate_ignores_llm_worker_hard_block_for_production_risk():
    verdict = check_production_control_gate(
        _plan(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "open short",
                "horizon": "6h",
                "entry_price": 3500,
                "stop_price": 3600,
                "target_1": 3300,
                "probability": 0.56,
                "manual_execution_required": True,
                "invalidation": "invalid above stop",
            }
        ),
        candidate_audit={
            "decision_input_candidate": {
                "contribution_refs": [
                    {
                        "contribution_id": "llm-hard-block",
                        "agent_name": "ExecutionRiskAgent",
                        "required": True,
                        "hard_block": True,
                        "hard_block_reasons": ["llm:unverified_execution_risk"],
                        "migration_stage": "llm_tool_shadow_worker",
                    }
                ],
                "lead_synthesis": {"dropped_contributions": []},
            },
            "gate_candidate": {"passed": True, "violations": []},
            "plan_semantic_candidate": {"passed": True, "violations": []},
        },
        shadow_swarm_audit={"harness_validation": {"passed": True}},
    )

    assert verdict.allowed is True
    assert all(hit.rule_id != "production_control.worker_hard_block" for hit in verdict.rule_hits)


def test_merge_risk_verdicts_blocks_when_any_verdict_blocks_and_preserves_rule_hits():
    production = RiskVerdict(
        allowed=False,
        reasons=["production blocked"],
        rule_hits=[],
    )
    legacy = RiskVerdict(
        allowed=True,
        reasons=[],
        warnings=["legacy warning"],
        rule_hits=[],
    )

    merged = merge_risk_verdicts(production, legacy)

    assert merged.allowed is False
    assert merged.reasons == ["production blocked"]
    assert merged.warnings == ["legacy warning"]
