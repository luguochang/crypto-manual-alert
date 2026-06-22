from __future__ import annotations

from crypto_manual_alert.eval.promotion_artifacts import (
    build_config_change_review_request,
    build_manual_approval,
    build_shadow_candidate_comparison,
)
from crypto_manual_alert.eval.schema import EvalCase, EvalReplayOutput, EvalRun
from crypto_manual_alert.eval.store import EvalStore
from crypto_manual_alert.decision.frozen_input import stable_hash


def test_eval_store_persists_promotion_artifacts_as_dedicated_readback(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
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
                        "decision_input_ref": "trace:1:decision",
                        "decision_input_hash": "sha256:decision",
                        "replayable_input_ref": "trace:1:replayable",
                        "replayable_input_hash": "sha256:replayable",
                        "worker_artifact_count": 4,
                        "worker_manifest_complete": True,
                        "worker_manifest_consistency": {"passed": True},
                        "context_artifact_consistency": {"passed": True},
                        "switch_ready": True,
                        "blocking_reasons": [],
                    }
                },
            )
        },
    )
    run = EvalRun(
        eval_run_id="eval-run",
        dataset_name="selected_badcases",
        mode="judge_only_fixture",
        status="passed",
        started_at="2026-06-30T00:00:00+00:00",
        ended_at="2026-06-30T00:00:01+00:00",
        case_count=1,
        pass_count=1,
        fail_count=0,
        metadata={"promotion_artifacts": {"shadow_candidate_comparison": comparison}},
    )

    store.insert_run(run, cases=[], scores=[])

    assert store.get_promotion_artifacts("eval-run") == {
        "shadow_candidate_comparison": comparison
    }


