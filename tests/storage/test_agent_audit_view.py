from __future__ import annotations

import json

from crypto_manual_alert.storage.agent_audit_view import build_agent_audit_view


def test_agent_audit_view_projects_stable_fields_without_raw_payloads():
    payload = {
        "trace_id": "trace-1",
        "raw_decision": "raw completion must never leak",
        "frozen_input": {"full_prompt": "raw prompt must never leak"},
        "shadow_swarm_audit": {
            "mode": "shadow",
            "decision_effect": "none",
            "lead_plan": {
                "plan_id": "lead-plan-1",
                "tasks": [
                    {
                        "task_id": "shadow:ExecutionRiskAgent",
                        "agent_name": "ExecutionRiskAgent",
                        "role": "execution_risk",
                        "required": True,
                        "requested_tools": ["risk_check"],
                        "input_ref": "trace-1:shadow_swarm_input",
                    }
                ],
            },
            "worker_results": [
                {
                    "agent_name": "ExecutionRiskAgent",
                    "task_id": "shadow:ExecutionRiskAgent",
                    "status": "ok",
                    "required": True,
                    "trace_ref": "trace-1:shadow:ExecutionRiskAgent",
                    "contribution": {
                        "summary": "execution risk hard block",
                        "claims": [{"claim": "entry is blocked"}],
                        "conflicts": ["missing_execution_fact:mark"],
                        "missing_facts": ["mark"],
                        "constraints": {
                            "hard_block": True,
                            "hard_block_reasons": ["missing mark"],
                            "blocked_actions": ["trigger long"],
                            "required_confirmations": ["confirm mark"],
                            "tool_audit_results": [
                                {
                                    "tool_name": "risk_check",
                                    "status": "ok",
                                    "summary": "checked",
                                    "error_message": "legacy tool error must not leak",
                                }
                            ],
                        },
                    },
                }
            ],
            "lead_synthesis": {
                "included_contribution_ids": ["shadow_swarm:shadow:ExecutionRiskAgent"],
                "conflicts": ["missing_execution_fact:mark"],
                "missing_facts": ["mark"],
            },
            "harness_validation": {"passed": True, "violations": []},
        },
        "facts_gate": {"passed": False, "missing_execution_facts": ["mark"]},
        "harness_validation": {"passed": True},
        "evidence_packets": [{"id": "packet-1"}, {"id": "packet-2"}],
        "pre_final_decision_input": {
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "input_ref": "trace:trace-1:pre_final_decision_input",
            "input_hash": "sha256:input",
            "validation": {"passed": False},
            "missing_facts": ["mark"],
            "conflicts": ["missing_execution_fact:mark"],
            "effective_allowed_actions": ["no_trade"],
        },
        "gate_candidate": {"passed": False, "violations": [{"rule_id": "gate.block"}]},
        "final_decision_switch_readiness": {"ready": False, "reasons": ["review_required"]},
        "final_input_selection": {"mode": "legacy_prompt", "source_ref": "legacy_prompt_packet"},
        "legacy_prompt_lifecycle": {"status": "legacy_primary_until_switch_review"},
        "production_control_gate": {
            "allowed": False,
            "reasons": ["worker contribution reported a hard block"],
        },
        "symbol_consistency": {
            "request_symbol": "BTC-USDT-SWAP",
            "snapshot_symbol": "BTC-USDT-SWAP",
            "plan_instrument": "ETH-USDT-SWAP",
            "consistent": False,
        },
        "run_context": {
            "query_text": "assess ETH manually",
            "query_semantics": {
                "mode": "audit_note",
                "drives_lead_plan": False,
                "drives_worker_selection": False,
                "drives_tool_budget": False,
                "drives_facts_requirement": False,
                "drives_final_input": False,
            },
        },
        "replayable_input_candidate": {
            "input_ref": "candidate:replayable_input",
            "artifact_refs": {"shadow_workers": [{"agent_name": "ExecutionRiskAgent"}]},
        },
    }

    view = build_agent_audit_view(payload)

    assert view["available"] is True
    assert view["lead_plan"]["plan_id"] == "lead-plan-1"
    assert view["lead_plan"]["tasks"][0]["agent_name"] == "ExecutionRiskAgent"
    assert view["workers"][0]["hard_block"] is True
    assert view["workers"][0]["claim_count"] == 1
    assert "tool_audit_results" not in view["workers"][0]
    assert view["decision_input"]["input_hash"] == "sha256:input"
    assert view["query_semantics"]["mode"] == "audit_note"
    assert view["query_semantics"]["drives_final_input"] is False
    assert view["symbol_consistency"] == {
        "request_symbol": "BTC-USDT-SWAP",
        "snapshot_symbol": "BTC-USDT-SWAP",
        "plan_instrument": "ETH-USDT-SWAP",
        "consistent": False,
    }
    assert view["gates"]["production_control_gate"]["allowed"] is False
    assert view["replay_refs"]["input_ref"] == "candidate:replayable_input"
    assert "shadow_swarm_audit" in view["source_payload_keys"]
    rendered = json.dumps(view, ensure_ascii=False)
    assert "raw completion must never leak" not in rendered
    assert "raw prompt must never leak" not in rendered
    assert "raw_decision" not in rendered
    assert "frozen_input" not in rendered
    assert "legacy tool error must not leak" not in rendered


