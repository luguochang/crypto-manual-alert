from __future__ import annotations

from typing import Any


def context_artifact_consistency(
    *,
    context_artifacts: dict[str, Any],
    decision_input: dict[str, Any],
    replayable_input: dict[str, Any],
    artifact_refs: dict[str, Any],
    candidate_artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not context_artifacts:
        return {"passed": False, "violations": [{"rule_id": "context_artifacts_missing"}]}
    violations: list[dict[str, Any]] = []
    context_decision_ref = (
        context_artifacts.get("decision_input_ref")
        if isinstance(context_artifacts.get("decision_input_ref"), dict)
        else {}
    )
    gate_refs = (
        context_artifacts.get("gate_result_refs")
        if isinstance(context_artifacts.get("gate_result_refs"), dict)
        else {}
    )
    context_candidate_decision_ref = (
        gate_refs.get("decision_input_candidate")
        if isinstance(gate_refs.get("decision_input_candidate"), dict)
        else context_decision_ref
    )
    if (
        decision_input.get("input_ref")
        and context_candidate_decision_ref.get("input_ref") != decision_input.get("input_ref")
    ):
        violations.append(
            {
                "rule_id": "context_decision_input_ref_mismatch",
                "expected": decision_input.get("input_ref"),
                "observed": context_candidate_decision_ref.get("input_ref"),
            }
        )
    if (
        decision_input.get("input_hash")
        and context_candidate_decision_ref.get("input_hash") != decision_input.get("input_hash")
    ):
        violations.append(
            {
                "rule_id": "context_decision_input_hash_mismatch",
                "expected": decision_input.get("input_hash"),
                "observed": context_candidate_decision_ref.get("input_hash"),
            }
        )
    context_replay_ref = (
        gate_refs.get("replayable_input_candidate")
        if isinstance(gate_refs.get("replayable_input_candidate"), dict)
        else {}
    )
    if replayable_input.get("input_ref") and context_replay_ref.get("input_ref") != replayable_input.get("input_ref"):
        violations.append(
            {
                "rule_id": "context_replayable_input_ref_mismatch",
                "expected": replayable_input.get("input_ref"),
                "observed": context_replay_ref.get("input_ref"),
            }
        )
    if replayable_input.get("input_hash") and context_replay_ref.get("input_hash") != replayable_input.get("input_hash"):
        violations.append(
            {
                "rule_id": "context_replayable_input_hash_mismatch",
                "expected": replayable_input.get("input_hash"),
                "observed": context_replay_ref.get("input_hash"),
            }
        )
    evidence_refs = context_artifacts.get("evidence_refs") if isinstance(context_artifacts.get("evidence_refs"), list) else []
    contribution_refs = (
        context_artifacts.get("contribution_refs")
        if isinstance(context_artifacts.get("contribution_refs"), list)
        else []
    )
    expected_evidence_count = context_artifacts.get("evidence_count")
    if isinstance(expected_evidence_count, int) and len(evidence_refs) != expected_evidence_count:
        violations.append(
            {
                "rule_id": "context_evidence_count_mismatch",
                "expected": expected_evidence_count,
                "observed": len(evidence_refs),
            }
        )
    expected_contribution_count = context_artifacts.get("contribution_count")
    if isinstance(expected_contribution_count, int) and len(contribution_refs) != expected_contribution_count:
        violations.append(
            {
                "rule_id": "context_contribution_count_mismatch",
                "expected": expected_contribution_count,
                "observed": len(contribution_refs),
            }
        )
    decision_ref = artifact_refs.get("decision_input_candidate")
    if isinstance(decision_ref, dict) and context_candidate_decision_ref:
        if decision_ref.get("input_ref") != context_candidate_decision_ref.get("input_ref"):
            violations.append({"rule_id": "artifact_ref_context_decision_input_ref_mismatch"})
        if decision_ref.get("input_hash") != context_candidate_decision_ref.get("input_hash"):
            violations.append({"rule_id": "artifact_ref_context_decision_input_hash_mismatch"})
    append_context_candidate_artifact_violations(
        violations,
        gate_refs=gate_refs,
        candidate_artifacts=candidate_artifacts,
    )
    return {"passed": not violations, "violations": violations}


def append_context_candidate_artifact_violations(
    violations: list[dict[str, Any]],
    *,
    gate_refs: dict[str, Any],
    candidate_artifacts: dict[str, dict[str, Any]],
) -> None:
    for context_name, artifact_type in (
        ("lead_synthesis_artifact", "lead_synthesis"),
        ("gate_candidate", "gate_candidate"),
        ("plan_semantic_candidate", "plan_semantic_candidate"),
        ("final_decision_switch_readiness", "final_decision_switch_readiness"),
    ):
        context_ref = gate_refs.get(context_name) if isinstance(gate_refs.get(context_name), dict) else {}
        sidecar_artifact = candidate_artifacts.get(artifact_type)
        if not context_ref:
            if isinstance(sidecar_artifact, dict):
                violations.append(
                    {
                        "rule_id": f"context_{artifact_type}_artifact_ref_missing",
                        "artifact_type": artifact_type,
                    }
                )
            continue
        if not isinstance(sidecar_artifact, dict):
            violations.append(
                {
                    "rule_id": f"context_{artifact_type}_artifact_missing",
                    "artifact_type": artifact_type,
                }
            )
            continue
        context_artifact_ref = context_ref.get("artifact_ref")
        sidecar_artifact_ref = sidecar_artifact.get("artifact_ref")
        if context_artifact_ref and sidecar_artifact_ref and context_artifact_ref != sidecar_artifact_ref:
            violations.append(
                {
                    "rule_id": f"context_{artifact_type}_artifact_ref_mismatch",
                    "expected": sidecar_artifact_ref,
                    "observed": context_artifact_ref,
                }
            )
        context_hash = context_ref.get("artifact_hash")
        sidecar_hash = sidecar_artifact.get("artifact_hash")
        if context_hash and sidecar_hash and context_hash != sidecar_hash:
            violations.append(
                {
                    "rule_id": f"context_{artifact_type}_artifact_hash_mismatch",
                    "expected": sidecar_hash,
                    "observed": context_hash,
                }
            )
