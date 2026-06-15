from __future__ import annotations

from crypto_manual_alert.decision.replayable_input import build_replayable_input_candidate


def test_replayable_input_candidate_records_artifact_refs_without_raw_payloads():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
            "evidence_refs": [
                {"evidence_id": "ev-1", "source_type": "search_derived"},
            ],
            "lead_synthesis": {
                "included_contribution_ids": ["c-root"],
                "dropped_contributions": [],
            },
            "raw_forbidden": "raw snippet must not be copied",
        },
        shadow_swarm_audit={
            "lead_plan": {"plan_id": "shadow:trace-1"},
            "worker_results": [
                {
                    "task_id": "shadow:RootCauseAgent",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "trace_ref": "trace-1:shadow:RootCauseAgent",
                    "failure_policy_applied": "none",
                    "required": True,
                    "error": None,
                    "contribution": {
                        "contribution_id": "c-root",
                        "output_hash": "sha256:root",
                        "input_ref": "trace:trace-1:shadow_swarm_input",
                        "trace_ref": "trace-1:shadow:RootCauseAgent",
                        "failure_policy_applied": "none",
                        "constraints": {
                            "tool_audit_results": [
                                {
                                    "tool_name": "web_search",
                                    "status": "ok",
                                    "result_ref": "shadow_tool:web_search:eth-etf",
                                    "result_refs": [
                                        {
                                            "title": "ETH ETF",
                                            "url": "https://example.test/eth-etf",
                                            "snippet_ref": "shadow_tool.web_search.RootCauseAgent[0].snippet_redacted",
                                        }
                                    ],
                                }
                            ]
                        },
                        "summary": "raw contribution text must not be copied",
                    },
                    "agent_run_result": {
                        "task_id": "shadow:RootCauseAgent",
                        "agent_name": "RootCauseAgent",
                        "status": "ok",
                        "contribution_ref": "trace:trace-1:shadow_swarm_input",
                        "input_view_hash": "sha256:input-view",
                        "agent_run_request_hash": "sha256:request",
                        "output_hash": "sha256:root",
                        "trace_ref": "trace-1:shadow:RootCauseAgent",
                        "failure_policy_applied": "none",
                        "required": True,
                        "decision_effect": "none",
                        "error": None,
                    },
                }
            ],
        },
    )

    public = candidate.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["legacy_frozen_input_hash"] == "abc123"
    assert public["artifact_refs"]["decision_input_candidate"] == {
        "input_ref": "trace:trace-1:decision_input_candidate",
        "input_hash": "sha256:decision",
    }
    assert public["artifact_refs"]["shadow_workers"] == [
        {
            "task_id": "shadow:RootCauseAgent",
            "agent_name": "RootCauseAgent",
            "status": "ok",
            "contribution_id": "c-root",
            "output_hash": "sha256:root",
            "input_ref": "trace:trace-1:shadow_swarm_input",
        }
    ]
    assert public["artifact_refs"]["worker_result_manifest"] == [
        {
            "task_id": "shadow:RootCauseAgent",
            "agent_name": "RootCauseAgent",
            "status": "ok",
            "input_ref": "trace:trace-1:shadow_swarm_input",
            "input_hash": "sha256:input-view",
            "agent_run_request_hash": "sha256:request",
            "output_hash": "sha256:root",
            "trace_ref": "trace-1:shadow:RootCauseAgent",
            "failure_policy_applied": "none",
            "required": True,
            "agent_run_result": {
                "task_id": "shadow:RootCauseAgent",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "contribution_ref": "trace:trace-1:shadow_swarm_input",
                "input_view_hash": "sha256:input-view",
                "agent_run_request_hash": "sha256:request",
                "output_hash": "sha256:root",
                "trace_ref": "trace-1:shadow:RootCauseAgent",
                "failure_policy_applied": "none",
                "required": True,
                "decision_effect": "none",
            },
        }
    ]
    assert public["artifact_refs"]["worker_result_manifest"][0]["input_hash"].startswith("sha256:")
    assert public["coverage"]["worker_artifact_count"] == 1
    assert public["coverage"]["worker_manifest_count"] == 1
    assert public["coverage"]["worker_manifest_complete"] is True
    assert public["coverage"]["worker_manifest_missing_fields"] == []
    assert public["coverage"]["evidence_ref_count"] == 1
    serialized = str(public)
    assert "raw snippet must not be copied" not in serialized
    assert "raw contribution text must not be copied" not in serialized
    assert "tool_audit_result_refs" not in serialized
    assert "error_message" not in serialized


