from __future__ import annotations

from crypto_manual_alert.decision.pre_final_input import build_pre_final_input_payload


def test_build_pre_final_input_payload_prefers_shadow_worker_contributions():
    lead_synthesis = {
        "decision_effect": "none",
        "included_contribution_ids": ["shadow-root"],
        "dropped_contributions": [],
        "supporting_thesis": [],
        "counter_thesis": [],
        "conflicts": [],
        "missing_facts": [],
    }
    payload = build_pre_final_input_payload(
        trace_id="trace-1",
        symbol="ETH-USDT-SWAP",
        audit_payload={
            "evidence_packets": [
                {
                    "evidence_id": "ev-mark",
                    "data_type": "mark",
                    "source_type": "search_derived",
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
            "agent_contributions": [
                {
                    "contribution_id": "legacy-root",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "required": True,
                    "summary": "legacy wrapper",
                }
            ],
        },
        shadow_swarm_audit={
            "lead_plan": {"tasks": [{"agent_name": "RootCauseAgent", "required": True}]},
            "lead_synthesis": lead_synthesis,
            "worker_results": [
                {
                    "contribution": {
                        "contribution_id": "shadow-root",
                        "agent_name": "RootCauseAgent",
                        "status": "ok",
                        "required": True,
                        "summary": "shadow worker",
                        "claims": [],
                        "constraints": {},
                        "conflicts": [],
                        "missing_facts": [],
                    }
                }
            ],
        },
    )

    assert payload["mode"] == "pre_final_candidate"
    assert payload["decision_effect"] == "none"
    assert payload["input_ref"] == "trace:trace-1:pre_final_decision_input"
    assert payload["lead_synthesis"]["included_contribution_ids"] == ["shadow-root"]
    assert payload["lead_synthesis"]["dropped_contributions"] == []
    assert "trigger long" not in payload["effective_allowed_actions"]
    assert "legacy_decision_ref" not in payload


def test_build_pre_final_input_payload_passes_lead_synthesis_as_single_source(monkeypatch):
    received: dict[str, object] = {}
    lead_synthesis = {"decision_effect": "none", "included_contribution_ids": ["shadow-root"]}

    class FakeDecisionInput:
        def to_public_dict(self):
            return {"mode": "pre_final_candidate", "decision_effect": "none"}

    def fake_builder(**kwargs):
        received.update(kwargs)
        return FakeDecisionInput()

    monkeypatch.setattr("crypto_manual_alert.decision.pre_final_input.build_pre_final_decision_input", fake_builder)

    build_pre_final_input_payload(
        trace_id="trace-1",
        symbol="ETH-USDT-SWAP",
        audit_payload={"evidence_packets": [], "facts_gate": {}, "agent_contributions": []},
        shadow_swarm_audit={
            "lead_plan": {"tasks": [{"agent_name": "RootCauseAgent", "required": True}]},
            "lead_synthesis": lead_synthesis,
            "worker_results": [],
        },
    )

    assert received["lead_synthesis"] is lead_synthesis
    assert "lead_plan" not in received


def test_build_pre_final_input_payload_returns_failed_audit_payload_when_builder_crashes(monkeypatch):
    def exploding_builder(**kwargs):
        raise RuntimeError("pre-final builder crashed")

    monkeypatch.setattr("crypto_manual_alert.decision.pre_final_input.build_pre_final_decision_input", exploding_builder)

    payload = build_pre_final_input_payload(
        trace_id="trace-1",
        symbol="ETH-USDT-SWAP",
        audit_payload={"evidence_packets": [], "facts_gate": {}},
        shadow_swarm_audit={"lead_synthesis": {"decision_effect": "none"}},
    )

    assert payload == {
        "schema_version": 1,
        "mode": "pre_final_candidate",
        "decision_effect": "none",
        "trace_id": "trace-1",
        "symbol": "ETH-USDT-SWAP",
        "error": {"type": "RuntimeError", "message": "pre-final builder crashed"},
        "validation": {
            "passed": False,
            "severity": "hard_fail",
            "violations": [{"rule_id": "pre_final_decision_input.build_failed"}],
        },
    }
