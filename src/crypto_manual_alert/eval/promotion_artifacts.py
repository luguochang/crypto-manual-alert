from __future__ import annotations

from typing import Any

from crypto_manual_alert.eval.schema import EvalReplayOutput


SAFE_BLOCKED_ACTIONS = {
    "open long",
    "open short",
    "trigger long",
    "trigger short",
    "flip long to short",
    "flip short to long",
    "increase long",
    "increase short",
}
SAFE_MISSING_FACTS = {
    "mark",
    "index",
    "order_book",
    "funding",
    "open_interest",
    "liquidation",
    "basis",
    "options",
    "macro",
    "news",
    "sentiment",
}
SAFE_BLOCKING_REASONS = {
    "candidate_gate_failed",
    "plan_semantic_candidate_failed",
    "worker_manifest_consistency_failed",
    "context_artifact_consistency_failed",
    "final_switch_readiness_not_ready",
    "worker_artifact_coverage_incomplete",
    "worker_manifest_incomplete",
    "execution_fact_source_violation",
    "candidate_block_evidence_incomplete",
}


def build_manual_approval(
    *,
    eval_run_id: str,
    approver: str,
    decision: str,
    notes: str,
) -> dict[str, Any]:
    """Build an explicit manual approval artifact for promotion review."""

    if not _non_empty(approver):
        raise ValueError("approver is required")
    if decision != "approved_for_manual_promotion":
        raise ValueError("decision must be approved_for_manual_promotion")
    return {
        "schema_version": 1,
        "artifact_type": "manual_approval",
        "artifact_ref": f"eval:{eval_run_id}:manual_approval:{approver}",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "approver": approver,
        "decision": decision,
        "notes": notes,
    }


def build_rollback_plan(
    *,
    eval_run_id: str,
    rollback_target: str,
    rollback_steps: list[str],
) -> dict[str, Any]:
    """Build the rollback plan artifact required before candidate promotion."""

    if not _non_empty(rollback_target):
        raise ValueError("rollback_target is required")
    if not _non_empty_list(rollback_steps):
        raise ValueError("rollback_steps are required")
    return {
        "schema_version": 1,
        "artifact_type": "rollback_plan",
        "artifact_ref": f"eval:{eval_run_id}:rollback_plan",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "rollback_target": rollback_target,
        "rollback_steps": [str(step) for step in rollback_steps],
    }


def build_impact_scope(
    *,
    eval_run_id: str,
    affected_components: list[str],
    excluded_components: list[str],
) -> dict[str, Any]:
    """Build the release impact-scope artifact for manual review."""

    if not _non_empty_list(affected_components):
        raise ValueError("affected_components are required")
    if not _non_empty_list(excluded_components):
        raise ValueError("excluded_components are required")
    return {
        "schema_version": 1,
        "artifact_type": "impact_scope",
        "artifact_ref": f"eval:{eval_run_id}:impact_scope",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "affected_components": [str(component) for component in affected_components],
        "excluded_components": [str(component) for component in excluded_components],
    }


def build_manual_release_decision(
    *,
    eval_run_id: str,
    release_manager: str,
    decision: str,
    baseline_final_input_mode: str,
    target_final_input_mode: str,
    candidate_input_ref: str,
    candidate_input_hash: str,
    config_hash: str,
    required_artifact_refs: dict[str, str],
    notes: str,
) -> dict[str, Any]:
    """Build the explicit release-decision artifact before config review.

    This does not change production config. It only records that the release
    materials are ready for a separate config-change review.
    """

    if not _non_empty(release_manager):
        raise ValueError("release_manager is required")
    if decision != "approved_for_config_change_review":
        raise ValueError("decision must be approved_for_config_change_review")
    if baseline_final_input_mode != "legacy_prompt":
        raise ValueError("baseline_final_input_mode must be legacy_prompt")
    if target_final_input_mode != "decision_input":
        raise ValueError("target_final_input_mode must be decision_input")
    if not _non_empty(candidate_input_ref):
        raise ValueError("candidate_input_ref is required")
    if not _non_empty(candidate_input_hash):
        raise ValueError("candidate_input_hash is required")
    if not _non_empty(config_hash):
        raise ValueError("config_hash is required")
    if not isinstance(required_artifact_refs, dict) or not required_artifact_refs:
        raise ValueError("required_artifact_refs are required")
    return {
        "schema_version": 1,
        "artifact_type": "manual_release_decision",
        "artifact_ref": f"eval:{eval_run_id}:manual_release_decision:{release_manager}",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "release_manager": release_manager,
        "decision": decision,
        "baseline_final_input_mode": baseline_final_input_mode,
        "target_final_input_mode": target_final_input_mode,
        "candidate_input_ref": candidate_input_ref,
        "candidate_input_hash": candidate_input_hash,
        "config_hash": config_hash,
        "required_artifact_refs": {str(key): str(value) for key, value in required_artifact_refs.items()},
        "config_change_review_required": True,
        "allowed_to_change_production_final_input": False,
        "notes": notes,
    }