def test_replayable_input_candidate_records_tool_call_artifact_refs_without_raw_payloads():
    candidate = build_replayable_input_candidate(
        trace_id="trace-tool",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-tool:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={
            "lead_plan": {"plan_id": "shadow:trace-tool"},
            "worker_results": [
                {
                    "task_id": "shadow:RootCauseAgent",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "trace_ref": "trace-tool:shadow:RootCauseAgent",
                    "failure_policy_applied": "none",
                    "required": True,
                    "contribution": {
                        "contribution_id": "c-root",
                        "output_hash": "sha256:root",
                        "input_ref": "trace:trace-tool:shadow_swarm_input",
                        "trace_ref": "trace-tool:shadow:RootCauseAgent",
                        "failure_policy_applied": "none",
                        "tool_call_artifact_refs": [
                            {
                                "tool_call_id": "tool-call-1",
                                "skill_name": "root_cause_search",
                                "status": "ok",
                                "source_type": "search_derived",
                                "source_tier": "external_search",
                                "retrieved_at": "2026-07-04T01:00:00Z",
                                "freshness_status": "fresh",
                                "result_ref": "skill:root_cause_search:trace-tool:1",
                                "output_hash": "sha256:tool-output",
                                "can_satisfy_execution_fact": False,
                                "result_count": 3,
                                "error_type": None,
                                "snippet": "raw snippet must not be copied",
                                "raw_payload": {"html": "raw page must not be copied"},
                                "error": {"message": "raw error message must not be copied"},
                                "evidence_candidates": [{"claim": "raw claim must not be copied"}],
                            }
                        ],
                    },
                    "agent_run_result": {
                        "task_id": "shadow:RootCauseAgent",
                        "agent_name": "RootCauseAgent",
                        "status": "ok",
                        "contribution_ref": "trace:trace-tool:shadow_swarm_input",
                        "input_view_hash": "sha256:input-view",
                        "agent_run_request_hash": "sha256:request",
                        "output_hash": "sha256:root",
                        "trace_ref": "trace-tool:shadow:RootCauseAgent",
                        "failure_policy_applied": "none",
                        "required": True,
                        "decision_effect": "none",
                        "error": None,
                        "input_view": {"raw": "raw worker input must not be copied"},
                        "request_json": "{\"prompt\":\"raw prompt must not be copied\"}",
                        "response_json": "{\"content\":\"raw model output must not be copied\"}",
                    },
                }
            ],
        },
    ).to_public_dict()

    manifest_item = candidate["artifact_refs"]["worker_result_manifest"][0]

    assert manifest_item["tool_call_artifact_refs"] == [
        {
            "tool_call_id": "tool-call-1",
            "skill_name": "root_cause_search",
            "status": "ok",
            "source_type": "search_derived",
            "source_tier": "external_search",
            "retrieved_at": "2026-07-04T01:00:00Z",
            "freshness_status": "fresh",
            "result_ref": "skill:root_cause_search:trace-tool:1",
            "output_hash": "sha256:tool-output",
            "can_satisfy_execution_fact": False,
            "result_count": 3,
        }
    ]
    assert candidate["coverage"]["tool_call_artifact_count"] == 1
    serialized = str(candidate)
    assert "raw snippet must not be copied" not in serialized
    assert "raw page must not be copied" not in serialized
    assert "raw error message must not be copied" not in serialized
    assert "raw claim must not be copied" not in serialized
    assert "raw worker input must not be copied" not in serialized
    assert "raw prompt must not be copied" not in serialized
    assert "raw model output must not be copied" not in serialized
    assert "snippet" not in serialized
    assert "raw_payload" not in serialized
    assert "evidence_candidates" not in serialized
    assert "request_json" not in serialized
    assert "response_json" not in serialized
    assert "error_message" not in serialized


