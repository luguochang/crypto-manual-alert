from __future__ import annotations

import json

from crypto_manual_alert.eval.promotion_artifacts import (
    build_config_change_review_approval,
    build_config_change_review_request,
    build_impact_scope,
    build_manual_approval,
    build_manual_release_decision,
    build_rollback_plan,
    build_shadow_candidate_comparison,
)
from crypto_manual_alert.eval.schema import EvalReplayOutput


def test_shadow_candidate_comparison_uses_safe_refs_without_raw_payloads():
    comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs={
            "case-1": EvalReplayOutput(
                replay_id="replay-1",
                case_id="case-1",
                source_trace_id="trace-1",
                source_badcase_id=1,
                frozen_input_hash="frozen-hash",
                status="completed",
                mode="frozen_observed",
                output_payload={
                    "candidate_replay": {
                        "status": "available",
                        "decision_input_ref": "trace:1:decision_input_candidate",
                        "decision_input_hash": "sha256:decision",
                        "replayable_input_ref": "trace:1:replayable_input_candidate",
                        "replayable_input_hash": "sha256:replayable",
                        "worker_artifact_count": 4,
                        "worker_manifest_complete": True,
                        "worker_manifest_consistency": {"passed": True},
                        "context_artifact_consistency": {"passed": True},
                        "blocked_actions": ["trigger long"],
                        "missing_facts": ["mark"],
                        "switch_ready": True,
                        "blocking_reasons": [],
                        "raw_snippet": "raw snippet must not leak",
                        "raw_payload": {"secret": "must not leak"},
                    },
                    "decision_input_shadow_final": {
                        "status": "completed",
                        "artifact_ref": "candidate:decision_input_shadow_final",
                        "artifact_hash": "sha256:shadow-final",
                        "source_decision_input_ref": "trace:1:decision_input_candidate",
                        "source_decision_input_hash": "sha256:decision",
                        "decision_effect": "none",
                        "production_final_input": False,
                        "notification_input": False,
                        "shadow_final_summary": {
                            "main_action": "no trade",
                            "probability": 0.52,
                            "raw_prompt": "must not leak",
                        },
                    },
                    "shadow_legacy_comparison": {
                        "status": "available",
                        "decision_effect": "none",
                        "legacy_observed_summary": {
                            "main_action": "no trade",
                            "probability": None,
                            "raw_prompt": "must not leak",
                        },
                        "shadow_final_summary": {
                            "main_action": "no trade",
                            "probability": 0.52,
                            "raw_output": "must not leak",
                        },
                        "main_action_match": True,
                        "probability_delta": None,
                        "differences": [],
                    },
                },
            )
        },
    )

    assert comparison["artifact_ref"] == "eval:eval-run:shadow_candidate_comparison"
    assert comparison["decision_effect"] == "none"
    assert comparison["case_summaries"] == [
        {
            "case_id": "case-1",
            "status": "available",
            "decision_input_ref": "trace:1:decision_input_candidate",
            "decision_input_hash": "sha256:decision",
            "replayable_input_ref": "trace:1:replayable_input_candidate",
            "replayable_input_hash": "sha256:replayable",
            "worker_artifact_count": 4,
            "worker_manifest_complete": True,
            "worker_manifest_consistency_passed": True,
            "context_artifact_consistency_passed": True,
            "blocked_actions": ["trigger long"],
            "missing_facts": ["mark"],
            "switch_ready": True,
            "blocking_reasons": [],
            "decision_input_shadow_final": {
                "status": "completed",
                "artifact_ref": "candidate:decision_input_shadow_final",
                "artifact_hash": "sha256:shadow-final",
                "decision_effect": "none",
                "source_decision_input_ref": "trace:1:decision_input_candidate",
                "source_decision_input_hash": "sha256:decision",
                "main_action": "no trade",
                "probability": 0.52,
            },
            "shadow_legacy_comparison": {
                "status": "available",
                "decision_effect": "none",
                "legacy_main_action": "no trade",
                "shadow_main_action": "no trade",
                "main_action_match": True,
                "probability_delta": None,
                "differences": [],
            },
        }
    ]
    rendered = json.dumps(comparison, ensure_ascii=False).lower()
    assert "raw snippet must not leak" not in rendered
    assert "must not leak" not in rendered


