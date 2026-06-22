from __future__ import annotations

from crypto_manual_alert.eval.replayable_input_summary import (
    replayable_artifact_refs_summary,
    replayable_coverage_summary,
)


def test_replayable_coverage_summary_keeps_only_allowed_keys_in_sorted_order():
    summary = replayable_coverage_summary(
        {
            "worker_artifact_count": 4,
            "has_version_lock": True,
            "has_final_decision_output": True,
            "raw_prompt": "must not leak",
            "unknown": "must not leak",
        }
    )

    assert list(summary) == [
        "has_final_decision_output",
        "has_version_lock",
        "worker_artifact_count",
    ]
    assert summary == {
        "has_final_decision_output": True,
        "has_version_lock": True,
        "worker_artifact_count": 4,
    }


def test_replayable_coverage_summary_returns_empty_for_non_mapping():
    assert replayable_coverage_summary(None) == {}
    assert replayable_coverage_summary([]) == {}


def test_replayable_artifact_refs_summary_preserves_safe_observed_run_refs():
    refs = replayable_artifact_refs_summary(
        {
            "decision_input_candidate": {
                "input_ref": "trace:audit:decision_input_candidate",
                "input_hash": "sha256:decision",
                "raw_prompt": "must not leak",
            },
            "shadow_workers": [
                {
                    "task_id": "task-root-cause",
                    "agent_name": "RootCauseAgent",
                    "status": "completed",
                    "contribution_id": "contribution-1",
                    "output_hash": "sha256:worker",
                    "input_ref": "trace:audit:worker-input",
                    "raw_output": "must not leak",
                }
            ],
            "worker_result_manifest": [
                {
                    "task_id": "task-root-cause",
                    "agent_name": "RootCauseAgent",
                    "status": "completed",
                    "input_ref": "trace:audit:worker-input",
                    "input_hash": "sha256:input",
                    "agent_run_request_hash": "sha256:request",
                    "output_hash": "sha256:worker",
                    "trace_ref": "span-1",
                    "failure_policy_applied": "none",
                    "agent_run_result": {
                        "input_view_hash": "sha256:view",
                        "agent_run_request_hash": "sha256:request",
                        "output_hash": "sha256:worker",
                        "raw_payload": "must not leak",
                    },
                    "tool_call_artifact_refs": [
                        {
                            "tool_call_id": "tool-1",
                            "skill_name": "root_cause_search",
                            "status": "ok",
                            "result_ref": "skill-result-1",
                            "raw": "must be sanitized",
                        }
                    ],
                }
            ],
            "final_decision_output": {
                "output_ref": "trace:audit:final_decision_output",
                "output_hash": "sha256:final",
                "char_count": 128,
                "stored_raw": False,
                "raw_decision": "must not leak",
            },
            "final_input_selection": {
                "mode": "legacy_prompt",
                "source_ref": "legacy_prompt_packet",
                "decision_effect": "none",
                "readiness_ready": False,
                "selection_hash": "sha256:selection",
                "raw_prompt": "must not leak",
            },
            "parsed_plan": {
                "plan_ref": "trace:audit:parsed_plan",
                "plan_id": "plan-1",
                "main_action": "no trade",
                "plan_hash": "sha256:plan",
                "raw_payload": "must not leak",
            },
            "production_control_gate": {
                "gate_ref": "trace:audit:production_control_gate",
                "gate_hash": "sha256:control",
                "allowed": False,
                "rule_ids": ["production_control.worker_hard_block"],
                "raw_details": "must not leak",
            },
            "risk_gate_result": {
                "gate_ref": "trace:audit:risk_gate_result",
                "gate_hash": "sha256:risk",
                "allowed": False,
                "rule_ids": ["risk.max_leverage"],
            },
            "side_effect_policy": {
                "allow_production_journal_write": True,
                "allow_notification_intent": True,
                "policy_hash": "sha256:policy",
                "raw_policy": "must not leak",
            },
            "context_artifact_summary": {
                "evidence_count": 2,
                "contribution_count": 4,
                "artifact_hash": "sha256:context",
                "raw_context": "must not leak",
            },
            "version_lock": {
                "version_lock_ref": "trace:audit:version_lock",
                "version_lock_hash": "sha256:version-lock",
                "config_hash": "sha256:config",
                "skill_hashes": {"crypto-macro-decision": "sha256:skill"},
                "prompt_hashes": {"legacy_final_prompt": "sha256:prompt"},
                "model": "gpt-fixture",
                "rule_hashes": {"risk_gate": "sha256:risk-rules"},
                "redaction_policy_hash": "sha256:redaction",
                "raw_prompt": "must not leak",
            },
        }
    )

    assert refs["decision_input_candidate"] == {
        "input_ref": "trace:audit:decision_input_candidate",
        "input_hash": "sha256:decision",
    }
    assert refs["shadow_workers"] == [
        {
            "task_id": "task-root-cause",
            "agent_name": "RootCauseAgent",
            "status": "completed",
            "contribution_id": "contribution-1",
            "output_hash": "sha256:worker",
            "input_ref": "trace:audit:worker-input",
        }
    ]
    assert refs["worker_result_manifest"][0]["agent_run_result"] == {
        "input_view_hash": "sha256:view",
        "agent_run_request_hash": "sha256:request",
        "output_hash": "sha256:worker",
    }
    assert refs["worker_result_manifest"][0]["tool_call_artifact_refs"] == [
        {
            "tool_call_id": "tool-1",
            "skill_name": "root_cause_search",
            "status": "ok",
            "result_ref": "skill-result-1",
        }
    ]
    assert refs["final_decision_output"] == {
        "output_ref": "trace:audit:final_decision_output",
        "output_hash": "sha256:final",
        "char_count": 128,
        "stored_raw": False,
    }
    assert refs["version_lock"]["model"] == "gpt-fixture"
    assert "must not leak" not in str(refs)


