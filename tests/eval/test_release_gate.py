from __future__ import annotations

from crypto_manual_alert.eval.promotion_artifacts import (
    build_config_change_review_request,
    build_impact_scope,
    build_manual_approval,
    build_manual_release_decision,
    build_rollback_plan,
    build_shadow_candidate_comparison,
)
from crypto_manual_alert.eval.release_gate import build_release_gate_summary
from crypto_manual_alert.eval.release_promotion_review import promotion_review
from crypto_manual_alert.eval.schema import EvalReplayOutput, EvalScore
from crypto_manual_alert.eval.side_effect_proof import build_no_production_side_effect_proof


def test_release_gate_collects_failed_score_categories_and_candidate_replay_blockers():
    summary = build_release_gate_summary(
        scores=[
            _score(passed=True, failure_category="none"),
            _score(passed=False, failure_category="candidate_gate_failed"),
            _score(passed=False, failure_category="plan_semantic_candidate_failed"),
        ],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                        "worker_artifact_count": 7,
                    "switch_ready": False,
                    "blocking_reasons": ["candidate_gate_failed"],
                    "blocked_actions": ["trigger long"],
                    "missing_facts": ["mark"],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "eval_scores_failed",
            "candidate_gate_failed",
            "plan_semantic_candidate_failed",
            "final_switch_readiness_not_ready",
        ],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gates_passed"] is False
    assert summary["promotion_approved"] is False
    assert summary["promotion_review"] == {
        "status": "blocked",
        "decision_effect": "none",
        "candidate_gate_status": "blocked",
        "promotion_material_status": "not_evaluated",
        "allowed_to_change_production_final_input": False,
        "manual_approval_required": True,
        "approval_artifact_ref": None,
    }
    assert summary["hard_gate_results"]["candidate_business_gates"] == {
        "passed": False,
        "blocking_reasons": ["candidate_gate_failed", "plan_semantic_candidate_failed"],
        "blocked_action_cases": [
            {
                "case_id": "case-1",
                "blocked_actions": ["trigger long"],
                "missing_facts": ["mark"],
            }
        ],
        "incomplete_block_evidence_cases": [],
    }
    assert summary["hard_gate_results"]["final_switch_readiness"] == {
        "passed": False,
        "blocking_reasons": ["final_switch_readiness_not_ready"],
    }


def test_release_gate_blocks_when_candidate_replay_is_missing_or_worker_coverage_is_incomplete():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay({"status": "missing"}),
            "case-2": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 3,
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            ),
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "candidate_replay_missing",
            "worker_artifact_coverage_incomplete",
        ],
        candidate_replay_available=1,
        candidate_replay_missing=1,
        worker_artifact_count_min=3,
    )
    assert summary["hard_gate_results"]["candidate_replay"] == {
        "passed": False,
        "blocking_reasons": ["candidate_replay_missing"],
    }
    assert summary["hard_gate_results"]["worker_artifact_coverage"] == {
        "passed": False,
        "blocking_reasons": ["worker_artifact_coverage_incomplete"],
        "required_min": 7,
        "observed_min": 3,
        "manifest_missing_fields": [],
        "manifest_consistency_violations": [],
        "context_artifact_consistency_violations": [],
    }


def test_release_gate_requires_current_seven_required_worker_artifacts():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 4,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {"passed": True, "violations": []},
                    "context_artifact_consistency": {"passed": True, "violations": []},
                    "counter_conflict_coverage": {"passed": True, "violations": []},
                    "complete_replay_refs": _complete_replay_refs_all_present(),
                    "span_tree_parent_complete": True,
                    "span_tree_missing_parent_count": 0,
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["worker_artifact_coverage_incomplete"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=4,
    )
    assert summary["hard_gate_results"]["worker_artifact_coverage"]["required_min"] == 7
    assert summary["hard_gate_results"]["worker_artifact_coverage"]["observed_min"] == 4


def test_release_gate_blocks_when_required_candidate_replay_evidence_is_missing():
    replay = _replay(_clean_candidate_replay(worker_artifact_count=7))
    for key in (
        "worker_manifest_consistency",
        "context_artifact_consistency",
        "counter_conflict_coverage",
    ):
        replay.output_payload["candidate_replay"].pop(key)

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={"case-1": replay},
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "worker_manifest_consistency_missing",
            "context_artifact_consistency_missing",
            "counter_conflict_coverage_missing",
        ],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )


