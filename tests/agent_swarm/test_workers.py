from __future__ import annotations

from crypto_manual_alert.lead.synthesis import build_lead_synthesis_candidate
from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.agent_swarm.workers import build_local_shadow_workers


def test_local_shadow_workers_emit_distinct_audit_contributions_from_input_view():
    input_view = {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-1",
        "snapshot": {
            "unavailable": ["order_book: ConnectTimeout"],
            "points": {
                "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                "web_eth_price_context": {"source": "search-derived", "status": "ok", "value": "fallback"},
            },
        },
        "research": {
            "results": {
                "macro_context": [
                    {
                        "title": "ETF inflow surprise",
                        "snippet": "ETH sentiment improved after ETF inflows.",
                        "source": "fixture-search",
                    }
                ],
                "derivatives_context": [
                    {
                        "title": "Funding turns hot",
                        "snippet": "Funding and leverage show crowded longs.",
                        "source": "fixture-search",
                    }
                ],
            },
            "unavailable": ["liquidation_heatmap"],
        },
        "facts_gate": {
            "passed": False,
            "missing_execution_facts": ["order_book"],
            "blocked_action_classes": ["opening", "trigger", "flip"],
            "reasons": ["order_book: missing"],
        },
        "verdict": {
            "allowed": False,
            "reasons": ["缺少 order_book，禁止 trigger。"],
            "rule_hits": [{"rule_id": "facts.execution.missing", "blocking": True}],
        },
    }
    workers = build_local_shadow_workers()

    contributions = {
        agent_name: worker.run(_task(agent_name), input_view)
        for agent_name, worker in workers.items()
    }

    assert set(contributions) == {
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    }
    assert {
        agent_name: item.status
        for agent_name, item in contributions.items()
    } == {
        "LiveFactAgent": "ok",
        "DerivativesAgent": "ok",
        "MacroEventAgent": "ok",
        "RootCauseAgent": "ok",
        "MarketSentimentAgent": "ok",
        "DataQualityAgent": "ok",
        "ExecutionRiskAgent": "ok",
    }
    assert all(item.input_ref == "trace:trace-1:shadow_swarm_input" for item in contributions.values())
    assert all(item.output_hash.startswith("sha256:") for item in contributions.values())
    assert all(item.failure_policy_applied == "none" for item in contributions.values())
    assert all(item.migration_stage == "shadow_swarm" for item in contributions.values())

    live_fact = contributions["LiveFactAgent"]
    assert live_fact.constraints["core_fact_coverage"] == {
        "mark": True,
        "index": False,
        "order_book": False,
    }
    assert live_fact.constraints["source_tiers"]["mark"] == "exchange_native"
    assert "order_book" in live_fact.missing_facts
    assert all(claim["side"] == "neutral" for claim in live_fact.claims)

    derivatives = contributions["DerivativesAgent"]
    assert derivatives.constraints["decision_effect"] == "none"
    assert derivatives.constraints["missing_derivative_facts"] == [
        "funding_rate",
        "open_interest",
        "liquidation_map",
        "basis",
    ]
    assert derivatives.constraints["confidence_cap"] == 0.58
    assert derivatives.constraints["blocked_action_classes"] == ["opening", "trigger", "flip"]
    assert {
        "missing_derivative_fact:funding_rate",
        "missing_derivative_fact:open_interest",
        "missing_derivative_fact:liquidation_map",
        "missing_derivative_fact:basis",
    }.issubset(set(derivatives.conflicts))

    macro = contributions["MacroEventAgent"]
    assert macro.constraints["decision_effect"] == "none"
    assert macro.constraints["missing_event_facts"] == ["active_event_status"]
    assert "missing_event_fact:active_event_status" in macro.conflicts

    root = contributions["RootCauseAgent"]
    assert "pre-decision" in root.summary
    assert any("ETF inflow surprise" in claim["claim"] for claim in root.claims)
    assert root.constraints["decision_effect"] == "none"

    sentiment = contributions["MarketSentimentAgent"]
    assert "crowded" in sentiment.summary.lower()
    assert sentiment.constraints["confidence_cap"] == 0.58
    assert any("Funding turns hot" in claim["claim"] for claim in sentiment.claims)
    assert any(
        claim["side"] == "bearish" and "crowded" in claim["claim"].lower()
        for claim in sentiment.claims
    )

    data_quality = contributions["DataQualityAgent"]
    assert "order_book" in data_quality.missing_facts
    assert data_quality.constraints["blocked_action_classes"] == ["opening", "trigger", "flip"]

    execution = contributions["ExecutionRiskAgent"]
    assert "pre-decision" in execution.summary
    assert "missing_execution_fact:order_book" in execution.conflicts
    assert execution.constraints["blocked_action_classes"] == ["opening", "trigger", "flip"]
    assert execution.constraints["hard_block"] is True
    assert execution.constraints["hard_block_reasons"] == ["facts_gate:execution_facts_missing"]

    lead_synthesis = build_lead_synthesis_candidate(
        agent_contributions=[item.to_public_dict() for item in contributions.values()]
    ).to_public_dict()
    assert any("crowded" in claim.lower() for claim in lead_synthesis["counter_thesis"])
    assert lead_synthesis["strongest_counter_thesis_ref"] == {
        "contribution_id": "shadow_swarm:shadow:MarketSentimentAgent",
        "agent_name": "MarketSentimentAgent",
        "claim": "crowded long positioning can fade an objectively positive catalyst in the short term",
        "side": "bearish",
        "evidence_ids": ["research.derivatives_context[0]"],
        "strength": 0.66,
    }
    assert {
        ref["conflict_id"]
        for ref in lead_synthesis["conflict_refs"]
    } >= {"objective_catalyst_vs_crowded_positioning", "missing_execution_fact:order_book"}


def _task(agent_name: str) -> SubTask:
    return SubTask(
        task_id=f"shadow:{agent_name}",
        agent_name=agent_name,
        role="audit",
        input_ref="trace:trace-1:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-1"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref=f"trace-1:shadow:{agent_name}",
    )
