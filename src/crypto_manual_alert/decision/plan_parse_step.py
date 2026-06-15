from __future__ import annotations

from dataclasses import dataclass

from crypto_manual_alert.domain import DecisionPlan
from crypto_manual_alert.decision.plan_parser import parse_decision_plan


@dataclass(frozen=True)
class PlanParseStepResult:
    """Parsed legacy final output for the current run.

    This step converts the FinalDecisionAgent raw JSON into a DecisionPlan and
    exposes only the parser span summary. It does not run risk gates, repair
    output, or write persistence records.
    """

    plan: DecisionPlan

    @property
    def parse_summary(self) -> dict[str, str]:
        return {"plan_id": self.plan.plan_id, "main_action": self.plan.main_action}


def run_plan_parse_step(raw_decision: str) -> PlanParseStepResult:
    plan = parse_decision_plan(raw_decision)
    return PlanParseStepResult(plan=plan)