def test_replayable_input_candidate_records_observed_run_refs_without_raw_outputs():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={"lead_plan": {"plan_id": "shadow:trace-1"}, "worker_results": []},
        lead_synthesis_artifact={
            "artifact_ref": "candidate:lead_synthesis",
            "input_ref": "trace:trace-1:lead_synthesis",
            "input_hash": "sha256:lead-input",
            "decision_effect": "none",
            "raw_payload": "must not be copied",
        },
        observed_run_artifacts={
            "final_decision_output": "{\"notes\":\"raw completion must not be copied\"}",
            "final_input_selection": {
                "mode": "legacy_prompt",
                "source_ref": "legacy_prompt_packet",
                "decision_effect": "production_final_input",
                "readiness_ready": False,
            },
            "parsed_plan": {
                "plan_id": "plan-1",
                "main_action": "trigger long",
                "raw_payload": "must not be copied",
            },
            "production_control_gate": {
                "allowed": False,
                "rule_hits": [{"rule_id": "production_control.worker_hard_block"}],
                "raw_details": "must not be copied",
            },
            "risk_gate_result": {
                "allowed": False,
                "rule_hits": [{"rule_id": "risk.max_leverage"}],
            },
            "side_effect_policy": {
                "allow_production_journal_write": True,
                "allow_notification_intent": True,
            },
            "context_artifact_summary": {
                "evidence_count": 2,
                "contribution_count": 4,
                "gate_result_names": ["facts_gate"],
                "lead_plan_ref": {"plan_id": "shadow:trace-1", "artifact_hash": "sha256:lead-plan"},
                "decision_input_ref": {
                    "input_ref": "trace:trace-1:pre_final_decision_input",
                    "input_hash": "sha256:pre-final",
                },
                "raw_context": "must not be copied",
            },
        },
    ).to_public_dict()

    refs = candidate["artifact_refs"]
    assert refs["lead_synthesis_artifact"] == {
        "artifact_ref": "candidate:lead_synthesis",
        "input_ref": "trace:trace-1:lead_synthesis",
        "input_hash": "sha256:lead-input",
        "decision_effect": "none",
        "artifact_hash": refs["lead_synthesis_artifact"]["artifact_hash"],
    }
    assert refs["lead_synthesis_artifact"]["artifact_hash"].startswith("sha256:")
    assert refs["final_decision_output"] == {
        "output_ref": "trace:trace-1:final_decision_output",
        "output_hash": refs["final_decision_output"]["output_hash"],
        "char_count": len("{\"notes\":\"raw completion must not be copied\"}"),
        "stored_raw": False,
    }
    assert refs["final_decision_output"]["output_hash"].startswith("sha256:")
    assert refs["final_input_selection"]["mode"] == "legacy_prompt"
    assert refs["final_input_selection"]["selection_hash"].startswith("sha256:")
    assert refs["parsed_plan"] == {
        "plan_ref": "trace:trace-1:parsed_plan",
        "plan_id": "plan-1",
        "main_action": "trigger long",
        "plan_hash": refs["parsed_plan"]["plan_hash"],
    }
    assert refs["parsed_plan"]["plan_hash"].startswith("sha256:")
    assert refs["production_control_gate"] == {
        "gate_ref": "trace:trace-1:production_control_gate",
        "gate_hash": refs["production_control_gate"]["gate_hash"],
        "allowed": False,
        "rule_ids": ["production_control.worker_hard_block"],
    }
    assert refs["risk_gate_result"] == {
        "gate_ref": "trace:trace-1:risk_gate_result",
        "gate_hash": refs["risk_gate_result"]["gate_hash"],
        "allowed": False,
        "rule_ids": ["risk.max_leverage"],
    }
    assert refs["side_effect_policy"]["policy_hash"].startswith("sha256:")
    assert refs["context_artifact_summary"]["artifact_hash"].startswith("sha256:")
    assert refs["context_artifact_summary"]["evidence_count"] == 2
    assert refs["context_artifact_summary"]["contribution_count"] == 4
    assert refs["context_artifact_summary"]["lead_plan_ref"] == {
        "plan_id": "shadow:trace-1",
        "artifact_hash": "sha256:lead-plan",
    }
    assert candidate["coverage"]["has_lead_synthesis_artifact"] is True
    assert candidate["coverage"]["has_final_decision_output"] is True
    assert candidate["coverage"]["has_final_input_selection"] is True
    assert candidate["coverage"]["has_parsed_plan"] is True
    assert candidate["coverage"]["has_production_control_gate"] is True
    assert candidate["coverage"]["has_risk_gate_result"] is True
    assert candidate["coverage"]["has_side_effect_policy"] is True
    assert candidate["coverage"]["has_context_artifact_summary"] is True
    serialized = str(candidate)
    assert "raw completion must not be copied" not in serialized
    assert "raw_payload" not in serialized
    assert "raw_details" not in serialized
    assert "raw_context" not in serialized