def test_release_gate_blocks_when_complete_replay_refs_are_false_even_if_missing_list_is_empty():
    candidate_replay = _clean_candidate_replay(worker_artifact_count=7)
    candidate_replay["complete_replay_refs"] = {
        **_complete_replay_refs_all_present(),
        "has_telemetry_refs": False,
    }
    candidate_replay["complete_replay_missing_refs"] = []

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={"case-1": _replay(candidate_replay)},
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["complete_replay_input_incomplete"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["complete_replay_input"]["missing_refs"] == [
        {"case_id": "case-1", "missing_refs": ["telemetry_refs"]}
    ]


def test_release_gate_blocks_when_span_tree_parent_evidence_is_missing():
    candidate_replay = _clean_candidate_replay(worker_artifact_count=7)
    candidate_replay["span_tree_parent_complete"] = None
    candidate_replay["span_tree_missing_parent_count"] = None

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={"case-1": _replay(candidate_replay)},
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["span_tree_parent_incomplete"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["complete_replay_input"]["span_tree_incomplete_cases"] == [
        {"case_id": "case-1", "missing_parent_count": 0}
    ]


def test_release_gate_blocks_when_worker_manifest_is_incomplete_even_with_enough_workers():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": False,
                    "worker_manifest_missing_fields": [
                        {
                            "task_id": "shadow:RootCauseAgent",
                            "agent_name": "RootCauseAgent",
                            "missing_fields": ["output_hash"],
                        }
                    ],
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["worker_manifest_incomplete"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["worker_artifact_coverage"] == {
        "passed": False,
        "blocking_reasons": ["worker_manifest_incomplete"],
        "required_min": 7,
            "observed_min": 7,
        "manifest_missing_fields": [
            {
                "case_id": "case-1",
                "task_id": "shadow:RootCauseAgent",
                "agent_name": "RootCauseAgent",
                "missing_fields": ["output_hash"],
            }
        ],
        "manifest_consistency_violations": [],
        "context_artifact_consistency_violations": [],
    }


def test_release_gate_blocks_when_worker_manifest_consistency_fails():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {
                        "passed": False,
                        "violations": [
                            {
                                "rule_id": "worker_manifest_count_mismatch",
                                "expected": 4,
                                "observed": 1,
                            }
                        ],
                        "manifest_count": 1,
                        "worker_ref_count": 1,
                    },
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["worker_manifest_consistency_failed"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["worker_artifact_coverage"] == {
        "passed": False,
        "blocking_reasons": ["worker_manifest_consistency_failed"],
        "required_min": 7,
            "observed_min": 7,
        "manifest_missing_fields": [],
        "manifest_consistency_violations": [
            {
                "case_id": "case-1",
                "rule_id": "worker_manifest_count_mismatch",
                "expected": 4,
                "observed": 1,
            }
        ],
        "context_artifact_consistency_violations": [],
    }


def test_release_gate_preserves_worker_failure_policy_in_manifest_consistency_violations():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {
                        "passed": False,
                        "violations": [
                            {
                                "rule_id": "lead_synthesis_missing_failed_worker_drop",
                                "task_id": "shadow:DataQualityAgent",
                                "agent_name": "DataQualityAgent",
                                "failure_policy_applied": "hard_block",
                            }
                        ],
                    },
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    assert summary["hard_gate_results"]["worker_artifact_coverage"][
        "manifest_consistency_violations"
    ] == [
        {
            "case_id": "case-1",
            "rule_id": "lead_synthesis_missing_failed_worker_drop",
            "task_id": "shadow:DataQualityAgent",
            "agent_name": "DataQualityAgent",
            "failure_policy_applied": "hard_block",
        }
    ]


def test_release_gate_blocks_when_context_artifact_consistency_fails():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "context_artifact_consistency": {
                        "passed": False,
                        "violations": [
                            {
                                "rule_id": "context_decision_input_hash_mismatch",
                                "expected": "sha256:decision",
                                "observed": "sha256:other",
                            }
                        ],
                    },
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["context_artifact_consistency_failed"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["worker_artifact_coverage"][
        "context_artifact_consistency_violations"
    ] == [
        {
            "case_id": "case-1",
            "rule_id": "context_decision_input_hash_mismatch",
            "expected": "sha256:decision",
            "observed": "sha256:other",
        }
    ]


def test_release_gate_blocks_when_artifact_snapshot_readback_fails():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "artifact_snapshot_consistency": {
                        "passed": False,
                        "violations": [
                            {
                                "rule_id": "candidate_artifact_snapshot_missing",
                                "artifact_type": "decision_input_candidate",
                            }
                        ],
                    },
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["artifact_snapshot_readback_failed"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["worker_artifact_coverage"][
        "artifact_snapshot_consistency_violations"
    ] == [
        {
            "case_id": "case-1",
            "rule_id": "candidate_artifact_snapshot_missing",
            "artifact_type": "decision_input_candidate",
        }
    ]


def test_release_gate_blocks_when_artifact_snapshot_consistency_missing_or_malformed():
    for candidate_replay in (
        {
            "status": "available",
            "worker_artifact_count": 7,
            "worker_manifest_complete": True,
            "worker_manifest_missing_fields": [],
            "switch_ready": True,
            "blocking_reasons": [],
            "artifact_snapshot_consistency": None,
        },
        {
            "status": "available",
            "worker_artifact_count": 7,
            "worker_manifest_complete": True,
            "worker_manifest_missing_fields": [],
            "switch_ready": True,
            "blocking_reasons": [],
            "artifact_snapshot_consistency": "passed",
        },
        {
            "status": "available",
            "worker_artifact_count": 7,
            "worker_manifest_complete": True,
            "worker_manifest_missing_fields": [],
            "switch_ready": True,
            "blocking_reasons": [],
            "artifact_snapshot_consistency": {"violations": []},
        },
    ):
        summary = build_release_gate_summary(
            scores=[_score(passed=True, failure_category="none")],
            replay_outputs={"case-1": _replay(candidate_replay)},
        )

        _assert_common_release_gate_fields(
            summary,
            ready=False,
            blocking_reasons=["artifact_snapshot_readback_failed"],
            candidate_replay_available=1,
            candidate_replay_missing=0,
            worker_artifact_count_min=7,
        )
        assert summary["hard_gate_results"]["worker_artifact_coverage"][
            "artifact_snapshot_consistency_violations"
        ] == [
            {
                "case_id": "case-1",
                "rule_id": "candidate_artifact_snapshot_consistency_missing",
            }
        ]


def test_release_gate_blocks_required_worker_hard_block_from_switch_readiness():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {"passed": True, "violations": [], "advisories": []},
                    "context_artifact_consistency": {"passed": True, "violations": []},
                    "switch_ready": False,
                    "blocking_reasons": ["required_worker_missing_or_failed"],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "required_worker_missing_or_failed",
            "final_switch_readiness_not_ready",
        ],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["final_switch_readiness"] == {
        "passed": False,
        "blocking_reasons": ["final_switch_readiness_not_ready"],
    }


def test_release_gate_blocks_worker_hard_block_constraints():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {"passed": True, "violations": [], "advisories": []},
                    "context_artifact_consistency": {"passed": True, "violations": []},
                    "switch_ready": False,
                    "blocking_reasons": ["worker_hard_block"],
                    "worker_hard_blocks": [
                        {
                            "contribution_id": "risk-hard-block",
                            "agent_name": "ExecutionRiskAgent",
                            "reasons": ["facts_gate:execution_facts_missing"],
                            "raw_payload": "must not leak",
                        }
                    ],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "worker_hard_block",
            "final_switch_readiness_not_ready",
        ],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["worker_hard_blocks"] == {
        "passed": False,
        "blocking_reasons": ["worker_hard_block"],
        "worker_hard_blocks": [
            {
                "case_id": "case-1",
                "contribution_id": "risk-hard-block",
                "agent_name": "ExecutionRiskAgent",
                "reasons": ["facts_gate:execution_facts_missing"],
            }
        ],
    }


def test_release_gate_blocks_worker_hard_block_even_if_switch_readiness_reason_is_missing():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {"passed": True, "violations": [], "advisories": []},
                    "context_artifact_consistency": {"passed": True, "violations": []},
                    "switch_ready": True,
                    "blocking_reasons": [],
                    "worker_hard_blocks": [
                        {
                            "contribution_id": "risk-hard-block",
                            "agent_name": "ExecutionRiskAgent",
                            "reasons": ["facts_gate:execution_facts_missing"],
                        }
                    ],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["worker_hard_block"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["worker_hard_blocks"]["passed"] is False


def test_release_gate_blocks_when_counter_conflict_coverage_fails():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {"passed": True, "violations": [], "advisories": []},
                    "context_artifact_consistency": {"passed": True, "violations": []},
                    "counter_conflict_coverage": {
                        "passed": False,
                        "violations": [
                            {
                                "rule_id": "lead_synthesis_counter_thesis_refs_missing",
                                "counter_thesis_count": 1,
                                "raw_payload": "must not leak",
                            },
                            {
                                "rule_id": "lead_synthesis_conflict_refs_missing",
                                "conflict_count": 1,
                            },
                        ],
                    },
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["counter_conflict_coverage_failed"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["counter_conflict_coverage"] == {
        "passed": False,
        "blocking_reasons": ["counter_conflict_coverage_failed"],
        "violations": [
            {
                "case_id": "case-1",
                "rule_id": "lead_synthesis_counter_thesis_refs_missing",
                "counter_thesis_count": 1,
            },
            {
                "case_id": "case-1",
                "rule_id": "lead_synthesis_conflict_refs_missing",
                "conflict_count": 1,
            },
        ],
    }


def test_release_gate_blocks_failed_replay_output_even_if_candidate_payload_claims_available():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                },
                status="failed",
                mode="candidate_decision",
                metadata={"source": "eval.candidate_decision_replay", "decision_effect": "none"},
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["candidate_replay_output_not_completed"],
        candidate_replay_available=0,
        candidate_replay_missing=1,
        worker_artifact_count_min=0,
    )
    assert summary["hard_gate_results"]["candidate_replay"] == {
        "passed": False,
        "blocking_reasons": ["candidate_replay_output_not_completed"],
    }


def test_release_gate_requires_candidate_decision_replay_readback_for_promotion():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                },
                mode="frozen_observed",
                metadata={"source": "eval.frozen_observed_replay"},
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["candidate_replay_readback_not_verified"],
        candidate_replay_available=0,
        candidate_replay_missing=1,
        worker_artifact_count_min=0,
    )
    assert summary["hard_gate_results"]["candidate_replay"] == {
        "passed": False,
        "blocking_reasons": ["candidate_replay_readback_not_verified"],
    }


def test_release_gate_rejects_candidate_replay_without_no_side_effect_metadata():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                },
                mode="candidate_decision",
                metadata={"source": "eval.candidate_decision_replay"},
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["candidate_replay_readback_not_verified"],
        candidate_replay_available=0,
        candidate_replay_missing=1,
        worker_artifact_count_min=0,
    )