def test_eval_store_rejects_cross_run_promotion_artifact_writes(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    stale_approval = build_manual_approval(
        eval_run_id="other-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )

    try:
        store.upsert_promotion_artifacts(
            "eval-run",
            {"manual_approval": stale_approval},
        )
    except ValueError as exc:
        assert "promotion artifact eval_run_id mismatch" in str(exc)
    else:
        raise AssertionError("cross-run promotion artifact should fail")


def test_eval_store_rolls_back_batch_when_one_promotion_artifact_is_invalid(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    valid_approval = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )
    stale_approval = build_manual_approval(
        eval_run_id="other-run",
        approver="other-owner",
        decision="approved_for_manual_promotion",
        notes="stale",
    )

    try:
        store.upsert_promotion_artifacts(
            "eval-run",
            {
                "manual_approval": valid_approval,
                "manual_release_decision": stale_approval,
            },
        )
    except ValueError as exc:
        assert "promotion artifact eval_run_id mismatch" in str(exc)
    else:
        raise AssertionError("invalid batch promotion artifact should fail")

    assert store.get_promotion_artifacts("eval-run") == {}


def test_eval_store_rejects_promotion_artifacts_with_side_effects(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    unsafe_approval = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )
    unsafe_approval["decision_effect"] = "production_final_input"

    try:
        store.upsert_promotion_artifacts(
            "eval-run",
            {"manual_approval": unsafe_approval},
        )
    except ValueError as exc:
        assert "promotion artifact decision_effect must be none" in str(exc)
    else:
        raise AssertionError("side-effect promotion artifact should fail")


def test_eval_store_rejects_promotion_artifact_ref_bound_to_other_run(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    approval = build_manual_approval(
        eval_run_id="eval-run",
        approver="risk-owner",
        decision="approved_for_manual_promotion",
        notes="reviewed",
    )
    approval["artifact_ref"] = "eval:other-run:manual_approval:risk-owner"

    try:
        store.upsert_promotion_artifacts("eval-run", {"manual_approval": approval})
    except ValueError as exc:
        assert "promotion artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("cross-run artifact_ref should fail")


def test_eval_store_persists_config_change_review_request_as_no_effect_artifact(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="human config review only",
    )

    store.upsert_promotion_artifacts(
        "eval-run",
        {"config_change_review_request": request},
    )

    assert store.get_promotion_artifacts("eval-run") == {
        "config_change_review_request": request
    }


def test_eval_store_rejects_effectful_config_change_review_request(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="human config review only",
    )
    request["decision_effect"] = "production_config_change"

    try:
        store.upsert_promotion_artifacts(
            "eval-run",
            {"config_change_review_request": request},
        )
    except ValueError as exc:
        assert "promotion artifact decision_effect must be none" in str(exc)
    else:
        raise AssertionError("effectful config review request should fail")


def test_eval_store_rejects_config_review_request_that_claims_switch_permission(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    request = build_config_change_review_request(
        eval_run_id="eval-run",
        requester="release-owner",
        manual_release_decision_ref="eval:eval-run:manual_release_decision:release-owner",
        baseline_final_input_mode="legacy_prompt",
        requested_final_input_mode="decision_input",
        candidate_input_ref="trace:eval:decision_input_candidate",
        candidate_input_hash="sha256:decision",
        notes="human config review only",
    )
    request["allowed_to_change_production_final_input"] = True

    try:
        store.upsert_promotion_artifacts(
            "eval-run",
            {"config_change_review_request": request},
        )
    except ValueError as exc:
        assert "config review request cannot allow production final input changes" in str(exc)
    else:
        raise AssertionError("switch-permitting config review request should fail")


def test_eval_store_persists_candidate_artifacts_as_dedicated_readback(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={
            "candidate_audit": {
                "artifact_snapshot": {
                    "schema_version": 1,
                    "decision_effect": "none",
                    "production_final_input": False,
                    "notification_input": False,
                    "decision_input_candidate": {
                        "input_ref": "trace:trace-1:decision_input_candidate",
                        "input_hash": "sha256:decision",
                        "decision_effect": "none",
                        "artifact_hash": "sha256:decision-artifact",
                    },
                    "replayable_input_candidate": {
                        "input_ref": "trace:trace-1:replayable_input_candidate",
                        "input_hash": "sha256:replayable",
                        "decision_effect": "none",
                        "artifact_hash": "sha256:replayable-artifact",
                    },
                    "lead_synthesis": {
                        "artifact_ref": "candidate:lead_synthesis",
                        "decision_effect": "none",
                        "artifact_hash": "sha256:lead",
                    },
                    "worker_result_manifest": {
                        "artifact_ref": "candidate:worker_result_manifest",
                        "decision_effect": "none",
                        "manifest_count": 4,
                        "artifact_hash": "sha256:manifest",
                    },
                    "gate_candidate": {
                        "artifact_ref": "candidate:gate_candidate",
                        "decision_effect": "none",
                        "passed": True,
                        "artifact_hash": "sha256:gate",
                    },
                    "plan_semantic_candidate": {
                        "artifact_ref": "candidate:plan_semantic_candidate",
                        "decision_effect": "none",
                        "passed": True,
                        "artifact_hash": "sha256:semantic",
                    },
                    "final_decision_switch_readiness": {
                        "artifact_ref": "candidate:final_decision_switch_readiness",
                        "decision_effect": "none",
                        "ready": False,
                        "artifact_hash": "sha256:readiness",
                    },
                }
            }
        },
    )

    store.upsert_cases([case])

    assert store.get_candidate_artifacts("case-1") == {
        "decision_input_candidate": {
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
            "decision_effect": "none",
            "artifact_hash": "sha256:decision-artifact",
        },
        "replayable_input_candidate": {
            "input_ref": "trace:trace-1:replayable_input_candidate",
            "input_hash": "sha256:replayable",
            "decision_effect": "none",
            "artifact_hash": "sha256:replayable-artifact",
        },
        "lead_synthesis": {
            "artifact_ref": "candidate:lead_synthesis",
            "decision_effect": "none",
            "artifact_hash": "sha256:lead",
        },
        "worker_result_manifest": {
            "artifact_ref": "candidate:worker_result_manifest",
            "decision_effect": "none",
            "manifest_count": 4,
            "artifact_hash": "sha256:manifest",
        },
        "gate_candidate": {
            "artifact_ref": "candidate:gate_candidate",
            "decision_effect": "none",
            "passed": True,
            "artifact_hash": "sha256:gate",
        },
        "plan_semantic_candidate": {
            "artifact_ref": "candidate:plan_semantic_candidate",
            "decision_effect": "none",
            "passed": True,
            "artifact_hash": "sha256:semantic",
        },
        "final_decision_switch_readiness": {
            "artifact_ref": "candidate:final_decision_switch_readiness",
            "decision_effect": "none",
            "ready": False,
            "artifact_hash": "sha256:readiness",
        },
    }
    stored = store.get_candidate_artifacts("case-1", include_store_metadata=True)
    lead = dict(stored["lead_synthesis"])
    stored_hash = lead.pop("stored_artifact_hash")
    assert stored_hash == stable_hash(lead)
    assert stored_hash != lead["artifact_hash"]
    assert "stored_artifact_hash" not in store.get_candidate_artifacts("case-1")["lead_synthesis"]


def test_eval_store_run_detail_uses_no_effect_not_run_replay_fallback(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={},
    )
    run = EvalRun(
        eval_run_id="eval-run",
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

    store.insert_run(run, cases=[case], scores=[])

    detail = store.get_run_detail("eval-run")
    assert detail is not None
    assert detail["cases"][0]["replay_result"] == {
        "status": "not_run",
        "mode": "none",
        "case_id": "case-1",
        "source_trace_id": "trace-1",
        "source_badcase_id": 1,
        "frozen_input_hash": "frozen-hash",
        "final_action": None,
        "allowed": None,
        "output_hash": None,
        "reason_summary": None,
        "error_message": None,
        "duration_ms": None,
        "metadata": {},
    }
    assert "output_payload" not in detail["cases"][0]["replay_result"]
    assert "created_at" not in detail["cases"][0]["replay_result"]


def test_eval_store_recomputes_candidate_artifact_store_hash_from_payload(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    artifact = {
        "artifact_ref": "candidate:lead_synthesis",
        "decision_effect": "none",
        "artifact_hash": "sha256:self-reported-but-not-store-hash",
        "extra_field": "payload participates in store hash",
    }
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={
            "candidate_audit": {
                "artifact_snapshot": {
                    "schema_version": 1,
                    "decision_effect": "none",
                    "production_final_input": False,
                    "notification_input": False,
                    "lead_synthesis": artifact,
                }
            }
        },
    )

    store.upsert_cases([case])

    assert store.get_candidate_artifact_hash("case-1", "lead_synthesis") == stable_hash(artifact)


def test_eval_store_rolls_back_case_batch_when_candidate_artifact_is_invalid(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    valid_case = EvalCase(
        case_id="case-valid",
        dataset_name="selected_badcases",
        source_trace_id="trace-valid",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={
            "candidate_audit": {
                "artifact_snapshot": {
                    "schema_version": 1,
                    "decision_effect": "none",
                    "production_final_input": False,
                    "notification_input": False,
                    "lead_synthesis": {
                        "artifact_ref": "candidate:lead_synthesis",
                        "decision_effect": "none",
                        "artifact_hash": "sha256:lead",
                    },
                }
            }
        },
    )
    invalid_case = EvalCase(
        case_id="case-invalid",
        dataset_name="selected_badcases",
        source_trace_id="trace-invalid",
        source_badcase_id=2,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={
            "candidate_audit": {
                "artifact_snapshot": {
                    "schema_version": 1,
                    "decision_effect": "none",
                    "production_final_input": False,
                    "notification_input": False,
                    "lead_synthesis": {
                        "artifact_ref": "candidate:not_lead_synthesis",
                        "decision_effect": "none",
                        "artifact_hash": "sha256:lead",
                    },
                }
            }
        },
    )

    try:
        store.upsert_cases([valid_case, invalid_case])
    except ValueError as exc:
        assert "candidate artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("invalid candidate artifact in batch should fail")

    assert store.get_case("case-valid") is None
    assert store.get_candidate_artifacts("case-valid") == {}


def test_eval_store_rejects_malformed_candidate_artifact_refs(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={
            "candidate_audit": {
                "artifact_snapshot": {
                    "schema_version": 1,
                    "decision_effect": "none",
                    "production_final_input": False,
                    "notification_input": False,
                    "decision_input_candidate": {
                        "input_ref": "trace:trace-1:not_decision_input",
                        "input_hash": "sha256:decision",
                        "decision_effect": "none",
                        "artifact_hash": "sha256:decision-artifact",
                    }
                }
            }
        },
    )

    try:
        store.upsert_cases([case])
    except ValueError as exc:
        assert "candidate decision input artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("malformed candidate artifact ref should fail")


def test_eval_store_rejects_candidate_artifacts_with_side_effects(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={
            "candidate_audit": {
                "artifact_snapshot": {
                    "schema_version": 1,
                    "decision_effect": "none",
                    "production_final_input": False,
                    "notification_input": False,
                    "lead_synthesis": {
                        "artifact_ref": "candidate:lead_synthesis",
                        "decision_effect": "production_final_input",
                        "artifact_hash": "sha256:lead",
                    }
                }
            }
        },
    )

    try:
        store.upsert_cases([case])
    except ValueError as exc:
        assert "candidate artifact decision_effect must be none" in str(exc)
    else:
        raise AssertionError("effectful candidate artifact should fail")


def test_eval_store_rejects_candidate_artifact_snapshot_with_production_side_effect_flags(tmp_path):
    store = EvalStore(tmp_path / "eval.db")

    for unsafe_fields in (
        {"production_final_input": True},
        {"notification_input": True},
        {"decision_effect": "production_final_input"},
    ):
        case = EvalCase(
            case_id=f"case-{len(str(unsafe_fields))}",
            dataset_name="selected_badcases",
            source_trace_id="trace-1",
            source_badcase_id=1,
            created_at="2026-06-30T00:00:00+00:00",
            symbol="ETH-USDT-SWAP",
            horizon="6h",
            failure_category="grounding_error",
            severity="high",
            expected_behavior="expected",
            actual_behavior="actual",
            summary="summary",
            status="open",
            frozen_input_hash="frozen-hash",
            input_summary={
                "candidate_audit": {
                    "artifact_snapshot": {
                        "schema_version": 1,
                        "decision_effect": "none",
                        "production_final_input": False,
                        "notification_input": False,
                        **unsafe_fields,
                        "lead_synthesis": {
                            "artifact_ref": "candidate:lead_synthesis",
                            "decision_effect": "none",
                            "artifact_hash": "sha256:lead",
                        },
                    }
                }
            },
        )

        try:
            store.upsert_cases([case])
        except ValueError as exc:
            assert "candidate artifact snapshot decision_effect must be none" in str(exc)
        else:
            raise AssertionError("effectful candidate artifact snapshot should fail")


def test_eval_store_rejects_candidate_artifacts_missing_decision_effect(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={
            "candidate_audit": {
                "artifact_snapshot": {
                    "schema_version": 1,
                    "decision_effect": "none",
                    "production_final_input": False,
                    "notification_input": False,
                    "lead_synthesis": {
                        "artifact_ref": "candidate:lead_synthesis",
                        "artifact_hash": "sha256:lead",
                    },
                }
            }
        },
    )

    try:
        store.upsert_cases([case])
    except ValueError as exc:
        assert "candidate artifact decision_effect must be none" in str(exc)
    else:
        raise AssertionError("candidate artifact without explicit decision_effect should fail")
