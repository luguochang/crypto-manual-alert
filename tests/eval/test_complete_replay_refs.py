from __future__ import annotations

from crypto_manual_alert.eval.complete_replay_refs import (
    complete_replay_missing_refs,
    complete_replay_refs,
)


def test_complete_replay_refs_reports_missing_named_refs():
    refs = complete_replay_refs(
        {
            "has_final_decision_output": True,
            "has_final_input_selection": True,
            "has_parsed_plan": True,
            "has_risk_gate_result": True,
            "has_side_effect_policy": True,
        }
    )

    assert refs["has_final_decision_output"] is True
    assert refs["has_lead_synthesis_artifact"] is False
    assert complete_replay_missing_refs(refs) == [
        "lead_synthesis_artifact",
        "production_control_gate",
        "context_artifact_summary",
        "version_lock",
        "telemetry_refs",
        "evidence_snapshot_refs",
        "memory_snapshot_refs",
        "span_tree_refs",
    ]