def test_release_gate_rejects_candidate_replay_with_nested_decision_effect_violation():
    output = _replay(
        {
            "status": "available",
            "worker_artifact_count": 7,
            "worker_manifest_complete": True,
            "worker_manifest_missing_fields": [],
            "switch_ready": True,
            "blocking_reasons": [],
        },
        mode="candidate_decision",
        metadata={"source": "eval.candidate_decision_replay", "decision_effect": "none"},
    )
    output.output_payload["candidate_decision"] = {
        "decision_effect": "production_final_input",
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={"case-1": output},
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["candidate_replay_decision_effect_violation"],
        candidate_replay_available=0,
        candidate_replay_missing=1,
        worker_artifact_count_min=0,
    )
    assert summary["hard_gate_results"]["candidate_replay"] == {
        "passed": False,
        "blocking_reasons": ["candidate_replay_decision_effect_violation"],
    }


def test_release_gate_rejects_candidate_replay_with_nested_side_effect_flags():
    for nested_key, field_name in (
        ("candidate_decision", "production_final_input"),
        ("decision_input_shadow_final", "notification_input"),
        ("candidate_final_legacy_comparison", "live_order_input"),
    ):
        output = _replay(
            _clean_candidate_replay(worker_artifact_count=7),
            mode="candidate_decision",
            metadata={"source": "eval.candidate_decision_replay", "decision_effect": "none"},
        )
        nested = output.output_payload.get(nested_key)
        if not isinstance(nested, dict):
            nested = {"decision_effect": "none"}
            output.output_payload[nested_key] = nested
        nested[field_name] = True

        summary = build_release_gate_summary(
            scores=[_score(passed=True, failure_category="none")],
            replay_outputs={"case-1": output},
            eval_run_id="eval-run",
            promotion_artifacts={"no_production_side_effect_proof": _no_production_side_effect_proof()},
        )

        _assert_common_release_gate_fields(
            summary,
            ready=False,
            blocking_reasons=["candidate_replay_decision_effect_violation"],
            candidate_replay_available=0,
            candidate_replay_missing=1,
            worker_artifact_count_min=0,
        )


def test_release_gate_rejects_candidate_final_comparison_decision_effect_violation():
    replay = _replay(
        {
            "status": "available",
            "worker_artifact_count": 7,
            "worker_manifest_complete": True,
            "worker_manifest_missing_fields": [],
            "worker_manifest_consistency": {"passed": True, "violations": []},
            "context_artifact_consistency": {"passed": True, "violations": []},
            "switch_ready": True,
            "blocking_reasons": [],
        }
    )
    replay.output_payload["candidate_final_legacy_comparison"] = {
        "status": "available",
        "decision_effect": "production_final_input",
        "legacy_observed_summary": {"main_action": "no trade"},
        "candidate_final_summary": {"main_action": "trigger long"},
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={"case-1": replay},
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["candidate_replay_decision_effect_violation"],
        candidate_replay_available=0,
        candidate_replay_missing=1,
        worker_artifact_count_min=0,
    )
    assert summary["hard_gate_results"]["candidate_replay"] == {
        "passed": False,
        "blocking_reasons": ["candidate_replay_decision_effect_violation"],
    }


def test_release_gate_is_ready_only_when_scores_replay_and_switch_are_clean():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=True,
        blocking_reasons=[],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gates_passed"] is True
    assert summary["promotion_approved"] is False
    assert summary["promotion_review"] == {
        "status": "blocked_missing_artifacts",
        "decision_effect": "none",
        "candidate_gate_status": "passed",
        "promotion_material_status": "missing_required_artifacts",
        "allowed_to_change_production_final_input": False,
        "manual_approval_required": True,
            "approval_artifact_ref": None,
            "required_artifacts": {
                "no_production_side_effect_proof": {"present": False, "artifact_ref": None},
                "manual_approval": {"present": False, "artifact_ref": None},
                "rollback_plan": {"present": False, "artifact_ref": None},
                "impact_scope": {"present": False, "artifact_ref": None},
                "shadow_candidate_comparison": {"present": False, "artifact_ref": None},
            },
            "missing_artifacts": [
                "no_production_side_effect_proof",
                "manual_approval",
                "rollback_plan",
                "impact_scope",
            "shadow_candidate_comparison",
        ],
    }
    assert all(result["passed"] is True for result in summary["hard_gate_results"].values())


def test_release_gate_blocks_missing_manual_execution_side_effects_and_critical_rules():
    summary = build_release_gate_summary(
        scores=[
            _score(
                passed=False,
                failure_category="manual_only_violation",
                judge_name="rule.manual_only",
                severity="critical",
            ),
            _score(
                passed=False,
                failure_category="eval_side_effect_guard_failed",
                judge_name="eval.side_effect_guard",
                severity="critical",
            ),
            _score(
                passed=False,
                failure_category="unsafe_entry_stop_plan",
                judge_name="rule.opening_requirements",
                severity="critical",
            ),
        ],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "eval_scores_failed",
            "manual_execution_required_failed",
            "manual_only_violation",
            "eval_side_effect_guard_failed",
            "critical_rule_failed",
            "unsafe_entry_stop_plan",
        ],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["manual_execution_required"] == {
        "passed": False,
        "blocking_reasons": ["manual_execution_required_failed", "manual_only_violation"],
    }
    assert summary["hard_gate_results"]["eval_side_effect_guard"] == {
        "passed": False,
        "blocking_reasons": ["eval_side_effect_guard_failed"],
    }
    assert summary["hard_gate_results"]["critical_rule_failures"] == {
        "passed": False,
        "blocking_reasons": ["critical_rule_failed", "unsafe_entry_stop_plan"],
    }