def test_agent_audit_view_projects_worker_tool_call_artifact_refs_without_raw_payloads():
    payload = {
        "trace_id": "trace-tool",
        "shadow_swarm_audit": {
            "mode": "shadow",
            "lead_plan": {"plan_id": "lead-plan-tool", "tasks": []},
            "worker_results": [
                {
                    "agent_name": "RootCauseAgent",
                    "task_id": "shadow:RootCauseAgent",
                    "status": "ok",
                    "required": True,
                    "trace_ref": "trace-tool:shadow:RootCauseAgent",
                    "contribution": {
                        "summary": "root cause checked",
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
                                "raw_payload": "raw tool payload must not leak",
                                "snippet": "raw snippet must not leak",
                                "error": {"message": "raw error must not leak"},
                            }
                        ],
                    },
                }
            ],
        },
        "pre_final_decision_input": {
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "input_ref": "trace:trace-tool:pre_final_decision_input",
        },
    }

    view = build_agent_audit_view(payload)

    worker = view["workers"][0]
    assert worker["tool_call_artifact_count"] == 1
    assert worker["tool_call_artifact_refs"] == [
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
    rendered = json.dumps(view, ensure_ascii=False)
    assert "raw tool payload must not leak" not in rendered
    assert "raw snippet must not leak" not in rendered
    assert "raw error must not leak" not in rendered
    assert "raw_payload" not in rendered
    assert "snippet" not in rendered


def test_agent_audit_view_projects_runtime_flow_from_span_tree_refs():
    payload = {
        "trace_id": "trace-flow",
        "shadow_swarm_audit": {
            "mode": "shadow",
            "lead_plan": {"plan_id": "lead-plan-flow", "tasks": []},
            "worker_results": [],
        },
        "pre_final_decision_input": {
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "input_ref": "trace:trace-flow:pre_final_decision_input",
        },
        "replayable_input_candidate": {
            "artifact_refs": {
                "span_tree_refs": {
                    "span_tree_ref": "trace:trace-flow:span_tree",
                    "span_tree_hash": "sha256:span-tree",
                    "span_refs": [
                        {
                            "span_id": "span-market",
                            "parent_span_id": None,
                            "span_name": "market.fetch",
                            "span_type": "market.fetch",
                            "status": "ok",
                            "duration_ms": 12,
                            "span_input_hash": "sha256:input",
                            "input_refs": {"symbol": "BTC-USDT-SWAP"},
                            "span_output_hash": "sha256:output",
                            "output_refs": {"bundle_ref": "trace:trace-flow:market_bundle"},
                        },
                        {
                            "span_id": "span-worker",
                            "parent_span_id": None,
                            "span_name": "shadow_swarm.worker",
                            "span_type": "agent.worker",
                            "status": "ok",
                            "duration_ms": 4,
                        },
                    ],
                    "parent_complete": True,
                }
            }
        },
    }

    view = build_agent_audit_view(payload)

    assert view["runtime_flow"] == [
        {
            "name": "market.fetch",
            "owner": "market.fetch",
            "effect": "runtime span executed",
            "status": "ok",
            "duration_ms": 12,
            "span_id": "span-market",
            "parent_span_id": None,
            "span_input_hash": "sha256:input",
            "input_refs": {"symbol": "BTC-USDT-SWAP"},
            "span_output_hash": "sha256:output",
            "output_refs": {"bundle_ref": "trace:trace-flow:market_bundle"},
            "source": "span_tree_refs",
            "span_tree_ref": "trace:trace-flow:span_tree",
        },
        {
            "name": "shadow_swarm.worker",
            "owner": "agent.worker",
            "effect": "runtime span executed",
            "status": "ok",
            "duration_ms": 4,
            "span_id": "span-worker",
            "parent_span_id": None,
            "source": "span_tree_refs",
            "span_tree_ref": "trace:trace-flow:span_tree",
        },
    ]


def test_agent_audit_view_projects_full_chain_observability_fields_without_raw_payloads():
    payload = {
        "trace_id": "trace-observable",
        "shadow_swarm_audit": {
            "mode": "shadow",
            "lead_plan": {"plan_id": "lead-plan-observable", "tasks": []},
            "worker_results": [
                {
                    "agent_name": "RootCauseAgent",
                    "task_id": "shadow:RootCauseAgent",
                    "status": "ok",
                    "required": True,
                    "trace_ref": "trace-observable:shadow:RootCauseAgent",
                    "contribution": {
                        "summary": "root cause checked",
                        "claims": [{"claim": "macro surprise amplified by positioning"}],
                        "constraints": {
                            "root_cause_graph": [
                                {
                                    "node_id": "macro_event_surprise",
                                    "factor_type": "macro_event",
                                    "evidence_ids": ["e-macro"],
                                    "depends_on": [],
                                },
                                {
                                    "node_id": "derivatives_crowding_amplifier",
                                    "factor_type": "derivatives",
                                    "evidence_ids": ["e-oi"],
                                    "depends_on": ["macro_event_surprise"],
                                },
                            ]
                        },
                        "tool_call_artifact_refs": [
                            {
                                "tool_call_id": "tool-call-root",
                                "skill_name": "root_cause_search",
                                "status": "ok",
                                "source_type": "search_derived",
                                "source_tier": "external_search",
                                "retrieved_at": "2026-07-04T01:00:00Z",
                                "freshness_status": "fresh",
                                "result_ref": "skill:root_cause_search:trace-observable:1",
                                "output_hash": "sha256:root-tool",
                                "can_satisfy_execution_fact": False,
                                "result_count": 3,
                                "snippet": "raw snippet must not leak",
                            }
                        ],
                    },
                },
                {
                    "agent_name": "ExecutionRiskAgent",
                    "task_id": "shadow:ExecutionRiskAgent",
                    "status": "ok",
                    "required": True,
                    "trace_ref": "trace-observable:shadow:ExecutionRiskAgent",
                    "contribution": {
                        "summary": "execution fact checked",
                        "conflicts": ["mark must be exchange native"],
                        "tool_call_artifact_refs": [
                            {
                                "tool_call_id": "tool-call-order-book",
                                "skill_name": "liquidity_order_book",
                                "status": "ok",
                                "source_type": "exchange_native",
                                "source_tier": "exchange",
                                "retrieved_at": "2026-07-04T01:00:05Z",
                                "freshness_status": "fresh",
                                "result_ref": "skill:liquidity_order_book:trace-observable:1",
                                "output_hash": "sha256:book-tool",
                                "can_satisfy_execution_fact": True,
                            }
                        ],
                    },
                },
            ],
            "lead_synthesis": {
                "counter_thesis": ["spot bid may fade if ETF flow is already priced in"],
                "strongest_counter_thesis_ref": "counter:priced_in_etf_flow",
                "conflict_refs": [
                    {
                        "worker_a": "RootCauseAgent",
                        "worker_b": "ExecutionRiskAgent",
                        "claim_ref": "claim:macro_event_surprise",
                        "conflict_type": "source_quality",
                        "severity": "medium",
                    }
                ],
            },
        },
        "facts_gate": {"passed": False, "missing_execution_facts": ["index"]},
        "evidence_packets": [
            {
                "evidence_id": "e-mark",
                "name": "mark",
                "data_type": "mark",
                "source_type": "exchange_native",
                "source_tier": 1,
                "source_name": "okx_public",
                "source_url": None,
                "observed_at": "2026-07-04T01:00:01+00:00",
                "retrieved_at": "2026-07-04T01:00:02+00:00",
                "freshness_status": "fresh",
                "can_satisfy_execution_fact": True,
                "raw_value": "raw price must not leak",
            },
            {
                "evidence_id": "e-macro",
                "name": "macro_context",
                "data_type": "news",
                "source_type": "search_derived",
                "source_tier": 4,
                "source_name": "search",
                "source_url": "https://example.test/macro",
                "observed_at": None,
                "retrieved_at": "2026-07-04T01:00:03+00:00",
                "freshness_status": "unknown",
                "can_satisfy_execution_fact": False,
                "value": {"snippet": "raw research value must not leak"},
            },
        ],
        "pre_final_decision_input": {
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "input_ref": "trace:trace-observable:pre_final_decision_input",
            "input_hash": "sha256:decision-input",
        },
        "candidate_final_decision": {
            "artifact_type": "candidate_final_decision",
            "mode": "candidate_final_sidecar",
            "decision_effect": "none",
            "production_final_input": False,
            "input_ref": "trace:trace-observable:pre_final_decision_input",
            "input_hash": "sha256:decision-input",
            "input_gate_passed": True,
            "raw_candidate_decision": '{"main_action":"no trade","probability":0.4}',
            "error": None,
        },
        "parsed_plan": {"main_action": "trigger long", "probability": 0.62},
        "verdict": {"allowed": False},
        "final_input_selection": {
            "mode": "legacy_prompt",
            "source_ref": "legacy_prompt_packet",
            "decision_effect": "production_final_input",
        },
        "production_control_gate": {"allowed": False, "reasons": ["worker hard block"]},
        "final_decision_switch_readiness": {"ready": False, "reasons": ["review_required"]},
    }

    view = build_agent_audit_view(payload)

    assert view["tool_calls"] == [
        {
            "worker": "RootCauseAgent",
            "task_id": "shadow:RootCauseAgent",
            "tool_call_id": "tool-call-root",
            "skill_name": "root_cause_search",
            "status": "ok",
            "source_type": "search_derived",
            "source_tier": "external_search",
            "retrieved_at": "2026-07-04T01:00:00Z",
            "freshness_status": "fresh",
            "result_ref": "skill:root_cause_search:trace-observable:1",
            "output_hash": "sha256:root-tool",
            "can_satisfy_execution_fact": False,
            "result_count": 3,
        },
        {
            "worker": "ExecutionRiskAgent",
            "task_id": "shadow:ExecutionRiskAgent",
            "tool_call_id": "tool-call-order-book",
            "skill_name": "liquidity_order_book",
            "status": "ok",
            "source_type": "exchange_native",
            "source_tier": "exchange",
            "retrieved_at": "2026-07-04T01:00:05Z",
            "freshness_status": "fresh",
            "result_ref": "skill:liquidity_order_book:trace-observable:1",
            "output_hash": "sha256:book-tool",
            "can_satisfy_execution_fact": True,
        },
    ]
    assert view["evidence_sources"] == [
        {
            "evidence_ref": "e-mark",
            "claim_ref": "market:mark",
            "source_url": None,
            "source_type": "exchange_native",
            "source_tier": 1,
            "observed_at": "2026-07-04T01:00:01+00:00",
            "retrieved_at": "2026-07-04T01:00:02+00:00",
            "freshness_status": "fresh",
            "can_satisfy_execution_fact": True,
        },
        {
            "evidence_ref": "e-macro",
            "claim_ref": "research:macro_context",
            "source_url": "https://example.test/macro",
            "source_type": "search_derived",
            "source_tier": 4,
            "observed_at": None,
            "retrieved_at": "2026-07-04T01:00:03+00:00",
            "freshness_status": "unknown",
            "can_satisfy_execution_fact": False,
        },
    ]
    assert {
        "source_type": "exchange_native",
        "source_tier": 1,
        "freshness_status": "fresh",
        "count": 1,
        "can_satisfy_execution_fact_count": 1,
    } in view["source_freshness"]
    assert view["root_cause_graph"] == {
        "nodes": [
            {
                "node_id": "macro_event_surprise",
                "worker": "RootCauseAgent",
                "layer": 0,
                "factor_type": "macro_event",
                "evidence_refs": ["e-macro"],
            },
            {
                "node_id": "derivatives_crowding_amplifier",
                "worker": "RootCauseAgent",
                "layer": 1,
                "factor_type": "derivatives",
                "evidence_refs": ["e-oi"],
            },
        ],
        "edges": [
            {
                "from": "macro_event_surprise",
                "to": "derivatives_crowding_amplifier",
                "worker": "RootCauseAgent",
            }
        ],
    }
    assert view["conflict_edges"] == [
        {
            "worker_a": "RootCauseAgent",
            "worker_b": "ExecutionRiskAgent",
            "claim_ref": "claim:macro_event_surprise",
            "conflict_type": "source_quality",
            "severity": "medium",
        }
    ]
    assert view["strongest_counter_thesis_ref"] == "counter:priced_in_etf_flow"
    assert view["input_lineage"]["production_final_input_mode"] == "legacy_prompt"
    assert view["input_lineage"]["decision_input"]["decision_effect"] == "none"
    assert view["release_eval_gate"]["structural_gate"]["ready"] is False
    assert view["release_eval_gate"]["financial_quality_gate"]["status"] == "not_configured"
    rendered = json.dumps(view, ensure_ascii=False)
    assert "raw price must not leak" not in rendered
    assert "raw research value must not leak" not in rendered
    assert "raw snippet must not leak" not in rendered


def test_agent_audit_view_is_unavailable_when_payload_has_no_agent_audit():
    view = build_agent_audit_view({"trace_id": "trace-1", "parsed_plan": {"main_action": "hold"}})

    assert view == {"available": False, "reason": "agent_audit_payload_missing"}


def test_agent_audit_view_projects_controlled_shadow_without_raw_payloads():
    payload = {
        "trace_id": "trace-controlled",
        "raw_decision": "raw completion must never leak",
        "controlled_shadow": {
            "mode": "controlled_shadow",
            "audit_only": True,
            "production_final_input": False,
            "notification_input": False,
            "reason": "controlled shadow mode records audit only",
            "raw_decision": "controlled raw must never leak",
        },
        "shadow_swarm_audit": {
            "mode": "shadow",
            "lead_plan": {"plan_id": "lead-plan-1", "tasks": []},
            "worker_results": [],
        },
        "pre_final_decision_input": {
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "input_ref": "trace:trace-controlled:pre_final_decision_input",
        },
        "run_context": {
            "query_text": "controlled audit query",
            "query_semantics": {
                "mode": "audit_note",
                "drives_lead_plan": False,
                "drives_worker_selection": False,
                "drives_tool_budget": False,
                "drives_facts_requirement": False,
                "drives_final_input": False,
            },
        },
    }

    view = build_agent_audit_view(payload)

    assert view["available"] is True
    assert view["mode"] == "controlled_shadow"
    assert view["controlled_shadow"] == {
        "mode": "controlled_shadow",
        "audit_only": True,
        "production_final_input": False,
        "notification_input": False,
        "reason": "controlled shadow mode records audit only",
    }
    assert view["query_semantics"]["mode"] == "audit_note"
    rendered = json.dumps(view, ensure_ascii=False)
    assert "raw completion must never leak" not in rendered
    assert "controlled raw must never leak" not in rendered
    assert "raw_decision" not in rendered


def test_agent_audit_view_projects_sanitized_candidate_final_comparison():
    payload = {
        "trace_id": "trace-candidate",
        "shadow_swarm_audit": {
            "mode": "shadow",
            "lead_plan": {"plan_id": "lead-plan-1", "tasks": []},
            "worker_results": [],
        },
        "pre_final_decision_input": {
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "input_ref": "trace:trace-candidate:pre_final_decision_input",
            "input_hash": "sha256:candidate-input",
        },
        "parsed_plan": {
            "main_action": "trigger long",
            "probability": 0.67,
        },
        "verdict": {"allowed": False},
        "production_control_gate": {
            "allowed": False,
            "reasons": ["production_control.candidate.action_not_allowed"],
            "rule_hits": [
                {
                    "rule_id": "production_control.candidate.action_not_allowed",
                    "blocking": True,
                }
            ],
        },
        "candidate_final_decision": {
            "artifact_type": "candidate_final_decision",
            "mode": "candidate_final_sidecar",
            "decision_effect": "none",
            "production_final_input": False,
            "input_ref": "trace:trace-candidate:pre_final_decision_input",
            "input_hash": "sha256:candidate-input",
            "input_gate_passed": True,
            "raw_candidate_decision": (
                '{"main_action":"no trade","probability":0.41,'
                '"manual_execution_required":true}'
            ),
            "error": None,
        },
        "final_input_selection": {
            "mode": "legacy_prompt",
            "source_ref": "legacy_prompt_packet",
            "decision_effect": "production_final_input",
        },
    }

    view = build_agent_audit_view(payload)

    comparison = view["candidate_final_comparison"]
    assert comparison["decision_effect"] == "none"
    assert comparison["production_final_input"] is False
    assert comparison["status"] == "audit_only"
    assert comparison["legacy"] == {
        "action": "trigger long",
        "probability": 0.67,
        "allowed": False,
    }
    assert comparison["candidate"] == {
        "input_ref": "trace:trace-candidate:pre_final_decision_input",
        "input_hash": "sha256:candidate-input",
        "action": "no trade",
        "probability": 0.41,
        "allowed": True,
        "error": None,
    }
    assert comparison["diff"] == {
        "action_changed": True,
        "probability_delta": -0.26,
    }
    assert comparison["production_control_gate"] == {
        "allowed": False,
        "reasons": ["production_control.candidate.action_not_allowed"],
        "blocking_rule_ids": ["production_control.candidate.action_not_allowed"],
    }
    rendered = json.dumps(view, ensure_ascii=False)
    assert "raw_candidate_decision" not in rendered
    assert '"main_action":"no trade"' not in rendered


def test_agent_audit_view_projects_candidate_final_diagnosis_for_gate_failure():
    payload = {
        "trace_id": "trace-candidate-failed",
        "shadow_swarm_audit": {
            "mode": "shadow",
            "lead_plan": {"plan_id": "lead-plan-1", "tasks": []},
            "worker_results": [],
        },
        "pre_final_decision_input": {
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "input_ref": "trace:trace-candidate-failed:pre_final_decision_input",
            "input_hash": "sha256:candidate-input",
        },
        "parsed_plan": {"main_action": "no trade", "probability": 0.0},
        "verdict": {"allowed": False},
        "candidate_final_decision": {
            "artifact_type": "candidate_final_decision",
            "mode": "candidate_final_sidecar",
            "decision_effect": "none",
            "production_final_input": False,
            "input_ref": "trace:trace-candidate-failed:pre_final_decision_input",
            "input_hash": "sha256:candidate-input",
            "input_gate_passed": False,
            "raw_candidate_decision": None,
            "error": {"type": "input_gate_failed"},
            "diagnosis": {
                "summary": "candidate final sidecar blocked by input gate",
                "blocking_reasons": ["pre_final_input.validation_failed"],
            },
        },
    }

    comparison = build_agent_audit_view(payload)["candidate_final_comparison"]

    assert comparison["candidate"]["diagnosis"] == {
        "summary": "candidate final sidecar blocked by input gate",
        "blocking_reasons": ["pre_final_input.validation_failed"],
    }
