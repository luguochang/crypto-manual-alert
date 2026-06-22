from __future__ import annotations

import json
import sqlite3
import tempfile
from typing import Any

import httpx
import pytest

from crypto_manual_alert.config import EvalConfig, EvalReleaseGateConfig
from crypto_manual_alert.eval.case_builder import EvalCaseBuilder
from crypto_manual_alert.eval.judges.llm import OpenAICompatibleLLMJudge
from crypto_manual_alert.eval.replay import ReplayRunner
from crypto_manual_alert.eval.runner import EvalRunner
from crypto_manual_alert.eval.store import EvalStore
from crypto_manual_alert.decision.frozen_input import stable_hash
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder


def test_eval_case_builder_persists_replayable_frozen_input(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]

    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)

    frozen = store.get_frozen_input(case.frozen_input_hash)
    assert frozen is not None
    assert frozen.input_payload["market_snapshot"]["symbol"] == "ETH-USDT-SWAP"
    assert frozen.source_trace_id == trace_id
    assert frozen.source_badcase_id == badcase_id
    assert "raw_decision" not in json.dumps(frozen.input_payload).lower()
    assert "request_json" not in json.dumps(frozen.input_payload).lower()


def test_eval_case_builder_includes_sanitized_candidate_audit_summary(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)

    case = EvalCaseBuilder(journal).build_cases(badcase_ids=[badcase_id])[0]

    candidate_audit = case.input_summary["candidate_audit"]
    assert candidate_audit["gate_candidate"] == {
        "passed": False,
        "severity": "hard_fail",
        "violations": [{"rule_id": "candidate.action_not_allowed"}],
        "blocked_actions": ["trigger long"],
        "missing_facts": ["mark"],
    }
    assert candidate_audit["plan_semantic_candidate"] == {
        "passed": False,
        "severity": "hard_fail",
        "violations": [{"rule_id": "plan_semantic.long_stop_not_below_entry"}],
    }
    assert candidate_audit["final_decision_switch_readiness"] == {
        "ready": False,
        "blocking_reasons": ["candidate_gate_failed"],
    }
    assert candidate_audit["decision_input_candidate"] == {
        "input_ref": "trace:eval:decision_input_candidate",
        "input_hash": "sha256:decision",
        "decision_effect": None,
        "contribution_refs": [],
        "execution_fact_source_violations": [],
    }
    assert candidate_audit["replayable_input_candidate"] == {
        "input_ref": "trace:eval:replayable_input_candidate",
        "input_hash": "sha256:replayable",
        "decision_effect": "none",
        "coverage": {
            "worker_artifact_count": 4,
            "has_decision_input_candidate": True,
            "worker_manifest_count": 4,
            "worker_manifest_complete": True,
            "worker_manifest_missing_fields": [],
        },
        "artifact_refs": {
            "decision_input_candidate": {
                "input_ref": "trace:eval:decision_input_candidate",
                "input_hash": "sha256:decision",
            },
            "shadow_workers": [
                {
                    "task_id": "shadow:RootCauseAgent",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "contribution_id": "c-root",
                    "output_hash": "sha256:root",
                    "input_ref": "trace:eval:shadow_swarm_input",
                }
            ],
            "worker_result_manifest": [
                {
                    "task_id": "shadow:RootCauseAgent",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "input_ref": "trace:eval:shadow_swarm_input",
                    "input_hash": "sha256:input-view",
                    "agent_run_request_hash": "sha256:request",
                    "output_hash": "sha256:root",
                    "trace_ref": "trace-eval:shadow:RootCauseAgent",
                    "failure_policy_applied": "none",
                    "agent_run_result": {
                        "input_view_hash": "sha256:input-view",
                        "agent_run_request_hash": "sha256:request",
                    },
                }
            ],
        },
    }
    assert candidate_audit["context_artifacts"] == {
        "evidence_count": 7,
        "contribution_count": 4,
        "has_lead_plan": True,
        "lead_plan_ref": None,
        "has_decision_input": True,
        "decision_input_ref": {
            "input_ref": "trace:eval:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        "gate_result_refs": {
            "replayable_input_candidate": {
                "input_ref": "trace:eval:replayable_input_candidate",
                "input_hash": "sha256:replayable",
            }
        },
        "evidence_refs": [{"evidence_id": "ev-search-mark"}],
        "contribution_refs": [{"contribution_id": "c-root", "agent_name": "RootCauseAgent"}],
    }
    assert candidate_audit["artifact_snapshot"] == {
        "schema_version": 1,
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "decision_input_candidate": {
            "input_ref": "trace:eval:decision_input_candidate",
            "input_hash": "sha256:decision",
            "decision_effect": "none",
            "artifact_hash": stable_hash(
                {
                    "input_ref": "trace:eval:decision_input_candidate",
                        "input_hash": "sha256:decision",
                        "lead_synthesis": {
                            "decision_effect": "none",
                            "included_contribution_ids": ["c-root"],
                            "dropped_contributions": [],
                            "supporting_thesis": ["Root cause is macro liquidity."],
                            "counter_thesis": [],
                        },
                        "evidence_refs": [
                        {
                            "evidence_id": "ev-search-mark",
                            "data_type": "mark",
                            "source_type": "search_derived",
                            "can_satisfy_execution_fact": False,
                        }
                    ],
                    "raw_forbidden": "<redacted>",
                }
            ),
        },
        "replayable_input_candidate": {
            "input_ref": "trace:eval:replayable_input_candidate",
            "input_hash": "sha256:replayable",
            "decision_effect": "none",
            "artifact_hash": stable_hash(
                {
                    "input_ref": "trace:eval:replayable_input_candidate",
                    "input_hash": "sha256:replayable",
                    "decision_effect": "none",
                    "artifact_refs": {
                        "decision_input_candidate": {
                            "input_ref": "trace:eval:decision_input_candidate",
                            "input_hash": "sha256:decision",
                        },
                        "shadow_workers": [
                            {
                                "task_id": "shadow:RootCauseAgent",
                                "agent_name": "RootCauseAgent",
                                "status": "ok",
                                "contribution_id": "c-root",
                                "output_hash": "sha256:root",
                                "input_ref": "trace:eval:shadow_swarm_input",
                            }
                        ],
                        "worker_result_manifest": [
                            {
                                "task_id": "shadow:RootCauseAgent",
                                "agent_name": "RootCauseAgent",
                                "status": "ok",
                                "input_ref": "trace:eval:shadow_swarm_input",
                                "input_hash": "sha256:input-view",
                                "agent_run_request_hash": "sha256:request",
                                "output_hash": "sha256:root",
                                "trace_ref": "trace-eval:shadow:RootCauseAgent",
                                "failure_policy_applied": "none",
                                "agent_run_result": {
                                    "input_view_hash": "sha256:input-view",
                                    "agent_run_request_hash": "sha256:request",
                                    "raw_input_view": "<redacted>",
                                },
                            }
                        ],
                    },
                    "coverage": {
                        "worker_artifact_count": 4,
                        "has_decision_input_candidate": True,
                        "worker_manifest_count": 4,
                        "worker_manifest_complete": True,
                        "worker_manifest_missing_fields": [],
                        "raw_worker_payload": "<redacted>",
                    },
                }
            ),
        },
        "lead_synthesis": {
            "artifact_ref": "candidate:lead_synthesis",
            "decision_effect": "none",
            "artifact_hash": stable_hash(
                {
                    "decision_effect": "none",
                    "included_contribution_ids": ["c-root"],
                    "dropped_contributions": [],
                    "supporting_thesis": ["Root cause is macro liquidity."],
                    "counter_thesis": [],
                }
            ),
        },
        "worker_result_manifest": {
            "artifact_ref": "candidate:worker_result_manifest",
            "decision_effect": "none",
            "manifest_count": 1,
            "artifact_hash": stable_hash(
                [
                    {
                        "task_id": "shadow:RootCauseAgent",
                        "agent_name": "RootCauseAgent",
                        "status": "ok",
                        "input_ref": "trace:eval:shadow_swarm_input",
                        "input_hash": "sha256:input-view",
                        "agent_run_request_hash": "sha256:request",
                        "output_hash": "sha256:root",
                        "trace_ref": "trace-eval:shadow:RootCauseAgent",
                        "failure_policy_applied": "none",
                        "agent_run_result": {
                            "input_view_hash": "sha256:input-view",
                            "agent_run_request_hash": "sha256:request",
                            "raw_input_view": "<redacted>",
                        },
                    }
                ]
            ),
        },
        "gate_candidate": {
            "artifact_ref": "candidate:gate_candidate",
            "decision_effect": "none",
            "passed": False,
            "artifact_hash": stable_hash(
                {
                    "passed": False,
                    "severity": "hard_fail",
                    "violations": [{"rule_id": "candidate.action_not_allowed"}],
                    "blocked_actions": ["trigger long"],
                    "missing_facts": ["mark"],
                }
            ),
        },
        "plan_semantic_candidate": {
            "artifact_ref": "candidate:plan_semantic_candidate",
            "decision_effect": "none",
            "passed": False,
            "artifact_hash": stable_hash(
                {
                    "passed": False,
                    "severity": "hard_fail",
                    "violations": [{"rule_id": "plan_semantic.long_stop_not_below_entry"}],
                    "raw_snippet": "<redacted>",
                }
            ),
        },
        "final_decision_switch_readiness": {
            "artifact_ref": "candidate:final_decision_switch_readiness",
            "decision_effect": "none",
            "ready": False,
            "artifact_hash": stable_hash(
                {
                    "ready": False,
                    "blocking_reasons": ["candidate_gate_failed"],
                }
            ),
        },
    }
    rendered = json.dumps(candidate_audit, ensure_ascii=False).lower()
    assert "raw snippet must not leak" not in rendered
    assert "raw_decision" not in rendered


