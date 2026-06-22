from __future__ import annotations

from typing import Any


def validate_promotion_artifact(
    eval_run_id: str,
    artifact_type: str,
    artifact: Any,
) -> None:
    if not isinstance(artifact, dict):
        raise ValueError("promotion artifact must be a mapping")
    if artifact.get("eval_run_id") != eval_run_id:
        raise ValueError("promotion artifact eval_run_id mismatch")
    if artifact.get("artifact_type") != artifact_type:
        raise ValueError("promotion artifact type mismatch")
    if artifact.get("decision_effect") != "none":
        raise ValueError("promotion artifact decision_effect must be none")
    if artifact.get("schema_version") != 1:
        raise ValueError("promotion artifact schema_version must be 1")
    if not artifact.get("artifact_ref"):
        raise ValueError("promotion artifact artifact_ref is required")
    if not _promotion_artifact_ref_matches(artifact_type, str(artifact.get("artifact_ref")), eval_run_id):
        raise ValueError("promotion artifact_ref mismatch")
    if artifact_type == "config_change_review_request":
        _validate_config_change_review_request_artifact(artifact)
    if artifact_type == "config_change_review_approval":
        _validate_config_change_review_approval_artifact(artifact)


def _promotion_artifact_ref_matches(artifact_type: str, artifact_ref: str, eval_run_id: str) -> bool:
    if artifact_type in {
        "manual_approval",
        "manual_release_decision",
        "config_change_review_request",
        "config_change_review_approval",
    }:
        return artifact_ref.startswith(f"eval:{eval_run_id}:{artifact_type}:") and not artifact_ref.endswith(":")
    return artifact_ref == f"eval:{eval_run_id}:{artifact_type}"


def _validate_config_change_review_request_artifact(artifact: dict[str, Any]) -> None:
    if artifact.get("allowed_to_change_production_final_input") is not False:
        raise ValueError("config review request cannot allow production final input changes")
    if artifact.get("config_change_review_required") is not True:
        raise ValueError("config review request must require config change review")
    if artifact.get("baseline_final_input_mode") != "legacy_prompt":
        raise ValueError("config review request baseline_final_input_mode must be legacy_prompt")
    if artifact.get("requested_final_input_mode") != "decision_input":
        raise ValueError("config review request requested_final_input_mode must be decision_input")
    if not artifact.get("manual_release_decision_ref"):
        raise ValueError("config review request manual_release_decision_ref is required")
    if not artifact.get("candidate_input_ref"):
        raise ValueError("config review request candidate_input_ref is required")
    if not artifact.get("candidate_input_hash"):
        raise ValueError("config review request candidate_input_hash is required")
    if not artifact.get("requester"):
        raise ValueError("config review request requester is required")


def _validate_config_change_review_approval_artifact(artifact: dict[str, Any]) -> None:
    if artifact.get("allowed_to_change_production_final_input") is not False:
        raise ValueError("config review approval cannot directly allow production final input changes")
    if artifact.get("runtime_switch_gate_required") is not True:
        raise ValueError("config review approval must require runtime switch gate")
    if artifact.get("baseline_final_input_mode") != "legacy_prompt":
        raise ValueError("config review approval baseline_final_input_mode must be legacy_prompt")
    if artifact.get("approved_final_input_mode") != "decision_input":
        raise ValueError("config review approval approved_final_input_mode must be decision_input")
    if artifact.get("decision") != "approved_for_final_input_config_change":
        raise ValueError("config review approval decision is invalid")
    for field_name in (
        "reviewer",
        "config_change_review_request_ref",
        "manual_release_decision_ref",
        "candidate_input_ref",
        "candidate_input_hash",
        "config_hash",
        "rollback_plan_ref",
    ):
        if not artifact.get(field_name):
            raise ValueError(f"config review approval {field_name} is required")
