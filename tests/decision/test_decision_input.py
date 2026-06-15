from __future__ import annotations

import json

from crypto_manual_alert.decision.decision_input import build_decision_input_candidate, build_pre_final_decision_input


def test_decision_input_candidate_blocks_executable_actions_when_execution_facts_are_missing():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[
            {
                "evidence_id": "ev-search-mark",
                "name": "mark",
                "symbol": "ETH-USDT-SWAP",
                "data_type": "mark",
                "value": 3500,
                "source_type": "search_derived",
                "freshness_status": "unknown",
                "can_satisfy_execution_fact": False,
                "confidence_cap": 0.58,
                "claims": ["raw snippet must not enter candidate"],
            },
            {
                "evidence_id": "ev-news",
                "name": "macro_context",
                "symbol": "ETH-USDT-SWAP",
                "data_type": "news",
                "value": {"snippet": "raw news body must not enter candidate"},
                "source_type": "search_derived",
                "freshness_status": "unknown",
                "can_satisfy_execution_fact": False,
                "confidence_cap": 0.58,
                "claims": ["ETF flow improved"],
            },
        ],
        facts_gate={
            "passed": False,
            "severity": "hard_fail",
            "missing_execution_facts": ["index", "mark", "order_book"],
            "blocked_action_classes": ["opening", "trigger", "flip"],
            "reasons": ["mark: present but not execution fact source; source_types=search_derived"],
        },
        agent_contributions=[
            {
                "contribution_id": "shadow_swarm:RootCauseAgent",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "required": True,
                "summary": "ETF flow is the likely root driver.",
                "claims": [{"claim": "ETF flow improved", "evidence_ids": ["ev-news"]}],
                "constraints": {"decision_effect": "none"},
                "conflicts": [],
                "missing_facts": [],
            },
            {
                "contribution_id": "shadow_swarm:DataQualityAgent",
                "agent_name": "DataQualityAgent",
                "status": "failed",
                "required": True,
                "summary": "worker failed",
                "claims": [],
                "constraints": {},
                "conflicts": ["worker_timeout"],
                "missing_facts": ["order_book"],
            },
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["shadow_swarm:RootCauseAgent"],
            "dropped_contributions": [
                {
                    "contribution_id": "shadow_swarm:DataQualityAgent",
                    "agent_name": "DataQualityAgent",
                    "reason": "status=failed",
                },
                {
                    "contribution_id": None,
                    "agent_name": "MarketSentimentAgent",
                    "reason": "missing_required_contribution",
                },
                {
                    "contribution_id": None,
                    "agent_name": "ExecutionRiskAgent",
                    "reason": "missing_required_contribution",
                },
            ],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": ["worker_timeout"],
            "missing_facts": ["order_book", "MarketSentimentAgent", "ExecutionRiskAgent"],
        },
        legacy_plan={"main_action": "trigger long", "probability": 0.67},
        verdict={"allowed": False, "reasons": ["missing execution facts"]},
    )

    public = candidate.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["input_ref"] == "trace:trace-1:decision_input_candidate"
    assert public["symbol"] == "ETH-USDT-SWAP"
    assert "trigger long" not in public["effective_allowed_actions"]
    assert "open long" not in public["effective_allowed_actions"]
    assert "flip long to short" not in public["effective_allowed_actions"]
    assert "no trade" in public["effective_allowed_actions"]
    assert public["confidence_policy"]["max_probability"] == 0.58
    assert set(public["missing_facts"]) >= {"index", "mark", "order_book"}
    assert public["lead_synthesis"]["included_contribution_ids"] == ["shadow_swarm:RootCauseAgent"]
    assert {
        (item["contribution_id"], item["agent_name"], item["reason"])
        for item in public["lead_synthesis"]["dropped_contributions"]
    } >= {
        ("shadow_swarm:DataQualityAgent", "DataQualityAgent", "status=failed"),
        (None, "MarketSentimentAgent", "missing_required_contribution"),
        (None, "ExecutionRiskAgent", "missing_required_contribution"),
    }
    assert "worker_timeout" in public["lead_synthesis"]["conflicts"]
    assert public["evidence_refs"] == [
        {
            "evidence_id": "ev-search-mark",
            "data_type": "mark",
            "source_type": "search_derived",
            "freshness_status": "unknown",
            "can_satisfy_execution_fact": False,
            "confidence_cap": 0.58,
        },
        {
            "evidence_id": "ev-news",
            "data_type": "news",
            "source_type": "search_derived",
            "freshness_status": "unknown",
            "can_satisfy_execution_fact": False,
            "confidence_cap": 0.58,
        },
    ]
    serialized = str(public)
    assert "raw snippet must not enter candidate" not in serialized
    assert "raw news body must not enter candidate" not in serialized
    assert public["validation"]["passed"] is False
    assert public["validation"]["severity"] == "hard_fail"
    assert {
        violation["rule_id"] for violation in public["validation"]["violations"]
    } >= {
        "decision_input.facts_gate_hard_fail",
        "decision_input.required_worker_missing_or_failed",
    }