def test_shadow_candidate_comparison_filters_raw_strings_from_list_fields():
    comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs={
            "case-1": EvalReplayOutput(
                replay_id="replay-1",
                case_id="case-1",
                source_trace_id="trace-1",
                source_badcase_id=1,
                frozen_input_hash="frozen-hash",
                status="completed",
                mode="frozen_observed",
                output_payload={
                    "candidate_replay": {
                        "status": "available",
                        "decision_input_ref": "trace:1:decision_input_candidate",
                        "decision_input_hash": "sha256:decision",
                        "replayable_input_ref": "trace:1:replayable_input_candidate",
                        "replayable_input_hash": "sha256:replayable",
                        "worker_artifact_count": 4,
                        "worker_manifest_complete": True,
                        "worker_manifest_consistency": {"passed": True},
                        "context_artifact_consistency": {"passed": True},
                        "blocked_actions": ["trigger long", "raw snippet must not leak"],
                        "missing_facts": ["mark", "raw payload must not leak"],
                        "switch_ready": False,
                        "blocking_reasons": ["candidate_gate_failed", "raw secret must not leak"],
                    }
                },
            )
        },
    )

    assert comparison["case_summaries"][0]["blocked_actions"] == ["trigger long"]
    assert comparison["case_summaries"][0]["missing_facts"] == ["mark"]
    assert comparison["case_summaries"][0]["blocking_reasons"] == ["candidate_gate_failed"]
    rendered = json.dumps(comparison, ensure_ascii=False).lower()
    assert "raw snippet must not leak" not in rendered
    assert "raw payload must not leak" not in rendered
    assert "raw secret must not leak" not in rendered


def test_shadow_candidate_comparison_omits_missing_shadow_final_summary():
    comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs={
            "case-1": EvalReplayOutput(
                replay_id="replay-1",
                case_id="case-1",
                source_trace_id="trace-1",
                source_badcase_id=1,
                frozen_input_hash="frozen-hash",
                status="completed",
                mode="candidate_decision",
                output_payload={
                    "candidate_replay": {
                        "status": "available",
                        "decision_input_ref": "trace:1:decision_input_candidate",
                        "decision_input_hash": "sha256:decision",
                        "replayable_input_ref": "trace:1:replayable_input_candidate",
                        "replayable_input_hash": "sha256:replayable",
                        "worker_artifact_count": 4,
                        "worker_manifest_complete": True,
                        "worker_manifest_consistency": {"passed": True},
                        "context_artifact_consistency": {"passed": True},
                        "blocked_actions": [],
                        "missing_facts": [],
                        "switch_ready": False,
                        "blocking_reasons": ["candidate_gate_failed"],
                    }
                },
            )
        },
    )

    assert "decision_input_shadow_final" not in comparison["case_summaries"][0]


def test_manual_approval_artifact_is_explicit_and_no_side_effect():
    approval = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="Reviewed replay and release gate output.",
    )

    assert approval == {
        "schema_version": 1,
        "artifact_type": "manual_approval",
        "artifact_ref": "eval:eval-run:manual_approval:risk-owner",
        "eval_run_id": "eval-run",
        "decision_effect": "none",
        "approver": "risk-owner",
        "decision": "approved_for_manual_promotion",
        "notes": "Reviewed replay and release gate output.",
    }


def test_manual_approval_rejects_empty_approver():
    try:
        build_manual_approval(
            eval_run_id="eval-run",
            approver="",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        )
    except ValueError as exc:
        assert "approver is required" in str(exc)
    else:
        raise AssertionError("empty approver should fail")


def test_rollback_plan_artifact_requires_target_and_steps():
    rollback_plan = build_rollback_plan(
        eval_run_id="eval-run",
        rollback_target="config:decision.final_input_mode=legacy_prompt",
        rollback_steps=[
            "Restore legacy final input mode",
            "Run focused release gate regression",
        ],
    )

    assert rollback_plan == {
        "schema_version": 1,
        "artifact_type": "rollback_plan",
        "artifact_ref": "eval:eval-run:rollback_plan",
        "eval_run_id": "eval-run",
        "decision_effect": "none",
        "rollback_target": "config:decision.final_input_mode=legacy_prompt",
        "rollback_steps": [
            "Restore legacy final input mode",
            "Run focused release gate regression",
        ],
    }