def test_replayable_artifact_refs_summary_preserves_safe_trace_support_refs():
    refs = replayable_artifact_refs_summary(
        {
            "telemetry_refs": {
                "telemetry_ref": "trace:audit:telemetry",
                "telemetry_hash": "sha256:telemetry",
                "span_count": 2,
                "llm_interaction_count": 1,
                "total_duration_ms": 120,
                "total_prompt_tokens": 10,
                "total_completion_tokens": 20,
                "total_tokens": 30,
                "total_cost_usd": 0.01,
                "span_refs": [
                    {
                        "span_id": "span-1",
                        "parent_span_id": None,
                        "span_name": "decision.final",
                        "span_type": "llm",
                        "status": "ok",
                        "duration_ms": 100,
                        "raw_payload": "must not leak",
                    }
                ],
                "llm_interaction_refs": [
                    {
                        "interaction_ref": "llm-1",
                        "span_id": "span-1",
                        "component": "final",
                        "provider": "fixture",
                        "model": "gpt-fixture",
                        "endpoint": "/chat/completions",
                        "status": "ok",
                        "input_hash": "sha256:input",
                        "output_hash": "sha256:output",
                        "duration_ms": 100,
                        "prompt_tokens": 10,
                        "completion_tokens": 20,
                        "total_tokens": 30,
                        "cost_usd": 0.01,
                        "finish_reason": "stop",
                        "retry_count": 0,
                        "request_json": "must not leak",
                    }
                ],
            },
            "evidence_snapshot_refs": {
                "evidence_snapshot_ref": "trace:audit:evidence",
                "evidence_snapshot_hash": "sha256:evidence",
                "facts_gate_hash": "sha256:facts",
                "evidence_count": 1,
                "source_type_counts": {"exchange_native": 1},
                "data_type_counts": {"mark": 1},
                "execution_fact_eligible_count": 1,
                "facts_gate": {"passed": True},
                "evidence_refs": [
                    {
                        "evidence_id": "ev-1",
                        "name": "mark price",
                        "symbol": "BTC",
                        "data_type": "mark",
                        "source_type": "exchange_native",
                        "source_name": "okx",
                        "source_url": "https://example.invalid",
                        "freshness_status": "fresh",
                        "can_satisfy_execution_fact": True,
                        "confidence_cap": 0.7,
                        "trace_ref": "span-ev",
                        "evidence_hash": "sha256:ev",
                        "raw_payload": "must not leak",
                    }
                ],
            },
            "memory_snapshot_refs": {
                "memory_snapshot_ref": "trace:audit:memory",
                "memory_snapshot_hash": "sha256:memory",
                "session_id": "session-1",
                "allowed_fields": ["position"],
                "allowed_field_names": ["position"],
                "recent_turn_count": 3,
                "summary_hash": "sha256:summary",
                "long_term_memory_refs": ["mem-1"],
                "quarantined_fields": ["allowed_fields.mark"],
                "memory_warnings": [
                    "memory_snapshot.quarantined_fact_like_fields: memory is context only, not live market evidence"
                ],
                "raw_context": "must not leak",
            },
            "span_tree_refs": {
                "span_tree_ref": "trace:audit:span-tree",
                "span_tree_hash": "sha256:span-tree",
                "span_count": 2,
                "root_span_count": 1,
                "parent_link_count": 1,
                "parent_complete": True,
                "missing_parent_span_ids": [],
                "span_refs": [
                    {
                        "span_id": "span-1",
                        "parent_span_id": None,
                        "span_name": "root",
                        "span_type": "workflow",
                        "status": "ok",
                        "duration_ms": 120,
                        "raw_payload": "must not leak",
                    }
                ],
            },
        }
    )

    assert refs["telemetry_refs"]["span_refs"] == [
        {
            "span_id": "span-1",
            "parent_span_id": None,
            "span_name": "decision.final",
            "span_type": "llm",
            "status": "ok",
            "duration_ms": 100,
        }
    ]
    assert refs["telemetry_refs"]["llm_interaction_refs"][0]["interaction_ref"] == "llm-1"
    assert refs["evidence_snapshot_refs"]["evidence_refs"][0]["evidence_id"] == "ev-1"
    assert refs["memory_snapshot_refs"]["session_id"] == "session-1"
    assert refs["memory_snapshot_refs"]["quarantined_fields"] == ["allowed_fields.mark"]
    assert refs["memory_snapshot_refs"]["memory_warnings"] == [
        "memory_snapshot.quarantined_fact_like_fields: memory is context only, not live market evidence"
    ]
    assert refs["span_tree_refs"]["span_refs"][0]["span_name"] == "root"
    assert "must not leak" not in str(refs)


def test_replayable_artifact_refs_summary_returns_empty_for_non_mapping():
    assert replayable_artifact_refs_summary(None) == {}
    assert replayable_artifact_refs_summary([]) == {}