def test_decision_input_candidate_uses_run_lead_plan_required_agents_for_synthesis():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "root-ok",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "required": True,
                "summary": "Root cause is covered.",
                "claims": [],
                "constraints": {},
                "conflicts": [],
                "missing_facts": [],
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["root-ok"],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["lead_synthesis"]["included_contribution_ids"] == ["root-ok"]
    assert public["lead_synthesis"]["dropped_contributions"] == []
    assert public["missing_facts"] == []
    assert public["validation"]["passed"] is True


def test_decision_input_contribution_refs_keep_business_projection_fields():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "shadow_swarm:shadow:ExecutionRiskAgent",
                "agent_name": "ExecutionRiskAgent",
                "task_id": "shadow:ExecutionRiskAgent",
                "status": "ok",
                "required": True,
                "summary": "execution risk blocks opening",
                "claims": [{"claim": "order book missing", "evidence_ids": ["ev-order-book"]}],
                "constraints": {},
                "conflicts": [],
                "missing_facts": [],
                "input_ref": "trace:1:shadow_input",
                "output_hash": "sha256:execution",
                "trace_ref": "trace-1:shadow:ExecutionRiskAgent",
                "evidence_ids": ["ev-order-book"],
                "confidence_cap": 0.55,
                "blocked_actions": ["open long", "trigger long"],
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["shadow_swarm:shadow:ExecutionRiskAgent"],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["contribution_refs"] == [
        {
            "contribution_id": "shadow_swarm:shadow:ExecutionRiskAgent",
            "agent_name": "ExecutionRiskAgent",
            "task_id": "shadow:ExecutionRiskAgent",
            "status": "ok",
            "required": True,
            "output_hash": "sha256:execution",
            "input_ref": "trace:1:shadow_input",
            "trace_ref": "trace-1:shadow:ExecutionRiskAgent",
            "evidence_ids": ["ev-order-book"],
            "confidence_cap": 0.55,
            "confidence_cap_reasons": [],
            "blocked_actions": ["open long", "trigger long"],
            "hard_block": False,
            "hard_block_reasons": [],
            "manual_review_reminders": [],
            "allowed_action_class_reduction": {},
            "required_confirmations": [],
        }
    ]


