from __future__ import annotations

from crypto_manual_alert.eval.promotion_artifact_validation import validate_promotion_artifact
from crypto_manual_alert.eval.promotion_artifacts import (
    build_config_change_review_approval,
    build_config_change_review_request,
    build_manual_approval,
    build_manual_release_decision,
)


def test_validate_promotion_artifact_accepts_no_effect_manual_approval():
    artifact = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )

    validate_promotion_artifact("eval-run", "manual_approval", artifact)


def test_validate_promotion_artifact_rejects_cross_run_artifact():
    artifact = build_manual_approval(
        eval_run_id="other-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )

    try:
        validate_promotion_artifact("eval-run", "manual_approval", artifact)
    except ValueError as exc:
        assert "promotion artifact eval_run_id mismatch" in str(exc)
    else:
        raise AssertionError("cross-run promotion artifact should fail")


def test_validate_promotion_artifact_rejects_non_mapping_artifact():
    try:
        validate_promotion_artifact("eval-run", "manual_approval", "not-a-mapping")
    except ValueError as exc:
        assert "promotion artifact must be a mapping" in str(exc)
    else:
        raise AssertionError("non-mapping promotion artifact should fail")


def test_validate_promotion_artifact_rejects_type_mismatch():
    artifact = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )

    try:
        validate_promotion_artifact("eval-run", "rollback_plan", artifact)
    except ValueError as exc:
        assert "promotion artifact type mismatch" in str(exc)
    else:
        raise AssertionError("promotion artifact type mismatch should fail")


def test_validate_promotion_artifact_rejects_side_effectful_artifact():
    artifact = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )
    artifact["decision_effect"] = "production_final_input"

    try:
        validate_promotion_artifact("eval-run", "manual_approval", artifact)
    except ValueError as exc:
        assert "promotion artifact decision_effect must be none" in str(exc)
    else:
        raise AssertionError("side-effect promotion artifact should fail")


def test_validate_promotion_artifact_rejects_unsupported_schema_version():
    artifact = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )
    artifact["schema_version"] = 2

    try:
        validate_promotion_artifact("eval-run", "manual_approval", artifact)
    except ValueError as exc:
        assert "promotion artifact schema_version must be 1" in str(exc)
    else:
        raise AssertionError("unsupported promotion artifact schema should fail")


def test_validate_promotion_artifact_rejects_missing_artifact_ref():
    artifact = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )
    artifact.pop("artifact_ref")

    try:
        validate_promotion_artifact("eval-run", "manual_approval", artifact)
    except ValueError as exc:
        assert "promotion artifact artifact_ref is required" in str(exc)
    else:
        raise AssertionError("promotion artifact without ref should fail")


def test_validate_promotion_artifact_rejects_ref_bound_to_other_run():
    artifact = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )
    artifact["artifact_ref"] = "eval:other-run:manual_approval:risk-owner"

    try:
        validate_promotion_artifact("eval-run", "manual_approval", artifact)
    except ValueError as exc:
        assert "promotion artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("cross-run artifact_ref should fail")


def test_validate_manual_release_decision_accepts_non_empty_ref_suffix():
    artifact = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        required_artifact_refs={"manual_approval": "eval:eval-run:manual_approval:risk-owner"},
        notes="reviewed",
    )

    validate_promotion_artifact("eval-run", "manual_release_decision", artifact)


def test_validate_suffix_ref_artifacts_reject_trailing_colon():
    artifact = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        required_artifact_refs={"manual_approval": "eval:eval-run:manual_approval:risk-owner"},
        notes="reviewed",
    )
    artifact["artifact_ref"] = "eval:eval-run:manual_release_decision:"

    try:
        validate_promotion_artifact("eval-run", "manual_release_decision", artifact)
    except ValueError as exc:
        assert "promotion artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("empty suffix artifact_ref should fail")


def test_validate_config_review_request_rejects_switch_permission():
    artifact = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="human config review only",
    )
    artifact["allowed_to_change_production_final_input"] = True

    try:
        validate_promotion_artifact("eval-run", "config_change_review_request", artifact)
    except ValueError as exc:
        assert "config review request cannot allow production final input changes" in str(exc)
    else:
        raise AssertionError("switch-permitting config review request should fail")


def test_validate_config_review_request_rejects_required_field_regressions():
    base = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="human config review only",
    )

    cases = [
        ("config_change_review_required", False, "config review request must require config change review"),
        ("baseline_final_input_mode", "decision_input", "config review request baseline_final_input_mode must be legacy_prompt"),
        ("requested_final_input_mode", "legacy_prompt", "config review request requested_final_input_mode must be decision_input"),
        ("manual_release_decision_ref", "", "config review request manual_release_decision_ref is required"),
        ("candidate_input_ref", "", "config review request candidate_input_ref is required"),
        ("candidate_input_hash", "", "config review request candidate_input_hash is required"),
        ("requester", "", "config review request requester is required"),
    ]

    for key, value, message in cases:
        artifact = dict(base)
        artifact[key] = value
        try:
            validate_promotion_artifact("eval-run", "config_change_review_request", artifact)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"config review request with bad {key} should fail")


def test_validate_config_review_approval_accepts_no_effect_human_approval():
    artifact = build_config_change_review_approval(
        eval_run_id="eval-run",
        reviewer="config-owner",
        decision="approved_for_final_input_config_change",
        config_change_review_request_ref="eval:eval-run:config_change_review_request:release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        approved_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        rollback_plan_ref="eval:eval-run:rollback_plan",
        notes="reviewed",
    )

    validate_promotion_artifact("eval-run", "config_change_review_approval", artifact)


def test_validate_config_review_approval_rejects_switch_permission():
    artifact = build_config_change_review_approval(
        eval_run_id="eval-run",
        reviewer="config-owner",
        decision="approved_for_final_input_config_change",
        config_change_review_request_ref="eval:eval-run:config_change_review_request:release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        approved_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        rollback_plan_ref="eval:eval-run:rollback_plan",
        notes="reviewed",
    )
    artifact["allowed_to_change_production_final_input"] = True

    try:
        validate_promotion_artifact("eval-run", "config_change_review_approval", artifact)
    except ValueError as exc:
        assert "config review approval cannot directly allow production final input changes" in str(exc)
    else:
        raise AssertionError("switch-permitting config review approval should fail")
