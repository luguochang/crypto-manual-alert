from __future__ import annotations

from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions


def test_live_fact_agent_reports_core_fact_coverage_without_directional_judgment():
    from crypto_manual_alert.market_agents.live_fact import LiveFactAgent

    contribution = LiveFactAgent().run(_task(), _input_view())

    assert contribution.agent_name == "LiveFactAgent"
    assert contribution.status == "ok"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["core_fact_coverage"] == {
        "mark": True,
        "index": True,
        "order_book": False,
    }
    assert contribution.constraints["source_tiers"] == {
        "mark": "exchange_native",
        "index": "exchange_native",
        "order_book": "missing",
    }
    assert contribution.constraints["freshness"] == {
        "mark": "ok",
        "index": "ok",
    }
    assert contribution.constraints["blocked_action_classes"] == ["opening", "trigger", "flip"]
    assert contribution.constraints["required_confirmations"] == ["confirm order_book"]
    assert contribution.missing_facts == ["order_book"]
    assert "missing_execution_fact:order_book" in contribution.conflicts
    assert all(claim["side"] == "neutral" for claim in contribution.claims)
    assert "main_action" not in contribution.to_public_dict()

    validation = validate_agent_contributions([contribution], policy=load_harness_policy("shadow_audit"))
    assert validation.passed is True


def test_market_agent_registry_includes_live_fact_agent_as_first_fact_worker():
    from crypto_manual_alert.market_agents.live_fact import LiveFactAgent
    from crypto_manual_alert.market_agents.registry import build_local_shadow_workers

    workers = build_local_shadow_workers()

    assert tuple(workers)[:1] == ("LiveFactAgent",)
    assert type(workers["LiveFactAgent"]) is LiveFactAgent


def _task() -> SubTask:
    return SubTask(
        task_id="shadow:LiveFactAgent",
        agent_name="LiveFactAgent",
        role="live_fact_audit",
        input_ref="trace:trace-live:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-live"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref="trace-live:shadow:LiveFactAgent",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-live",
        "snapshot": {
            "points": {
                "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                "index": {"source": "okx_public", "status": "ok", "value": 3498},
            },
        },
        "facts_gate": {
            "passed": False,
            "severity": "hard_fail",
            "missing_execution_facts": ["order_book"],
            "blocked_action_classes": ["opening", "trigger", "flip"],
        },
    }