def test_eval_case_builder_preserves_safe_lead_synthesis_artifact_refs(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    _trace_id, badcase_id = _seed_trace_with_lead_synthesis_artifact(journal)

    case = EvalCaseBuilder(journal).build_cases(badcase_ids=[badcase_id])[0]

    lead_artifact = case.input_summary["candidate_audit"]["artifact_snapshot"]["lead_synthesis"]
    assert lead_artifact["counter_thesis_count"] == 1
    assert lead_artifact["counter_thesis_refs"] == [
        {
            "contribution_id": "c-sentiment",
            "agent_name": "MarketSentimentAgent",
            "claim": "Crowded longs can reverse.",
            "side": "bearish",
        }
    ]
    assert lead_artifact["strongest_counter_thesis_ref"] == {
        "contribution_id": "c-sentiment",
        "agent_name": "MarketSentimentAgent",
        "claim": "Crowded longs can reverse.",
        "side": "bearish",
    }
    assert lead_artifact["conflict_count"] == 1
    assert lead_artifact["conflict_refs"] == [
        {
            "conflict_id": "trend_vs_crowding",
            "summary": "Trend conflicts with crowding.",
            "contribution_refs": ["c-root", "c-sentiment"],
        }
    ]
    rendered = json.dumps(lead_artifact, ensure_ascii=False).lower()
    assert "raw payload must not leak" not in rendered
    assert "raw snippet must not leak" not in rendered


def test_replay_runner_writes_sidecar_output_without_prod_side_effects(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    before = _prod_counts(journal.path)

    output = ReplayRunner(store).replay(case)

    assert _prod_counts(journal.path) == before
    assert output.status == "completed"
    assert output.final_action == "no trade"
    assert output.allowed is True
    assert output.output_payload["candidate_replay"] == {
        "status": "available",
        "decision_input_ref": "trace:eval:decision_input_candidate",
        "decision_input_hash": "sha256:decision",
        "replayable_input_ref": "trace:eval:replayable_input_candidate",
        "replayable_input_hash": "sha256:replayable",
        "worker_artifact_count": 4,
        "worker_manifest_complete": True,
        "worker_manifest_missing_fields": [],
            "worker_manifest_consistency": {
                "passed": False,
                "violations": [
                    {
                        "rule_id": "worker_manifest_count_mismatch",
                    "expected": 4,
                    "observed": 1,
                },
                {
                    "rule_id": "worker_artifact_count_mismatch",
                    "expected": 4,
                        "observed": 1,
                    },
                ],
                "advisories": [],
                "manifest_count": 1,
                "worker_ref_count": 1,
            },
        "context_artifact_consistency": {
            "passed": False,
            "violations": [
                {
                    "rule_id": "context_evidence_count_mismatch",
                    "expected": 7,
                    "observed": 1,
                },
                {
                    "rule_id": "context_contribution_count_mismatch",
                    "expected": 4,
                    "observed": 1,
                },
                {
                    "rule_id": "context_lead_synthesis_artifact_ref_missing",
                    "artifact_type": "lead_synthesis",
                },
                {
                    "rule_id": "context_gate_candidate_artifact_ref_missing",
                    "artifact_type": "gate_candidate",
                },
                {
                    "rule_id": "context_plan_semantic_candidate_artifact_ref_missing",
                    "artifact_type": "plan_semantic_candidate",
                },
                {
                    "rule_id": "context_final_decision_switch_readiness_artifact_ref_missing",
                    "artifact_type": "final_decision_switch_readiness",
                },
            ],
        },
        "artifact_snapshot_consistency": {
            "passed": True,
            "violations": [],
            "artifact_types": [
                "decision_input_candidate",
                "replayable_input_candidate",
                "lead_synthesis",
                "worker_result_manifest",
                "gate_candidate",
                "plan_semantic_candidate",
                "final_decision_switch_readiness",
            ],
        },
        "counter_conflict_coverage": {
            "passed": True,
            "violations": [],
            "counter_thesis_count": 0,
            "counter_thesis_ref_count": 0,
            "conflict_count": 0,
            "conflict_ref_count": 0,
        },
        "complete_replay_refs": {
            "has_lead_synthesis_artifact": False,
            "has_final_decision_output": False,
            "has_final_input_selection": False,
            "has_parsed_plan": False,
            "has_production_control_gate": False,
            "has_risk_gate_result": False,
            "has_side_effect_policy": False,
            "has_context_artifact_summary": False,
            "has_version_lock": False,
            "has_telemetry_refs": False,
            "has_evidence_snapshot_refs": False,
            "has_memory_snapshot_refs": False,
            "has_span_tree_refs": False,
        },
        "complete_replay_missing_refs": [
            "lead_synthesis_artifact",
            "final_decision_output",
            "final_input_selection",
            "parsed_plan",
            "production_control_gate",
            "risk_gate_result",
            "side_effect_policy",
            "context_artifact_summary",
            "version_lock",
            "telemetry_refs",
            "evidence_snapshot_refs",
            "memory_snapshot_refs",
            "span_tree_refs",
        ],
        "span_tree_parent_complete": None,
        "span_tree_missing_parent_count": None,
        "worker_hard_blocks": [],
        "blocked_actions": ["trigger long"],
        "missing_facts": ["mark"],
        "execution_fact_source_violations": [],
        "switch_ready": False,
        "blocking_reasons": ["candidate_gate_failed"],
    }
    assert output.frozen_input_hash == case.frozen_input_hash
    assert store.get_replay_output(case.case_id)["status"] == "completed"


def test_replay_runner_enforces_supported_modes_without_prod_side_effects(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    before = _prod_counts(journal.path)
    runner = ReplayRunner(store)

    judge_only = runner.replay(case, mode="judge_only")

    assert _prod_counts(journal.path) == before
    assert judge_only.status == "completed"
    assert judge_only.mode == "judge_only"
    assert judge_only.output_payload["candidate_replay"]["status"] == "available"

    candidate = runner.replay(case, mode="candidate_decision")

    assert _prod_counts(journal.path) == before
    assert candidate.status == "completed"
    assert candidate.mode == "candidate_decision"
    assert candidate.output_payload["candidate_replay"]["status"] == "available"
    assert candidate.output_payload["candidate_decision"] == {
        "status": "completed",
        "decision_effect": "none",
        "decision_input_ref": "trace:eval:decision_input_candidate",
        "decision_input_hash": "sha256:decision",
        "replayable_input_ref": "trace:eval:replayable_input_candidate",
        "replayable_input_hash": "sha256:replayable",
        "worker_artifact_count": 4,
        "worker_manifest_complete": True,
        "worker_manifest_missing_fields": [],
            "worker_manifest_consistency": {
                "passed": False,
                "violations": [
                    {
                        "rule_id": "worker_manifest_count_mismatch",
                    "expected": 4,
                    "observed": 1,
                },
                {
                    "rule_id": "worker_artifact_count_mismatch",
                    "expected": 4,
                        "observed": 1,
                    },
                ],
                "advisories": [],
                "manifest_count": 1,
                "worker_ref_count": 1,
            },
        "context_artifact_consistency": {
            "passed": False,
            "violations": [
                {
                    "rule_id": "context_evidence_count_mismatch",
                    "expected": 7,
                    "observed": 1,
                },
                {
                    "rule_id": "context_contribution_count_mismatch",
                    "expected": 4,
                    "observed": 1,
                },
                {
                    "rule_id": "context_lead_synthesis_artifact_ref_missing",
                    "artifact_type": "lead_synthesis",
                },
                {
                    "rule_id": "context_gate_candidate_artifact_ref_missing",
                    "artifact_type": "gate_candidate",
                },
                {
                    "rule_id": "context_plan_semantic_candidate_artifact_ref_missing",
                    "artifact_type": "plan_semantic_candidate",
                },
                {
                    "rule_id": "context_final_decision_switch_readiness_artifact_ref_missing",
                    "artifact_type": "final_decision_switch_readiness",
                },
            ],
        },
        "artifact_snapshot_consistency": {
            "passed": True,
            "violations": [],
            "artifact_types": [
                "decision_input_candidate",
                "replayable_input_candidate",
                "lead_synthesis",
                "worker_result_manifest",
                "gate_candidate",
                "plan_semantic_candidate",
                "final_decision_switch_readiness",
            ],
        },
        "counter_conflict_coverage": {
            "passed": True,
            "violations": [],
            "counter_thesis_count": 0,
            "counter_thesis_ref_count": 0,
            "conflict_count": 0,
            "conflict_ref_count": 0,
        },
        "complete_replay_refs": {
            "has_lead_synthesis_artifact": False,
            "has_final_decision_output": False,
            "has_final_input_selection": False,
            "has_parsed_plan": False,
            "has_production_control_gate": False,
            "has_risk_gate_result": False,
            "has_side_effect_policy": False,
            "has_context_artifact_summary": False,
            "has_version_lock": False,
            "has_telemetry_refs": False,
            "has_evidence_snapshot_refs": False,
            "has_memory_snapshot_refs": False,
            "has_span_tree_refs": False,
        },
        "complete_replay_missing_refs": [
            "lead_synthesis_artifact",
            "final_decision_output",
            "final_input_selection",
            "parsed_plan",
            "production_control_gate",
            "risk_gate_result",
            "side_effect_policy",
            "context_artifact_summary",
            "version_lock",
            "telemetry_refs",
            "evidence_snapshot_refs",
            "memory_snapshot_refs",
            "span_tree_refs",
        ],
        "span_tree_parent_complete": None,
        "span_tree_missing_parent_count": None,
        "worker_hard_blocks": [],
        "blocked_actions": ["trigger long"],
        "missing_facts": ["mark"],
        "execution_fact_source_violations": [],
        "switch_ready": False,
        "blocking_reasons": ["candidate_gate_failed"],
    }

    try:
        runner.replay(case, mode="live_runner")
    except ValueError as exc:
        assert "unsupported replay mode" in str(exc)
    else:
        raise AssertionError("unsupported replay mode should fail")


def test_candidate_decision_replay_can_run_injected_decision_input_shadow_final(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    before = _prod_counts(journal.path)
    captured_payloads: list[dict[str, Any]] = []

    class FixtureShadowFinal:
        def run(self, payload):
            captured_payloads.append(payload)
            return json.dumps(
                {
                    "instrument": "ETH-USDT-SWAP",
                    "main_action": "no trade",
                    "probability": 0.53,
                    "raw_prompt": "must not leak",
                }
            )

    output = ReplayRunner(store, decision_input_final_adapter=FixtureShadowFinal()).replay(
        case,
        mode="candidate_decision",
    )

    assert _prod_counts(journal.path) == before
    assert output.status == "completed"
    assert captured_payloads == [
        store.get_candidate_artifacts(case.case_id)["decision_input_candidate"]
    ]
    shadow_final = output.output_payload["decision_input_shadow_final"]
    assert shadow_final["status"] == "completed"
    assert shadow_final["decision_effect"] == "none"
    assert shadow_final["production_final_input"] is False
    assert shadow_final["notification_input"] is False
    assert shadow_final["source_decision_input_ref"] == "trace:eval:decision_input_candidate"
    assert shadow_final["source_decision_input_hash"] == "sha256:decision"
    assert shadow_final["source_replayable_input_ref"] == "trace:eval:replayable_input_candidate"
    assert shadow_final["source_replayable_input_hash"] == "sha256:replayable"
    assert shadow_final["shadow_final_summary"] == {
        "instrument": "ETH-USDT-SWAP",
        "main_action": "no trade",
        "probability": 0.53,
    }
    assert output.output_payload["shadow_legacy_comparison"] == {
        "status": "available",
        "decision_effect": "none",
        "legacy_observed_summary": {
            "main_action": "no trade",
            "probability": 0.52,
        },
        "shadow_final_summary": {
            "main_action": "no trade",
            "probability": 0.53,
        },
        "main_action_match": True,
        "probability_delta": 0.01,
        "differences": ["probability_changed"],
    }
    rendered = json.dumps(shadow_final, ensure_ascii=False).lower()
    assert "raw_prompt" not in rendered
    assert "must not leak" not in rendered


def test_candidate_decision_replay_compares_persisted_candidate_final_sidecar(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    candidate_audit = case.input_summary["candidate_audit"]
    candidate_audit["candidate_final_decision"] = {
        "artifact_type": "candidate_final_decision",
        "mode": "candidate_final_sidecar",
        "decision_effect": "none",
        "production_final_input": False,
        "input_ref": "trace:eval:pre_final_decision_input",
        "input_hash": "sha256:pre-final",
        "input_gate_passed": True,
        "raw_candidate_decision": json.dumps(
            {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "probability": 0.61,
                "raw_output": "must not leak",
            }
        ),
        "error": None,
    }
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    before = _prod_counts(journal.path)

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    assert _prod_counts(journal.path) == before
    assert output.status == "completed"
    assert output.output_payload["candidate_final_legacy_comparison"] == {
        "status": "available",
        "decision_effect": "none",
        "legacy_observed_summary": {
            "main_action": "no trade",
            "probability": 0.52,
        },
        "candidate_final_summary": {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "probability": 0.61,
        },
        "main_action_match": False,
        "probability_delta": 0.09,
        "differences": ["main_action_changed", "probability_changed"],
    }
    rendered = json.dumps(output.output_payload, ensure_ascii=False).lower()
    assert "raw_output" not in rendered
    assert "must not leak" not in rendered


def test_candidate_replay_reads_artifact_snapshot_back_from_eval_store(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    before = _prod_counts(journal.path)

    case.input_summary["candidate_audit"]["artifact_snapshot"] = {
        "schema_version": 1,
        "decision_effect": "none",
        "decision_input_candidate": {
            "input_ref": "trace:mutated:decision_input_candidate",
            "input_hash": "sha256:mutated",
            "artifact_hash": "sha256:mutated",
        },
    }

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    assert _prod_counts(journal.path) == before
    assert output.status == "completed"
    assert output.output_payload["candidate_decision"]["artifact_snapshot_consistency"] == {
        "passed": True,
        "violations": [],
        "artifact_types": [
            "decision_input_candidate",
            "replayable_input_candidate",
            "lead_synthesis",
            "worker_result_manifest",
            "gate_candidate",
            "plan_semantic_candidate",
            "final_decision_switch_readiness",
        ],
    }


def test_candidate_replay_detects_candidate_artifact_store_hash_mismatch(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    with sqlite3.connect(store.path) as conn:
        artifact = store.get_candidate_artifacts(case.case_id)["lead_synthesis"]
        artifact["artifact_hash"] = "sha256:tampered-json"
        tampered_store_hash = stable_hash(artifact)
        conn.execute(
            """
            UPDATE eval_candidate_artifacts
            SET artifact_json = ?
            WHERE case_id = ? AND artifact_type = ?
            """,
            (json.dumps(artifact, ensure_ascii=False), case.case_id, "lead_synthesis"),
        )
        conn.commit()

    output = ReplayRunner(store).replay(case, mode="candidate_decision")

    consistency = output.output_payload["candidate_decision"]["artifact_snapshot_consistency"]
    assert consistency["passed"] is False
    assert {
        "rule_id": "candidate_artifact_store_hash_mismatch",
        "artifact_type": "lead_synthesis",
        "expected": store.get_candidate_artifact_hash(case.case_id, "lead_synthesis"),
        "observed": tampered_store_hash,
    } in consistency["violations"]


def test_eval_runner_judge_openai_uses_replay_and_real_llm_scores_without_prod_side_effects(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    monkeypatch.setenv("OPENAI_API_KEY", "judge-key")
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        content = json.dumps(
            {
                "passed": True,
                "score": 0.82,
                "severity": "low",
                "failure_category": "none",
                "reason_summary": "evidence, replay, and expected behavior have no direct conflict.",
                "evidence_refs": ["frozen_input_hash", "replay.output"],
                "needs_human_review": False,
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
            },
        )

    judge = OpenAICompatibleLLMJudge(
        base_url="https://judge.example",
        api_key="judge-key",
        model="judge-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    runner = EvalRunner(journal=journal, store=store, data_dir=tmp_path, llm_judge=judge)
    before = _all_prod_counts(journal.path)

    run = runner.run(badcase_ids=[badcase_id], mode="judge_openai")

    assert _all_prod_counts(journal.path) == before
    assert run.metadata["judge_provider"] == "openai_compatible"
    assert run.metadata["replay"]["completed"] == 1
    assert run.metadata["replay"]["candidate_decision_completed"] == 1
    assert run.metadata["replay"]["candidate_decision_failed"] == 0
    stored_candidate_replay = store.get_replay_output("badcase-1", mode="candidate_decision")
    assert stored_candidate_replay["mode"] == "candidate_decision"
    assert stored_candidate_replay["metadata"] == {
        "source": "eval.candidate_decision_replay",
        "decision_effect": "none",
    }
    comparison = run.metadata["promotion_artifacts"]["shadow_candidate_comparison"]
    assert comparison == {
        "schema_version": 1,
        "artifact_type": "shadow_candidate_comparison",
        "artifact_ref": f"eval:{run.eval_run_id}:shadow_candidate_comparison",
        "eval_run_id": run.eval_run_id,
        "decision_effect": "none",
        "case_count": 1,
        "candidate_replay_available": 1,
        "candidate_replay_missing": 0,
        "worker_artifact_count_min": 4,
        "switch_ready_count": 0,
        "switch_not_ready_count": 1,
        "case_summaries": [
            {
                "case_id": "badcase-1",
                "status": "available",
                "decision_input_ref": "trace:eval:decision_input_candidate",
                "decision_input_hash": "sha256:decision",
                "replayable_input_ref": "trace:eval:replayable_input_candidate",
                "replayable_input_hash": "sha256:replayable",
                "worker_artifact_count": 4,
                "worker_manifest_complete": True,
                "worker_manifest_consistency_passed": False,
                "context_artifact_consistency_passed": False,
                "blocked_actions": ["trigger long"],
                "missing_facts": ["mark"],
                "switch_ready": False,
                "blocking_reasons": ["candidate_gate_failed"],
            }
        ],
    }
    assert "raw snippet must not leak" not in json.dumps(comparison, ensure_ascii=False).lower()
    release_gate = run.metadata["release_gate"]
    assert release_gate["ready"] is False
    assert release_gate["hard_gates_passed"] is False
    assert release_gate["promotion_approved"] is False
    assert release_gate["decision_effect"] == "none"
    assert release_gate["blocking_reasons"] == [
        "minimum_eval_coverage_not_met",
        "badcase_severity_coverage_not_met",
        "eval_scores_failed",
        "candidate_gate_failed",
        "plan_semantic_candidate_failed",
        "worker_manifest_consistency_failed",
        "context_artifact_consistency_failed",
        "complete_replay_input_incomplete",
        "span_tree_parent_incomplete",
        "final_switch_readiness_not_ready",
        "worker_artifact_coverage_incomplete",
    ]
    assert release_gate["hard_gate_results"]["no_production_side_effect_proof"] == {
        "passed": True,
        "blocking_reasons": [],
        "artifact_ref": f"eval:{run.eval_run_id}:no_production_side_effect_proof",
    }
    assert release_gate["candidate_replay_available"] == 1
    assert release_gate["candidate_replay_missing"] == 0
    assert release_gate["worker_artifact_count_min"] == 4
    assert release_gate["hard_gate_results"]["worker_artifact_coverage"]["manifest_consistency_violations"] == [
        {
            "case_id": "badcase-1",
            "rule_id": "worker_manifest_count_mismatch",
            "expected": 4,
            "observed": 1,
        },
        {
            "case_id": "badcase-1",
            "rule_id": "worker_artifact_count_mismatch",
            "expected": 4,
            "observed": 1,
        },
    ]
    assert release_gate["hard_gate_results"]["worker_artifact_coverage"][
        "context_artifact_consistency_violations"
    ] == [
        {
            "case_id": "badcase-1",
            "rule_id": "context_evidence_count_mismatch",
            "expected": 7,
            "observed": 1,
        },
        {
            "case_id": "badcase-1",
            "rule_id": "context_contribution_count_mismatch",
            "expected": 4,
            "observed": 1,
        },
        {
            "case_id": "badcase-1",
            "rule_id": "context_lead_synthesis_artifact_ref_missing",
            "artifact_type": "lead_synthesis",
        },
        {
            "case_id": "badcase-1",
            "rule_id": "context_gate_candidate_artifact_ref_missing",
            "artifact_type": "gate_candidate",
        },
        {
            "case_id": "badcase-1",
            "rule_id": "context_plan_semantic_candidate_artifact_ref_missing",
            "artifact_type": "plan_semantic_candidate",
        },
        {
            "case_id": "badcase-1",
            "rule_id": "context_final_decision_switch_readiness_artifact_ref_missing",
            "artifact_type": "final_decision_switch_readiness",
        },
    ]
    assert release_gate["promotion_review"] == {
        "status": "blocked",
        "decision_effect": "none",
        "candidate_gate_status": "blocked",
        "promotion_material_status": "not_evaluated",
        "allowed_to_change_production_final_input": False,
        "manual_approval_required": True,
        "approval_artifact_ref": None,
    }
    detail = store.get_run_detail(run.eval_run_id)
    scores = [score for score in detail["scores"] if score["judge_type"] == "llm"]
    assert len(scores) == 5
    assert {score["judge_name"] for score in scores} == {
        "llm.evidence_grounding",
        "llm.opposing_thesis",
        "llm.data_gap_honesty",
        "llm.execution_clarity",
        "llm.overconfidence",
    }
    assert all(score["metadata"]["duration_ms"] >= 0 for score in scores)
    assert all(score["metadata"]["total_tokens"] == 16 for score in scores)
    assert len(requests) == 5
    rendered_request = json.dumps(requests, ensure_ascii=False).lower()
    assert "judge-key" not in rendered_request
    assert "raw_decision" not in rendered_request
    assert "frozen_input_hash" in rendered_request
    assert detail["cases"][0]["replay_result"]["status"] == "completed"


def test_eval_runner_uses_configured_release_gate_thresholds_without_prod_side_effects(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    config = EvalConfig(
        release_gate=EvalReleaseGateConfig(
            minimum_case_count=2,
            schema_valid_rate_threshold=1.0,
            required_badcase_severities=["critical"],
        )
    )
    before = _all_prod_counts(journal.path)

    run = EvalRunner(journal=journal, store=store, data_dir=tmp_path, eval_config=config).run(
        badcase_ids=[badcase_id],
        mode="cheap",
    )

    assert _all_prod_counts(journal.path) == before
    proof = run.metadata["promotion_artifacts"]["no_production_side_effect_proof"]
    assert proof["artifact_type"] == "no_production_side_effect_proof"
    assert proof["artifact_ref"] == f"eval:{run.eval_run_id}:no_production_side_effect_proof"
    assert proof["decision_effect"] == "none"
    assert proof["production_final_input"] is False
    assert proof["notification_input"] is False
    assert proof["live_order_input"] is False
    assert proof["passed"] is True
    assert proof["deltas"] == {
        table: 0
        for table in ("plan_runs", "notifications", "manual_outcomes", "traces", "trace_spans", "llm_interactions")
    }
    release_gate = run.metadata["release_gate"]
    assert release_gate["hard_gate_results"]["minimum_eval_coverage"] == {
        "passed": False,
        "blocking_reasons": ["minimum_eval_coverage_not_met"],
        "required_min": 2,
        "observed": 1,
    }
    assert release_gate["hard_gate_results"]["schema_valid_rate"]["required_min"] == 1.0
    assert "minimum_eval_coverage_not_met" in release_gate["blocking_reasons"]
    assert "badcase_severity_coverage_not_met" in release_gate["blocking_reasons"]
    assert release_gate["hard_gate_results"]["badcase_severity_coverage"] == {
        "passed": False,
        "blocking_reasons": ["badcase_severity_coverage_not_met"],
        "required_severities": ["critical"],
        "observed_counts": {"critical": 0},
        "missing_severities": ["critical"],
    }
    assert release_gate["promotion_approved"] is False
    assert release_gate["promotion_review"]["allowed_to_change_production_final_input"] is False


def test_openai_llm_judge_invalid_json_returns_review_score():
    case = _minimal_case()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    judge = OpenAICompatibleLLMJudge(
        base_url="https://judge.example",
        api_key="judge-key",
        model="judge-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    scores = judge.evaluate("eval-run-id", case, replay_output={"status": "completed"})

    assert len(scores) == 5
    assert all(score.passed is False for score in scores)
    assert all(score.needs_human_review is True for score in scores)
    assert all(score.failure_category == "llm_judge_invalid_response" for score in scores)


def _seed_trace_with_frozen_input(journal: Journal) -> tuple[str, int]:
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP", horizon="6h")
    with recorder.span(trace_id, "decision.final", "decision.llm") as span:
        span.set_output({"raw_decision_chars": 120})
    with recorder.span(trace_id, "risk.check", "risk.check") as span:
        span.set_output({"allowed": True, "reasons": [], "rule_hits": []})
    recorder.finish_trace(trace_id, status="allowed", final_plan_id="plan_eval_seed", final_action="no trade", allowed=True)
    frozen_payload = {
        "skill": {"name": "crypto-macro-decision", "sha256": "skill-hash"},
        "market_snapshot": {
            "symbol": "ETH-USDT-SWAP",
            "fetched_at": "2026-06-30T00:00:00+00:00",
            "points": {},
            "unavailable": [],
        },
        "required_output": "strict JSON DecisionPlan",
    }
    journal.append_plan_run(
        "plan_eval_seed",
        "allowed",
        {
            "trace_id": trace_id,
            "frozen_input": {
                "schema_version": 1,
                "kind": "decision_prompt_packet",
                "sha256": "frozen-hash",
                "payload": frozen_payload,
            },
            "frozen_input_hash": "frozen-hash",
            "parsed_plan": {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "no trade",
                "horizon": "6h",
                "manual_execution_required": True,
                "probability": 0.52,
                "why_not_opposite": "Short thesis lacks confirmation.",
                "invalidation": "Re-run if market breaks range.",
            },
            "verdict": {"allowed": True, "reasons": [], "warnings": [], "rule_hits": []},
            "analysis": {
                "reasoning_summary": "Seeded replayable plan.",
                "data_gaps": [],
                "risk_rule_hits": [],
            },
            "decision_input_candidate": {
                "input_ref": "trace:eval:decision_input_candidate",
                "input_hash": "sha256:decision",
                "lead_synthesis": {
                    "decision_effect": "none",
                    "included_contribution_ids": ["c-root"],
                    "dropped_contributions": [],
                    "supporting_thesis": ["Root cause is macro liquidity."],
                    "counter_thesis": [],
                },
                "evidence_refs": [
                    {
                        "evidence_id": "ev-search-mark",
                        "data_type": "mark",
                        "source_type": "search_derived",
                        "can_satisfy_execution_fact": False,
                    }
                ],
                "raw_forbidden": "raw snippet must not leak",
            },
            "replayable_input_candidate": {
                "input_ref": "trace:eval:replayable_input_candidate",
                "input_hash": "sha256:replayable",
                "decision_effect": "none",
                "artifact_refs": {
                    "decision_input_candidate": {
                        "input_ref": "trace:eval:decision_input_candidate",
                        "input_hash": "sha256:decision",
                    },
                    "shadow_workers": [
                        {
                            "task_id": "shadow:RootCauseAgent",
                            "agent_name": "RootCauseAgent",
                            "status": "ok",
                            "contribution_id": "c-root",
                            "output_hash": "sha256:root",
                            "input_ref": "trace:eval:shadow_swarm_input",
                        }
                    ],
                    "worker_result_manifest": [
                        {
                            "task_id": "shadow:RootCauseAgent",
                            "agent_name": "RootCauseAgent",
                            "status": "ok",
                            "input_ref": "trace:eval:shadow_swarm_input",
                            "input_hash": "sha256:input-view",
                            "agent_run_request_hash": "sha256:request",
                            "output_hash": "sha256:root",
                            "trace_ref": "trace-eval:shadow:RootCauseAgent",
                            "failure_policy_applied": "none",
                            "agent_run_result": {
                                "input_view_hash": "sha256:input-view",
                                "agent_run_request_hash": "sha256:request",
                                "raw_input_view": "raw snippet must not leak",
                            },
                        }
                    ],
                },
                "coverage": {
                    "worker_artifact_count": 4,
                    "has_decision_input_candidate": True,
                    "worker_manifest_count": 4,
                    "worker_manifest_complete": True,
                    "worker_manifest_missing_fields": [],
                    "raw_worker_payload": "raw snippet must not leak",
                },
            },
            "run_context": {
                "artifacts": {
                    "evidence_count": 7,
                    "contribution_count": 4,
                    "has_lead_plan": True,
                    "has_decision_input": True,
                    "evidence_refs": [{"evidence_id": "ev-search-mark"}],
                    "contribution_refs": [
                        {"contribution_id": "c-root", "agent_name": "RootCauseAgent"}
                    ],
                    "decision_input_ref": {
                        "input_ref": "trace:eval:decision_input_candidate",
                        "input_hash": "sha256:decision",
                    },
                    "gate_result_refs": {
                        "replayable_input_candidate": {
                            "input_ref": "trace:eval:replayable_input_candidate",
                            "input_hash": "sha256:replayable",
                        }
                    },
                    "raw": "raw snippet must not leak",
                }
            },
            "gate_candidate": {
                "passed": False,
                "severity": "hard_fail",
                "violations": [{"rule_id": "candidate.action_not_allowed"}],
                "blocked_actions": ["trigger long"],
                "missing_facts": ["mark"],
            },
            "plan_semantic_candidate": {
                "passed": False,
                "severity": "hard_fail",
                "violations": [{"rule_id": "plan_semantic.long_stop_not_below_entry"}],
                "raw_snippet": "raw snippet must not leak",
            },
            "final_decision_switch_readiness": {
                "ready": False,
                "blocking_reasons": ["candidate_gate_failed"],
            },
            "raw_decision": "must not leak",
        },
    )
    badcase_id = journal.record_badcase(
        trace_id=trace_id,
        plan_id="plan_eval_seed",
        category="grounding_error",
        severity="high",
        summary="replayable eval seed",
        expected_behavior="no trade is acceptable when evidence is thin",
        actual_behavior="no trade",
        eval_dataset_name="failure_cases",
        evidence_refs=["plan_run.frozen_input_hash", "plan_run.verdict"],
    )
    return trace_id, badcase_id


def _seed_trace_with_lead_synthesis_artifact(journal: Journal) -> tuple[str, int]:
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP", horizon="6h")
    recorder.finish_trace(trace_id, status="blocked", final_plan_id="plan_lead_artifact", final_action="no trade", allowed=False)
    lead_synthesis_artifact = {
        "schema_version": 1,
        "artifact_type": "lead_synthesis",
        "artifact_ref": "candidate:lead_synthesis",
        "decision_effect": "none",
        "input_ref": "trace:eval:lead_synthesis",
        "input_hash": "sha256:lead-input",
        "lead_plan_ref": "shadow:eval",
        "lead_plan_hash": "sha256:lead-plan",
        "worker_manifest_hash": "sha256:worker-manifest",
        "included_contribution_refs": [],
        "dropped_contribution_refs": [],
        "counter_thesis_count": 1,
        "counter_thesis_refs": [
            {
                "contribution_id": "c-sentiment",
                "agent_name": "MarketSentimentAgent",
                "claim": "Crowded longs can reverse.",
                "side": "bearish",
                "raw_payload": "raw payload must not leak",
            }
        ],
        "strongest_counter_thesis_ref": {
            "contribution_id": "c-sentiment",
            "agent_name": "MarketSentimentAgent",
            "claim": "Crowded longs can reverse.",
            "side": "bearish",
            "raw_payload": "raw payload must not leak",
        },
        "conflict_count": 1,
        "conflict_refs": [
            {
                "conflict_id": "trend_vs_crowding",
                "summary": "Trend conflicts with crowding.",
                "contribution_refs": ["c-root", "c-sentiment"],
                "raw_snippet": "raw snippet must not leak",
            }
        ],
        "policy_version": "lead_synthesis_artifact.test",
        "artifact_hash": "sha256:lead-artifact",
    }
    journal.append_plan_run(
        "plan_lead_artifact",
        "blocked",
        {
            "trace_id": trace_id,
            "frozen_input_hash": "frozen-lead-artifact",
            "parsed_plan": {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "no trade",
                "horizon": "6h",
                "manual_execution_required": True,
                "probability": 0.5,
            },
            "verdict": {"allowed": False, "reasons": ["fixture"], "warnings": [], "rule_hits": []},
            "decision_input_candidate": {
                "input_ref": "trace:eval:decision_input_candidate",
                "input_hash": "sha256:decision",
                "decision_effect": "none",
                "lead_synthesis": {
                    "counter_thesis": ["Crowded longs can reverse."],
                    "counter_thesis_refs": lead_synthesis_artifact["counter_thesis_refs"],
                    "strongest_counter_thesis_ref": lead_synthesis_artifact[
                        "strongest_counter_thesis_ref"
                    ],
                    "conflicts": ["trend_vs_crowding"],
                    "conflict_refs": lead_synthesis_artifact["conflict_refs"],
                },
                "evidence_refs": [],
                "contribution_refs": [],
            },
            "replayable_input_candidate": {
                "input_ref": "trace:eval:replayable_input_candidate",
                "input_hash": "sha256:replayable",
                "decision_effect": "none",
                "coverage": {"worker_artifact_count": 4, "worker_manifest_complete": True},
                "artifact_refs": {"worker_result_manifest": []},
            },
            "lead_synthesis_artifact": lead_synthesis_artifact,
            "gate_candidate": {"passed": True, "blocked_actions": [], "missing_facts": []},
            "plan_semantic_candidate": {"passed": True},
            "final_decision_switch_readiness": {"ready": True, "blocking_reasons": []},
        },
    )
    badcase_id = journal.record_badcase(
        trace_id=trace_id,
        plan_id="plan_lead_artifact",
        category="coverage_gap",
        severity="high",
        summary="lead synthesis artifact coverage seed",
        expected_behavior="counter refs are replayable",
        actual_behavior="candidate artifact recorded",
        eval_dataset_name="failure_cases",
        evidence_refs=["plan_run.lead_synthesis_artifact"],
    )
    return trace_id, badcase_id


def _minimal_case():
    temp_dir = tempfile.TemporaryDirectory()
    journal = Journal(f"{temp_dir.name}/journal.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    return EvalCaseBuilder(journal).build_cases(badcase_ids=[badcase_id])[0]


def _prod_counts(path) -> dict[str, int]:
    with sqlite3.connect(path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes")
        }


def _all_prod_counts(path) -> dict[str, int]:
    with sqlite3.connect(path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes", "traces", "trace_spans", "llm_interactions")
        }

