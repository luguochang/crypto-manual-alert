from __future__ import annotations

import copy
from typing import Any


FORBIDDEN_CANDIDATE_INPUT_KEYS = {
    "legacy_prompt",
    "prompt_packet",
    "raw_decision",
    "frozen_input",
    "frozen_input_hash",
}


def run_candidate_final_decision_sidecar(
    *,
    decision_engine: Any,
    pre_final_decision_input: dict[str, Any] | None,
    input_gate: dict[str, Any],
) -> dict[str, Any]:
    """Run an audit-only candidate final decision from gated DecisionInput.

    This sidecar never produces a production final input. It is a separate
    candidate experiment path from `run_final_decision_step()`.
    """

    input_ref = _input_value(pre_final_decision_input, "input_ref")
    input_hash = _input_value(pre_final_decision_input, "input_hash")
    if input_gate.get("passed") is not True:
        return _sidecar_payload(
            input_ref=input_ref,
            input_hash=input_hash,
            input_gate_passed=False,
            raw_candidate_decision=None,
            error={
                "type": "input_gate_failed",
                "violations": list(input_gate.get("violations") or []),
            },
            diagnosis=_input_gate_diagnosis(input_gate),
        )
    if not isinstance(pre_final_decision_input, dict):
        return _sidecar_payload(
            input_ref=input_ref,
            input_hash=input_hash,
            input_gate_passed=False,
            raw_candidate_decision=None,
            error={"type": "decision_input_missing"},
            diagnosis={
                "summary": "candidate final sidecar blocked because DecisionInput is missing",
                "blocking_reasons": ["decision_input_missing"],
            },
        )

    candidate_input = copy.deepcopy(pre_final_decision_input)
    for key in FORBIDDEN_CANDIDATE_INPUT_KEYS:
        candidate_input.pop(key, None)
    candidate_input["mode"] = "candidate_final_input"
    candidate_input["decision_effect"] = "none"
    candidate_input["source_candidate_ref"] = input_ref
    candidate_input["source_candidate_hash"] = input_hash
    try:
        raw_candidate_decision = str(decision_engine.run(candidate_input))
    except Exception as exc:  # noqa: BLE001 - candidate sidecar must not affect production final.
        return _sidecar_payload(
            input_ref=input_ref,
            input_hash=input_hash,
            input_gate_passed=True,
            raw_candidate_decision=None,
            error={"type": type(exc).__name__, "message": str(exc)},
            diagnosis={
                "summary": "candidate final sidecar engine failed",
                "blocking_reasons": [type(exc).__name__],
            },
        )
    return _sidecar_payload(
        input_ref=input_ref,
        input_hash=input_hash,
        input_gate_passed=True,
        raw_candidate_decision=raw_candidate_decision,
        error=None,
        diagnosis=None,
    )


def _sidecar_payload(
    *,
    input_ref: Any,
    input_hash: Any,
    input_gate_passed: bool,
    raw_candidate_decision: str | None,
    error: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        "artifact_type": "candidate_final_decision",
        "mode": "candidate_final_sidecar",
        "decision_effect": "none",
        "production_final_input": False,
        "input_ref": input_ref,
        "input_hash": input_hash,
        "input_gate_passed": input_gate_passed,
        "raw_candidate_decision": raw_candidate_decision,
        "error": error,
    }
    if diagnosis is not None:
        payload["diagnosis"] = diagnosis
    return payload


def _input_value(payload: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(payload, dict):
        return None
    return payload.get(key)


def _input_gate_diagnosis(input_gate: dict[str, Any]) -> dict[str, Any]:
    violations = input_gate.get("violations") if isinstance(input_gate, dict) else []
    rule_ids = [
        str(item.get("rule_id"))
        for item in violations or []
        if isinstance(item, dict) and item.get("rule_id")
    ]
    return {
        "summary": "candidate final sidecar blocked by input gate",
        "blocking_reasons": rule_ids,
    }