def test_release_gate_result_is_a_no_side_effect_promotion_review():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    assert summary["schema_version"] == 1
    assert summary["hard_gates_passed"] is True
    assert summary["promotion_approved"] is False
    assert summary["decision_effect"] == "none"
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False
    assert summary["promotion_review"]["approval_artifact_ref"] is None
    assert summary["promotion_review"]["missing_artifacts"] == [
        "no_production_side_effect_proof",
        "manual_approval",
        "rollback_plan",
        "impact_scope",
        "shadow_candidate_comparison",
    ]


def test_release_gate_recognizes_shadow_candidate_comparison_without_approving_promotion():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            },
        )
    }
    comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs=replay_outputs,
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            "no_production_side_effect_proof": _no_production_side_effect_proof(),
            "shadow_candidate_comparison": comparison,
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=True,
        blocking_reasons=[],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["promotion_approved"] is False
    assert summary["promotion_review"] == {
        "status": "blocked_missing_artifacts",
        "decision_effect": "none",
        "candidate_gate_status": "passed",
        "promotion_material_status": "missing_required_artifacts",
        "allowed_to_change_production_final_input": False,
        "manual_approval_required": True,
        "approval_artifact_ref": None,
        "required_artifacts": {
            "no_production_side_effect_proof": {
                "present": True,
                "artifact_ref": "eval:eval-run:no_production_side_effect_proof",
            },
            "manual_approval": {"present": False, "artifact_ref": None},
            "rollback_plan": {"present": False, "artifact_ref": None},
            "impact_scope": {"present": False, "artifact_ref": None},
            "shadow_candidate_comparison": {
                "present": True,
                "artifact_ref": comparison["artifact_ref"],
            },
        },
        "missing_artifacts": [
            "manual_approval",
            "rollback_plan",
            "impact_scope",
        ],
    }


def test_release_gate_requires_no_production_side_effect_proof_for_promotion_material():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            },
        )
    }
    comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs=replay_outputs,
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={"shadow_candidate_comparison": comparison},
    )

    assert summary["hard_gates_passed"] is False
    assert "no_production_side_effect_proof_missing" in summary["blocking_reasons"]
    assert summary["hard_gate_results"]["no_production_side_effect_proof"] == {
        "passed": False,
        "blocking_reasons": ["no_production_side_effect_proof_missing"],
        "artifact_ref": None,
    }
    assert "required_artifacts" not in summary["promotion_review"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_blocks_failed_no_production_side_effect_proof():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            },
        )
    }
    failed_proof = _no_production_side_effect_proof()
    failed_proof["passed"] = False
    failed_proof["deltas"]["notifications"] = 1
    failed_proof["blocking_reasons"] = ["production_side_effect_delta_detected"]

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={"no_production_side_effect_proof": failed_proof},
    )

    assert summary["hard_gates_passed"] is False
    assert "no_production_side_effect_proof_failed" in summary["blocking_reasons"]
    assert summary["hard_gate_results"]["no_production_side_effect_proof"] == {
        "passed": False,
        "blocking_reasons": ["no_production_side_effect_proof_failed"],
        "artifact_ref": None,
    }


def test_release_gate_rejects_malformed_no_production_side_effect_proof():
    malformed_proof = _no_production_side_effect_proof()
    malformed_proof["deltas"].pop("plan_runs")

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={"case-1": _replay(_clean_candidate_replay(worker_artifact_count=7))},
        eval_run_id="eval-run",
        promotion_artifacts={"no_production_side_effect_proof": malformed_proof},
    )

    assert summary["hard_gates_passed"] is False
    assert summary["hard_gate_results"]["no_production_side_effect_proof"] == {
        "passed": False,
        "blocking_reasons": ["no_production_side_effect_proof_failed"],
        "artifact_ref": None,
    }


def test_release_gate_requires_shadow_final_summary_for_shadow_candidate_comparison_material():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            },
            shadow_final=False,
        )
    }
    comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs=replay_outputs,
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            "no_production_side_effect_proof": _no_production_side_effect_proof(),
            "shadow_candidate_comparison": comparison,
        },
    )

    assert summary["hard_gates_passed"] is True
    assert summary["promotion_review"]["required_artifacts"]["shadow_candidate_comparison"] == {
        "present": False,
        "artifact_ref": None,
    }
    assert "shadow_candidate_comparison" in summary["promotion_review"]["missing_artifacts"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_requires_shadow_candidate_comparison_to_cover_seven_workers():
    review = promotion_review(
        ready=True,
        eval_run_id="eval-run",
        current_candidate_inputs={("trace:case-1:decision_input_candidate", "sha256:decision")},
        promotion_artifacts={
            "shadow_candidate_comparison": {
                "schema_version": 1,
                "artifact_type": "shadow_candidate_comparison",
                "artifact_ref": "eval:eval-run:shadow_candidate_comparison",
                "eval_run_id": "eval-run",
                "decision_effect": "none",
                "case_count": 1,
                "candidate_replay_available": 1,
                "candidate_replay_missing": 0,
                "worker_artifact_count_min": 4,
                "switch_ready_count": 1,
                "switch_not_ready_count": 0,
                "case_summaries": [
                    {
                        "case_id": "case-1",
                        "status": "available",
                        "decision_input_ref": "trace:case-1:decision_input_candidate",
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
                            "source_decision_input_ref": "trace:case-1:decision_input_candidate",
                            "source_decision_input_hash": "sha256:decision",
                            "main_action": "no trade",
                        },
                        "shadow_legacy_comparison": {
                            "status": "available",
                            "decision_effect": "none",
                            "legacy_main_action": "no trade",
                            "shadow_main_action": "no trade",
                            "main_action_match": True,
                            "differences": [],
                        },
                    }
                ],
            }
        },
    )

    assert review["required_artifacts"]["shadow_candidate_comparison"] == {
        "present": False,
        "artifact_ref": None,
    }
    assert "shadow_candidate_comparison" in review["missing_artifacts"]
    assert review["allowed_to_change_production_final_input"] is False