def test_decision_input_contribution_refs_keep_sanitized_tool_call_artifact_refs():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "shadow_swarm:shadow:RootCauseAgent",
                "agent_name": "RootCauseAgent",
                "task_id": "shadow:RootCauseAgent",
                "status": "ok",
                "required": True,
                "summary": "root cause checked with search",
                "claims": [{"claim": "raw snippet must not enter decision input"}],
                "constraints": {},
                "conflicts": [],
                "missing_facts": [],
                "input_ref": "trace:1:shadow_input",
                "output_hash": "sha256:root",
                "trace_ref": "trace-1:shadow:RootCauseAgent",
                "tool_call_artifact_refs": [
                    {
                        "tool_call_id": "tool:trace-1:RootCauseAgent:realtime_search:1",
                        "skill_name": "realtime_search",
                        "status": "ok",
                        "source_type": "search_derived",
                        "source_tier": "search",
                        "retrieved_at": "2026-07-04T10:00:00+00:00",
                        "freshness_status": "fresh",
                        "result_ref": "skill_result:trace-1:RootCauseAgent:realtime_search:1",
                        "output_hash": "sha256:tool",
                        "can_satisfy_execution_fact": False,
                        "result_count": 1,
                        "error_type": None,
                        "error_message": "RAW ERROR MUST NOT ENTER DECISION INPUT",
                        "snippet": "RAW SNIPPET MUST NOT ENTER DECISION INPUT",
                        "evidence_candidates": [{"title": "raw"}],
                        "raw_payload": {"snippet": "raw"},
                    }
                ],
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["shadow_swarm:shadow:RootCauseAgent"],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    tool_refs = public["contribution_refs"][0]["tool_call_artifact_refs"]
    assert tool_refs == [
        {
            "tool_call_id": "tool:trace-1:RootCauseAgent:realtime_search:1",
            "skill_name": "realtime_search",
            "status": "ok",
            "source_type": "search_derived",
            "source_tier": "search",
            "retrieved_at": "2026-07-04T10:00:00+00:00",
            "freshness_status": "fresh",
            "result_ref": "skill_result:trace-1:RootCauseAgent:realtime_search:1",
            "output_hash": "sha256:tool",
            "can_satisfy_execution_fact": False,
            "result_count": 1,
        }
    ]
    serialized = json.dumps(public, ensure_ascii=False)
    assert "RAW ERROR" not in serialized
    assert "RAW SNIPPET" not in serialized
    assert "evidence_candidates" not in serialized
    assert "raw_payload" not in serialized


