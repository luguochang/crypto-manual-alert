from __future__ import annotations

from typing import Any

from .side_effect_proof import validate_no_production_side_effect_proof


REQUIRED_WORKER_ARTIFACT_COUNT = 7
PROMOTION_REQUIRED_ARTIFACTS = (
    "no_production_side_effect_proof",
    "manual_approval",
    "rollback_plan",
    "impact_scope",
    "shadow_candidate_comparison",
)


def promotion_review(
    *,
    ready: bool,
    eval_run_id: str | None,
    promotion_artifacts: dict[str, dict[str, Any]],
    current_candidate_inputs: set[tuple[str, str]],
) -> dict[str, Any]:
    candidate_gate_status = "passed" if ready else "blocked"
    review: dict[str, Any] = {
        "status": "blocked" if not ready else "blocked_missing_artifacts",
        "decision_effect": "none",
        "candidate_gate_status": candidate_gate_status,
        "promotion_material_status": "not_evaluated" if not ready else "missing_required_artifacts",
        "allowed_to_change_production_final_input": False,
        "manual_approval_required": True,
        "approval_artifact_ref": None,
    }
    if not ready:
        return review

    required_artifacts = {
        artifact_name: required_artifact_status(
            artifact_name,
            promotion_artifacts,
            eval_run_id=eval_run_id,
            current_candidate_inputs=current_candidate_inputs,
        )
        for artifact_name in PROMOTION_REQUIRED_ARTIFACTS
    }
    review["required_artifacts"] = required_artifacts
    review["missing_artifacts"] = [
        artifact_name
        for artifact_name, artifact in required_artifacts.items()
        if not artifact["present"]
    ]
    if not review["missing_artifacts"]:
        review["status"] = "ready_for_manual_release_decision"
        review["promotion_material_status"] = "complete"
        release_decision = promotion_artifacts.get("manual_release_decision")
        if valid_manual_release_decision(
            release_decision,
            eval_run_id=eval_run_id,
            required_artifacts=required_artifacts,
            current_candidate_inputs=current_candidate_inputs,
        ):
            review["status"] = "ready_for_config_change_review"
            review["manual_release_decision_ref"] = release_decision.get("artifact_ref")
            review["config_change_review_required"] = True
            config_request = promotion_artifacts.get("config_change_review_request")
            if valid_config_change_review_request(
                config_request,
                eval_run_id=eval_run_id,
                release_decision=release_decision,
            ):
                review["status"] = "config_change_review_requested"
                review["config_change_review_request_ref"] = config_request.get("artifact_ref")
                config_approval = promotion_artifacts.get("config_change_review_approval")
                if valid_config_change_review_approval(
                    config_approval,
                    eval_run_id=eval_run_id,
                    release_decision=release_decision,
                    config_request=config_request,
                ):
                    review["status"] = "config_change_review_approved"
                    review["config_change_review_approval_ref"] = config_approval.get("artifact_ref")
                    review["runtime_switch_gate_required"] = True
    review["required_artifacts"] = public_required_artifacts(required_artifacts)
    return review


def required_artifact_status(
    artifact_name: str,
    promotion_artifacts: dict[str, dict[str, Any]],
    *,
    eval_run_id: str | None,
    current_candidate_inputs: set[tuple[str, str]],
) -> dict[str, Any]:
    artifact = promotion_artifacts.get(artifact_name)
    if not valid_promotion_artifact(
        artifact_name,
        artifact,
        eval_run_id=eval_run_id,
        current_candidate_inputs=current_candidate_inputs,
    ):
        return {"present": False, "artifact_ref": None}
    return {"present": True, "artifact_ref": artifact.get("artifact_ref"), "artifact": artifact}


def public_required_artifacts(required_artifacts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        artifact_name: {
            "present": artifact.get("present") is True,
            "artifact_ref": artifact.get("artifact_ref"),
        }
        for artifact_name, artifact in required_artifacts.items()
    }


