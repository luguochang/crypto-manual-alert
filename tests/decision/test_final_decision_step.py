from __future__ import annotations

from crypto_manual_alert.decision.final_decision_step import run_final_decision_step


class CapturingDecisionEngine:
    def __init__(self):
        self.input_payload = None

    def run(self, input_payload):
        self.input_payload = input_payload
        return '{"main_action":"no trade"}'


def test_run_final_decision_step_uses_legacy_prompt_selection_without_decision_input():
    engine = CapturingDecisionEngine()
    legacy_prompt_packet = {"market_snapshot": {"symbol": "ETH-USDT-SWAP"}}

    result = run_final_decision_step(
        decision_engine=engine,
        final_input_mode="legacy_prompt",
        legacy_prompt_packet=legacy_prompt_packet,
    )

    assert engine.input_payload == legacy_prompt_packet
    assert result.raw_decision == '{"main_action":"no trade"}'
    assert result.final_input_selection == {
        "mode": "legacy_prompt",
        "source_ref": "legacy_prompt_packet",
        "decision_effect": "production_final_input",
        "readiness_ready": False,
    }
    assert result.output_summary == {"raw_decision_chars": 26}


def test_run_final_decision_step_keeps_legacy_prompt_even_when_decision_input_is_ready():
    engine = CapturingDecisionEngine()
    legacy_prompt_packet = {"legacy": True}
    decision_input = {
        "schema_version": 1,
        "mode": "candidate_audit",
        "decision_effect": "none",
        "input_ref": "trace:1:decision_input_candidate",
        "input_hash": "sha256:decision-input",
        "validation": {"passed": True, "violations": []},
    }

    result = run_final_decision_step(
        decision_engine=engine,
        final_input_mode="legacy_prompt",
        legacy_prompt_packet=legacy_prompt_packet,
        decision_input_candidate=decision_input,
        switch_readiness={"ready": True, "blocking_reasons": []},
    )

    assert engine.input_payload is legacy_prompt_packet
    assert result.final_input_selection == {
        "mode": "legacy_prompt",
        "source_ref": "legacy_prompt_packet",
        "decision_effect": "production_final_input",
        "readiness_ready": False,
    }


def test_run_final_decision_step_can_call_engine_with_valid_decision_input():
    engine = CapturingDecisionEngine()
    decision_input = {
        "schema_version": 1,
        "mode": "candidate_audit",
        "decision_effect": "none",
        "input_ref": "trace:1:decision_input_candidate",
        "input_hash": "sha256:decision-input",
        "validation": {"passed": True, "violations": []},
        "effective_allowed_actions": ["no trade"],
    }

    result = run_final_decision_step(
        decision_engine=engine,
        final_input_mode="decision_input",
        legacy_prompt_packet={"legacy": True},
        decision_input_candidate=decision_input,
        switch_readiness={"ready": True, "blocking_reasons": []},
    )

    assert engine.input_payload["source_candidate_ref"] == "trace:1:decision_input_candidate"
    assert engine.input_payload["decision_effect"] == "production_final_input"
    assert result.final_input_selection == {
        "mode": "decision_input",
        "source_ref": "trace:1:decision_input_candidate",
        "decision_effect": "production_final_input",
        "readiness_ready": True,
    }