def test_rollback_plan_rejects_empty_steps():
    try:
        build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=[],
        )
    except ValueError as exc:
        assert "rollback_steps are required" in str(exc)
    else:
        raise AssertionError("empty rollback steps should fail")


def test_impact_scope_artifact_records_limited_release_surface():
    impact_scope = build_impact_scope(
        eval_run_id="eval-run",
        affected_components=[
            "FinalInputSelector experiment",
            "Eval release gate",
        ],
        excluded_components=[
            "production journal",
            "notification delivery",
        ],
    )

    assert impact_scope == {
        "schema_version": 1,
        "artifact_type": "impact_scope",
        "artifact_ref": "eval:eval-run:impact_scope",
        "eval_run_id": "eval-run",
        "decision_effect": "none",
        "affected_components": [
            "FinalInputSelector experiment",
            "Eval release gate",
        ],
        "excluded_components": [
            "production journal",
            "notification delivery",
        ],
    }


def test_impact_scope_rejects_empty_affected_components():
    try:
        build_impact_scope(
            eval_run_id="eval-run",
            affected_components=[],
            excluded_components=["production journal"],
        )
    except ValueError as exc:
        assert "affected_components are required" in str(exc)
    else:
        raise AssertionError("empty affected components should fail")


def test_manual_release_decision_records_config_review_without_switching_production():
    release_decision = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        required_artifact_refs={
            "manual_approval": "eval:eval-run:manual_approval:risk-owner",
            "rollback_plan": "eval:eval-run:rollback_plan",
            "impact_scope": "eval:eval-run:impact_scope",
            "shadow_candidate_comparison": "eval:eval-run:shadow_candidate_comparison",
        },
        notes="Ready for a separate config change review.",
    )

    assert release_decision == {
        "schema_version": 1,
        "artifact_type": "manual_release_decision",
        "artifact_ref": "eval:eval-run:manual_release_decision:release-owner",
        "eval_run_id": "eval-run",
        "decision_effect": "none",
        "release_manager": "release-owner",
        "decision": "approved_for_config_change_review",
        "baseline_final_input_mode": "legacy_prompt",
        "target_final_input_mode": "decision_input",
        "candidate_input_ref": "trace:eval:decision_input_candidate",
        "candidate_input_hash": "sha256:decision",
        "config_hash": "sha256:config",
        "required_artifact_refs": {
            "manual_approval": "eval:eval-run:manual_approval:risk-owner",
            "rollback_plan": "eval:eval-run:rollback_plan",
            "impact_scope": "eval:eval-run:impact_scope",
            "shadow_candidate_comparison": "eval:eval-run:shadow_candidate_comparison",
        },
        "config_change_review_required": True,
        "allowed_to_change_production_final_input": False,
        "notes": "Ready for a separate config change review.",
    }


def test_manual_release_decision_rejects_missing_candidate_hash():
    try:
        build_manual_release_decision(
            eval_run_id="eval-run",
            release_manager="release-owner",
            decision="approved_for_config_change_review",
            baseline_final_input_mode="legacy_prompt",
            target_final_input_mode="decision_input",
            candidate_input_ref="trace:eval:decision_input_candidate",
            candidate_input_hash="",
            config_hash="sha256:config",
            required_artifact_refs={"manual_approval": "eval:eval-run:manual_approval:risk-owner"},
            notes="reviewed",
        )
    except ValueError as exc:
        assert "candidate_input_hash is required" in str(exc)
    else:
        raise AssertionError("missing candidate hash should fail")