def valid_promotion_artifact(
    artifact_name: str,
    artifact: dict[str, Any] | None,
    *,
    eval_run_id: str | None,
    current_candidate_inputs: set[tuple[str, str]],
) -> bool:
    if not eval_run_id:
        return False
    if not isinstance(artifact, dict):
        return False
    base_valid = (
        artifact.get("schema_version") == 1
        and artifact.get("artifact_type") == artifact_name
        and artifact.get("decision_effect") == "none"
        and bool(artifact.get("artifact_ref"))
    )
    if not base_valid:
        return False
    if artifact.get("eval_run_id") != eval_run_id:
        return False
    if not artifact_ref_matches(artifact_name, str(artifact.get("artifact_ref")), eval_run_id):
        return False
    if artifact_name == "manual_approval":
        return non_empty(artifact.get("approver")) and artifact.get("decision") == "approved_for_manual_promotion"
    if artifact_name == "rollback_plan":
        return non_empty(artifact.get("rollback_target")) and non_empty_list(artifact.get("rollback_steps"))
    if artifact_name == "impact_scope":
        return non_empty_list(artifact.get("affected_components")) and non_empty_list(
            artifact.get("excluded_components")
        )
    if artifact_name == "no_production_side_effect_proof":
        return validate_no_production_side_effect_proof(artifact, eval_run_id=eval_run_id)[0]
    if artifact_name == "shadow_candidate_comparison":
        case_count = safe_int(artifact.get("case_count"))
        available = safe_int(artifact.get("candidate_replay_available"))
        missing = safe_int(artifact.get("candidate_replay_missing"))
        worker_min = safe_int(artifact.get("worker_artifact_count_min"))
        switch_ready = safe_int(artifact.get("switch_ready_count"))
        summaries = artifact.get("case_summaries") if isinstance(artifact.get("case_summaries"), list) else []
        return (
            case_count > 0
            and available == case_count
            and missing == 0
            and worker_min >= REQUIRED_WORKER_ARTIFACT_COUNT
            and switch_ready == case_count
            and len(summaries) == case_count
            and all(clean_shadow_candidate_case(item) for item in summaries)
            and comparison_candidates_in_current_replay(summaries, current_candidate_inputs)
        )
    return True


def artifact_ref_matches(artifact_name: str, artifact_ref: str, eval_run_id: str) -> bool:
    if artifact_name == "manual_approval":
        return artifact_ref.startswith(f"eval:{eval_run_id}:manual_approval:") and not artifact_ref.endswith(":")
    return artifact_ref == f"eval:{eval_run_id}:{artifact_name}"


def valid_manual_release_decision(
    artifact: dict[str, Any] | None,
    *,
    eval_run_id: str | None,
    required_artifacts: dict[str, dict[str, Any]],
    current_candidate_inputs: set[tuple[str, str]],
) -> bool:
    if not isinstance(artifact, dict):
        return False
    if not eval_run_id:
        return False
    if (
        artifact.get("schema_version") != 1
        or artifact.get("artifact_type") != "manual_release_decision"
        or artifact.get("decision_effect") != "none"
        or artifact.get("decision") != "approved_for_config_change_review"
        or artifact.get("allowed_to_change_production_final_input") is not False
        or artifact.get("config_change_review_required") is not True
        or artifact.get("baseline_final_input_mode") != "legacy_prompt"
        or artifact.get("target_final_input_mode") != "decision_input"
        or not non_empty(artifact.get("release_manager"))
        or not non_empty(artifact.get("candidate_input_ref"))
        or not non_empty(artifact.get("candidate_input_hash"))
        or not non_empty(artifact.get("config_hash"))
    ):
        return False
    if artifact.get("eval_run_id") != eval_run_id:
        return False
    artifact_ref = str(artifact.get("artifact_ref") or "")
    if not artifact_ref.startswith(f"eval:{eval_run_id}:manual_release_decision:") or artifact_ref.endswith(":"):
        return False
    refs = artifact.get("required_artifact_refs")
    if not isinstance(refs, dict):
        return False
    for artifact_name in PROMOTION_REQUIRED_ARTIFACTS:
        expected = required_artifacts.get(artifact_name, {}).get("artifact_ref")
        if not expected or refs.get(artifact_name) != expected:
            return False
    comparison = required_artifacts.get("shadow_candidate_comparison", {}).get("artifact")
    if not manual_release_candidate_in_comparison(artifact, comparison):
        return False
    if not candidate_input_in_current_replay(artifact, current_candidate_inputs):
        return False
    return True


def manual_release_candidate_in_comparison(
    release_decision: dict[str, Any],
    comparison: dict[str, Any] | None,
) -> bool:
    if not isinstance(comparison, dict):
        return False
    summaries = comparison.get("case_summaries")
    if not isinstance(summaries, list):
        return False
    expected_ref = release_decision.get("candidate_input_ref")
    expected_hash = release_decision.get("candidate_input_hash")
    for item in summaries:
        if not isinstance(item, dict) or item.get("status") != "available":
            continue
        if item.get("decision_input_ref") == expected_ref and item.get("decision_input_hash") == expected_hash:
            return True
    return False


def comparison_candidates_in_current_replay(
    summaries: list[Any],
    current_candidate_inputs: set[tuple[str, str]],
) -> bool:
    if not current_candidate_inputs:
        return False
    for item in summaries:
        if not isinstance(item, dict) or item.get("status") != "available":
            continue
        candidate = (
            str(item.get("decision_input_ref") or ""),
            str(item.get("decision_input_hash") or ""),
        )
        if candidate not in current_candidate_inputs:
            return False
    return True


