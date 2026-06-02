from __future__ import annotations

from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions


def test_derivatives_agent_reports_structured_derivatives_without_final_action():
    from crypto_manual_alert.market_agents.derivatives import DerivativesAgent

    contribution = DerivativesAgent().run(_task(), _input_view())

    assert contribution.agent_name == "DerivativesAgent"
    assert contribution.status == "ok"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["derivatives"] == {
        "funding_rate": {"value": 0.0007, "source": "exchange_native", "status": "ok"},
        "open_interest": {"value": 1250000000, "source": "aggregator_api", "status": "ok", "delta": 0.083},
        "liquidation_map": {"value": "long_cluster_above", "source": "aggregator_api", "status": "ok"},
        "basis": {"value": 0.014, "source": "exchange_native", "status": "ok"},
        "long_short_ratio": {"value": 1.82, "source": "aggregator_api", "status": "ok"},
        "taker_flow": {"value": "buy_pressure", "source": "exchange_native", "status": "ok"},
    }
    assert contribution.constraints["crowding_state"] == "crowded_longs"
    assert contribution.constraints["blocked_action_classes"] == []
    assert contribution.missing_facts == []
    assert all(claim["side"] == "neutral" for claim in contribution.claims)
    public = contribution.to_public_dict()
    assert public["task_id"] == "shadow:DerivativesAgent"
    assert public["input_ref"] == "trace:trace-derivatives:shadow_swarm_input"
    assert public["output_hash"].startswith("sha256:")
    assert public["trace_ref"] == "trace-derivatives:shadow:DerivativesAgent"
    assert public["evidence_ids"] == [
        "snapshot.points.funding_rate",
        "snapshot.points.open_interest",
        "snapshot.points.liquidation_map",
        "snapshot.points.basis",
        "snapshot.points.long_short_ratio",
        "snapshot.points.taker_flow",
    ]
    assert "main_action" not in public
    assert "entry" not in public
    assert "stop" not in public
    assert "target" not in public
    assert "leverage" not in public
    assert "position_size" not in public

    validation = validate_agent_contributions([contribution], policy=load_harness_policy("shadow_audit"))
    assert validation.passed is True


def test_derivatives_agent_caps_confidence_and_blocks_action_classes_when_core_derivatives_are_missing():
    from crypto_manual_alert.market_agents.derivatives import DerivativesAgent

    input_view = _input_view()
    points = input_view["snapshot"]["points"]
    assert isinstance(points, dict)
    points.pop("open_interest")
    points.pop("liquidation_map")
    points.pop("basis")

    contribution = DerivativesAgent().run(_task(), input_view)

    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.missing_facts == ["open_interest", "liquidation_map", "basis"]
    assert contribution.constraints["missing_derivative_facts"] == ["open_interest", "liquidation_map", "basis"]
    assert contribution.constraints["confidence_cap"] == 0.58
    assert contribution.constraints["blocked_action_classes"] == ["opening", "trigger", "flip"]
    assert contribution.constraints["required_confirmations"] == [
        "confirm open_interest",
        "confirm liquidation_map",
        "confirm basis",
    ]
    assert {
        "missing_derivative_fact:open_interest",
        "missing_derivative_fact:liquidation_map",
        "missing_derivative_fact:basis",
    }.issubset(set(contribution.conflicts))


def test_market_agent_registry_includes_derivatives_agent_after_live_fact_worker():
    from crypto_manual_alert.market_agents.derivatives import DerivativesAgent
    from crypto_manual_alert.market_agents.registry import build_local_shadow_workers

    workers = build_local_shadow_workers()

    assert tuple(workers)[:2] == ("LiveFactAgent", "DerivativesAgent")
    assert type(workers["DerivativesAgent"]) is DerivativesAgent


def _task() -> SubTask:
    return SubTask(
        task_id="shadow:DerivativesAgent",
        agent_name="DerivativesAgent",
        role="derivatives_structure_audit",
        input_ref="trace:trace-derivatives:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-derivatives"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref="trace-derivatives:shadow:DerivativesAgent",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-derivatives",
        "snapshot": {
            "points": {
                "funding_rate": {"source": "okx_public", "status": "ok", "value": 0.0007},
                "open_interest": {
                    "source": "coinglass_api",
                    "status": "ok",
                    "value": 1_250_000_000,
                    "delta": 0.083,
                },
                "liquidation_map": {
                    "source": "coinglass_api",
                    "status": "ok",
                    "value": "long_cluster_above",
                },
                "basis": {"source": "okx_public", "status": "ok", "value": 0.014},
                "long_short_ratio": {"source": "coinglass_api", "status": "ok", "value": 1.82},
                "taker_flow": {"source": "okx_public", "status": "ok", "value": "buy_pressure"},
            },
        },
        "facts_gate": {
            "passed": True,
            "missing_execution_facts": [],
            "blocked_action_classes": [],
        },
    }