def test_config_change_review_request_records_no_side_effect_review_intent():
    request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="Request human config review only.",
    )

    assert request == {
        "schema_version": 1,
        "artifact_type": "config_change_review_request",
        "artifact_ref": "eval:eval-run:config_change_review_request:release-owner",
        "eval_run_id": "eval-run",
        "decision_effect": "none",
        "requester": "release-owner",
        "manual_release_decision_ref": "eval:eval-run:manual_release_decision:release-owner",
        "baseline_final_input_mode": "legacy_prompt",
        "requested_final_input_mode": "decision_input",
        "candidate_input_ref": "trace:eval:decision_input_candidate",
        "candidate_input_hash": "sha256:decision",
        "config_change_review_required": True,
        "allowed_to_change_production_final_input": False,
        "notes": "Request human config review only.",
    }


def test_config_change_review_request_rejects_missing_requester():
    try:
        build_config_change_review_request(
            eval_run_id="eval-run",
            requester="",
            manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
            baseline_final_input_mode="legacy_prompt",
            requested_final_input_mode="decision_input",
            candidate_input_ref="trace:eval:decision_input_candidate",
            candidate_input_hash="sha256:decision",
            notes="review",
        )
    except ValueError as exc:
        assert "requester is required" in str(exc)
    else:
        raise AssertionError("missing requester should fail")


def test_config_change_review_request_rejects_unsupported_mode_pair():
    try:
        build_config_change_review_request(
            eval_run_id="eval-run",
            requester="release-owner",
            manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
            baseline_final_input_mode="decision_input",
            requested_final_input_mode="legacy_prompt",
            candidate_input_ref="trace:eval:decision_input_candidate",
            candidate_input_hash="sha256:decision",
            notes="review",
        )
    except ValueError as exc:
        assert "baseline_final_input_mode must be legacy_prompt" in str(exc)
    else:
        raise AssertionError("unsupported mode pair should fail")


def test_config_change_review_request_rejects_missing_candidate_hash():
    try:
        build_config_change_review_request(
            eval_run_id="eval-run",
            requester="release-owner",
            manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
            baseline_final_input_mode="legacy_prompt",
            requested_final_input_mode="decision_input",
            candidate_input_ref="trace:eval:decision_input_candidate",
            candidate_input_hash="",
            notes="review",
        )
    except ValueError as exc:
        assert "candidate_input_hash is required" in str(exc)
    else:
        raise AssertionError("missing candidate hash should fail")


def test_config_change_review_request_rejects_unsupported_requested_mode():
    try:
        build_config_change_review_request(
            eval_run_id="eval-run",
            requester="release-owner",
            manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
            baseline_final_input_mode="legacy_prompt",
            requested_final_input_mode="legacy_prompt",
            candidate_input_ref="trace:eval:decision_input_candidate",
            candidate_input_hash="sha256:decision",
            notes="review",
        )
    except ValueError as exc:
        assert "requested_final_input_mode must be decision_input" in str(exc)
    else:
        raise AssertionError("unsupported requested mode should fail")


def test_config_change_review_approval_records_no_side_effect_human_review():
    approval = build_config_change_review_approval(
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
        notes="Reviewed config diff and rollback plan.",
    )

    assert approval == {
        "schema_version": 1,
        "artifact_type": "config_change_review_approval",
        "artifact_ref": "eval:eval-run:config_change_review_approval:config-owner",
        "eval_run_id": "eval-run",
        "decision_effect": "none",
        "reviewer": "config-owner",
        "decision": "approved_for_final_input_config_change",
        "config_change_review_request_ref": "eval:eval-run:config_change_review_request:release-owner",
        "manual_release_decision_ref": "eval:eval-run:manual_release_decision:release-owner",
        "baseline_final_input_mode": "legacy_prompt",
        "approved_final_input_mode": "decision_input",
        "candidate_input_ref": "trace:eval:decision_input_candidate",
        "candidate_input_hash": "sha256:decision",
        "config_hash": "sha256:config",
        "rollback_plan_ref": "eval:eval-run:rollback_plan",
        "allowed_to_change_production_final_input": False,
        "runtime_switch_gate_required": True,
        "notes": "Reviewed config diff and rollback plan.",
    }


def test_config_change_review_approval_rejects_missing_reviewer():
    try:
        build_config_change_review_approval(
            eval_run_id="eval-run",
            reviewer="",
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
    except ValueError as exc:
        assert "reviewer is required" in str(exc)
    else:
        raise AssertionError("missing reviewer should fail")