def test_release_gate_requires_shadow_legacy_comparison_for_shadow_candidate_comparison_material():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            },
            shadow_final=True,
            shadow_legacy_comparison=False,
        )
    }
    comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs=replay_outputs,
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            "no_production_side_effect_proof": _no_production_side_effect_proof(),
            "shadow_candidate_comparison": comparison,
        },
    )

    assert summary["hard_gates_passed"] is True
    assert summary["promotion_review"]["required_artifacts"]["shadow_candidate_comparison"] == {
        "present": False,
        "artifact_ref": None,
    }
    assert "shadow_candidate_comparison" in summary["promotion_review"]["missing_artifacts"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_all_required_promotion_artifacts_still_do_not_auto_approve():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
            ,
            shadow_final=True,
        )
    }
    promotion_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts=promotion_artifacts,
    )

    _assert_common_release_gate_fields(
        summary,
        ready=True,
        blocking_reasons=[],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["promotion_approved"] is False
    assert summary["promotion_review"]["status"] == "ready_for_manual_release_decision"
    assert summary["promotion_review"]["candidate_gate_status"] == "passed"
    assert summary["promotion_review"]["promotion_material_status"] == "complete"
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False
    assert summary["promotion_review"]["missing_artifacts"] == []
    assert summary["promotion_review"]["required_artifacts"] == {
        "no_production_side_effect_proof": {
            "present": True,
            "artifact_ref": "eval:eval-run:no_production_side_effect_proof",
        },
        "manual_approval": {
            "present": True,
            "artifact_ref": "eval:eval-run:manual_approval:risk-owner",
        },
        "rollback_plan": {
            "present": True,
            "artifact_ref": "eval:eval-run:rollback_plan",
        },
        "impact_scope": {
            "present": True,
            "artifact_ref": "eval:eval-run:impact_scope",
        },
        "shadow_candidate_comparison": {
            "present": True,
            "artifact_ref": "eval:eval-run:shadow_candidate_comparison",
        },
    }


def test_release_gate_manual_release_decision_only_reaches_config_review():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    required_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }
    release_decision = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        required_artifact_refs={
            name: artifact["artifact_ref"]
            for name, artifact in required_artifacts.items()
        },
        notes="ready for config review",
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            **required_artifacts,
            "manual_release_decision": release_decision,
        },
    )

    assert summary["promotion_approved"] is False
    assert summary["promotion_review"]["status"] == "ready_for_config_change_review"
    assert summary["promotion_review"]["manual_release_decision_ref"] == (
        "eval:eval-run:manual_release_decision:release-owner"
    )
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False
    assert summary["promotion_review"]["config_change_review_required"] is True


def test_release_gate_rejects_shadow_candidate_comparison_when_current_replay_hash_differs():
    current_replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "decision_input_ref": "trace:case-1:decision_input_candidate",
                "decision_input_hash": "sha256:new-decision",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    old_replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "decision_input_ref": "trace:case-1:decision_input_candidate",
                "decision_input_hash": "sha256:old-decision",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    promotion_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=old_replay_outputs,
        ),
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=current_replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts=promotion_artifacts,
    )

    assert summary["promotion_review"]["status"] == "blocked_missing_artifacts"
    assert summary["promotion_review"]["required_artifacts"]["shadow_candidate_comparison"] == {
        "present": False,
        "artifact_ref": None,
    }
    assert "shadow_candidate_comparison" in summary["promotion_review"]["missing_artifacts"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_records_config_change_review_request_without_allowing_switch():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    required_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }
    release_decision = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        required_artifact_refs={
            name: artifact["artifact_ref"]
            for name, artifact in required_artifacts.items()
        },
        notes="ready for config review",
    )
    config_request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref=release_decision["artifact_ref"],
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="submit human config review request",
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            **required_artifacts,
            "manual_release_decision": release_decision,
            "config_change_review_request": config_request,
        },
    )

    assert summary["promotion_approved"] is False
    assert summary["promotion_review"]["status"] == "config_change_review_requested"
    assert summary["promotion_review"]["manual_release_decision_ref"] == release_decision["artifact_ref"]
    assert summary["promotion_review"]["config_change_review_request_ref"] == config_request["artifact_ref"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False
    assert summary["promotion_review"]["config_change_review_required"] is True


def test_release_gate_rejects_config_change_review_request_with_stale_candidate_hash():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    required_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }
    release_decision = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        required_artifact_refs={
            name: artifact["artifact_ref"]
            for name, artifact in required_artifacts.items()
        },
        notes="ready for config review",
    )
    stale_config_request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref=release_decision["artifact_ref"],
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:stale",
        notes="submit human config review request",
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            **required_artifacts,
            "manual_release_decision": release_decision,
            "config_change_review_request": stale_config_request,
        },
    )

    assert summary["promotion_review"]["status"] == "ready_for_config_change_review"
    assert "config_change_review_request_ref" not in summary["promotion_review"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_rejects_release_and_config_request_when_current_replay_hash_differs():
    current_replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "decision_input_ref": "trace:case-1:decision_input_candidate",
                "decision_input_hash": "sha256:new",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    old_replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "decision_input_ref": "trace:case-1:decision_input_candidate",
                "decision_input_hash": "sha256:old",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    required_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=old_replay_outputs,
        ),
    }
    release_decision = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:old",
        config_hash="sha256:config",
        required_artifact_refs={
            name: artifact["artifact_ref"]
            for name, artifact in required_artifacts.items()
        },
        notes="ready for config review",
    )
    config_request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref=release_decision["artifact_ref"],
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:old",
        notes="submit human config review request",
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=current_replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            **required_artifacts,
            "manual_release_decision": release_decision,
            "config_change_review_request": config_request,
        },
    )

    assert summary["promotion_review"]["status"] == "blocked_missing_artifacts"
    assert summary["promotion_review"]["required_artifacts"]["shadow_candidate_comparison"] == {
        "present": False,
        "artifact_ref": None,
    }
    assert "shadow_candidate_comparison" in summary["promotion_review"]["missing_artifacts"]
    assert "manual_release_decision_ref" not in summary["promotion_review"]
    assert "config_change_review_request_ref" not in summary["promotion_review"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_rejects_forged_config_change_review_request_that_claims_switch_allowed():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    required_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }
    release_decision = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        config_hash="sha256:config",
        required_artifact_refs={
            name: artifact["artifact_ref"]
            for name, artifact in required_artifacts.items()
        },
        notes="ready for config review",
    )
    forged_config_request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref=release_decision["artifact_ref"],
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="submit human config review request",
    )
    forged_config_request["allowed_to_change_production_final_input"] = True
    forged_config_request["decision_effect"] = "production_config_change"

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            **required_artifacts,
            "manual_release_decision": release_decision,
            "config_change_review_request": forged_config_request,
        },
    )

    assert summary["promotion_review"]["status"] == "ready_for_config_change_review"
    assert "config_change_review_request_ref" not in summary["promotion_review"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_rejects_forged_manual_release_decision_that_claims_production_switch_allowed():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    required_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }
    forged_release_decision = {
        "schema_version": 1,
        "artifact_type": "manual_release_decision",
        "artifact_ref": "eval:eval-run:manual_release_decision:release-owner",
        "eval_run_id": "eval-run",
        "decision_effect": "production_config_change",
        "release_manager": "release-owner",
        "decision": "approved_for_config_change_review",
        "baseline_final_input_mode": "legacy_prompt",
        "target_final_input_mode": "decision_input",
        "candidate_input_ref": "trace:case-1:decision_input_candidate",
        "candidate_input_hash": "sha256:decision",
        "config_hash": "sha256:config",
        "required_artifact_refs": {
            name: artifact["artifact_ref"]
            for name, artifact in required_artifacts.items()
        },
        "config_change_review_required": False,
        "allowed_to_change_production_final_input": True,
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            **required_artifacts,
            "manual_release_decision": forged_release_decision,
        },
    )

    assert summary["promotion_approved"] is False
    assert summary["promotion_review"]["status"] == "ready_for_manual_release_decision"
    assert "manual_release_decision_ref" not in summary["promotion_review"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_rejects_manual_release_decision_with_stale_candidate_hash():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    required_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }
    release_decision = build_manual_release_decision(
        eval_run_id="eval-run",
        release_manager="release-owner",
        decision="approved_for_config_change_review",
        baseline_final_input_mode="legacy_prompt",
        target_final_input_mode="decision_input",
        candidate_input_ref="trace:case-1:decision_input_candidate",
        candidate_input_hash="sha256:stale-candidate",
        config_hash="sha256:config",
        required_artifact_refs={
            name: artifact["artifact_ref"]
            for name, artifact in required_artifacts.items()
        },
        notes="ready for config review",
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            **required_artifacts,
            "manual_release_decision": release_decision,
        },
    )

    assert summary["promotion_review"]["status"] == "ready_for_manual_release_decision"
    assert "manual_release_decision_ref" not in summary["promotion_review"]
    assert summary["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_release_gate_rejects_cross_run_promotion_artifacts():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    stale_approval = build_manual_approval(
        eval_run_id="other-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            "no_production_side_effect_proof": _no_production_side_effect_proof(),
            "manual_approval": stale_approval,
        },
    )

    assert summary["promotion_review"]["required_artifacts"]["manual_approval"] == {
        "present": False,
        "artifact_ref": None,
    }
    assert "manual_approval" in summary["promotion_review"]["missing_artifacts"]