def valid_config_change_review_request(
    artifact: dict[str, Any] | None,
    *,
    eval_run_id: str | None,
    release_decision: dict[str, Any],
) -> bool:
    if not isinstance(artifact, dict):
        return False
    if not eval_run_id:
        return False
    if (
        artifact.get("schema_version") != 1
        or artifact.get("artifact_type") != "config_change_review_request"
        or artifact.get("decision_effect") != "none"
        or artifact.get("allowed_to_change_production_final_input") is not False
        or artifact.get("config_change_review_required") is not True
        or artifact.get("baseline_final_input_mode") != "legacy_prompt"
        or artifact.get("requested_final_input_mode") != "decision_input"
        or not non_empty(artifact.get("requester"))
        or not non_empty(artifact.get("manual_release_decision_ref"))
        or not non_empty(artifact.get("candidate_input_ref"))
        or not non_empty(artifact.get("candidate_input_hash"))
    ):
        return False
    if artifact.get("eval_run_id") != eval_run_id:
        return False
    artifact_ref = str(artifact.get("artifact_ref") or "")
    if not artifact_ref.startswith(f"eval:{eval_run_id}:config_change_review_request:") or artifact_ref.endswith(":"):
        return False
    return (
        artifact.get("manual_release_decision_ref") == release_decision.get("artifact_ref")
        and artifact.get("candidate_input_ref") == release_decision.get("candidate_input_ref")
        and artifact.get("candidate_input_hash") == release_decision.get("candidate_input_hash")
    )


def valid_config_change_review_approval(
    artifact: dict[str, Any] | None,
    *,
    eval_run_id: str | None,
    release_decision: dict[str, Any],
    config_request: dict[str, Any],
) -> bool:
    if not isinstance(artifact, dict):
        return False
    if not eval_run_id:
        return False
    if (
        artifact.get("schema_version") != 1
        or artifact.get("artifact_type") != "config_change_review_approval"
        or artifact.get("decision_effect") != "none"
        or artifact.get("decision") != "approved_for_final_input_config_change"
        or artifact.get("allowed_to_change_production_final_input") is not False
        or artifact.get("runtime_switch_gate_required") is not True
        or artifact.get("baseline_final_input_mode") != "legacy_prompt"
        or artifact.get("approved_final_input_mode") != "decision_input"
        or not non_empty(artifact.get("reviewer"))
        or not non_empty(artifact.get("config_change_review_request_ref"))
        or not non_empty(artifact.get("manual_release_decision_ref"))
        or not non_empty(artifact.get("candidate_input_ref"))
        or not non_empty(artifact.get("candidate_input_hash"))
        or not non_empty(artifact.get("config_hash"))
        or not non_empty(artifact.get("rollback_plan_ref"))
    ):
        return False
    if artifact.get("eval_run_id") != eval_run_id:
        return False
    artifact_ref = str(artifact.get("artifact_ref") or "")
    if not artifact_ref.startswith(f"eval:{eval_run_id}:config_change_review_approval:") or artifact_ref.endswith(":"):
        return False
    required_artifact_refs = release_decision.get("required_artifact_refs")
    rollback_plan_ref = (
        required_artifact_refs.get("rollback_plan")
        if isinstance(required_artifact_refs, dict)
        else None
    )
    return (
        artifact.get("config_change_review_request_ref") == config_request.get("artifact_ref")
        and artifact.get("manual_release_decision_ref") == release_decision.get("artifact_ref")
        and artifact.get("candidate_input_ref") == release_decision.get("candidate_input_ref")
        and artifact.get("candidate_input_hash") == release_decision.get("candidate_input_hash")
        and artifact.get("config_hash") == release_decision.get("config_hash")
        and artifact.get("rollback_plan_ref") == rollback_plan_ref
    )


def candidate_input_in_current_replay(
    artifact: dict[str, Any],
    current_candidate_inputs: set[tuple[str, str]],
) -> bool:
    return (
        str(artifact.get("candidate_input_ref") or ""),
        str(artifact.get("candidate_input_hash") or ""),
    ) in current_candidate_inputs


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def clean_shadow_candidate_case(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    shadow_final = item.get("decision_input_shadow_final")
    return (
        item.get("status") == "available"
        and item.get("worker_manifest_complete") is True
        and item.get("worker_manifest_consistency_passed") is True
        and item.get("context_artifact_consistency_passed") is True
        and item.get("switch_ready") is True
        and not item.get("blocking_reasons")
        and clean_shadow_final_summary(shadow_final)
        and clean_shadow_legacy_comparison(item.get("shadow_legacy_comparison"))
    )


def clean_shadow_final_summary(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("status") == "completed"
        and value.get("decision_effect") == "none"
        and non_empty(value.get("artifact_ref"))
        and non_empty(value.get("artifact_hash"))
        and non_empty(value.get("source_decision_input_ref"))
        and non_empty(value.get("source_decision_input_hash"))
        and non_empty(value.get("main_action"))
    )


def clean_shadow_legacy_comparison(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("status") == "available"
        and value.get("decision_effect") == "none"
        and non_empty(value.get("legacy_main_action"))
        and non_empty(value.get("shadow_main_action"))
        and isinstance(value.get("main_action_match"), bool)
        and isinstance(value.get("differences"), list)
    )


def non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(item for item in value)
