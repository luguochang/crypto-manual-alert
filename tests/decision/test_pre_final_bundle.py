from __future__ import annotations

from crypto_manual_alert.decision.pre_final_bundle import build_pre_final_bundle


def test_pre_final_bundle_binds_pre_final_inputs_without_production_effect():
    bundle = build_pre_final_bundle(
        trace_id="trace-1",
        symbol="ETH-USDT-SWAP",
        audit_payload={
            "facts_gate": {
                "passed": False,
                "severity": "hard_fail",
                "missing_execution_facts": ["mark"],
            },
            "harness_validation": {"passed": True, "violations": []},
            "evidence_packets": [{"evidence_id": "ev-1"}],
        },
        shadow_swarm_audit={
            "decision_effect": "none",
            "lead_plan": {
                "plan_id": "shadow:trace-1",
                "decision_effect": "none",
                "tasks": [
                    {"task_id": "shadow:RootCauseAgent", "agent_name": "RootCauseAgent", "required": True}
                ],
            },
            "worker_results": [
                {
                    "task_id": "shadow:RootCauseAgent",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "required": True,
                    "failure_policy_applied": "none",
                    "contribution": {
                        "contribution_id": "shadow:RootCauseAgent",
                        "input_ref": "trace:trace-1:worker:RootCauseAgent",
                        "output_hash": "sha256:root",
                    },
                    "agent_run_result": {
                        "input_view_hash": "sha256:input-view",
                        "agent_run_request_hash": "sha256:request",
                    },
                }
            ],
            "harness_validation": {"passed": True, "violations": []},
        },
        pre_final_decision_input={
            "input_ref": "trace:trace-1:pre_final_decision_input",
            "input_hash": "sha256:pre-final",
            "decision_effect": "none",
            "validation": {"passed": False, "violations": [{"rule_id": "decision_input.facts_gate_hard_fail"}]},
        },
    )

    assert bundle["schema_version"] == 1
    assert bundle["artifact_type"] == "pre_final_bundle"
    assert bundle["artifact_ref"] == "trace:trace-1:pre_final_bundle"
    assert bundle["decision_effect"] == "none"
    assert bundle["production_final_input"] is False
    assert bundle["notification_input"] is False
    assert bundle["symbol"] == "ETH-USDT-SWAP"
    assert bundle["facts_gate_ref"] == {
        "passed": False,
        "severity": "hard_fail",
        "missing_execution_facts": ["mark"],
        "artifact_hash": bundle["facts_gate_ref"]["artifact_hash"],
    }
    assert bundle["pre_final_decision_input_ref"] == {
        "input_ref": "trace:trace-1:pre_final_decision_input",
        "input_hash": "sha256:pre-final",
        "decision_effect": "none",
        "validation_passed": False,
        "artifact_hash": bundle["pre_final_decision_input_ref"]["artifact_hash"],
    }
    assert bundle["lead_plan_ref"]["plan_id"] == "shadow:trace-1"
    assert bundle["lead_plan_ref"]["decision_effect"] == "none"
    assert bundle["worker_manifest"] == [
        {
            "task_id": "shadow:RootCauseAgent",
            "agent_name": "RootCauseAgent",
            "status": "ok",
            "required": True,
            "failure_policy_applied": "none",
            "contribution_id": "shadow:RootCauseAgent",
            "input_ref": "trace:trace-1:worker:RootCauseAgent",
            "output_hash": "sha256:root",
            "input_view_hash": "sha256:input-view",
            "agent_run_request_hash": "sha256:request",
        }
    ]
    assert bundle["harness_validation_ref"]["passed"] is True
    assert bundle["coverage"] == {
        "has_facts_gate": True,
        "has_pre_final_decision_input": True,
        "has_lead_plan": True,
        "worker_count": 1,
        "required_worker_count": 1,
        "failed_worker_count": 0,
    }
    assert bundle["artifact_hash"].startswith("sha256:")