def test_replayable_input_candidate_records_version_lock_refs_without_raw_config_or_prompt():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={"lead_plan": {"plan_id": "shadow:trace-1"}, "worker_results": []},
        observed_run_artifacts={
            "version_lock": {
                "config_hash": "sha256:config",
                "skill_hashes": {"crypto-macro-decision": "sha256:skill"},
                "prompt_hashes": {"legacy_final_prompt": "sha256:prompt"},
                "model": "gpt-fixture",
                "rule_hashes": {"risk_gate": "sha256:risk-rules"},
                "redaction_policy_hash": "sha256:redaction",
                "raw_prompt": "must not be copied",
                "openai_api_key": "must not be copied",
            }
        },
    ).to_public_dict()

    refs = candidate["artifact_refs"]["version_lock"]
    assert refs == {
        "version_lock_ref": "trace:trace-1:version_lock",
        "version_lock_hash": refs["version_lock_hash"],
        "config_hash": "sha256:config",
        "skill_hashes": {"crypto-macro-decision": "sha256:skill"},
        "prompt_hashes": {"legacy_final_prompt": "sha256:prompt"},
        "model": "gpt-fixture",
        "rule_hashes": {"risk_gate": "sha256:risk-rules"},
        "redaction_policy_hash": "sha256:redaction",
    }
    assert refs["version_lock_hash"].startswith("sha256:")
    assert candidate["coverage"]["has_version_lock"] is True
    serialized = str(candidate)
    assert "must not be copied" not in serialized
    assert "openai_api_key" not in serialized


def test_replayable_input_candidate_records_telemetry_refs_without_raw_payloads():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={"lead_plan": {"plan_id": "shadow:trace-1"}, "worker_results": []},
        observed_run_artifacts={
            "telemetry_refs": {
                "spans": [
                    {
                        "span_id": "span-final",
                        "parent_span_id": None,
                        "span_name": "decision.final",
                        "span_type": "decision.llm",
                        "status": "ok",
                        "duration_ms": 123,
                        "input_summary": {"prompt": "raw prompt must not be copied"},
                    }
                ],
                "llm_interactions": [
                    {
                        "id": 7,
                        "span_id": "span-final",
                        "component": "decision.final",
                        "provider": "openai_compatible",
                        "model": "gpt-test",
                        "endpoint": "/v1/chat/completions",
                        "status": "ok",
                        "input_hash": "input-hash",
                        "output_hash": "output-hash",
                        "duration_ms": 120,
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "total_tokens": 20,
                        "cost_usd": 0.001,
                        "finish_reason": "stop",
                        "retry_count": 0,
                        "request_json": "{\"api_key\":\"raw secret\"}",
                        "response_json": "{\"raw\":\"raw model text must not be copied\"}",
                    }
                ],
            }
        },
    ).to_public_dict()

    telemetry = candidate["artifact_refs"]["telemetry_refs"]
    assert telemetry["telemetry_ref"] == "trace:trace-1:telemetry"
    assert telemetry["telemetry_hash"].startswith("sha256:")
    assert telemetry["span_count"] == 1
    assert telemetry["llm_interaction_count"] == 1
    assert telemetry["total_duration_ms"] == 243
    assert telemetry["total_prompt_tokens"] == 12
    assert telemetry["total_completion_tokens"] == 8
    assert telemetry["total_tokens"] == 20
    assert telemetry["total_cost_usd"] == 0.001
    span_refs = telemetry["span_refs"]
    assert len(span_refs) == 1
    span_ref = span_refs[0]
    assert span_ref["span_id"] == "span-final"
    assert span_ref["parent_span_id"] is None
    assert span_ref["span_name"] == "decision.final"
    assert span_ref["span_type"] == "decision.llm"
    assert span_ref["status"] == "ok"
    assert span_ref["duration_ms"] == 123
    # input_summary is recorded as a redacted hash + refs, never as the raw prompt
    assert "span_input_hash" in span_ref
    assert "raw prompt must not be copied" not in str(span_ref)
    assert telemetry["llm_interaction_refs"] == [
        {
            "interaction_ref": "trace:trace-1:llm_interaction:7",
            "span_id": "span-final",
            "component": "decision.final",
            "provider": "openai_compatible",
            "model": "gpt-test",
            "endpoint": "/v1/chat/completions",
            "status": "ok",
            "input_hash": "input-hash",
            "output_hash": "output-hash",
            "duration_ms": 120,
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
            "cost_usd": 0.001,
            "finish_reason": "stop",
            "retry_count": 0,
        }
    ]
    assert candidate["coverage"]["has_telemetry_refs"] is True
    serialized = str(candidate)
    assert "request_json" not in serialized
    assert "response_json" not in serialized
    assert "raw prompt must not be copied" not in serialized
    assert "raw secret" not in serialized
    assert "raw model text must not be copied" not in serialized


