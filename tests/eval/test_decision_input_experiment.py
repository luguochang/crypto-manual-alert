from __future__ import annotations

import json

import pytest

from crypto_manual_alert.eval.decision_input_experiment import (
    DecisionInputExperimentRunner,
    DecisionInputExperimentSafetyError,
)


def _decision_input_candidate() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "candidate_audit",
        "decision_effect": "none",
        "trace_id": "trace-1",
        "symbol": "ETH-USDT-SWAP",
        "input_ref": "trace:trace-1:decision_input_candidate",
        "input_hash": "sha256:decision-input",
        "effective_allowed_actions": ["no trade", "trigger long"],
        "lead_synthesis": {"summary": "safe synthesis"},
    }


def _replayable_input_candidate() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "candidate_replay",
        "decision_effect": "none",
        "input_ref": "trace:trace-1:replayable_input_candidate",
        "input_hash": "sha256:replayable-input",
        "coverage": {"worker_artifact_count": 4},
    }


def test_decision_input_experiment_runs_shadow_final_without_production_effect():
    captured_payloads: list[dict[str, object]] = []

    class FixtureShadowFinal:
        def run(self, payload):
            captured_payloads.append(payload)
            return json.dumps(
                {
                    "instrument": "ETH-USDT-SWAP",
                    "main_action": "no trade",
                    "probability": 0.52,
                    "notes": "shadow-only decision",
                    "raw_prompt": "must not leak",
                }
            )

    runner = DecisionInputExperimentRunner(final_adapter=FixtureShadowFinal())

    result = runner.run(
        decision_input_candidate=_decision_input_candidate(),
        replayable_input_candidate=_replayable_input_candidate(),
    )

    assert captured_payloads == [_decision_input_candidate()]
    assert result["schema_version"] == 1
    assert result["artifact_type"] == "decision_input_shadow_final"
    assert result["artifact_ref"] == "candidate:decision_input_shadow_final"
    assert result["decision_effect"] == "none"
    assert result["production_final_input"] is False
    assert result["notification_input"] is False
    assert result["status"] == "completed"
    assert result["source_decision_input_ref"] == "trace:trace-1:decision_input_candidate"
    assert result["source_decision_input_hash"] == "sha256:decision-input"
    assert result["source_replayable_input_ref"] == "trace:trace-1:replayable_input_candidate"
    assert result["source_replayable_input_hash"] == "sha256:replayable-input"
    assert result["shadow_final_summary"] == {
        "instrument": "ETH-USDT-SWAP",
        "main_action": "no trade",
        "probability": 0.52,
    }
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert "raw_prompt" not in rendered
    assert "must not leak" not in rendered
    assert "shadow-only decision" not in rendered
    assert result["raw_output_hash"]
    assert result["artifact_hash"]


def test_decision_input_experiment_rejects_effectful_candidate_inputs():
    class NeverCalled:
        def run(self, payload):  # pragma: no cover - should not be reached
            raise AssertionError("adapter should not run")

    unsafe = _decision_input_candidate()
    unsafe["decision_effect"] = "production_final_input"

    runner = DecisionInputExperimentRunner(final_adapter=NeverCalled())

    with pytest.raises(DecisionInputExperimentSafetyError, match="decision_effect must be none"):
        runner.run(
            decision_input_candidate=unsafe,
            replayable_input_candidate=_replayable_input_candidate(),
        )


def test_decision_input_experiment_records_adapter_failures_as_no_effect_artifact():
    class FailingShadowFinal:
        def run(self, payload):
            raise RuntimeError("shadow final down")

    runner = DecisionInputExperimentRunner(final_adapter=FailingShadowFinal())

    result = runner.run(
        decision_input_candidate=_decision_input_candidate(),
        replayable_input_candidate=_replayable_input_candidate(),
    )

    assert result["status"] == "failed"
    assert result["decision_effect"] == "none"
    assert result["production_final_input"] is False
    assert result["notification_input"] is False
    assert result["error"] == {
        "type": "RuntimeError",
        "message": "shadow final down",
    }
