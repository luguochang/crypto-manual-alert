from __future__ import annotations

from typing import Any


CANDIDATE_ARTIFACT_TYPES = [
    "decision_input_candidate",
    "replayable_input_candidate",
    "lead_synthesis",
    "worker_result_manifest",
    "gate_candidate",
    "plan_semantic_candidate",
    "final_decision_switch_readiness",
]


def validate_candidate_artifact_snapshot(snapshot: dict[str, Any]) -> None:
    if (
        snapshot.get("decision_effect") != "none"
        or snapshot.get("production_final_input") is not False
        or snapshot.get("notification_input") is not False
    ):
        raise ValueError("candidate artifact snapshot decision_effect must be none")


def validate_candidate_artifact(case_id: str, artifact_type: str, artifact: dict[str, Any]) -> None:
    if not artifact.get("artifact_hash"):
        raise ValueError("candidate artifact artifact_hash is required")
    if artifact.get("decision_effect") != "none":
        raise ValueError("candidate artifact decision_effect must be none")
    if artifact_type == "decision_input_candidate" and not str(artifact.get("input_ref")).endswith(
        ":decision_input_candidate"
    ):
        raise ValueError("candidate decision input artifact_ref mismatch")
    if artifact_type == "replayable_input_candidate" and not str(artifact.get("input_ref")).endswith(
        ":replayable_input_candidate"
    ):
        raise ValueError("candidate replayable input artifact_ref mismatch")
    if artifact_type in {
        "lead_synthesis",
        "worker_result_manifest",
        "gate_candidate",
        "plan_semantic_candidate",
        "final_decision_switch_readiness",
    } and artifact.get("artifact_ref") != f"candidate:{artifact_type}":
        raise ValueError("candidate artifact_ref mismatch")
    if artifact_type in {"decision_input_candidate", "replayable_input_candidate"} and not artifact.get("input_ref"):
        raise ValueError("candidate artifact input_ref is required")


def candidate_artifact_ref(artifact: dict[str, Any]) -> str:
    return str(artifact.get("input_ref") or artifact.get("artifact_ref") or "")