def test_replayable_input_candidate_records_span_tree_refs_and_parent_completeness():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={"lead_plan": {"plan_id": "shadow:trace-1"}, "worker_results": []},
        observed_run_artifacts={
            "span_tree_refs": {
                "spans": [
                    {
                        "span_id": "span-root",
                        "parent_span_id": None,
                        "span_name": "decision.final",
                        "span_type": "decision.llm",
                        "status": "ok",
                        "duration_ms": 120,
                        "input_summary": {"prompt": "raw prompt must not be copied"},
                    },
                    {
                        "span_id": "span-child",
                        "parent_span_id": "span-root",
                        "span_name": "shadow_swarm.worker",
                        "span_type": "agent.worker",
                        "status": "ok",
                        "duration_ms": 42,
                        "output_summary": {"raw_payload": "raw output must not be copied"},
                    },
                    {
                        "span_id": "span-orphan",
                        "parent_span_id": "span-missing",
                        "span_name": "research.query",
                        "span_type": "tool.search",
                        "status": "error",
                        "duration_ms": 5,
                    },
                ]
            }
        },
    ).to_public_dict()

    span_tree = candidate["artifact_refs"]["span_tree_refs"]
    assert span_tree == {
        "span_tree_ref": "trace:trace-1:span_tree",
        "span_tree_hash": span_tree["span_tree_hash"],
        "span_count": 3,
        "root_span_count": 1,
        "parent_link_count": 2,
        "parent_complete": False,
        "missing_parent_span_ids": ["span-missing"],
        "span_refs": [
            {
                "span_id": "span-root",
                "parent_span_id": None,
                "span_name": "decision.final",
                "span_type": "decision.llm",
                "status": "ok",
                "duration_ms": 120,
                "span_input_hash": span_tree["span_refs"][0]["span_input_hash"],
            },
            {
                "span_id": "span-child",
                "parent_span_id": "span-root",
                "span_name": "shadow_swarm.worker",
                "span_type": "agent.worker",
                "status": "ok",
                "duration_ms": 42,
                "span_output_hash": span_tree["span_refs"][1]["span_output_hash"],
            },
            {
                "span_id": "span-orphan",
                "parent_span_id": "span-missing",
                "span_name": "research.query",
                "span_type": "tool.search",
                "status": "error",
                "duration_ms": 5,
            },
        ],
    }
    assert span_tree["span_tree_hash"].startswith("sha256:")
    assert candidate["coverage"]["has_span_tree_refs"] is True
    assert candidate["coverage"]["span_tree_parent_complete"] is False
    assert candidate["coverage"]["span_tree_missing_parent_count"] == 1
    serialized = str(candidate)
    assert "raw prompt must not be copied" not in serialized
    assert "raw output must not be copied" not in serialized
    assert "input_summary" not in serialized
    assert "output_summary" not in serialized


