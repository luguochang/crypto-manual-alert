from __future__ import annotations

from crypto_manual_alert.market_agents.data_quality import DataQualityLocalWorker
from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions


def test_data_quality_agent_outputs_source_coverage_staleness_and_conflict_details():
    contribution = DataQualityLocalWorker().run(_task(), _input_view())

    assert contribution.agent_name == "DataQualityAgent"
    assert contribution.status == "ok"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["execution_fact_coverage"] == {
        "mark": True,
        "index": True,
        "order_book": False,
    }
    assert contribution.constraints["source_quality"] == {
        "mark": {
            "source": "okx_public",
            "source_type": "exchange_native",
            "status": "ok",
            "can_satisfy_execution_fact": True,
        },
        "index": {
            "source": "coinglass_api",
            "source_type": "aggregator_api",
            "status": "ok",
            "can_satisfy_execution_fact": False,
        },
        "order_book": {
            "source": "missing",
            "source_type": "missing",
            "status": "missing",
            "can_satisfy_execution_fact": False,
        },
    }
    assert contribution.constraints["staleness_details"] == [
        {
            "fact_name": "index",
            "status": "ok",
            "source_type": "aggregator_api",
            "reason": "not_exchange_native_execution_fact",
        },
        {
            "fact_name": "order_book",
            "status": "missing",
            "source_type": "missing",
            "reason": "missing",
        },
    ]
    assert contribution.constraints["conflicting_fact_details"] == [
        {"fact_name": "index", "reason": "facts_gate_conflict"}
    ]
    assert contribution.constraints["missing_execution_facts"] == ["index", "order_book"]
    assert contribution.constraints["blocked_action_classes"] == ["opening", "trigger", "flip"]
    assert contribution.constraints["required_confirmations"] == [
        "confirm index from exchange-native source",
        "confirm order_book from exchange-native source",
    ]
    assert contribution.missing_facts == ["index", "order_book"]
    assert "missing_execution_fact:index" in contribution.conflicts
    assert "conflicting_execution_fact:index" in contribution.conflicts
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def test_data_quality_agent_clean_snapshot_keeps_audit_only_fields():
    contribution = DataQualityLocalWorker().run(
        _task(),
        {
            "symbol": "ETH-USDT-SWAP",
            "trace_id": "trace-data-quality",
            "snapshot": {
                "points": {
                    "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                    "index": {"source": "okx_public", "status": "ok", "value": 3498},
                    "order_book": {"source": "okx_public", "status": "ok", "value": {"bids": [], "asks": []}},
                }
            },
            "facts_gate": {"blocked_action_classes": []},
        },
    )

    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["execution_fact_coverage"] == {
        "mark": True,
        "index": True,
        "order_book": True,
    }
    assert contribution.constraints["staleness_details"] == []
    assert contribution.constraints["conflicting_fact_details"] == []
    assert contribution.constraints["missing_execution_facts"] == []
    assert contribution.constraints["blocked_action_classes"] == []
    assert contribution.constraints["required_confirmations"] == []
    assert contribution.missing_facts == []
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def test_data_quality_agent_does_not_echo_non_execution_unavailable_prefixes():
    contribution = DataQualityLocalWorker().run(
        _task(),
        {
            "symbol": "ETH-USDT-SWAP",
            "trace_id": "trace-data-quality",
            "snapshot": {
                "unavailable": ["leverage: upstream field must not be echoed"],
                "points": {
                    "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                    "index": {"source": "okx_public", "status": "ok", "value": 3498},
                    "order_book": {"source": "okx_public", "status": "ok", "value": {"bids": [], "asks": []}},
                },
            },
            "facts_gate": {"blocked_action_classes": []},
        },
    )

    assert contribution.constraints["missing_execution_facts"] == []
    assert contribution.missing_facts == []
    assert all("leverage" not in str(item) for item in contribution.conflicts)
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def _task() -> SubTask:
    return SubTask(
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:trace-data-quality:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-data-quality"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref="trace-data-quality:shadow:DataQualityAgent",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-data-quality",
        "snapshot": {
            "unavailable": ["order_book: ConnectTimeout"],
            "points": {
                "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                "index": {"source": "coinglass_api", "status": "ok", "value": 3498},
            },
        },
        "facts_gate": {
            "missing_execution_facts": ["index", "order_book"],
            "conflicting_execution_facts": ["index"],
            "blocked_action_classes": ["opening", "trigger", "flip"],
            "severity": "hard_fail",
        },
    }