def test_release_gate_rejects_promotion_artifacts_without_eval_run_id():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    promotion_artifacts = {
        "no_production_side_effect_proof": _no_production_side_effect_proof(),
        "manual_approval": build_manual_approval(
            eval_run_id="eval-run",
            approver="risk-owner",
            decision="approved_for_manual_promotion",
            notes="reviewed",
        ),
        "rollback_plan": build_rollback_plan(
            eval_run_id="eval-run",
            rollback_target="config:decision.final_input_mode=legacy_prompt",
            rollback_steps=["restore legacy prompt"],
        ),
        "impact_scope": build_impact_scope(
            eval_run_id="eval-run",
            affected_components=["FinalInputSelector experiment"],
            excluded_components=["production journal", "notification delivery"],
        ),
        "shadow_candidate_comparison": build_shadow_candidate_comparison(
            eval_run_id="eval-run",
            replay_outputs=replay_outputs,
        ),
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        promotion_artifacts=promotion_artifacts,
    )

    assert summary["hard_gates_passed"] is True
    assert summary["promotion_review"]["status"] == "blocked_missing_artifacts"
    assert summary["promotion_review"]["required_artifacts"] == {
        "no_production_side_effect_proof": {"present": False, "artifact_ref": None},
        "manual_approval": {"present": False, "artifact_ref": None},
        "rollback_plan": {"present": False, "artifact_ref": None},
        "impact_scope": {"present": False, "artifact_ref": None},
        "shadow_candidate_comparison": {"present": False, "artifact_ref": None},
    }
    assert summary["promotion_review"]["missing_artifacts"] == [
        "no_production_side_effect_proof",
        "manual_approval",
        "rollback_plan",
        "impact_scope",
        "shadow_candidate_comparison",
    ]


def test_release_gate_rejects_dirty_shadow_candidate_comparison_artifact():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }
    dirty_comparison = build_shadow_candidate_comparison(
        eval_run_id="eval-run",
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {"passed": False, "violations": []},
                    "context_artifact_consistency": {"passed": True, "violations": []},
                    "switch_ready": False,
                    "blocking_reasons": ["candidate_gate_failed"],
                }
            )
        },
    )

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            "no_production_side_effect_proof": _no_production_side_effect_proof(),
            "shadow_candidate_comparison": dirty_comparison,
        },
    )

    assert summary["promotion_review"]["required_artifacts"]["shadow_candidate_comparison"] == {
        "present": False,
        "artifact_ref": None,
    }
    assert "shadow_candidate_comparison" in summary["promotion_review"]["missing_artifacts"]


def test_release_gate_rejects_incomplete_promotion_artifact_shells():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            "no_production_side_effect_proof": _no_production_side_effect_proof(),
            "manual_approval": {
                "schema_version": 1,
                "artifact_type": "manual_approval",
                "artifact_ref": "eval:eval-run:manual_approval:",
                "eval_run_id": "eval-run",
                "decision_effect": "none",
                "approver": "",
                "decision": "approved_for_manual_promotion",
                "notes": "missing approver",
            },
            "rollback_plan": {
                "schema_version": 1,
                "artifact_type": "rollback_plan",
                "artifact_ref": "eval:eval-run:rollback_plan",
                "eval_run_id": "eval-run",
                "decision_effect": "none",
                "rollback_target": "",
                "rollback_steps": [],
            },
            "impact_scope": {
                "schema_version": 1,
                "artifact_type": "impact_scope",
                "artifact_ref": "eval:eval-run:impact_scope",
                "eval_run_id": "eval-run",
                "decision_effect": "none",
                "affected_components": [],
                "excluded_components": [],
            },
            "shadow_candidate_comparison": {
                "schema_version": 1,
                "artifact_type": "shadow_candidate_comparison",
                "artifact_ref": "eval:eval-run:shadow_candidate_comparison",
                "eval_run_id": "eval-run",
                "decision_effect": "none",
                "case_count": 0,
                "candidate_replay_available": 0,
                "worker_artifact_count_min": 0,
                "case_summaries": [],
            },
        },
    )

    assert summary["hard_gates_passed"] is True
    assert summary["promotion_approved"] is False
    assert summary["promotion_review"]["status"] == "blocked_missing_artifacts"
    assert summary["promotion_review"]["required_artifacts"] == {
        "no_production_side_effect_proof": {
            "present": True,
            "artifact_ref": "eval:eval-run:no_production_side_effect_proof",
        },
        "manual_approval": {"present": False, "artifact_ref": None},
        "rollback_plan": {"present": False, "artifact_ref": None},
        "impact_scope": {"present": False, "artifact_ref": None},
        "shadow_candidate_comparison": {"present": False, "artifact_ref": None},
    }
    assert summary["promotion_review"]["missing_artifacts"] == [
        "manual_approval",
        "rollback_plan",
        "impact_scope",
        "shadow_candidate_comparison",
    ]