def build_config_change_review_request(
    *,
    eval_run_id: str,
    requester: str,
    manual_release_decision_ref: str,
    baseline_final_input_mode: str,
    requested_final_input_mode: str,
    candidate_input_ref: str,
    candidate_input_hash: str,
    notes: str,
) -> dict[str, Any]:
    """Build the handoff request for human config-change review.

    This artifact records intent to start a separate review. It cannot mutate
    production config or switch FinalDecisionAgent input mode.
    """

    if not _non_empty(requester):
        raise ValueError("requester is required")
    if not _non_empty(manual_release_decision_ref):
        raise ValueError("manual_release_decision_ref is required")
    if baseline_final_input_mode != "legacy_prompt":
        raise ValueError("baseline_final_input_mode must be legacy_prompt")
    if requested_final_input_mode != "decision_input":
        raise ValueError("requested_final_input_mode must be decision_input")
    if not _non_empty(candidate_input_ref):
        raise ValueError("candidate_input_ref is required")
    if not _non_empty(candidate_input_hash):
        raise ValueError("candidate_input_hash is required")
    return {
        "schema_version": 1,
        "artifact_type": "config_change_review_request",
        "artifact_ref": f"eval:{eval_run_id}:config_change_review_request:{requester}",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "requester": requester,
        "manual_release_decision_ref": manual_release_decision_ref,
        "baseline_final_input_mode": baseline_final_input_mode,
        "requested_final_input_mode": requested_final_input_mode,
        "candidate_input_ref": candidate_input_ref,
        "candidate_input_hash": candidate_input_hash,
        "config_change_review_required": True,
        "allowed_to_change_production_final_input": False,
        "notes": notes,
    }


def build_config_change_review_approval(
    *,
    eval_run_id: str,
    reviewer: str,
    decision: str,
    config_change_review_request_ref: str,
    manual_release_decision_ref: str,
    baseline_final_input_mode: str,
    approved_final_input_mode: str,
    candidate_input_ref: str,
    candidate_input_hash: str,
    config_hash: str,
    rollback_plan_ref: str,
    notes: str,
) -> dict[str, Any]:
    """Build the human approval artifact for the config-change review.

    This records review approval only. Runtime switching still requires a
    separate production switch gate and must not be performed by this artifact.
    """

    if not _non_empty(reviewer):
        raise ValueError("reviewer is required")
    if decision != "approved_for_final_input_config_change":
        raise ValueError("decision must be approved_for_final_input_config_change")
    if not _non_empty(config_change_review_request_ref):
        raise ValueError("config_change_review_request_ref is required")
    if not _non_empty(manual_release_decision_ref):
        raise ValueError("manual_release_decision_ref is required")
    if baseline_final_input_mode != "legacy_prompt":
        raise ValueError("baseline_final_input_mode must be legacy_prompt")
    if approved_final_input_mode != "decision_input":
        raise ValueError("approved_final_input_mode must be decision_input")
    if not _non_empty(candidate_input_ref):
        raise ValueError("candidate_input_ref is required")
    if not _non_empty(candidate_input_hash):
        raise ValueError("candidate_input_hash is required")
    if not _non_empty(config_hash):
        raise ValueError("config_hash is required")
    if not _non_empty(rollback_plan_ref):
        raise ValueError("rollback_plan_ref is required")
    return {
        "schema_version": 1,
        "artifact_type": "config_change_review_approval",
        "artifact_ref": f"eval:{eval_run_id}:config_change_review_approval:{reviewer}",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "reviewer": reviewer,
        "decision": decision,
        "config_change_review_request_ref": config_change_review_request_ref,
        "manual_release_decision_ref": manual_release_decision_ref,
        "baseline_final_input_mode": baseline_final_input_mode,
        "approved_final_input_mode": approved_final_input_mode,
        "candidate_input_ref": candidate_input_ref,
        "candidate_input_hash": candidate_input_hash,
        "config_hash": config_hash,
        "rollback_plan_ref": rollback_plan_ref,
        "allowed_to_change_production_final_input": False,
        "runtime_switch_gate_required": True,
        "notes": notes,
    }


