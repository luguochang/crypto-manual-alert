from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from crypto_manual_alert.config import Config
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.domain import DecisionPlan, RiskVerdict
from crypto_manual_alert.journal import Journal
from crypto_manual_alert.runner import PlanRunner


RunnerFactory = Callable[[Config, Journal], PlanRunner]


@dataclass(frozen=True)
class RunResult:
    """一次工作流执行后返回给 API/UI 的稳定摘要。"""

    trace_id: str
    plan: dict[str, Any]
    verdict: dict[str, Any]


class RunExecutor:
    """工作流受控入口。

    首版仍复用已经验证过的 PlanRunner 管线，只在外层统一 DecisionRequest、
    副作用边界和 API 需要的返回摘要，避免路由层直接承载业务编排。
    """

    def __init__(
        self,
        *,
        config: Config,
        journal: Journal,
        runner_factory: RunnerFactory | None = None,
    ):
        self.config = config
        self.journal = journal
        self.runner_factory = runner_factory or PlanRunner

    def submit(self, request: DecisionRequest) -> RunResult:
        """同步提交一次手动或定时决策。

        eval/replay/postmortem 会被拒绝，避免首版入口误触发 Bark 或生产 plan 写入。
        """

        if request.run_type not in {"manual", "scheduled"}:
            raise ValueError("RunExecutor only accepts manual or scheduled requests in v1")
        runner = self.runner_factory(self.config, self.journal)
        plan, verdict = runner.run_once(request.symbol)
        trace_id = _resolve_trace_id(self.journal, plan)
        return RunResult(trace_id=trace_id, plan=_plan_summary(plan), verdict=_verdict_summary(verdict))


def _resolve_trace_id(journal: Journal, plan: DecisionPlan) -> str:
    traces = journal.list_traces(limit=5)
    for trace in traces:
        if trace.get("final_plan_id") == plan.plan_id:
            return str(trace["trace_id"])
    return str(traces[0]["trace_id"]) if traces else ""


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
    return {
        "allowed": verdict.allowed,
        "reasons": list(verdict.reasons),
        "warnings": list(verdict.warnings),
    }