def test_pre_final_decision_input_contribution_refs_include_required_workers_and_safety_fields():
    required_workers = [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    contributions = [
        {
            "contribution_id": f"shadow_swarm:shadow:{agent_name}",
            "agent_name": agent_name,
            "task_id": f"shadow:{agent_name}",
            "status": "ok",
            "required": True,
            "summary": f"{agent_name} audit",
            "claims": [],
            "constraints": {
                "decision_effect": "none",
                "confidence_cap_reasons": [f"{agent_name}:cap_reason"],
                "hard_block": agent_name == "ExecutionRiskAgent",
                "hard_block_reasons": (
                    ["facts_gate:execution_facts_missing"]
                    if agent_name == "ExecutionRiskAgent"
                    else []
                ),
                "manual_review_reminders": [f"{agent_name}:manual_review"],
                "allowed_action_class_reduction": {
                    "remaining_action_classes": ["manual_review_only"],
                },
                "required_confirmations": [f"{agent_name}:confirmation"],
            },
            "conflicts": [],
            "missing_facts": [],
            "input_ref": "trace:trace-1:shadow_swarm_input",
            "output_hash": f"sha256:{agent_name}",
            "trace_ref": f"trace-1:shadow:{agent_name}",
            "evidence_ids": [f"ev:{agent_name}"],
            **({"confidence_cap": 0.55} if agent_name != "LiveFactAgent" else {}),
            "blocked_actions": ["open long"],
        }
        for agent_name in required_workers
    ]

    decision_input = build_pre_final_decision_input(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=contributions,
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [
                f"shadow_swarm:shadow:{agent_name}" for agent_name in required_workers
            ],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
    )

    refs = decision_input.to_public_dict()["contribution_refs"]

    assert [ref["agent_name"] for ref in refs] == required_workers
    for ref in refs:
        agent_name = ref["agent_name"]
        assert ref["task_id"] == f"shadow:{agent_name}"
        assert ref["evidence_ids"] == [f"ev:{agent_name}"]
        assert "confidence_cap" in ref
        assert ref["confidence_cap"] == (None if agent_name == "LiveFactAgent" else 0.55)
        assert ref["confidence_cap_reasons"] == [f"{agent_name}:cap_reason"]
        assert ref["blocked_actions"] == ["open long"]
        assert ref["hard_block"] is (agent_name == "ExecutionRiskAgent")
        assert ref["hard_block_reasons"] == (
            ["facts_gate:execution_facts_missing"]
            if agent_name == "ExecutionRiskAgent"
            else []
        )
        assert ref["manual_review_reminders"] == [f"{agent_name}:manual_review"]
        assert ref["allowed_action_class_reduction"] == {
            "remaining_action_classes": ["manual_review_only"],
        }
        assert ref["required_confirmations"] == [f"{agent_name}:confirmation"]
        assert ref["trace_ref"] == f"trace-1:shadow:{agent_name}"
        assert ref["output_hash"] == f"sha256:{agent_name}"


def test_pre_final_decision_input_fails_when_required_worker_refs_are_missing_without_drop_record():
    decision_input = build_pre_final_decision_input(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "shadow_swarm:shadow:RootCauseAgent",
                "agent_name": "RootCauseAgent",
                "task_id": "shadow:RootCauseAgent",
                "status": "ok",
                "required": True,
                "summary": "Root cause audit",
                "claims": [],
                "constraints": {"decision_effect": "none"},
                "conflicts": [],
                "missing_facts": [],
                "input_ref": "trace:trace-1:shadow_swarm_input",
                "output_hash": "sha256:root",
                "trace_ref": "trace-1:shadow:RootCauseAgent",
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["shadow_swarm:shadow:RootCauseAgent"],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
    )

    public = decision_input.to_public_dict()

    assert public["validation"]["passed"] is False
    missing = next(
        violation
        for violation in public["validation"]["violations"]
        if violation["rule_id"] == "decision_input.required_worker_refs_missing"
    )
    assert missing["missing_required_agents"] == [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]


def test_decision_input_confidence_policy_applies_facts_gate_soft_cap():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "soft_downgrade",
            "missing_execution_facts": [],
            "missing_auxiliary_facts": ["funding", "liquidation", "open_interest"],
            "blocked_action_classes": [],
            "reasons": ["funding: missing", "liquidation: missing", "open_interest: missing"],
            "confidence_cap": 0.58,
            "confidence_cap_reasons": ["facts_gate:derivatives_facts_missing"],
        },
        agent_contributions=[],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is True
    assert public["confidence_policy"]["max_probability"] == 0.58
    assert public["confidence_policy"]["cap_reasons"] == ["facts_gate:derivatives_facts_missing"]
    assert set(public["missing_facts"]) >= {"funding", "liquidation", "open_interest"}


def test_decision_input_confidence_policy_applies_fallback_source_cap():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[
            {
                "evidence_id": "ev-funding-fallback",
                "name": "funding",
                "symbol": "ETH-USDT-SWAP",
                "data_type": "funding",
                "source_type": "aggregator_api",
                "source_tier": 2,
                "freshness_status": "fresh",
                "can_satisfy_execution_fact": False,
                "fallback_used": True,
                "fallback_reason": "source_fallback:aggregator_api",
                "confidence_cap": 0.58,
            }
        ],
        facts_gate={
            "passed": True,
            "severity": "soft_downgrade",
            "missing_execution_facts": [],
            "missing_auxiliary_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
            "fallback_used": True,
            "fallback_source_types": ["aggregator_api"],
            "confidence_cap": 0.58,
            "confidence_cap_reasons": ["facts_gate:fallback_source_used"],
        },
        agent_contributions=[],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "trigger long", "probability": 0.59},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is True
    assert public["confidence_policy"]["max_probability"] == 0.58
    assert "facts_gate:fallback_source_used" in public["confidence_policy"]["cap_reasons"]
    assert public["evidence_refs"] == [
        {
            "evidence_id": "ev-funding-fallback",
            "data_type": "funding",
            "source_type": "aggregator_api",
            "freshness_status": "fresh",
            "can_satisfy_execution_fact": False,
            "confidence_cap": 0.58,
            "fallback_used": True,
            "fallback_reason": "source_fallback:aggregator_api",
            "source_tier": 2,
        }
    ]


