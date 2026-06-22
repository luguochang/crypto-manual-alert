from __future__ import annotations

import json
from typing import Any


def build_candidate_final_legacy_comparison(
    *,
    observed_output: dict[str, Any] | None,
    candidate_final_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    if not _completed_no_effect_candidate_final(candidate_final_decision):
        return {
            "status": "missing_candidate_final",
            "decision_effect": "none",
            "differences": ["candidate_final_unavailable"],
        }

    legacy_summary = _legacy_observed_summary(observed_output)
    candidate_summary = _candidate_final_summary(candidate_final_decision)
    if not candidate_summary.get("main_action"):
        return {
            "status": "missing_candidate_final",
            "decision_effect": "none",
            "differences": ["candidate_final_unavailable"],
        }
    if not legacy_summary.get("main_action"):
        return {
            "status": "missing_legacy_observed",
            "decision_effect": "none",
            "candidate_final_summary": candidate_summary,
            "differences": ["legacy_observed_unavailable"],
        }

    main_action_match = legacy_summary.get("main_action") == candidate_summary.get("main_action")
    probability_delta = _probability_delta(
        legacy_summary.get("probability"),
        candidate_summary.get("probability"),
    )
    differences = []
    if not main_action_match:
        differences.append("main_action_changed")
    if probability_delta is not None and probability_delta != 0:
        differences.append("probability_changed")
    return {
        "status": "available",
        "decision_effect": "none",
        "legacy_observed_summary": legacy_summary,
        "candidate_final_summary": candidate_summary,
        "main_action_match": main_action_match,
        "probability_delta": probability_delta,
        "differences": differences,
    }


def build_shadow_legacy_comparison(
    *,
    observed_output: dict[str, Any] | None,
    shadow_final: dict[str, Any] | None,
) -> dict[str, Any]:
    if not _completed_no_effect_shadow_final(shadow_final):
        return {
            "status": "missing_shadow_final",
            "decision_effect": "none",
            "differences": ["shadow_final_unavailable"],
        }

    legacy_summary = _legacy_observed_summary(observed_output)
    shadow_summary = _shadow_final_summary(shadow_final)
    if not legacy_summary.get("main_action"):
        return {
            "status": "missing_legacy_observed",
            "decision_effect": "none",
            "shadow_final_summary": shadow_summary,
            "differences": ["legacy_observed_unavailable"],
        }

    main_action_match = legacy_summary.get("main_action") == shadow_summary.get("main_action")
    probability_delta = _probability_delta(
        legacy_summary.get("probability"),
        shadow_summary.get("probability"),
    )
    differences = []
    if not main_action_match:
        differences.append("main_action_changed")
    if probability_delta is not None and probability_delta != 0:
        differences.append("probability_changed")
    return {
        "status": "available",
        "decision_effect": "none",
        "legacy_observed_summary": legacy_summary,
        "shadow_final_summary": shadow_summary,
        "main_action_match": main_action_match,
        "probability_delta": probability_delta,
        "differences": differences,
    }


def _completed_no_effect_shadow_final(shadow_final: dict[str, Any] | None) -> bool:
    return (
        isinstance(shadow_final, dict)
        and shadow_final.get("status") == "completed"
        and shadow_final.get("decision_effect") == "none"
    )


def _completed_no_effect_candidate_final(candidate_final_decision: dict[str, Any] | None) -> bool:
    return (
        isinstance(candidate_final_decision, dict)
        and candidate_final_decision.get("artifact_type") == "candidate_final_decision"
        and candidate_final_decision.get("decision_effect") == "none"
        and candidate_final_decision.get("production_final_input") is False
        and candidate_final_decision.get("input_gate_passed") is True
        and not candidate_final_decision.get("error")
    )


def _legacy_observed_summary(observed_output: dict[str, Any] | None) -> dict[str, Any]:
    parsed_plan = observed_output.get("parsed_plan") if isinstance(observed_output, dict) else None
    parsed = parsed_plan if isinstance(parsed_plan, dict) else {}
    return {
        "main_action": _safe_text(parsed.get("main_action")),
        "probability": _safe_probability(parsed.get("probability")),
    }


def _candidate_final_summary(candidate_final_decision: dict[str, Any] | None) -> dict[str, Any]:
    summary = (
        candidate_final_decision.get("candidate_final_summary")
        if isinstance(candidate_final_decision, dict)
        else None
    )
    parsed = summary if isinstance(summary, dict) else _candidate_final_raw_summary(candidate_final_decision)
    result = {
        "main_action": _safe_text(parsed.get("main_action")),
        "probability": _safe_probability(parsed.get("probability")),
    }
    instrument = _safe_text(parsed.get("instrument"))
    if instrument is not None:
        result = {"instrument": instrument, **result}
    return result


def _candidate_final_raw_summary(candidate_final_decision: dict[str, Any] | None) -> dict[str, Any]:
    raw_output = (
        candidate_final_decision.get("raw_candidate_decision")
        if isinstance(candidate_final_decision, dict)
        else None
    )
    if isinstance(raw_output, dict):
        return raw_output
    try:
        parsed = json.loads(str(raw_output))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _shadow_final_summary(shadow_final: dict[str, Any] | None) -> dict[str, Any]:
    summary = shadow_final.get("shadow_final_summary") if isinstance(shadow_final, dict) else None
    parsed = summary if isinstance(summary, dict) else {}
    return {
        "main_action": _safe_text(parsed.get("main_action")),
        "probability": _safe_probability(parsed.get("probability")),
    }


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _safe_probability(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _probability_delta(legacy_probability: Any, shadow_probability: Any) -> float | None:
    if not isinstance(legacy_probability, (int, float)) or isinstance(legacy_probability, bool):
        return None
    if not isinstance(shadow_probability, (int, float)) or isinstance(shadow_probability, bool):
        return None
    return round(float(shadow_probability) - float(legacy_probability), 6)
