from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.contracts import SubTask

from .common import claim, contribution, execution_hard_block, mapping, missing_execution_facts


class ExecutionRiskLocalWorker:
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        facts_gate = mapping(input_view.get("facts_gate"))
        missing_facts = missing_execution_facts(input_view)
        claims = [
            claim("pre-decision execution review has no final action", "shadow.input_scope", "neutral"),
            claim(
                f"facts gate severity={facts_gate.get('severity')}",
                "facts_gate.severity",
                "neutral",
            ),
        ]
        constraints = {
            "decision_effect": "none",
            "blocked_action_classes": list(facts_gate.get("blocked_action_classes") or []),
        }
        conflicts = [f"missing_execution_fact:{name}" for name in missing_facts]
        hard_block = execution_hard_block(facts_gate, missing_facts)
        constraints["hard_block"] = hard_block
        constraints["hard_block_reasons"] = _hard_block_reasons(hard_block)
        constraints["allowed_action_class_reduction"] = _allowed_action_class_reduction(
            constraints["blocked_action_classes"], hard_block
        )
        constraints["manual_review_reminders"] = _manual_review_reminders(facts_gate, missing_facts, hard_block)
        constraints["required_confirmations"] = _required_confirmations(facts_gate, missing_facts, hard_block)
        constraints["execution_risk_summary"] = {
            "severity": str(facts_gate.get("severity") or "unknown"),
            "missing_execution_facts": list(missing_facts),
            "blocked_action_classes": list(constraints["blocked_action_classes"]),
        }
        if hard_block:
            constraints["hard_block"] = True
            conflicts.append("execution_risk_hard_block")
        return contribution(
            subtask,
            status="ok",
            summary="pre-decision execution risk audit",
            claims=claims,
            constraints=constraints,
            conflicts=conflicts,
            missing_facts=missing_facts,
        )


def _hard_block_reasons(hard_block: bool) -> list[str]:
    return ["facts_gate:execution_facts_missing"] if hard_block else []


def _allowed_action_class_reduction(blocked_action_classes: list[str], hard_block: bool) -> dict[str, Any]:
    if hard_block:
        return {
            "blocked_action_classes": list(blocked_action_classes),
            "remaining_action_classes": ["no_action", "manual_review_only"],
            "reason": "core execution facts are incomplete or blocked upstream",
        }
    return {
        "blocked_action_classes": [],
        "remaining_action_classes": ["opening", "trigger", "flip", "no_action", "manual_review_only"],
        "reason": "no execution hard block from worker audit",
    }


def _manual_review_reminders(
    facts_gate: dict[str, Any],
    missing_facts: list[str],
    hard_block: bool,
) -> list[str]:
    if not hard_block:
        return []
    reminders = [f"manual review required until {name} is fresh" for name in missing_facts]
    if facts_gate.get("severity") == "hard_fail":
        reminders.append("manual review required until facts_gate hard block clears")
    return reminders


def _required_confirmations(
    facts_gate: dict[str, Any],
    missing_facts: list[str],
    hard_block: bool,
) -> list[str]:
    if not hard_block:
        return []
    confirmations = [f"confirm {name} is fresh" for name in missing_facts]
    if facts_gate.get("severity") == "hard_fail":
        confirmations.append("confirm facts_gate severity is not hard_fail")
    return confirmations
