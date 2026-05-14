from __future__ import annotations

from typing import Any


def project_input_lineage(
    *,
    payload: dict[str, Any],
    decision_input: dict[str, Any],
    candidate_final_comparison: dict[str, Any],
) -> dict[str, Any]:
    selection = _mapping(payload.get("final_input_selection"))
    mode = str(selection.get("mode") or "legacy_prompt")
    decision_input_ref = decision_input.get("input_ref")
    return {
        "production_final_input_mode": mode,
        "production_final_input_source_ref": selection.get("source_ref"),
        "production_decision_effect": selection.get("decision_effect"),
        "decision_input": _drop_none(
            {
                "mode": decision_input.get("mode"),
                "input_ref": decision_input_ref,
                "input_hash": decision_input.get("input_hash"),
                "decision_effect": decision_input.get("decision_effect"),
                "selected_as_final_input": mode == "decision_input"
                and bool(decision_input_ref)
                and selection.get("source_ref") == decision_input_ref,
            }
        ),
        "candidate_final": _drop_none(
            {
                "status": candidate_final_comparison.get("status"),
                "decision_effect": candidate_final_comparison.get("decision_effect"),
                "production_final_input": candidate_final_comparison.get("production_final_input"),
            }
        ),
        "audit_only_payloads": _audit_only_payloads(payload),
    }


def _audit_only_payloads(payload: dict[str, Any]) -> list[str]:
    names = [
        "shadow_swarm_audit",
        "pre_final_decision_input",
        "decision_input_candidate",
        "candidate_final_decision",
        "replayable_input_candidate",
        "lead_synthesis_artifact",
        "gate_candidate",
        "plan_semantic_candidate",
        "final_decision_switch_readiness",
    ]
    return [name for name in names if payload.get(name) is not None]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
