from __future__ import annotations

from crypto_manual_alert.market_agents.execution_risk import ExecutionRiskLocalWorker
from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.harness import load_harness_policy, validate_agent_contributions


def test_execution_risk_agent_outputs_hard_block_action_reduction_and_manual_review_reminders():
    contribution = ExecutionRiskLocalWorker().run(_task(), _input_view())

    assert contribution.agent_name == "ExecutionRiskAgent"
    assert contribution.status == "ok"
    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["hard_block"] is True
    assert contribution.constraints["hard_block_reasons"] == ["facts_gate:execution_facts_missing"]
    assert contribution.constraints["allowed_action_class_reduction"] == {
        "blocked_action_classes": ["opening", "trigger", "flip"],
        "remaining_action_classes": ["no_action", "manual_review_only"],
        "reason": "core execution facts are incomplete or blocked upstream",
    }
    assert contribution.constraints["manual_review_reminders"] == [
        "manual review required until order_book is fresh",
        "manual review required until facts_gate hard block clears",
    ]
    assert contribution.constraints["required_confirmations"] == [
        "confirm order_book is fresh",
        "confirm facts_gate severity is not hard_fail",
    ]
    assert contribution.constraints["execution_risk_summary"] == {
        "severity": "hard_fail",
        "missing_execution_facts": ["order_book"],
        "blocked_action_classes": ["opening", "trigger", "flip"],
    }
    assert contribution.missing_facts == ["order_book"]
    assert "execution_risk_hard_block" in contribution.conflicts
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def test_execution_risk_agent_clean_facts_remains_audit_only_without_hard_block():
    contribution = ExecutionRiskLocalWorker().run(
        _task(),
        {
            "symbol": "ETH-USDT-SWAP",
            "trace_id": "trace-execution-risk",
            "snapshot": {
                "points": {
                    "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                    "index": {"source": "okx_public", "status": "ok", "value": 3498},
                    "order_book": {"source": "okx_public", "status": "ok", "value": {"bids": [], "asks": []}},
                }
            },
            "facts_gate": {"severity": "ok", "blocked_action_classes": []},
        },
    )

    assert contribution.constraints["decision_effect"] == "none"
    assert contribution.constraints["hard_block"] is False
    assert contribution.constraints["hard_block_reasons"] == []
    assert contribution.constraints["allowed_action_class_reduction"] == {
        "blocked_action_classes": [],
        "remaining_action_classes": ["opening", "trigger", "flip", "no_action", "manual_review_only"],
        "reason": "no execution hard block from worker audit",
    }
    assert contribution.constraints["manual_review_reminders"] == []
    assert contribution.constraints["required_confirmations"] == []
    assert contribution.missing_facts == []
    assert validate_agent_contributions(
        [contribution], policy=load_harness_policy("shadow_audit")
    ).passed is True


def _task() -> SubTask:
    return SubTask(
        task_id="shadow:ExecutionRiskAgent",
        agent_name="ExecutionRiskAgent",
        role="execution_risk_review",
        input_ref="trace:trace-execution-risk:shadow_swarm_input",
        input_view={"symbol": "ETH-USDT-SWAP", "trace_id": "trace-execution-risk"},
        required=True,
        timeout_seconds=10,
        failure_policy="soft_downgrade",
        trace_ref="trace-execution-risk:shadow:ExecutionRiskAgent",
    )


def _input_view() -> dict[str, object]:
    return {
        "symbol": "ETH-USDT-SWAP",
        "trace_id": "trace-execution-risk",
        "snapshot": {
            "points": {
                "mark": {"source": "okx_public", "status": "ok", "value": 3500},
                "index": {"source": "okx_public", "status": "ok", "value": 3498},
            }
        },
        "facts_gate": {
            "severity": "hard_fail",
            "missing_execution_facts": ["order_book"],
            "blocked_action_classes": ["opening", "trigger", "flip"],
            "reasons": ["order_book: missing"],
        },
    }