def test_release_gate_rejects_malformed_promotion_artifact_numbers_without_raising():
    replay_outputs = {
        "case-1": _replay(
            {
                "status": "available",
                "worker_artifact_count": 7,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "worker_manifest_consistency": {"passed": True, "violations": []},
                "context_artifact_consistency": {"passed": True, "violations": []},
                "switch_ready": True,
                "blocking_reasons": [],
            }
        )
    }

    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs=replay_outputs,
        eval_run_id="eval-run",
        promotion_artifacts={
            "no_production_side_effect_proof": _no_production_side_effect_proof(),
            "shadow_candidate_comparison": {
                "schema_version": 1,
                "artifact_type": "shadow_candidate_comparison",
                "artifact_ref": "eval:eval-run:shadow_candidate_comparison",
                "eval_run_id": "eval-run",
                "decision_effect": "none",
                "case_count": "not-a-number",
                "candidate_replay_available": "not-a-number",
                "worker_artifact_count_min": "not-a-number",
                "switch_ready_count": "not-a-number",
                "switch_not_ready_count": "not-a-number",
                "case_summaries": [{"case_id": "case-1", "status": "available"}],
            }
        },
    )

    assert summary["promotion_review"]["required_artifacts"]["shadow_candidate_comparison"] == {
        "present": False,
        "artifact_ref": None,
    }


def test_release_gate_sanitizes_candidate_replay_violation_payloads():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "worker_manifest_consistency": {
                        "passed": False,
                        "violations": [
                            {
                                "rule_id": "worker_manifest_count_mismatch",
                                "expected": 4,
                                "observed": 1,
                                "raw_snippet": "raw snippet must not leak",
                            }
                        ],
                    },
                    "context_artifact_consistency": {
                        "passed": False,
                        "violations": [
                            {
                                "rule_id": "context_decision_input_hash_mismatch",
                                "expected": "sha256:decision",
                                "observed": "sha256:other",
                                "raw_payload": "raw payload must not leak",
                            }
                        ],
                    },
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
    )

    worker_coverage = summary["hard_gate_results"]["worker_artifact_coverage"]
    assert worker_coverage["manifest_consistency_violations"] == [
        {
            "case_id": "case-1",
            "rule_id": "worker_manifest_count_mismatch",
            "expected": 4,
            "observed": 1,
        }
    ]
    assert worker_coverage["context_artifact_consistency_violations"] == [
        {
            "case_id": "case-1",
            "rule_id": "context_decision_input_hash_mismatch",
            "expected": "sha256:decision",
            "observed": "sha256:other",
        }
    ]


def test_release_gate_blocks_manual_promotion_when_minimum_case_count_is_not_met():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
        minimum_case_count=2,
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["minimum_eval_coverage_not_met"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["minimum_eval_coverage"] == {
        "passed": False,
        "blocking_reasons": ["minimum_eval_coverage_not_met"],
        "required_min": 2,
        "observed": 1,
    }


def test_release_gate_blocks_when_schema_valid_rate_is_below_threshold():
    summary = build_release_gate_summary(
        scores=[
            _score(
                passed=True,
                failure_category="none",
                judge_name="rule.action_enum",
            ),
            _score(
                passed=False,
                failure_category="schema_action_invalid",
                judge_name="rule.action_enum",
                severity="high",
            ),
        ],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            ),
            "case-2": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            ),
        },
        schema_valid_rate_threshold=1.0,
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "schema_valid_rate_below_threshold",
            "eval_scores_failed",
            "schema_action_invalid",
        ],
        candidate_replay_available=2,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["schema_valid_rate"] == {
        "passed": False,
        "blocking_reasons": ["schema_valid_rate_below_threshold"],
        "required_min": 1.0,
        "observed_rate": 0.5,
        "observed_count": 2,
        "passed_count": 1,
    }