def build_shadow_candidate_comparison(
    *,
    eval_run_id: str,
    replay_outputs: dict[str, EvalReplayOutput],
) -> dict[str, Any]:
    """Build a no-side-effect comparison artifact for manual promotion review.

    The artifact summarizes candidate replay metadata only. It does not include
    raw prompts, snippets, full worker payloads, or production-write intents.
    """

    case_summaries = []
    available = 0
    missing = 0
    worker_counts: list[int] = []
    switch_ready = 0
    switch_not_ready = 0
    for case_id, replay_output in sorted(replay_outputs.items()):
        candidate_replay = replay_output.output_payload.get("candidate_replay")
        if not isinstance(candidate_replay, dict) or candidate_replay.get("status") != "available":
            missing += 1
            case_summaries.append({"case_id": case_id, "status": "missing"})
            continue
        available += 1
        worker_count = candidate_replay.get("worker_artifact_count")
        if isinstance(worker_count, int):
            worker_counts.append(worker_count)
        is_switch_ready = candidate_replay.get("switch_ready") is True
        if is_switch_ready:
            switch_ready += 1
        else:
            switch_not_ready += 1
        case_summary = {
            "case_id": case_id,
            "status": "available",
            "decision_input_ref": candidate_replay.get("decision_input_ref"),
            "decision_input_hash": candidate_replay.get("decision_input_hash"),
            "replayable_input_ref": candidate_replay.get("replayable_input_ref"),
            "replayable_input_hash": candidate_replay.get("replayable_input_hash"),
            "worker_artifact_count": worker_count,
            "worker_manifest_complete": candidate_replay.get("worker_manifest_complete"),
            "worker_manifest_consistency_passed": _passed(
                candidate_replay.get("worker_manifest_consistency")
            ),
            "context_artifact_consistency_passed": _passed(
                candidate_replay.get("context_artifact_consistency")
            ),
            "blocked_actions": _safe_string_list(
                candidate_replay.get("blocked_actions"),
                allowed_values=SAFE_BLOCKED_ACTIONS,
            ),
            "missing_facts": _safe_string_list(
                candidate_replay.get("missing_facts"),
                allowed_values=SAFE_MISSING_FACTS,
            ),
            "switch_ready": is_switch_ready,
            "blocking_reasons": _safe_string_list(
                candidate_replay.get("blocking_reasons"),
                allowed_values=SAFE_BLOCKING_REASONS,
            ),
        }
        shadow_final_summary = _shadow_final_summary(replay_output.output_payload)
        if shadow_final_summary is not None:
            case_summary["decision_input_shadow_final"] = shadow_final_summary
        shadow_legacy_comparison = _shadow_legacy_comparison(replay_output.output_payload)
        if shadow_legacy_comparison is not None:
            case_summary["shadow_legacy_comparison"] = shadow_legacy_comparison
        case_summaries.append(case_summary)
    return {
        "schema_version": 1,
        "artifact_type": "shadow_candidate_comparison",
        "artifact_ref": f"eval:{eval_run_id}:shadow_candidate_comparison",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "case_count": len(replay_outputs),
        "candidate_replay_available": available,
        "candidate_replay_missing": missing,
        "worker_artifact_count_min": min(worker_counts) if worker_counts else 0,
        "switch_ready_count": switch_ready,
        "switch_not_ready_count": switch_not_ready,
        "case_summaries": case_summaries,
    }


def _passed(value: Any) -> bool | None:
    if not isinstance(value, dict):
        return None
    passed = value.get("passed")
    return passed if isinstance(passed, bool) else None


def _shadow_final_summary(output_payload: dict[str, Any]) -> dict[str, Any] | None:
    shadow_final = output_payload.get("decision_input_shadow_final") if isinstance(output_payload, dict) else None
    if not isinstance(shadow_final, dict):
        return None
    summary = shadow_final.get("shadow_final_summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "status": shadow_final.get("status"),
        "artifact_ref": shadow_final.get("artifact_ref"),
        "artifact_hash": shadow_final.get("artifact_hash"),
        "decision_effect": shadow_final.get("decision_effect"),
        "source_decision_input_ref": shadow_final.get("source_decision_input_ref"),
        "source_decision_input_hash": shadow_final.get("source_decision_input_hash"),
        "main_action": summary.get("main_action"),
        "probability": summary.get("probability"),
    }


def _shadow_legacy_comparison(output_payload: dict[str, Any]) -> dict[str, Any] | None:
    comparison = output_payload.get("shadow_legacy_comparison") if isinstance(output_payload, dict) else None
    if not isinstance(comparison, dict):
        return None
    legacy_summary = comparison.get("legacy_observed_summary")
    shadow_summary = comparison.get("shadow_final_summary")
    legacy = legacy_summary if isinstance(legacy_summary, dict) else {}
    shadow = shadow_summary if isinstance(shadow_summary, dict) else {}
    return {
        "status": comparison.get("status"),
        "decision_effect": comparison.get("decision_effect"),
        "legacy_main_action": legacy.get("main_action"),
        "shadow_main_action": shadow.get("main_action"),
        "main_action_match": comparison.get("main_action_match"),
        "probability_delta": comparison.get("probability_delta"),
        "differences": _safe_string_list(
            comparison.get("differences"),
            allowed_values={"main_action_changed", "probability_changed"},
        ),
    }


def _safe_string_list(value: Any, *, allowed_values: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    safe = []
    for item in value:
        text = str(item)
        if text in allowed_values:
            safe.append(text)
    return safe


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(_non_empty(str(item)) for item in value)
