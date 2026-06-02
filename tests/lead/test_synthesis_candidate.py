from __future__ import annotations

from crypto_manual_alert.lead.synthesis import build_lead_synthesis_candidate


def test_lead_synthesis_candidate_preserves_counter_thesis_and_dropped_reasons():
    synthesis = build_lead_synthesis_candidate(
        required_agents=["RootCauseAgent", "MarketSentimentAgent", "DataQualityAgent", "ExecutionRiskAgent"],
        agent_contributions=[
            {
                "contribution_id": "c-root",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "summary": "ETF inflow is the primary bullish driver.",
                "claims": [{"claim": "ETF inflow supports upside", "side": "bullish"}],
                "conflicts": [],
                "missing_facts": [],
            },
            {
                "contribution_id": "c-sentiment",
                "agent_name": "MarketSentimentAgent",
                "status": "ok",
                "summary": "Long positioning is crowded; squeeze risk is elevated.",
                "claims": [{"claim": "Crowded longs can reverse", "side": "bearish"}],
                "conflicts": ["bullish_root_cause_vs_crowded_longs"],
                "missing_facts": [],
            },
            {
                "contribution_id": "c-quality",
                "agent_name": "DataQualityAgent",
                "status": "failed",
                "required": True,
                "failure_policy_applied": "soft_downgrade",
                "summary": "order book fetch failed",
                "claims": [],
                "conflicts": ["worker_timeout"],
                "missing_facts": ["order_book"],
            },
        ],
    )

    public = synthesis.to_public_dict()

    assert public["decision_effect"] == "none"
    assert public["included_contribution_ids"] == ["c-root", "c-sentiment"]
    assert public["dropped_contributions"] == [
        {
                "contribution_id": "c-quality",
                "agent_name": "DataQualityAgent",
                "reason": "status=failed",
                "required": True,
                "failure_policy_applied": "soft_downgrade",
                "error_type": None,
            },
            {
                "contribution_id": None,
                "agent_name": "ExecutionRiskAgent",
                "reason": "missing_required_contribution",
                "required": True,
                "failure_policy_applied": "hard_block",
                "error_type": None,
            },
        ]
    assert "ETF inflow supports upside" in public["supporting_thesis"]
    assert "Crowded longs can reverse" in public["counter_thesis"]
    assert "bullish_root_cause_vs_crowded_longs" in public["conflicts"]
    assert "worker_timeout" in public["conflicts"]
    assert set(public["missing_facts"]) == {"ExecutionRiskAgent", "order_book"}


def test_lead_synthesis_candidate_keeps_replayable_counter_and_conflict_refs():
    synthesis = build_lead_synthesis_candidate(
        required_agents=["RootCauseAgent", "MarketSentimentAgent"],
        agent_contributions=[
            {
                "contribution_id": "c-root",
                "agent_name": "RootCauseAgent",
                "status": "ok",
                "summary": "ETF inflow is the dominant bullish driver.",
                "claims": [
                    {
                        "claim": "ETF inflow supports upside continuation",
                        "side": "bullish",
                        "evidence_ids": ["ev-etf-flow"],
                    }
                ],
                "conflicts": [
                    {
                        "conflict_id": "trend_vs_crowding",
                        "summary": "Bullish ETF flow conflicts with crowded long positioning.",
                        "sides": ["bullish", "bearish"],
                        "contribution_refs": ["c-root", "c-sentiment"],
                        "raw_snippet": "must not be required for replay",
                    }
                ],
                "missing_facts": [],
            },
            {
                "contribution_id": "c-sentiment",
                "agent_name": "MarketSentimentAgent",
                "status": "ok",
                "summary": "Long positioning is crowded.",
                "claims": [
                    {
                        "claim": "Crowded longs can force a short-term reversal",
                        "side": "bearish",
                        "evidence_ids": ["ev-funding", "ev-oi"],
                    }
                ],
                "conflicts": ["funding_extreme_vs_spot_bid"],
                "missing_facts": [],
            },
        ],
    )

    public = synthesis.to_public_dict()

    assert public["counter_thesis"] == ["Crowded longs can force a short-term reversal"]
    assert public["counter_thesis_refs"] == [
        {
            "contribution_id": "c-sentiment",
            "agent_name": "MarketSentimentAgent",
            "claim": "Crowded longs can force a short-term reversal",
            "side": "bearish",
            "evidence_ids": ["ev-funding", "ev-oi"],
        }
    ]
    assert public["strongest_counter_thesis_ref"] == {
        "contribution_id": "c-sentiment",
        "agent_name": "MarketSentimentAgent",
        "claim": "Crowded longs can force a short-term reversal",
        "side": "bearish",
        "evidence_ids": ["ev-funding", "ev-oi"],
    }
    assert public["conflicts"] == [
        "Bullish ETF flow conflicts with crowded long positioning.",
        "funding_extreme_vs_spot_bid",
    ]
    assert public["conflict_refs"] == [
        {
            "conflict_id": "trend_vs_crowding",
            "summary": "Bullish ETF flow conflicts with crowded long positioning.",
            "sides": ["bullish", "bearish"],
            "contribution_refs": ["c-root", "c-sentiment"],
        },
        {
            "conflict_id": "funding_extreme_vs_spot_bid",
            "summary": "funding_extreme_vs_spot_bid",
            "contribution_refs": ["c-sentiment"],
        },
    ]
    serialized = str(public)
    assert "raw_snippet" not in serialized
    assert "must not be required for replay" not in serialized


