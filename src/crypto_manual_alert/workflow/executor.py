from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from crypto_manual_alert.config import Config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import DecisionPlan, RiskVerdict
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.controlled_adapter import ControlledSwarmAuditAdapter
from crypto_manual_alert.workflow.legacy_adapter import DecisionStep, LegacyPlanRunnerAdapter
from crypto_manual_alert.workflow.results import DecisionStepResult, coerce_decision_step_result


AdapterFactory = Callable[[Config, Journal], DecisionStep]
LegacyAdapterFactory = AdapterFactory


@dataclass(frozen=True)
class RunResult:
    """Stable API/UI summary returned after one workflow run."""

    trace_id: str
    context: dict[str, Any]
    plan: dict[str, Any]
    verdict: dict[str, Any]


class RunExecutor:
    """Controlled workflow entry point.

    The current implementation still delegates production execution to the
    verified legacy PlanRunner through LegacyPlanRunnerAdapter. Its job is to
    normalize DecisionRequest, create DecisionRunContext, and keep side-effect
    boundaries out of routing/API code.
    """

    def __init__(
        self,
        *,
        config: Config,
        journal: Journal,
        legacy_adapter_factory: AdapterFactory | None = None,
        controlled_adapter_factory: AdapterFactory | None = None,
    ):
        self.config = config
        self.journal = journal
        self.legacy_adapter_factory = legacy_adapter_factory or LegacyPlanRunnerAdapter
        self.controlled_adapter_factory = controlled_adapter_factory or ControlledSwarmAuditAdapter

    def submit(self, request: DecisionRequest) -> RunResult:
        """Submit one manual or scheduled production decision run."""

        if request.run_type not in {"manual", "scheduled"}:
            raise ValueError("RunExecutor only accepts manual or scheduled production requests")
        context = DecisionRunContext.create(request)
        decision_step = self._decision_step_factory()(self.config, self.journal)
        step_result = coerce_decision_step_result(decision_step.run(context), require_trace_id=True)
        plan = step_result.plan
        verdict = step_result.verdict
        trace_id = step_result.trace_id
        context_summary = context.to_public_summary()
        context_summary["artifacts"] = context.to_artifact_summary()
        return RunResult(
            trace_id=trace_id,
            context=context_summary,
            plan=_plan_summary(plan),
            verdict=_verdict_summary(verdict),
        )

    def _decision_step_factory(self) -> AdapterFactory:
        if self.config.workflow.execution_mode in {"controlled_shadow", "production_candidate_swarm"}:
            return self.controlled_adapter_factory
        return self.legacy_adapter_factory


def _plan_summary(plan: DecisionPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "instrument": plan.instrument,
        "main_action": plan.main_action,
        "horizon": plan.horizon,
        "manual_execution_required": plan.manual_execution_required,
        "expires_at": plan.expires_at.isoformat(),
        "reference_price": plan.reference_price,
        "entry_trigger": plan.entry_trigger,
        "stop_price": plan.stop_price,
        "target_1": plan.target_1,
        "target_2": plan.target_2,
        "probability": plan.probability,
    }


def _verdict_summary(verdict: RiskVerdict) -> dict[str, Any]:
    return verdict.to_public_dict()