def test_decision_input_inherits_event_status_stale_hard_block():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[
            {
                "evidence_id": "ev-stale-event",
                "name": "active_event_status",
                "symbol": "ETH-USDT-SWAP",
                "data_type": "active_event_status",
                "source_type": "event_pool",
                "source_tier": 2,
                "freshness_status": "stale",
                "can_satisfy_execution_fact": False,
                "confidence_cap": None,
            }
        ],
        facts_gate={
            "passed": False,
            "severity": "hard_fail",
            "missing_execution_facts": [],
            "missing_auxiliary_facts": [],
            "missing_event_facts": ["active_event_status"],
            "blocked_action_classes": ["opening", "trigger", "flip"],
            "reasons": ["active_event_status: stale"],
            "confidence_cap": 0.55,
            "confidence_cap_reasons": ["facts_gate:event_status_stale"],
        },
        agent_contributions=[],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "trigger long", "probability": 0.59},
        verdict={"allowed": False},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is False
    assert public["execution_mode"] == "blocked"
    assert "trigger long" not in public["effective_allowed_actions"]
    assert "active_event_status" in public["missing_facts"]
    assert public["confidence_policy"]["max_probability"] == 0.55
    assert public["confidence_policy"]["cap_reasons"] == ["facts_gate:event_status_stale"]


def test_decision_input_inherits_macro_surprise_incomplete_cap():
    candidate = build_decision_input_candidate(
        symbol="BTC-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[
            {
                "evidence_id": "ev-macro-event",
                "name": "macro_event",
                "symbol": "BTC-USDT-SWAP",
                "data_type": "macro_event",
                "source_type": "official",
                "source_tier": 1,
                "freshness_status": "fresh",
                "can_satisfy_execution_fact": False,
                "confidence_cap": None,
            }
        ],
        facts_gate={
            "passed": True,
            "severity": "soft_downgrade",
            "missing_execution_facts": [],
            "missing_auxiliary_facts": [],
            "missing_event_facts": [],
            "missing_macro_facts": ["macro_event.market_reaction"],
            "blocked_action_classes": [],
            "reasons": ["macro_event.market_reaction: missing"],
            "confidence_cap": 0.58,
            "confidence_cap_reasons": ["facts_gate:macro_surprise_incomplete"],
        },
        agent_contributions=[],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "trigger long", "probability": 0.59},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is True
    assert "macro_event.market_reaction" in public["missing_facts"]
    assert public["confidence_policy"]["max_probability"] == 0.58
    assert public["confidence_policy"]["cap_reasons"] == ["facts_gate:macro_surprise_incomplete"]


def test_decision_input_validation_does_not_treat_optional_dropped_contribution_as_required_failure():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "optional-failed",
                "agent_name": "ScenarioForkAgent",
                "status": "failed",
                "required": False,
                "summary": "optional scenario worker failed",
                "claims": [],
                "constraints": {},
                "conflicts": ["optional_worker_failed"],
                "missing_facts": [],
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [
                {
                    "contribution_id": "optional-failed",
                    "agent_name": "ScenarioForkAgent",
                    "reason": "status=failed",
                }
            ],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": ["optional_worker_failed"],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is True
    assert {
        violation["rule_id"] for violation in public["validation"]["violations"]
    } == set()


def test_decision_input_validation_uses_required_flag_from_dropped_contribution_when_refs_are_missing():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [
                {
                    "contribution_id": "quality-failed",
                    "agent_name": "DataQualityAgent",
                    "reason": "status=failed",
                    "required": True,
                    "failure_policy_applied": "hard_block",
                }
            ],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": ["worker_timeout"],
            "missing_facts": ["order_book"],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is False
    assert {
        violation["rule_id"] for violation in public["validation"]["violations"]
    } >= {"decision_input.required_worker_missing_or_failed"}