def test_release_gate_blocks_when_required_badcase_severity_coverage_is_missing():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                }
            )
        },
        cases=[
            {
                "case_id": "case-1",
                "severity": "medium",
            }
        ],
        required_badcase_severities=["high", "critical"],
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["badcase_severity_coverage_not_met"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["badcase_severity_coverage"] == {
        "passed": False,
        "blocking_reasons": ["badcase_severity_coverage_not_met"],
        "required_severities": ["high", "critical"],
        "observed_counts": {"high": 0, "critical": 0},
        "missing_severities": ["high", "critical"],
    }


def test_release_gate_requires_blocked_action_evidence_when_candidate_gate_fails():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": False,
                    "blocking_reasons": ["candidate_gate_failed"],
                    "blocked_actions": [],
                    "missing_facts": [],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=[
            "candidate_gate_failed",
            "candidate_block_evidence_incomplete",
            "final_switch_readiness_not_ready",
        ],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["candidate_business_gates"] == {
        "passed": False,
        "blocking_reasons": ["candidate_gate_failed", "candidate_block_evidence_incomplete"],
        "blocked_action_cases": [],
        "incomplete_block_evidence_cases": ["case-1"],
    }


def test_release_gate_blocks_search_derived_execution_fact_source_violations():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                    "execution_fact_source_violations": [
                        {
                            "evidence_id": "ev-search-mark",
                            "data_type": "mark",
                            "source_type": "search_derived",
                        }
                    ],
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["execution_fact_source_violation"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["execution_fact_sources"] == {
        "passed": False,
        "blocking_reasons": ["execution_fact_source_violation"],
        "violations": [
            {
                "case_id": "case-1",
                "evidence_id": "ev-search-mark",
                "data_type": "mark",
                "source_type": "search_derived",
            }
        ],
    }


def test_release_gate_blocks_when_complete_replay_refs_are_missing():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
                    "complete_replay_refs": {
                        "has_lead_synthesis_artifact": False,
                        "has_final_decision_output": True,
                        "has_final_input_selection": True,
                        "has_parsed_plan": False,
                        "has_production_control_gate": True,
                        "has_risk_gate_result": False,
                        "has_side_effect_policy": True,
                        "has_context_artifact_summary": True,
                        "has_version_lock": False,
                        "has_telemetry_refs": False,
                        "has_evidence_snapshot_refs": False,
                        "has_memory_snapshot_refs": False,
                        "has_span_tree_refs": False,
                    },
                    "complete_replay_missing_refs": [
                        "lead_synthesis_artifact",
                        "parsed_plan",
                        "risk_gate_result",
                        "version_lock",
                        "telemetry_refs",
                        "evidence_snapshot_refs",
                        "memory_snapshot_refs",
                        "span_tree_refs",
                        "raw payload must not leak",
                    ],
                    "span_tree_parent_complete": False,
                    "span_tree_missing_parent_count": 1,
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["complete_replay_input_incomplete", "span_tree_parent_incomplete"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["complete_replay_input"] == {
        "passed": False,
        "blocking_reasons": ["complete_replay_input_incomplete", "span_tree_parent_incomplete"],
        "missing_refs": [
            {
                "case_id": "case-1",
                "missing_refs": [
                    "lead_synthesis_artifact",
                    "parsed_plan",
                    "risk_gate_result",
                    "version_lock",
                    "telemetry_refs",
                    "evidence_snapshot_refs",
                    "memory_snapshot_refs",
                    "span_tree_refs",
                ],
            }
        ],
        "span_tree_incomplete_cases": [
            {
                "case_id": "case-1",
                "missing_parent_count": 1,
            }
        ],
    }


def test_release_gate_blocks_when_span_tree_parent_links_are_incomplete():
    summary = build_release_gate_summary(
        scores=[_score(passed=True, failure_category="none")],
        replay_outputs={
            "case-1": _replay(
                {
                    "status": "available",
                    "worker_artifact_count": 7,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "switch_ready": True,
                    "blocking_reasons": [],
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
                    "span_tree_parent_complete": False,
                    "span_tree_missing_parent_count": 2,
                }
            )
        },
    )

    _assert_common_release_gate_fields(
        summary,
        ready=False,
        blocking_reasons=["span_tree_parent_incomplete"],
        candidate_replay_available=1,
        candidate_replay_missing=0,
        worker_artifact_count_min=7,
    )
    assert summary["hard_gate_results"]["complete_replay_input"] == {
        "passed": False,
        "blocking_reasons": ["span_tree_parent_incomplete"],
        "missing_refs": [],
        "span_tree_incomplete_cases": [
            {
                "case_id": "case-1",
                "missing_parent_count": 2,
            }
        ],
    }


def _score(
    *,
    passed: bool,
    failure_category: str,
    judge_name: str = "rule.fixture",
    severity: str | None = None,
) -> EvalScore:
    return EvalScore(
        score_id=f"score:{failure_category}:{passed}",
        eval_run_id="eval-run",
        case_id="case-1",
        source_trace_id="trace-1",
        source_badcase_id=1,
        judge_name=judge_name,
        judge_type="rule",
        passed=passed,
        severity=severity or ("low" if passed else "high"),
        failure_category=failure_category,
        reason_summary="fixture score",
        evidence_refs=[],
    )


def _replay(
    candidate_replay: dict[str, object],
    *,
    status: str = "completed",
    mode: str = "candidate_decision",
    metadata: dict[str, object] | None = None,
    shadow_final: bool = True,
    shadow_legacy_comparison: bool = True,
) -> EvalReplayOutput:
    candidate_payload = dict(candidate_replay)
    if candidate_payload.get("status") == "available" and "artifact_snapshot_consistency" not in candidate_payload:
        candidate_payload["artifact_snapshot_consistency"] = {"passed": True, "violations": []}
    if candidate_payload.get("status") == "available":
        candidate_payload.setdefault("decision_input_ref", "trace:case-1:decision_input_candidate")
        candidate_payload.setdefault("decision_input_hash", "sha256:decision")
        candidate_payload.setdefault("worker_manifest_consistency", {"passed": True, "violations": []})
        candidate_payload.setdefault("context_artifact_consistency", {"passed": True, "violations": []})
        candidate_payload.setdefault("counter_conflict_coverage", {"passed": True, "violations": []})
        candidate_payload.setdefault("complete_replay_refs", _complete_replay_refs_all_present())
        candidate_payload.setdefault("complete_replay_missing_refs", [])
        candidate_payload.setdefault("span_tree_parent_complete", True)
        candidate_payload.setdefault("span_tree_missing_parent_count", 0)
    output_payload: dict[str, object] = {"candidate_replay": candidate_payload}
    if shadow_final:
        output_payload["decision_input_shadow_final"] = {
            "status": "completed",
            "artifact_ref": "candidate:decision_input_shadow_final",
            "artifact_hash": "sha256:shadow-final",
            "decision_effect": "none",
            "source_decision_input_ref": candidate_payload.get("decision_input_ref"),
            "source_decision_input_hash": candidate_payload.get("decision_input_hash"),
            "shadow_final_summary": {
                "main_action": "no trade",
                "probability": 0.52,
            },
        }
    if shadow_final and shadow_legacy_comparison:
        output_payload["shadow_legacy_comparison"] = {
            "status": "available",
            "decision_effect": "none",
            "legacy_observed_summary": {
                "main_action": "no trade",
                "probability": None,
            },
            "shadow_final_summary": {
                "main_action": "no trade",
                "probability": 0.52,
            },
            "main_action_match": True,
            "probability_delta": None,
            "differences": [],
        }
    return EvalReplayOutput(
        replay_id="replay-1",
        case_id="case-1",
        source_trace_id="trace-1",
        source_badcase_id=1,
        frozen_input_hash="frozen-hash",
        status=status,
        mode=mode,
        output_payload=output_payload,
        metadata=metadata or {"source": "eval.candidate_decision_replay", "decision_effect": "none"},
    )


def _clean_candidate_replay(*, worker_artifact_count: int = 7) -> dict[str, object]:
    return {
        "status": "available",
        "worker_artifact_count": worker_artifact_count,
        "worker_manifest_complete": True,
        "worker_manifest_missing_fields": [],
        "worker_manifest_consistency": {"passed": True, "violations": []},
        "context_artifact_consistency": {"passed": True, "violations": []},
        "artifact_snapshot_consistency": {"passed": True, "violations": []},
        "counter_conflict_coverage": {"passed": True, "violations": []},
        "complete_replay_refs": _complete_replay_refs_all_present(),
        "complete_replay_missing_refs": [],
        "span_tree_parent_complete": True,
        "span_tree_missing_parent_count": 0,
        "switch_ready": True,
        "blocking_reasons": [],
    }


def _complete_replay_refs_all_present() -> dict[str, bool]:
    return {
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
    }


def _no_production_side_effect_proof(eval_run_id: str = "eval-run") -> dict[str, object]:
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


def _assert_common_release_gate_fields(
    summary: dict[str, object],
    *,
    ready: bool,
    blocking_reasons: list[str],
    candidate_replay_available: int,
    candidate_replay_missing: int,
    worker_artifact_count_min: int,
) -> None:
    assert summary["schema_version"] == 1
    assert summary["ready"] is ready
    assert summary["hard_gates_passed"] is ready
    assert summary["promotion_approved"] is False
    assert summary["decision_effect"] == "none"
    assert summary["blocking_reasons"] == blocking_reasons
    assert summary["candidate_replay_available"] == candidate_replay_available
    assert summary["candidate_replay_missing"] == candidate_replay_missing
    assert summary["worker_artifact_count_min"] == worker_artifact_count_min
    assert isinstance(summary["hard_gate_results"], dict)
    assert set(summary["hard_gate_results"]) == {
        "minimum_eval_coverage",
        "schema_valid_rate",
        "eval_scores",
        "critical_rule_failures",
        "manual_execution_required",
        "eval_side_effect_guard",
        "no_production_side_effect_proof",
        "badcase_severity_coverage",
        "candidate_business_gates",
        "execution_fact_sources",
        "candidate_replay",
        "worker_artifact_coverage",
        "complete_replay_input",
        "worker_hard_blocks",
        "counter_conflict_coverage",
        "final_switch_readiness",
    }

