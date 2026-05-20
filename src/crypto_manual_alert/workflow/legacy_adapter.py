from __future__ import annotations

from typing import Protocol

from crypto_manual_alert.config import Config
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import DecisionPlan, RiskVerdict
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.legacy_plan_runner import PlanRunner
from crypto_manual_alert.workflow.results import DecisionStepResult, coerce_decision_step_result


class DecisionStep(Protocol):
    """Workflow step contract.

    The legacy adapter implements this contract now; a controlled AgentRunner
    can implement the same contract later.
    """

    def run(self, context: DecisionRunContext) -> DecisionStepResult:
        """Execute one workflow step from the full run context."""


class LegacyPlanRunnerAdapter:
    """Compatibility adapter around the old PlanRunner.

    This adapter reads the symbol from DecisionRunContext and delegates to the
    legacy pipeline. It does not mean Agent Swarm has taken over production.
    """

    def __init__(self, config: Config, journal: Journal):
        self.runner = PlanRunner(config, journal)

    def run(self, context: DecisionRunContext) -> DecisionStepResult:
        return coerce_decision_step_result(
            self.runner.run_once(context.symbol, run_context=context),
            require_trace_id=True,
        )