def test_decision_input_validation_blocks_execution_risk_hard_block_drop():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "risk-failed",
                "agent_name": "ExecutionRiskAgent",
                "status": "failed",
                "required": True,
                "output_hash": "sha256:risk",
                "input_ref": "trace:trace-1:shadow_swarm_input",
                "trace_ref": "trace-1:shadow:ExecutionRiskAgent",
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [
                {
                    "contribution_id": "risk-failed",
                    "agent_name": "ExecutionRiskAgent",
                    "reason": "status=failed",
                    "required": True,
                    "failure_policy_applied": "hard_block",
                    "error_type": "ExecutionRiskHardBlock",
                }
            ],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": ["execution_risk_hard_block"],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "trigger long", "probability": 0.61},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is False
    violations = public["validation"]["violations"]
    assert {
        violation["rule_id"] for violation in violations
    } >= {"decision_input.required_worker_missing_or_failed"}
    dropped = next(
        violation["dropped_contributions"]
        for violation in violations
        if violation["rule_id"] == "decision_input.required_worker_missing_or_failed"
    )
    assert dropped == [
        {
            "contribution_id": "risk-failed",
            "agent_name": "ExecutionRiskAgent",
            "reason": "status=failed",
            "required": True,
            "failure_policy_applied": "hard_block",
            "error_type": "ExecutionRiskHardBlock",
        }
    ]


def test_decision_input_validation_blocks_worker_hard_block_constraint():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "risk-hard-block",
                "agent_name": "ExecutionRiskAgent",
                "status": "ok",
                "required": True,
                "summary": "execution risk blocks executable action",
                "claims": [],
                "constraints": {
                    "decision_effect": "none",
                    "hard_block": True,
                    "hard_block_reasons": ["facts_gate:execution_facts_missing"],
                },
                "conflicts": ["execution_risk_hard_block"],
                "missing_facts": [],
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["risk-hard-block"],
            "dropped_contributions": [],
            "supporting_thesis": ["execution risk blocks executable action"],
            "counter_thesis": [],
            "conflicts": ["execution_risk_hard_block"],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "open short", "probability": 0.56},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["contribution_refs"] == [
        {
            "contribution_id": "risk-hard-block",
            "agent_name": "ExecutionRiskAgent",
            "status": "ok",
            "required": True,
            "output_hash": None,
            "input_ref": None,
            "trace_ref": None,
            "confidence_cap": None,
            "confidence_cap_reasons": [],
            "blocked_actions": [],
            "hard_block": True,
            "hard_block_reasons": ["facts_gate:execution_facts_missing"],
            "manual_review_reminders": [],
            "allowed_action_class_reduction": {},
            "required_confirmations": [],
        }
    ]
    assert public["validation"]["passed"] is False
    assert public["validation"]["severity"] == "hard_fail"
    assert {
        violation["rule_id"] for violation in public["validation"]["violations"]
    } >= {"decision_input.worker_hard_block"}
    hard_block = next(
        violation
        for violation in public["validation"]["violations"]
        if violation["rule_id"] == "decision_input.worker_hard_block"
    )
    assert hard_block["worker_hard_blocks"] == [
        {
            "contribution_id": "risk-hard-block",
            "agent_name": "ExecutionRiskAgent",
            "reasons": ["facts_gate:execution_facts_missing"],
        }
    ]


