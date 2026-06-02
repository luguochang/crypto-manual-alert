from __future__ import annotations

from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions
from crypto_manual_alert.market_agents.sentiment_crowding import SentimentCrowdingLocalWorker


def test_market_sentiment_agent_outputs_crowding_priced_in_reflexivity_and_counter_thesis():
    contribution = SentimentCrowdingLocalWorker().run(_task(), _input_view())

    assert contribution.agent_name == "MarketSentimentAgent"
    assert contribution.status == "ok"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["confidence_cap"] == 0.58
    assert contribution.constraints["sentiment_source_quality"] == "mixed_structured_and_search"
    assert contribution.constraints["crowding_state"] == {
        "state": "crowded_long",
        "drivers": ["positive_funding", "open_interest_expansion", "search_crowding_language"],
        "evidence_ids": ["snapshot.funding_rate", "snapshot.open_interest", "research.derivatives_context[0]"],
        "confidence": "medium",
    }
    assert contribution.constraints["priced_in_assessment"] == {
        "status": "partly_priced_in",
        "reason": "search context already frames ETF flow as consensus-positive while derivatives are crowded",
        "evidence_ids": ["research.macro_context[0]", "research.derivatives_context[0]"],
    }
    assert contribution.constraints["reflexivity_risk"] == {
        "level": "elevated",
        "mechanism": "one-sided positioning can make an objectively positive catalyst fade in the short term",
        "evidence_ids": ["snapshot.funding_rate", "snapshot.open_interest", "research.derivatives_context[0]"],
    }
    assert contribution.constraints["counter_thesis"] == [
        {
            "claim": "crowded long positioning can fade an objectively positive catalyst in the short term",
            "side": "bearish",
            "evidence_ids": ["snapshot.funding_rate", "snapshot.open_interest", "research.derivatives_context[0]"],
            "strength": 0.66,
        }
    ]
    assert contribution.constraints["required_confirmations"] == [
        "confirm crowding with exchange-native funding and open interest",
        "confirm whether ETF flow surprise is already priced in",
    ]
    assert contribution.constraints["missing_sentiment_facts"] == []
    assert any(claim["side"] == "bearish" and claim["strength"] == 0.66 for claim in contribution.claims)
    assert {
        ref["conflict_id"] for ref in contribution.conflicts if isinstance(ref, dict)
    } == {"objective_catalyst_vs_crowded_positioning"}
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def test_market_sentiment_agent_reports_missing_sentiment_facts_without_trade_fields():
    contribution = SentimentCrowdingLocalWorker().run(
        _task(),
        {
            "symbol": "ETH-USDT-SWAP",
            "trace_id": "trace-sentiment",
            "snapshot": {"points": {}},
            "research": {"results": {}},
            "facts_gate": {},
        },
    )

    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["crowding_state"] == {
        "state": "unknown",
        "drivers": [],
        "evidence_ids": [],
        "confidence": "low",
    }
    assert contribution.constraints["priced_in_assessment"] == {
        "status": "unknown",
        "reason": "insufficient sentiment and positioning evidence",
        "evidence_ids": [],
    }
    assert contribution.constraints["reflexivity_risk"] == {
        "level": "unknown",
        "mechanism": "insufficient evidence",
        "evidence_ids": [],
    }
    assert contribution.constraints["counter_thesis"] == []
    assert contribution.constraints["missing_sentiment_facts"] == [
        "funding_rate",
        "open_interest",
        "research.results",
    ]
    assert contribution.constraints["confidence_cap"] == 0.58
    assert contribution.constraints["required_confirmations"] == [
        "confirm funding_rate",
        "confirm open_interest",
        "confirm research.results",
    ]
    assert set(contribution.missing_facts) == {"funding_rate", "open_interest", "research.results"}
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def _task() -> SubTask:
    return SubTask(
        task_id="shadow:MarketSentimentAgent",
        agent_name="MarketSentimentAgent",
        role="market_sentiment_analysis",
        input_ref="trace:trace-sentiment:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-sentiment"},
        required=True,
        timeout_seconds=20,
        failure_policy="soft_downgrade",
        trace_ref="trace-sentiment:shadow:MarketSentimentAgent",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-sentiment",
        "snapshot": {
            "points": {
                "funding_rate": {"source": "okx_public", "status": "ok", "value": 0.0009},
                "open_interest": {"source": "okx_public", "status": "ok", "value": {"change_1h": "up"}},
                "macro_event": {
                    "source": "event_pool_refreshed",
                    "status": "ok",
                    "value": {"event_name": "ETF flow surprise", "surprise": "positive"},
                },
            }
        },
        "research": {
            "results": {
                "macro_context": [
                    {
                        "title": "ETF flow surprise already expected",
                        "snippet": "The market broadly expects ETF flow support.",
                        "source": "fixture-search",
                    }
                ],
                "derivatives_context": [
                    {
                        "title": "Crowded long positioning",
                        "snippet": "Funding and open interest show crowded longs.",
                        "source": "fixture-search",
                    }
                ],
            }
        },
        "facts_gate": {"passed": True, "missing_execution_facts": []},
    }