def test_replayable_input_candidate_records_evidence_snapshot_refs_without_raw_evidence():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={"lead_plan": {"plan_id": "shadow:trace-1"}, "worker_results": []},
        observed_run_artifacts={
            "evidence_snapshot_refs": {
                "evidence_packets": [
                    {
                        "evidence_id": "ev-mark",
                        "name": "mark",
                        "symbol": "ETH-USDT-SWAP",
                        "data_type": "mark",
                        "source_type": "exchange_native",
                        "source_name": "okx_public",
                        "source_url": None,
                        "freshness_status": "fresh",
                        "can_satisfy_execution_fact": True,
                        "confidence_cap": None,
                        "trace_ref": "market:mark",
                        "value": {"raw": "raw exchange payload must not be copied"},
                    },
                    {
                        "evidence_id": "ev-news",
                        "name": "macro_context",
                        "symbol": "ETH-USDT-SWAP",
                        "data_type": "news",
                        "source_type": "search_derived",
                        "source_name": "web_search",
                        "source_url": "https://example.test/news",
                        "freshness_status": "unknown",
                        "can_satisfy_execution_fact": False,
                        "confidence_cap": 0.58,
                        "trace_ref": "research:macro_context:0",
                        "claims": ["raw search snippet must not be copied"],
                        "value": {"snippet": "raw search snippet must not be copied"},
                    },
                ],
                "facts_gate": {
                    "passed": False,
                    "severity": "hard_fail",
                    "missing_execution_facts": ["index", "order_book"],
                    "blocked_action_classes": ["opening", "trigger", "flip"],
                    "reasons": ["index missing"],
                    "raw_details": "raw gate details must not be copied",
                },
            }
        },
    ).to_public_dict()

    evidence = candidate["artifact_refs"]["evidence_snapshot_refs"]
    assert evidence["evidence_snapshot_ref"] == "trace:trace-1:evidence_snapshot"
    assert evidence["evidence_snapshot_hash"].startswith("sha256:")
    assert evidence["facts_gate_hash"].startswith("sha256:")
    assert evidence["evidence_count"] == 2
    assert evidence["source_type_counts"] == {"exchange_native": 1, "search_derived": 1}
    assert evidence["data_type_counts"] == {"mark": 1, "news": 1}
    assert evidence["execution_fact_eligible_count"] == 1
    assert evidence["facts_gate"] == {
        "passed": False,
        "severity": "hard_fail",
        "missing_execution_facts": ["index", "order_book"],
        "blocked_action_classes": ["opening", "trigger", "flip"],
    }
    assert evidence["evidence_refs"] == [
        {
            "evidence_id": "ev-mark",
            "name": "mark",
            "symbol": "ETH-USDT-SWAP",
            "data_type": "mark",
            "source_type": "exchange_native",
            "source_name": "okx_public",
            "source_url": None,
            "freshness_status": "fresh",
            "can_satisfy_execution_fact": True,
            "confidence_cap": None,
            "trace_ref": "market:mark",
            "evidence_hash": evidence["evidence_refs"][0]["evidence_hash"],
        },
        {
            "evidence_id": "ev-news",
            "name": "macro_context",
            "symbol": "ETH-USDT-SWAP",
            "data_type": "news",
            "source_type": "search_derived",
            "source_name": "web_search",
            "source_url": "https://example.test/news",
            "freshness_status": "unknown",
            "can_satisfy_execution_fact": False,
            "confidence_cap": 0.58,
            "trace_ref": "research:macro_context:0",
            "evidence_hash": evidence["evidence_refs"][1]["evidence_hash"],
        },
    ]
    assert evidence["evidence_refs"][0]["evidence_hash"].startswith("sha256:")
    assert evidence["evidence_refs"][1]["evidence_hash"].startswith("sha256:")
    assert candidate["coverage"]["has_evidence_snapshot_refs"] is True
    serialized = str(candidate)
    assert "raw exchange payload must not be copied" not in serialized
    assert "raw search snippet must not be copied" not in serialized
    assert "raw gate details must not be copied" not in serialized
    assert "'value'" not in serialized
    assert "'claims'" not in serialized


def test_replayable_input_candidate_records_memory_snapshot_refs_without_raw_conversation():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={"lead_plan": {"plan_id": "shadow:trace-1"}, "worker_results": []},
        observed_run_artifacts={
            "memory_snapshot": {
                "snapshot_id": "memory:session-1:turn-12",
                "session_id": "session-1",
                "allowed_fields": {
                    "user_position": "flat",
                    "risk_preference": "low",
                    "preferred_horizon": "4h",
                    "asset_focus": ["BTC", "ETH"],
                },
                "recent_turn_count": 5,
                "summary": "User prefers lower leverage and manual-only alerts.",
                "long_term_memory_refs": [
                    {"memory_id": "mem-1", "memory_hash": "sha256:mem-1", "score": 0.82}
                ],
                "messages": [
                    {"role": "user", "content": "raw user conversation must not be copied"}
                ],
                "raw_conversation": "raw conversation must not be copied",
                "api_key": "secret must not be copied",
            }
        },
    ).to_public_dict()

    memory = candidate["artifact_refs"]["memory_snapshot_refs"]
    assert memory == {
        "memory_snapshot_ref": "memory:session-1:turn-12",
        "memory_snapshot_hash": memory["memory_snapshot_hash"],
        "session_id": "session-1",
        "allowed_fields": {
            "asset_focus": ["BTC", "ETH"],
            "preferred_horizon": "4h",
            "risk_preference": "low",
            "user_position": "flat",
        },
        "allowed_field_names": ["asset_focus", "preferred_horizon", "risk_preference", "user_position"],
        "recent_turn_count": 5,
        "summary_hash": memory["summary_hash"],
        "long_term_memory_refs": [
            {"memory_id": "mem-1", "memory_hash": "sha256:mem-1", "score": 0.82}
        ],
    }
    assert memory["memory_snapshot_hash"].startswith("sha256:")
    assert memory["summary_hash"].startswith("sha256:")
    assert candidate["coverage"]["has_memory_snapshot_refs"] is True
    serialized = str(candidate)
    assert "raw user conversation must not be copied" not in serialized
    assert "raw conversation must not be copied" not in serialized
    assert "secret must not be copied" not in serialized
    assert "'messages'" not in serialized
    assert "raw_conversation" not in serialized
    assert "api_key" not in serialized


