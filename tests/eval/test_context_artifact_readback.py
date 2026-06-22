from __future__ import annotations

from crypto_manual_alert.eval.replay import ReplayRunner
from crypto_manual_alert.eval.schema import EvalCase
from crypto_manual_alert.eval.store import EvalStore


def test_candidate_replay_detects_context_lead_synthesis_artifact_hash_mismatch(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:stale-context-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    consistency = output.output_payload["candidate_decision"]["context_artifact_consistency"]
    assert consistency["passed"] is False
    assert {
        "rule_id": "context_lead_synthesis_artifact_hash_mismatch",
        "expected": "sha256:sidecar-lead",
        "observed": "sha256:stale-context-lead",
    } in consistency["violations"]


def test_candidate_replay_detects_missing_context_gate_candidate_artifact_ref(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    consistency = output.output_payload["candidate_decision"]["context_artifact_consistency"]
    assert consistency["passed"] is False
    assert {
        "rule_id": "context_gate_candidate_artifact_ref_missing",
        "artifact_type": "gate_candidate",
    } in consistency["violations"]


def test_candidate_replay_detects_context_candidate_gate_hash_mismatches(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        gate_result_refs={
            "lead_synthesis_artifact": {
                "artifact_ref": "candidate:lead_synthesis",
                "artifact_hash": "sha256:sidecar-lead",
            },
            "gate_candidate": {
                "artifact_ref": "candidate:gate_candidate",
                "artifact_hash": "sha256:stale-gate",
            },
            "plan_semantic_candidate": {
                "artifact_ref": "candidate:plan_semantic_candidate",
                "artifact_hash": "sha256:stale-semantic",
            },
            "final_decision_switch_readiness": {
                "artifact_ref": "candidate:final_decision_switch_readiness",
                "artifact_hash": "sha256:stale-readiness",
            },
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    consistency = output.output_payload["candidate_decision"]["context_artifact_consistency"]
    assert consistency["passed"] is False
    assert {
        "rule_id": "context_gate_candidate_artifact_hash_mismatch",
        "expected": "sha256:gate",
        "observed": "sha256:stale-gate",
    } in consistency["violations"]
    assert {
        "rule_id": "context_plan_semantic_candidate_artifact_hash_mismatch",
        "expected": "sha256:semantic",
        "observed": "sha256:stale-semantic",
    } in consistency["violations"]
    assert {
        "rule_id": "context_final_decision_switch_readiness_artifact_hash_mismatch",
        "expected": "sha256:readiness",
        "observed": "sha256:stale-readiness",
    } in consistency["violations"]


def test_candidate_replay_detects_failed_required_worker_not_propagated_to_lead_synthesis(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        worker_result_manifest=[
            {
                "task_id": "task-quality",
                "agent_name": "DataQualityAgent",
                "status": "failed",
                "required": True,
                "input_ref": "trace:trace-1:worker-input",
                "input_hash": "sha256:worker-input",
                "agent_run_request_hash": "sha256:request",
                "output_hash": "sha256:quality",
                "trace_ref": "trace:trace-1:worker",
                "failure_policy_applied": "hard_block",
                "agent_run_result": {
                    "input_view_hash": "sha256:worker-input",
                    "agent_run_request_hash": "sha256:request",
                    "required": True,
                    "failure_policy_applied": "hard_block",
                },
            }
        ],
        lead_synthesis={
            "included_contribution_ids": [],
            "dropped_contributions": [],
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    consistency = output.output_payload["candidate_decision"]["worker_manifest_consistency"]
    assert consistency["passed"] is False
    assert {
        "rule_id": "lead_synthesis_missing_failed_worker_drop",
        "task_id": "task-quality",
        "agent_name": "DataQualityAgent",
        "failure_policy_applied": "hard_block",
    } in consistency["violations"]


def test_candidate_replay_advises_when_optional_worker_drop_is_not_recorded(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        worker_result_manifest=[
            {
                "task_id": "task-scenario",
                "agent_name": "ScenarioForkAgent",
                "status": "failed",
                "required": False,
                "input_ref": "trace:trace-1:worker-input",
                "input_hash": "sha256:worker-input",
                "agent_run_request_hash": "sha256:request",
                "output_hash": "sha256:scenario",
                "trace_ref": "trace:trace-1:worker",
                "failure_policy_applied": "soft_downgrade",
                "agent_run_result": {
                    "input_view_hash": "sha256:worker-input",
                    "agent_run_request_hash": "sha256:request",
                    "required": False,
                    "failure_policy_applied": "soft_downgrade",
                },
            }
        ],
        lead_synthesis={
            "included_contribution_ids": [],
            "dropped_contributions": [],
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    consistency = output.output_payload["candidate_decision"]["worker_manifest_consistency"]
    assert consistency["passed"] is True
    assert consistency["violations"] == []
    assert consistency["advisories"] == [
        {
            "rule_id": "lead_synthesis_missing_optional_worker_drop",
            "task_id": "task-scenario",
            "agent_name": "ScenarioForkAgent",
            "failure_policy_applied": "soft_downgrade",
        }
    ]


def test_candidate_replay_accepts_recorded_optional_soft_downgrade_drop(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        worker_result_manifest=[
            {
                "task_id": "task-scenario",
                "agent_name": "ScenarioForkAgent",
                "status": "failed",
                "required": False,
                "input_ref": "trace:trace-1:worker-input",
                "input_hash": "sha256:worker-input",
                "agent_run_request_hash": "sha256:request",
                "output_hash": "sha256:scenario",
                "trace_ref": "trace:trace-1:worker",
                "failure_policy_applied": "soft_downgrade",
                "agent_run_result": {
                    "input_view_hash": "sha256:worker-input",
                    "agent_run_request_hash": "sha256:request",
                    "required": False,
                    "failure_policy_applied": "soft_downgrade",
                },
            }
        ],
        lead_synthesis={
            "included_contribution_ids": [],
            "dropped_contributions": [
                {
                    "contribution_id": "c-scenario",
                    "agent_name": "ScenarioForkAgent",
                    "reason": "status=failed",
                    "required": False,
                    "failure_policy_applied": "soft_downgrade",
                }
            ],
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    consistency = output.output_payload["candidate_decision"]["worker_manifest_consistency"]
    assert consistency["passed"] is True
    assert consistency["violations"] == []
    assert consistency["advisories"] == []


def test_candidate_replay_detects_missing_counter_thesis_refs_in_lead_synthesis(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        lead_synthesis={
            "included_contribution_ids": ["c-root", "c-sentiment"],
            "dropped_contributions": [],
            "counter_thesis": ["Crowded longs can force a short-term reversal"],
            "counter_thesis_refs": [],
            "strongest_counter_thesis_ref": None,
            "conflicts": ["trend_vs_crowding"],
            "conflict_refs": [
                {
                    "conflict_id": "trend_vs_crowding",
                    "summary": "trend conflicts with crowding",
                    "contribution_refs": ["c-root", "c-sentiment"],
                }
            ],
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    coverage = output.output_payload["candidate_decision"]["counter_conflict_coverage"]
    assert coverage["passed"] is False
    assert {
        "rule_id": "lead_synthesis_counter_thesis_refs_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_strongest_counter_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]


def test_candidate_replay_detects_missing_conflict_refs_in_lead_synthesis(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        lead_synthesis={
            "included_contribution_ids": ["c-root", "c-sentiment"],
            "dropped_contributions": [],
            "counter_thesis": ["Crowded longs can force a short-term reversal"],
            "counter_thesis_refs": [
                {
                    "contribution_id": "c-sentiment",
                    "agent_name": "MarketSentimentAgent",
                    "claim": "Crowded longs can force a short-term reversal",
                    "side": "bearish",
                }
            ],
            "strongest_counter_thesis_ref": {
                "contribution_id": "c-sentiment",
                "agent_name": "MarketSentimentAgent",
                "claim": "Crowded longs can force a short-term reversal",
                "side": "bearish",
            },
            "conflicts": ["trend_vs_crowding"],
            "conflict_refs": [],
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    coverage = output.output_payload["candidate_decision"]["counter_conflict_coverage"]
    assert coverage["passed"] is False
    assert {
        "rule_id": "lead_synthesis_conflict_refs_missing",
        "conflict_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_artifact_conflict_refs_missing",
        "conflict_count": 1,
    } in coverage["violations"]
    assert len(coverage["violations"]) == 2


def test_candidate_replay_detects_missing_counter_refs_in_lead_synthesis_artifact(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        lead_synthesis={
            "included_contribution_ids": ["c-root", "c-sentiment"],
            "dropped_contributions": [],
            "counter_thesis": ["Crowded longs can force a short-term reversal"],
            "counter_thesis_refs": [
                {
                    "contribution_id": "c-sentiment",
                    "agent_name": "MarketSentimentAgent",
                    "claim": "Crowded longs can force a short-term reversal",
                    "side": "bearish",
                }
            ],
            "strongest_counter_thesis_ref": {
                "contribution_id": "c-sentiment",
                "agent_name": "MarketSentimentAgent",
                "claim": "Crowded longs can force a short-term reversal",
                "side": "bearish",
            },
            "conflicts": ["trend_vs_crowding"],
            "conflict_refs": [
                {
                    "conflict_id": "trend_vs_crowding",
                    "summary": "trend conflicts with crowding",
                    "contribution_refs": ["c-root", "c-sentiment"],
                }
            ],
        },
        lead_synthesis_artifact_overrides={
            "counter_thesis_refs": [],
            "strongest_counter_thesis_ref": None,
            "conflict_refs": [],
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    coverage = output.output_payload["candidate_decision"]["counter_conflict_coverage"]
    assert coverage["passed"] is False
    assert {
        "rule_id": "lead_synthesis_artifact_counter_thesis_refs_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_artifact_strongest_counter_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_artifact_conflict_refs_missing",
        "conflict_count": 1,
    } in coverage["violations"]


def test_candidate_replay_reports_worker_hard_block_constraints(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        decision_input_overrides={
            "contribution_refs": [
                {
                    "contribution_id": "risk-hard-block",
                    "agent_name": "ExecutionRiskAgent",
                    "required": True,
                    "hard_block": True,
                    "hard_block_reasons": ["facts_gate:execution_facts_missing"],
                    "raw_payload": "must not leak",
                }
            ]
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    worker_hard_blocks = output.output_payload["candidate_decision"]["worker_hard_blocks"]
    assert worker_hard_blocks == [
        {
            "contribution_id": "risk-hard-block",
            "agent_name": "ExecutionRiskAgent",
            "reasons": ["facts_gate:execution_facts_missing"],
        }
    ]
    assert "raw_payload" not in str(worker_hard_blocks)


def test_candidate_replay_reports_complete_replay_ref_coverage(tmp_path):
    store = EvalStore(tmp_path / "eval.db")
    case = _case_with_context_artifacts(
        context_lead_hash="sha256:sidecar-lead",
        sidecar_lead_hash="sha256:sidecar-lead",
        replayable_overrides={
            "coverage": {
                "worker_artifact_count": 1,
                "worker_manifest_count": 1,
                "worker_manifest_complete": True,
                "worker_manifest_missing_fields": [],
                "has_lead_synthesis_artifact": False,
                "has_final_decision_output": True,
                "has_final_input_selection": True,
                "has_parsed_plan": True,
                "has_production_control_gate": False,
                "has_risk_gate_result": True,
                "has_side_effect_policy": True,
                "has_context_artifact_summary": False,
                "has_version_lock": False,
                "has_telemetry_refs": False,
                "has_evidence_snapshot_refs": False,
                "has_memory_snapshot_refs": False,
                "has_span_tree_refs": False,
            }
        },
    )
    store.upsert_cases([case])

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    candidate = output.output_payload["candidate_decision"]
    assert candidate["complete_replay_refs"] == {
        "has_lead_synthesis_artifact": False,
        "has_final_decision_output": True,
        "has_final_input_selection": True,
        "has_parsed_plan": True,
        "has_production_control_gate": False,
        "has_risk_gate_result": True,
        "has_side_effect_policy": True,
        "has_context_artifact_summary": False,
        "has_version_lock": False,
        "has_telemetry_refs": False,
        "has_evidence_snapshot_refs": False,
        "has_memory_snapshot_refs": False,
        "has_span_tree_refs": False,
    }
    assert candidate["complete_replay_missing_refs"] == [
        "lead_synthesis_artifact",
        "production_control_gate",
        "context_artifact_summary",
        "version_lock",
        "telemetry_refs",
        "evidence_snapshot_refs",
        "memory_snapshot_refs",
        "span_tree_refs",
    ]


def _case_with_context_artifacts(
    *,
    context_lead_hash: str,
    sidecar_lead_hash: str,
    gate_result_refs: dict[str, object] | None = None,
    worker_result_manifest: list[dict[str, object]] | None = None,
    lead_synthesis: dict[str, object] | None = None,
    lead_synthesis_artifact_overrides: dict[str, object] | None = None,
    decision_input_overrides: dict[str, object] | None = None,
    replayable_overrides: dict[str, object] | None = None,
) -> EvalCase:
    context_gate_result_refs = gate_result_refs or {
        "replayable_input_candidate": {
            "input_ref": "trace:trace-1:replayable_input_candidate",
            "input_hash": "sha256:replayable",
        },
        "lead_synthesis_artifact": {
            "artifact_ref": "candidate:lead_synthesis",
            "artifact_hash": context_lead_hash,
        },
    }
    manifest = worker_result_manifest or [
        {
            "task_id": "task-root",
            "agent_name": "RootCauseAgent",
            "status": "ok",
            "input_ref": "trace:trace-1:worker-input",
            "input_hash": "sha256:worker-input",
            "agent_run_request_hash": "sha256:request",
            "output_hash": "sha256:root",
            "trace_ref": "trace:trace-1:worker",
            "failure_policy_applied": "none",
            "agent_run_result": {
                "input_view_hash": "sha256:worker-input",
                "agent_run_request_hash": "sha256:request",
            },
        }
    ]
    synthesis = lead_synthesis or {"included_contribution_ids": ["c-root"], "dropped_contributions": []}
    lead_synthesis_artifact = {
        "artifact_ref": "candidate:lead_synthesis",
        "decision_effect": "none",
        "artifact_hash": sidecar_lead_hash,
        "lead_synthesis": synthesis,
    }
    counter_thesis = synthesis.get("counter_thesis") if isinstance(synthesis.get("counter_thesis"), list) else []
    conflicts = synthesis.get("conflicts") if isinstance(synthesis.get("conflicts"), list) else []
    if counter_thesis:
        lead_synthesis_artifact["counter_thesis_count"] = len(counter_thesis)
        lead_synthesis_artifact["counter_thesis_refs"] = list(synthesis.get("counter_thesis_refs") or [])
        lead_synthesis_artifact["strongest_counter_thesis_ref"] = synthesis.get(
            "strongest_counter_thesis_ref"
        )
    if conflicts:
        lead_synthesis_artifact["conflict_count"] = len(conflicts)
        lead_synthesis_artifact["conflict_refs"] = list(synthesis.get("conflict_refs") or [])
    if lead_synthesis_artifact_overrides:
        lead_synthesis_artifact.update(lead_synthesis_artifact_overrides)
    decision_input = {
        "input_ref": "trace:trace-1:decision_input_candidate",
        "input_hash": "sha256:decision",
        "decision_effect": "none",
        "evidence_refs": [{"evidence_id": "ev-1"}],
    }
    if decision_input_overrides:
        decision_input.update(decision_input_overrides)
    replayable_input = {
        "input_ref": "trace:trace-1:replayable_input_candidate",
        "input_hash": "sha256:replayable",
        "decision_effect": "none",
        "coverage": {
            "worker_artifact_count": 1,
            "worker_manifest_count": 1,
            "worker_manifest_complete": True,
            "worker_manifest_missing_fields": [],
            "has_final_decision_output": True,
            "has_final_input_selection": True,
            "has_parsed_plan": True,
            "has_production_control_gate": True,
            "has_risk_gate_result": True,
            "has_side_effect_policy": True,
            "has_context_artifact_summary": True,
        },
        "artifact_refs": {
            "decision_input_candidate": {
                "input_ref": "trace:trace-1:decision_input_candidate",
                "input_hash": "sha256:decision",
            },
            "shadow_lead_plan": {"plan_id": "lead-1"},
            "shadow_workers": [
                {
                    "task_id": "task-root",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "contribution_id": "c-root",
                    "output_hash": "sha256:root",
                    "input_ref": "trace:trace-1:worker-input",
                }
            ],
            "worker_result_manifest": manifest,
        },
    }
    if replayable_overrides:
        replayable_input.update(replayable_overrides)
    return EvalCase(
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
                "decision_input_candidate": decision_input,
                "replayable_input_candidate": replayable_input,
                "context_artifacts": {
                    "evidence_count": 1,
                    "contribution_count": 1,
                    "has_lead_plan": True,
                    "has_decision_input": True,
                    "lead_plan_ref": {"plan_id": "lead-1"},
                    "decision_input_ref": {
                        "input_ref": "trace:trace-1:decision_input_candidate",
                        "input_hash": "sha256:decision",
                    },
                    "gate_result_refs": context_gate_result_refs,
                    "evidence_refs": [{"evidence_id": "ev-1"}],
                    "contribution_refs": [
                        {
                            "contribution_id": "c-root",
                            "agent_name": "RootCauseAgent",
                            "output_hash": "sha256:root",
                        }
                    ],
                },
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
                    "lead_synthesis": lead_synthesis_artifact,
                    "worker_result_manifest": {
                        "artifact_ref": "candidate:worker_result_manifest",
                        "decision_effect": "none",
                        "manifest_count": 1,
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
                        "ready": True,
                        "artifact_hash": "sha256:readiness",
                    },
                },
                "gate_candidate": {"passed": True, "blocked_actions": [], "missing_facts": []},
                "plan_semantic_candidate": {"passed": True},
                "final_decision_switch_readiness": {"ready": True, "blocking_reasons": []},
            }
        },
    )
