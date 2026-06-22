from __future__ import annotations

from crypto_manual_alert.eval.promotion_artifacts import (
    build_config_change_review_approval,
    build_config_change_review_request,
    build_impact_scope,
    build_manual_approval,
    build_manual_release_decision,
    build_rollback_plan,
)
from crypto_manual_alert.eval.promotion_review import upsert_promotion_review_artifacts
from crypto_manual_alert.eval.schema import EvalCase, EvalReplayOutput, EvalRun
from crypto_manual_alert.eval.side_effect_proof import build_no_production_side_effect_proof
from crypto_manual_alert.eval.store import EvalStore


def test_upsert_promotion_review_artifacts_recomputes_release_gate_without_approving(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    eval_run_id = "eval-run"
    comparison = {
        "schema_version": 1,
        "artifact_type": "shadow_candidate_comparison",
        "artifact_ref": "eval:eval-run:shadow_candidate_comparison",
        "eval_run_id": eval_run_id,
        "decision_effect": "none",
        "case_count": 1,
        "candidate_replay_available": 1,
        "candidate_replay_missing": 0,
        "worker_artifact_count_min": 7,
        "switch_ready_count": 1,
        "switch_not_ready_count": 0,
        "case_summaries": [
            {
                "case_id": "case-1",
                    "status": "available",
                    "decision_input_ref": "trace:eval:decision_input_candidate",
                    "decision_input_hash": "sha256:decision",
                    "worker_manifest_complete": True,
                    "worker_manifest_consistency_passed": True,
                    "context_artifact_consistency_passed": True,
                "switch_ready": True,
                "blocking_reasons": [],
                "decision_input_shadow_final": {
                    "status": "completed",
                    "artifact_ref": "candidate:decision_input_shadow_final",
                    "artifact_hash": "sha256:shadow-final",
                    "decision_effect": "none",
                    "source_decision_input_ref": "trace:eval:decision_input_candidate",
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
        ],
    }
    run = EvalRun(
        eval_run_id=eval_run_id,
        dataset_name="selected_badcases",
        mode="judge_only_fixture",
        status="passed",
        started_at="2026-06-30T00:00:00+00:00",
        ended_at="2026-06-30T00:00:01+00:00",
        case_count=1,
        pass_count=1,
        fail_count=0,
        metadata={
            "promotion_artifacts": {
                "no_production_side_effect_proof": _no_production_side_effect_proof(eval_run_id),
                "shadow_candidate_comparison": comparison,
            }
        },
    )
    store.insert_run(run, cases=[], scores=[])
    required_artifact_refs = {
        "no_production_side_effect_proof": "eval:eval-run:no_production_side_effect_proof",
        "manual_approval": "eval:eval-run:manual_approval:risk-owner",
        "rollback_plan": "eval:eval-run:rollback_plan",
        "impact_scope": "eval:eval-run:impact_scope",
        "shadow_candidate_comparison": "eval:eval-run:shadow_candidate_comparison",
    }

    review = upsert_promotion_review_artifacts(
        store,
        eval_run_id=eval_run_id,
        artifacts={
            "manual_approval": build_manual_approval(
                eval_run_id=eval_run_id,
                approver="risk-owner",
                decision="approved_for_manual_promotion",
                notes="reviewed",
            ),
            "rollback_plan": build_rollback_plan(
                eval_run_id=eval_run_id,
                rollback_target="config:decision.final_input_mode=legacy_prompt",
                rollback_steps=["restore legacy prompt"],
            ),
            "impact_scope": build_impact_scope(
                eval_run_id=eval_run_id,
                affected_components=["FinalInputSelector experiment"],
                excluded_components=["production journal", "notification delivery"],
            ),
            "manual_release_decision": build_manual_release_decision(
                eval_run_id=eval_run_id,
                release_manager="release-owner",
                decision="approved_for_config_change_review",
                baseline_final_input_mode="legacy_prompt",
                target_final_input_mode="decision_input",
                candidate_input_ref="trace:eval:decision_input_candidate",
                candidate_input_hash="sha256:decision",
                config_hash="sha256:config",
                required_artifact_refs=required_artifact_refs,
                notes="ready for config review",
            ),
        },
        replay_outputs={
            "case-1": _candidate_replay_output(worker_artifact_count=7)
        },
        scores=[],
    )

    assert review["promotion_review"]["status"] == "ready_for_config_change_review"
    assert review["promotion_approved"] is False
    assert review["promotion_review"]["allowed_to_change_production_final_input"] is False
    assert review["promotion_review"]["config_change_review_required"] is True
    config_request = build_config_change_review_request(
        eval_run_id=eval_run_id,
        requester="release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="human config review only",
    )

    review_after_request = upsert_promotion_review_artifacts(
        store,
        eval_run_id=eval_run_id,
        artifacts={"config_change_review_request": config_request},
        replay_outputs={
            "case-1": _candidate_replay_output(worker_artifact_count=7)
        },
        scores=[],
    )

    assert review_after_request["promotion_review"]["status"] == "config_change_review_requested"
    assert review_after_request["promotion_approved"] is False
    assert review_after_request["promotion_review"]["allowed_to_change_production_final_input"] is False
    assert review_after_request["promotion_review"]["config_change_review_request_ref"] == (
        "eval:eval-run:config_change_review_request:release-owner"
    )

    config_approval = build_config_change_review_approval(
        eval_run_id=eval_run_id,
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
        notes="reviewed config diff and rollback plan",
    )

    review_after_approval = upsert_promotion_review_artifacts(
        store,
        eval_run_id=eval_run_id,
        artifacts={"config_change_review_approval": config_approval},
        replay_outputs={
            "case-1": _candidate_replay_output(worker_artifact_count=7)
        },
        scores=[],
    )

    assert review_after_approval["promotion_review"]["status"] == "config_change_review_approved"
    assert review_after_approval["promotion_approved"] is False
    assert review_after_approval["promotion_review"]["allowed_to_change_production_final_input"] is False
    assert review_after_approval["promotion_review"]["runtime_switch_gate_required"] is True
    assert review_after_approval["promotion_review"]["config_change_review_approval_ref"] == (
        "eval:eval-run:config_change_review_approval:config-owner"
    )
    persisted = store.get_promotion_artifacts(eval_run_id)
    assert set(persisted) == {
        "no_production_side_effect_proof",
        "manual_approval",
        "rollback_plan",
        "impact_scope",
        "shadow_candidate_comparison",
        "manual_release_decision",
        "config_change_review_request",
        "config_change_review_approval",
    }


def test_upsert_promotion_review_artifacts_rejects_unknown_eval_run(tmp_path):
    store = EvalStore(tmp_path / "eval.db")

    try:
        upsert_promotion_review_artifacts(
            store,
            eval_run_id="missing-run",
            artifacts={},
            replay_outputs={},
            scores=[],
        )
    except ValueError as exc:
        assert "eval run not found" in str(exc)
    else:
        raise AssertionError("missing eval run should fail")


def test_upsert_promotion_review_artifacts_preserves_required_badcase_severity_gate(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    eval_run_id = "eval-run"
    run = EvalRun(
        eval_run_id=eval_run_id,
        dataset_name="selected_badcases",
        mode="judge_only_fixture",
        status="passed",
        started_at="2026-06-30T00:00:00+00:00",
        ended_at="2026-06-30T00:00:01+00:00",
        case_count=1,
        pass_count=1,
        fail_count=0,
        metadata={},
    )
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="medium",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={},
    )
    store.insert_run(run, cases=[case], scores=[])

    review = upsert_promotion_review_artifacts(
        store,
        eval_run_id=eval_run_id,
        artifacts={},
        replay_outputs={
            "case-1": _candidate_replay_output(worker_artifact_count=7),
        },
        scores=[],
        required_badcase_severities=["critical"],
    )

    assert "badcase_severity_coverage_not_met" in review["blocking_reasons"]
    assert review["hard_gate_results"]["badcase_severity_coverage"] == {
        "passed": False,
        "blocking_reasons": ["badcase_severity_coverage_not_met"],
        "required_severities": ["critical"],
        "observed_counts": {"critical": 0},
        "missing_severities": ["critical"],
    }


def _candidate_replay_output(*, worker_artifact_count: int = 7) -> EvalReplayOutput:
    return EvalReplayOutput(
        replay_id="replay-1",
        case_id="case-1",
        source_trace_id="trace-1",
        source_badcase_id=1,
        frozen_input_hash="frozen-hash",
        status="completed",
        mode="candidate_decision",
        metadata={"source": "eval.candidate_decision_replay", "decision_effect": "none"},
        output_payload={
            "candidate_replay": {
                "status": "available",
                "decision_input_ref": "trace:eval:decision_input_candidate",
                "decision_input_hash": "sha256:decision",
                "worker_artifact_count": worker_artifact_count,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "artifact_snapshot_consistency": {"passed": True, "violations": []},
                "counter_conflict_coverage": {"passed": True, "violations": []},
                "complete_replay_refs": {
                    "has_lead_synthesis_artifact": True,
                    "has_final_decision_output": True,
                    "has_final_input_selection": True,
                    "has_parsed_plan": True,
                    "has_production_control_gate": True,
                    "has_risk_gate_result": True,
                    "has_side_effect_policy": True,
                    "has_context_artifact_summary": True,
                    "has_version_lock": True,
                    "has_telemetry_refs": True,
                    "has_evidence_snapshot_refs": True,
                    "has_memory_snapshot_refs": True,
                    "has_span_tree_refs": True,
                },
                "complete_replay_missing_refs": [],
                "span_tree_parent_complete": True,
                "span_tree_missing_parent_count": 0,
                "switch_ready": True,
                "blocking_reasons": [],
            }
        },
    )


def _no_production_side_effect_proof(eval_run_id: str) -> dict[str, object]:
    counts = {
        "plan_runs": 1,
        "notifications": 0,
        "manual_outcomes": 0,
        "traces": 2,
        "trace_spans": 3,
        "llm_interactions": 0,
    }
    fingerprints = {
        table: f"sha256:{table}"
        for table in counts
    }
    return build_no_production_side_effect_proof(
        eval_run_id=eval_run_id,
        before_counts=counts,
        after_counts=dict(counts),
        before_fingerprints=fingerprints,
        after_fingerprints=dict(fingerprints),
    )