def test_decision_input_keeps_llm_worker_hard_block_as_audit_signal():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[
            {
                "contribution_id": "llm-risk-hard-block",
                "agent_name": "ExecutionRiskAgent",
                "status": "ok",
                "required": True,
                "summary": "LLM execution risk audit blocks candidate switch",
                "claims": [],
                "constraints": {
                    "decision_effect": "none",
                    "hard_block": True,
                    "hard_block_reasons": ["llm:unverified_execution_risk"],
                },
                "conflicts": ["execution_risk_hard_block"],
                "missing_facts": [],
                "migration_stage": "llm_tool_shadow_worker",
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["llm-risk-hard-block"],
            "dropped_contributions": [],
            "supporting_thesis": ["LLM execution risk audit blocks candidate switch"],
            "counter_thesis": [],
            "conflicts": ["execution_risk_hard_block"],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "open short", "probability": 0.56},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["contribution_refs"][0]["migration_stage"] == "llm_tool_shadow_worker"
    assert public["validation"]["passed"] is False
    assert any(
        violation["rule_id"] == "decision_input.worker_hard_block"
        for violation in public["validation"]["violations"]
    )


def test_decision_input_validation_ignores_optional_soft_downgrade_when_refs_are_missing():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
            "reasons": [],
        },
        agent_contributions=[],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": [],
            "dropped_contributions": [
                {
                    "contribution_id": "scenario-failed",
                    "agent_name": "ScenarioForkAgent",
                    "reason": "status=failed",
                    "required": False,
                    "failure_policy_applied": "soft_downgrade",
                }
            ],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": ["optional_worker_failed"],
            "missing_facts": [],
        },
        legacy_plan={"main_action": "no trade", "probability": 0.51},
        verdict={"allowed": True},
    )

    public = candidate.to_public_dict()

    assert public["validation"]["passed"] is True
    assert public["validation"]["violations"] == []


def test_pre_final_decision_input_is_buildable_without_legacy_plan_or_verdict():
    decision_input = build_pre_final_decision_input(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[
            {
                "evidence_id": "ev-search-mark",
                "name": "mark",
                "symbol": "ETH-USDT-SWAP",
                "data_type": "mark",
                "value": {"raw": "must not leak"},
                "source_type": "search_derived",
                "freshness_status": "unknown",
                "can_satisfy_execution_fact": False,
                "confidence_cap": 0.58,
                "claims": ["raw snippet must not enter final input"],
            }
        ],
        facts_gate={
            "passed": False,
            "severity": "hard_fail",
            "missing_execution_facts": ["mark"],
            "blocked_action_classes": ["trigger"],
            "reasons": ["mark: present but not execution fact source; source_types=search_derived"],
        },
        agent_contributions=[
            {
                "contribution_id": "root-ok",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "required": True,
                "summary": "Root cause is covered.",
                "claims": [{"claim": "ETF flow improved", "side": "bullish"}],
                "constraints": {},
                "conflicts": [],
                "missing_facts": [],
                "output_hash": "sha256:root",
                "input_ref": "trace:trace-1:shadow_swarm_input",
            }
        ],
        lead_synthesis={
            "decision_effect": "none",
            "included_contribution_ids": ["root-ok"],
            "dropped_contributions": [],
            "supporting_thesis": [],
            "counter_thesis": [],
            "conflicts": [],
            "missing_facts": [],
        },
    )

    public = decision_input.to_public_dict()

    assert public["mode"] == "pre_final_candidate"
    assert public["decision_effect"] == "none"
    assert public["input_ref"] == "trace:trace-1:pre_final_decision_input"
    assert "legacy_decision_ref" not in public
    assert public["lead_synthesis"]["included_contribution_ids"] == ["root-ok"]
    assert public["lead_synthesis"]["dropped_contributions"] == []
    assert "trigger long" not in public["effective_allowed_actions"]
    assert public["confidence_policy"]["max_probability"] == 0.58
    assert public["validation"]["passed"] is False
    assert public["validation"]["severity"] == "hard_fail"
    assert {
        violation["rule_id"] for violation in public["validation"]["violations"]
    } >= {
        "decision_input.facts_gate_hard_fail",
    }
    serialized = str(public)
    assert "must not leak" not in serialized
    assert "raw snippet must not enter final input" not in serialized
