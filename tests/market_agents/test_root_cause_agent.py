from __future__ import annotations

from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions
from crypto_manual_alert.market_agents.root_cause import RootCauseLocalWorker


def test_root_cause_agent_outputs_replayable_cause_graph_and_caps_search_backed_inference():
    contribution = RootCauseLocalWorker().run(_task(), _input_view())

    assert contribution.agent_name == "RootCauseAgent"
    assert contribution.status == "ok"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["confidence_cap"] == 0.58
    assert contribution.constraints["confidence_cap_reasons"] == ["facts_gate:root_cause_uses_search_context"]
    assert contribution.constraints["evidence_refs"] == [
        "snapshot.active_event_status",
        "snapshot.macro_event",
        "snapshot.funding_rate",
        "snapshot.open_interest",
        "research.macro_context[0]",
        "research.derivatives_context[0]",
    ]
    assert contribution.constraints["direct_causes"] == [
        {
            "cause_id": "macro_event_surprise",
            "factor_type": "macro_event",
            "description": "ETF flow surprise: actual above consensus",
            "evidence_ids": ["snapshot.macro_event"],
            "confidence": "medium",
        }
    ]
    assert contribution.constraints["second_order_causes"] == [
        {
            "cause_id": "derivatives_crowding_amplifier",
            "factor_type": "derivatives",
            "description": "positive funding and rising open interest can amplify the observed catalyst",
            "depends_on": ["macro_event_surprise"],
            "evidence_ids": ["snapshot.funding_rate", "snapshot.open_interest"],
            "confidence": "medium",
        },
        {
            "cause_id": "search_context_confirmation",
            "factor_type": "research",
            "description": "search-derived context reports ETF flow surprise",
            "depends_on": ["macro_event_surprise"],
            "evidence_ids": ["research.macro_context[0]"],
            "confidence": "low",
        },
    ]
    assert contribution.constraints["root_cause_graph"] == [
        {
            "node_id": "macro_event_surprise",
            "factor_type": "macro_event",
            "evidence_ids": ["snapshot.macro_event"],
            "depends_on": [],
        },
        {
            "node_id": "derivatives_crowding_amplifier",
            "factor_type": "derivatives",
            "evidence_ids": ["snapshot.funding_rate", "snapshot.open_interest"],
            "depends_on": ["macro_event_surprise"],
        },
        {
            "node_id": "search_context_confirmation",
            "factor_type": "research",
            "evidence_ids": ["research.macro_context[0]"],
            "depends_on": ["macro_event_surprise"],
        },
    ]
    assert contribution.constraints["missing_causal_facts"] == []
    assert contribution.constraints["required_confirmations"] == [
        "confirm macro_event_surprise with official/event-pool source",
        "confirm derivatives_crowding_amplifier with exchange or aggregator data",
    ]
    assert contribution.missing_facts == []
    assert any(claim["side"] == "bullish" and "ETF flow surprise" in claim["claim"] for claim in contribution.claims)
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def test_root_cause_agent_propagates_missing_causal_facts_without_trade_fields():
    contribution = RootCauseLocalWorker().run(
        _task(),
        {
            "symbol": "ETH-USDT-SWAP",
            "trace_id": "trace-root",
            "snapshot": {"points": {}},
            "research": {"results": {}},
            "facts_gate": {"missing_macro_facts": ["macro_event"], "confidence_cap": 0.55},
        },
    )

    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["root_cause_graph"] == []
    assert contribution.constraints["direct_causes"] == []
    assert contribution.constraints["second_order_causes"] == []
    assert contribution.constraints["missing_causal_facts"] == [
        "active_event_status",
        "macro_event",
        "research.results",
    ]
    assert contribution.constraints["confidence_cap"] == 0.55
    assert contribution.constraints["required_confirmations"] == [
        "confirm active_event_status",
        "confirm macro_event",
        "confirm research.results",
    ]
    assert set(contribution.missing_facts) == {"active_event_status", "macro_event", "research.results"}
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def _task() -> SubTask:
    return SubTask(
        task_id="shadow:RootCauseAgent",
        agent_name="RootCauseAgent",
        role="root_cause_audit",
        input_ref="trace:trace-root:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-root"},
        required=True,
        timeout_seconds=30,
        failure_policy="soft_downgrade",
        trace_ref="trace-root:shadow:RootCauseAgent",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-root",
        "snapshot": {
            "points": {
                "active_event_status": {
                    "source": "event_pool_refreshed",
                    "status": "ok",
                    "value": {"event_name": "ETF flow", "status": "released"},
                },
                "macro_event": {
                    "source": "bls_official",
                    "status": "ok",
                    "value": {
                        "event_name": "ETF flow surprise",
                        "actual": "above consensus",
                        "consensus": "flat",
                        "surprise": "positive",
                        "market_reaction": "spot bid improved",
                        "released_at": "2026-07-03T10:00:00Z",
                    },
                },
                "funding_rate": {"source": "okx_public", "status": "ok", "value": 0.0008},
                "open_interest": {"source": "okx_public", "status": "ok", "value": {"change_1h": "up"}},
            }
        },
        "research": {
            "results": {
                "macro_context": [
                    {
                        "title": "ETF flow surprise",
                        "snippet": "ETF flow surprise supports the catalyst.",
                        "source": "fixture-search",
                    }
                ],
                "derivatives_context": [
                    {
                        "title": "Funding turns hot",
                        "snippet": "Funding and open interest are elevated.",
                        "source": "fixture-search",
                    }
                ],
            }
        },
        "facts_gate": {"passed": True, "missing_execution_facts": []},
    }