def test_lead_synthesis_candidate_selects_strongest_counter_by_strength_and_evidence():
    synthesis = build_lead_synthesis_candidate(
        required_agents=["MarketSentimentAgent", "ExecutionRiskAgent"],
        agent_contributions=[
            {
                "contribution_id": "c-sentiment",
                "agent_name": "MarketSentimentAgent",
                "status": "ok",
                "claims": [
                    {
                        "claim": "Crowding can cause a shallow pullback",
                        "side": "bearish",
                        "evidence_ids": ["ev-funding"],
                        "strength": 0.45,
                    }
                ],
                "conflicts": [],
                "missing_facts": [],
            },
            {
                "contribution_id": "c-risk",
                "agent_name": "ExecutionRiskAgent",
                "status": "ok",
                "claims": [
                    {
                        "claim": "Event-window slippage makes fresh long entries fragile",
                        "side": "bearish",
                        "evidence_ids": ["ev-depth", "ev-liquidation-cluster"],
                        "strength": 0.86,
                    }
                ],
                "conflicts": [],
                "missing_facts": [],
            },
        ],
    )

    public = synthesis.to_public_dict()

    assert public["strongest_counter_thesis_ref"] == {
        "contribution_id": "c-risk",
        "agent_name": "ExecutionRiskAgent",
        "claim": "Event-window slippage makes fresh long entries fragile",
        "side": "bearish",
        "evidence_ids": ["ev-depth", "ev-liquidation-cluster"],
        "strength": 0.86,
    }


def test_lead_synthesis_candidate_preserves_failure_policy_for_required_and_optional_drops():
    synthesis = build_lead_synthesis_candidate(
        required_agents=["RootCauseAgent", "DataQualityAgent"],
        agent_contributions=[
            {
                "contribution_id": "c-quality",
                "agent_name": "DataQualityAgent",
                "status": "failed",
                "required": True,
                "failure_policy_applied": "hard_block",
                "error_type": "TimeoutError",
                "summary": "data quality timeout",
                "claims": [],
                "conflicts": ["worker_timeout"],
                "missing_facts": ["order_book"],
            },
            {
                "contribution_id": "c-scenario",
                "agent_name": "ScenarioForkAgent",
                "status": "failed",
                "required": False,
                "failure_policy_applied": "soft_downgrade",
                "error_type": "ValueError",
                "summary": "optional scenario failed",
                "claims": [],
                "conflicts": ["optional_worker_failed"],
                "missing_facts": [],
            },
        ],
    )

    public = synthesis.to_public_dict()

    assert public["dropped_contributions"] == [
        {
            "contribution_id": "c-quality",
            "agent_name": "DataQualityAgent",
            "reason": "status=failed",
            "required": True,
            "failure_policy_applied": "hard_block",
            "error_type": "TimeoutError",
        },
        {
            "contribution_id": "c-scenario",
            "agent_name": "ScenarioForkAgent",
            "reason": "status=failed",
            "required": False,
            "failure_policy_applied": "soft_downgrade",
            "error_type": "ValueError",
        },
        {
            "contribution_id": None,
            "agent_name": "RootCauseAgent",
            "reason": "missing_required_contribution",
            "required": True,
            "failure_policy_applied": "hard_block",
            "error_type": None,
        },
    ]


def test_lead_synthesis_marks_failed_required_agent_by_plan_even_if_contribution_claims_optional():
    synthesis = build_lead_synthesis_candidate(
        required_agents=["DataQualityAgent"],
        agent_contributions=[
            {
                "contribution_id": "c-quality",
                "agent_name": "DataQualityAgent",
                "status": "failed",
                "required": False,
                "failure_policy_applied": "hard_block",
                "error_type": "TimeoutError",
                "summary": "data quality timeout",
                "claims": [],
                "conflicts": ["worker_timeout"],
                "missing_facts": ["order_book"],
            },
        ],
    )

    public = synthesis.to_public_dict()

    assert public["dropped_contributions"] == [
        {
            "contribution_id": "c-quality",
            "agent_name": "DataQualityAgent",
            "reason": "status=failed",
            "required": True,
            "failure_policy_applied": "hard_block",
            "error_type": "TimeoutError",
        },
    ]
