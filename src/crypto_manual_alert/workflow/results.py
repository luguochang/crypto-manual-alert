from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence

from crypto_manual_alert.domain import DecisionPlan, RiskVerdict


@dataclass(frozen=True)
class DecisionStepResult:
    """Result returned by a workflow decision step.

    `trace_id` is part of the contract so RunExecutor does not need to guess the
    current trace by scanning recent journal rows.
    """

    trace_id: str
    plan: DecisionPlan
    verdict: RiskVerdict

    def __iter__(self) -> Iterator[DecisionPlan | RiskVerdict]:
        yield self.plan
        yield self.verdict


def coerce_decision_step_result(output: object, *, require_trace_id: bool = False) -> DecisionStepResult:
    if isinstance(output, DecisionStepResult):
        result = output
    elif isinstance(output, Sequence) and len(output) == 2:
        plan, verdict = output
        if isinstance(plan, DecisionPlan) and isinstance(verdict, RiskVerdict):
            result = DecisionStepResult(trace_id="", plan=plan, verdict=verdict)
        else:
            raise TypeError("decision step must return DecisionStepResult or (DecisionPlan, RiskVerdict)")
    else:
        raise TypeError("decision step must return DecisionStepResult or (DecisionPlan, RiskVerdict)")
    if require_trace_id and not result.trace_id:
        raise ValueError("decision step must return an explicit trace_id")
    return result