def test_replayable_input_candidate_quarantines_memory_market_facts():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
        },
        shadow_swarm_audit={"lead_plan": {"plan_id": "shadow:trace-1"}, "worker_results": []},
        observed_run_artifacts={
            "memory_snapshot": {
                "snapshot_id": "memory:session-1:turn-13",
                "session_id": "session-1",
                "allowed_fields": {
                    "risk_preference": "low",
                    "asset_focus": ["ETH"],
                    "mark": 3500.5,
                    "funding": "0.08%",
                    "open_interest": 123456,
                    "news_status": "ETF headline still active",
                    "macro_event_status": "CPI surprise pending",
                    "last_model_conclusion": "trigger long now",
                    "previous_final_action": "open long",
                },
                "recent_turn_count": 6,
            }
        },
    ).to_public_dict()

    memory = candidate["artifact_refs"]["memory_snapshot_refs"]

    assert memory["allowed_fields"] == {
        "asset_focus": ["ETH"],
        "risk_preference": "low",
    }
    assert memory["allowed_field_names"] == ["asset_focus", "risk_preference"]
    assert memory["quarantined_fields"] == [
        "allowed_fields.funding",
        "allowed_fields.last_model_conclusion",
        "allowed_fields.macro_event_status",
        "allowed_fields.mark",
        "allowed_fields.news_status",
        "allowed_fields.open_interest",
        "allowed_fields.previous_final_action",
    ]
    assert memory["memory_warnings"] == [
        "memory_snapshot.quarantined_fact_like_fields: memory is context only, not live market evidence"
    ]
    serialized = str(memory)
    assert "3500.5" not in serialized
    assert "ETF headline still active" not in serialized
    assert "trigger long now" not in serialized


def test_replayable_input_candidate_marks_incomplete_worker_manifest():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
            "evidence_refs": [],
            "lead_synthesis": {"included_contribution_ids": [], "dropped_contributions": []},
        },
        shadow_swarm_audit={
            "lead_plan": {"plan_id": "shadow:trace-1"},
            "worker_results": [
                {
                    "task_id": "shadow:RootCauseAgent",
                    "agent_name": "RootCauseAgent",
                    "status": "ok",
                    "contribution": {
                        "contribution_id": "c-root",
                        "input_ref": "trace:trace-1:shadow_swarm_input",
                    },
                }
            ],
        },
    )

    public = candidate.to_public_dict()

    assert public["coverage"]["worker_manifest_count"] == 1
    assert public["coverage"]["worker_manifest_complete"] is False
    assert public["coverage"]["worker_manifest_missing_fields"] == [
        {
            "task_id": "shadow:RootCauseAgent",
            "agent_name": "RootCauseAgent",
            "missing_fields": ["agent_run_request_hash", "output_hash", "trace_ref", "failure_policy_applied"],
        }
    ]


