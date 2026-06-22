from __future__ import annotations

from typing import Any


COMPLETE_REPLAY_REF_KEYS = {
    "lead_synthesis_artifact": "has_lead_synthesis_artifact",
    "final_decision_output": "has_final_decision_output",
    "final_input_selection": "has_final_input_selection",
    "parsed_plan": "has_parsed_plan",
    "production_control_gate": "has_production_control_gate",
    "risk_gate_result": "has_risk_gate_result",
    "side_effect_policy": "has_side_effect_policy",
    "context_artifact_summary": "has_context_artifact_summary",
    "version_lock": "has_version_lock",
    "telemetry_refs": "has_telemetry_refs",
    "evidence_snapshot_refs": "has_evidence_snapshot_refs",
    "memory_snapshot_refs": "has_memory_snapshot_refs",
    "span_tree_refs": "has_span_tree_refs",
}


def complete_replay_refs(coverage: dict[str, Any]) -> dict[str, bool]:
    return {coverage_key: coverage.get(coverage_key) is True for coverage_key in COMPLETE_REPLAY_REF_KEYS.values()}


def complete_replay_missing_refs(refs: dict[str, bool]) -> list[str]:
    return [
        ref_name
        for ref_name, coverage_key in COMPLETE_REPLAY_REF_KEYS.items()
        if refs.get(coverage_key) is not True
    ]
