from __future__ import annotations

import json
from typing import Any, Protocol

from crypto_manual_alert.decision.frozen_input import stable_hash


class DecisionInputExperimentSafetyError(ValueError):
    """Raised when an audit-only DecisionInput experiment receives effectful input."""


class ShadowFinalAdapter(Protocol):
    """Adapter used by eval-only DecisionInput experiments.

    It consumes a structured DecisionInput candidate and returns a raw shadow
    final response. The adapter is injected explicitly; this module does not
    read production config, write journal rows, or send notifications.
    """

    def run(self, payload: dict[str, Any]) -> str:
        """Run a shadow final decision from a DecisionInput candidate."""


class DecisionInputExperimentRunner:
    """Eval-only runner for shadow final decisions from DecisionInput.

    The result is a sidecar artifact with ``decision_effect=none``. It is not
    connected to FinalInputSelector and cannot promote production final input.
    """

    def __init__(self, *, final_adapter: ShadowFinalAdapter):
        self.final_adapter = final_adapter

    def run(
        self,
        *,
        decision_input_candidate: dict[str, Any],
        replayable_input_candidate: dict[str, Any],
    ) -> dict[str, Any]:
        _validate_audit_only_candidate("decision_input_candidate", decision_input_candidate)
        _validate_audit_only_candidate("replayable_input_candidate", replayable_input_candidate)

        base = _base_artifact(decision_input_candidate, replayable_input_candidate)
        try:
            raw_output = self.final_adapter.run(dict(decision_input_candidate))
        except Exception as exc:  # noqa: BLE001 - eval sidecar must record adapter failures, not raise into production.
            artifact = {
                **base,
                "status": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            return _with_artifact_hash(artifact)

        summary = _safe_shadow_final_summary(raw_output)
        artifact = {
            **base,
            "status": "completed",
            "shadow_final_summary": summary,
            "raw_output_hash": stable_hash({"raw_output": str(raw_output)}),
        }
        return _with_artifact_hash(artifact)


def _base_artifact(
    decision_input_candidate: dict[str, Any],
    replayable_input_candidate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "decision_input_shadow_final",
        "artifact_ref": "candidate:decision_input_shadow_final",
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "source_decision_input_ref": decision_input_candidate.get("input_ref"),
        "source_decision_input_hash": decision_input_candidate.get("input_hash"),
        "source_replayable_input_ref": replayable_input_candidate.get("input_ref"),
        "source_replayable_input_hash": replayable_input_candidate.get("input_hash"),
    }


def _validate_audit_only_candidate(name: str, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise DecisionInputExperimentSafetyError(f"{name} must be a mapping")
    if payload.get("decision_effect") != "none":
        raise DecisionInputExperimentSafetyError(f"{name} decision_effect must be none")
    if payload.get("production_final_input") is True:
        raise DecisionInputExperimentSafetyError(f"{name} production_final_input must be false")
    if payload.get("notification_input") is True:
        raise DecisionInputExperimentSafetyError(f"{name} notification_input must be false")
    if not payload.get("input_ref"):
        raise DecisionInputExperimentSafetyError(f"{name} input_ref is required")
    if not payload.get("input_hash"):
        raise DecisionInputExperimentSafetyError(f"{name} input_hash is required")


def _safe_shadow_final_summary(raw_output: Any) -> dict[str, Any]:
    parsed = _parse_json_object(raw_output)
    return {
        "instrument": parsed.get("instrument"),
        "main_action": parsed.get("main_action"),
        "probability": parsed.get("probability"),
    }


def _parse_json_object(raw_output: Any) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output
    try:
        parsed = json.loads(str(raw_output))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _with_artifact_hash(artifact: dict[str, Any]) -> dict[str, Any]:
    clean = dict(artifact)
    clean["artifact_hash"] = stable_hash(artifact)
    return clean