def test_replayable_input_candidate_worker_manifest_records_required_from_result_envelope():
    candidate = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={
            "input_ref": "trace:trace-1:decision_input_candidate",
            "input_hash": "sha256:decision",
            "evidence_refs": [],
            "lead_synthesis": {"included_contribution_ids": [], "dropped_contributions": []},
        },
        shadow_swarm_audit={
            "lead_plan": {"plan_id": "shadow:trace-1"},
            "worker_results": [
                {
                    "task_id": "shadow:DataQualityAgent",
                    "agent_name": "DataQualityAgent",
                    "status": "failed",
                    "trace_ref": "trace-1:shadow:DataQualityAgent",
                    "failure_policy_applied": "hard_block",
                    "required": True,
                    "contribution": {
                        "contribution_id": "c-quality",
                        "output_hash": "sha256:quality",
                        "input_ref": "trace:trace-1:shadow_swarm_input",
                        "trace_ref": "trace-1:shadow:DataQualityAgent",
                        "failure_policy_applied": "hard_block",
                        "required": False,
                    },
                    "agent_run_result": {
                        "task_id": "shadow:DataQualityAgent",
                        "agent_name": "DataQualityAgent",
                        "status": "failed",
                        "contribution_ref": "trace:trace-1:shadow_swarm_input",
                        "input_view_hash": "sha256:input-view",
                        "agent_run_request_hash": "sha256:request",
                        "output_hash": "sha256:quality",
                        "trace_ref": "trace-1:shadow:DataQualityAgent",
                        "failure_policy_applied": "hard_block",
                        "required": True,
                        "decision_effect": "none",
                        "error": {"type": "TimeoutError"},
                    },
                }
            ],
        },
    )

    manifest_item = candidate.to_public_dict()["artifact_refs"]["worker_result_manifest"][0]
    assert manifest_item["required"] is True
    assert manifest_item["failure_policy_applied"] == "hard_block"
    assert manifest_item["agent_run_result"]["required"] is True
    assert "error" not in manifest_item
    assert "error" not in manifest_item["agent_run_result"]


def test_replayable_input_candidate_worker_input_hash_changes_with_input_view_without_copying_it():
    base_worker_result = {
        "task_id": "shadow:RootCauseAgent",
        "agent_name": "RootCauseAgent",
        "status": "ok",
        "trace_ref": "trace-1:shadow:RootCauseAgent",
        "failure_policy_applied": "none",
        "error": None,
        "contribution": {
            "contribution_id": "c-root",
            "output_hash": "sha256:root",
            "input_ref": "trace:trace-1:shadow_swarm_input",
            "trace_ref": "trace-1:shadow:RootCauseAgent",
            "failure_policy_applied": "none",
            "constraints": {},
        },
        "agent_run_result": {
            "task_id": "shadow:RootCauseAgent",
            "agent_name": "RootCauseAgent",
            "status": "ok",
            "contribution_ref": "trace:trace-1:shadow_swarm_input",
            "output_hash": "sha256:root",
            "trace_ref": "trace-1:shadow:RootCauseAgent",
            "failure_policy_applied": "none",
            "decision_effect": "none",
            "input_view_hash": "sha256:input-view-a",
                "agent_run_request_hash": "sha256:request-a",
                "input_view": {"raw": "raw worker input must not be copied"},
            },
        }
    changed_worker_result = {
        **base_worker_result,
        "agent_run_result": {
            **base_worker_result["agent_run_result"],
            "input_view_hash": "sha256:input-view-b",
            "agent_run_request_hash": "sha256:request-b",
        },
    }

    first = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={"input_ref": "trace:1:decision", "input_hash": "sha256:decision"},
        shadow_swarm_audit={
            "lead_plan": {"plan_id": "shadow:trace-1"},
            "worker_results": [base_worker_result],
        },
    ).to_public_dict()
    second = build_replayable_input_candidate(
        trace_id="trace-1",
        frozen_input_hash="abc123",
        decision_input_candidate={"input_ref": "trace:1:decision", "input_hash": "sha256:decision"},
        shadow_swarm_audit={
            "lead_plan": {"plan_id": "shadow:trace-1"},
            "worker_results": [changed_worker_result],
        },
    ).to_public_dict()

    first_manifest = first["artifact_refs"]["worker_result_manifest"][0]
    second_manifest = second["artifact_refs"]["worker_result_manifest"][0]
    assert first_manifest["input_hash"] == "sha256:input-view-a"
    assert first_manifest["agent_run_request_hash"] == "sha256:request-a"
    assert second_manifest["input_hash"] == "sha256:input-view-b"
    assert second_manifest["agent_run_request_hash"] == "sha256:request-b"
    assert first_manifest["input_hash"] != second_manifest["input_hash"]
    serialized = str(first) + str(second)
    assert "raw worker input must not be copied" not in serialized
