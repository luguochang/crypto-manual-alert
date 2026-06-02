from __future__ import annotations

import pytest

from crypto_manual_alert.lead.default_plan import build_default_lead_plan
from crypto_manual_alert.orchestration.harness import load_harness_policy
from crypto_manual_alert.lead.agent import LeadAgent, LeadPlanError


def test_lead_agent_plans_only_harness_enabled_shadow_workers():
    policy = load_harness_policy("shadow_audit")
    lead_agent = LeadAgent(policy=policy)

    lead_plan = lead_agent.plan_tasks(symbol="ETH-USDT-SWAP", trace_id="trace-1")

    assert lead_plan.decision_effect == "none"
    assert [task.agent_name for task in lead_plan.tasks] == [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    assert all(task.timeout_seconds == policy.agent_policy(task.agent_name).timeout_seconds for task in lead_plan.tasks)
    assert all(task.requested_tools == () for task in lead_plan.tasks)
    assert all(task.required is True for task in lead_plan.tasks)


def test_lead_agent_requests_business_skills_for_llm_tool_shadow_mode():
    policy = load_harness_policy("shadow_audit")
    lead_agent = LeadAgent(policy=policy)

    local_plan = lead_agent.plan_tasks(symbol="ETH-USDT-SWAP", trace_id="trace-1", worker_mode="local_audit")
    llm_tool_plan = lead_agent.plan_tasks(symbol="ETH-USDT-SWAP", trace_id="trace-1", worker_mode="llm_tool_shadow")

    assert all(task.requested_tools == () for task in local_plan.tasks)
    assert {
        task.agent_name: task.requested_tools
        for task in llm_tool_plan.tasks
    } == {
        "LiveFactAgent": ("realtime_search",),
        "DerivativesAgent": (),
        "MacroEventAgent": ("macro_event",),
        "RootCauseAgent": ("root_cause_search",),
        "MarketSentimentAgent": ("market_sentiment",),
        "DataQualityAgent": (),
        "ExecutionRiskAgent": ("liquidity_order_book",),
    }


def test_lead_plan_exposes_harness_resource_caps():
    policy = load_harness_policy("shadow_audit")
    lead_plan = LeadAgent(policy=policy).plan_tasks(symbol="ETH-USDT-SWAP", trace_id="trace-1")

    assert lead_plan.max_parallel_workers == policy.max_parallel_workers
    assert lead_plan.deadline_ms == policy.deadline_ms
    assert lead_plan.max_tool_calls == policy.max_tool_calls
    assert lead_plan.to_public_dict()["resource_limits"] == {
        "max_parallel_workers": policy.max_parallel_workers,
        "deadline_ms": policy.deadline_ms,
        "max_tool_calls": policy.max_tool_calls,
    }


def test_default_lead_plan_builder_delegates_to_lead_agent_planning_contract():
    policy = load_harness_policy("shadow_audit")
    base_input_view = {"market": {"source": "fixture"}}

    compat_plan = build_default_lead_plan(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        policy=policy,
        base_input_view=base_input_view,
    )
    lead_plan = LeadAgent(policy=policy).plan_tasks(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        base_input_view=base_input_view,
    )

    assert compat_plan.to_public_dict() == lead_plan.to_public_dict()


def test_lead_agent_rejects_unknown_or_missing_required_worker_requests():
    lead_agent = LeadAgent(policy=load_harness_policy("shadow_audit"))

    with pytest.raises(LeadPlanError, match="not enabled"):
        lead_agent.plan_tasks(
            symbol="ETH-USDT-SWAP",
            trace_id="trace-1",
            requested_agents=["RootCauseAgent", "UnknownAgent"],
        )

    with pytest.raises(LeadPlanError, match="required worker agents missing"):
        lead_agent.plan_tasks(
            symbol="ETH-USDT-SWAP",
            trace_id="trace-1",
            requested_agents=["RootCauseAgent"],
        )


def test_lead_agent_synthesis_uses_lead_plan_required_tasks():
    lead_agent = LeadAgent(policy=load_harness_policy("shadow_audit"))
    lead_plan = lead_agent.plan_tasks(symbol="ETH-USDT-SWAP", trace_id="trace-1")

    synthesis = lead_agent.synthesize(
        lead_plan,
        agent_contributions=[
            {
                "contribution_id": "root-ok",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "summary": "ETF flow supports upside.",
                "claims": [{"claim": "ETF flow supports upside", "side": "bullish"}],
                "conflicts": [],
                "missing_facts": [],
            }
        ],
    )
    public = synthesis.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["included_contribution_ids"] == ["root-ok"]
    assert {
        item["agent_name"]
        for item in public["dropped_contributions"]
        if item["reason"] == "missing_required_contribution"
    } == {
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    }
