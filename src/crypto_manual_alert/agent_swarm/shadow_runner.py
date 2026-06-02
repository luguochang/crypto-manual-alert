from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from crypto_manual_alert.agent_swarm.pool_runner import AgentPoolTask, ControlledAgentPoolRunner
from crypto_manual_alert.agent_swarm.runtime import (
    AgentRunner,
    validate_agent_run_request_contract,
)
from crypto_manual_alert.agent_swarm.shadow_worker_failures import (
    failed_worker_result,
    not_configured_worker_result,
    preflight_rejected_worker_result,
    timeout_worker_result,
)
from crypto_manual_alert.orchestration.harness import (
    HarnessPolicy,
    HarnessValidationResult,
    load_harness_policy,
    validate_agent_contributions,
)
from crypto_manual_alert.orchestration.contracts import (
    LeadPlan,
    ShadowSwarmAudit,
    SubTask,
    WorkerAgent,
    WorkerResult,
)
from crypto_manual_alert.orchestration.runtime import AgentRunRequest
from crypto_manual_alert.lead.default_plan import build_default_lead_plan


@dataclass
class ShadowSwarmRunner:
    """Run fixed worker agents and convert every failure into an audit artifact."""

    policy: HarnessPolicy = field(default_factory=lambda: load_harness_policy("shadow_audit"))
    workers: dict[str, WorkerAgent] = field(default_factory=dict)
    agent_runner: AgentRunner = field(default_factory=AgentRunner)
    recorder: Any | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None

    def run(self, lead_plan: LeadPlan) -> ShadowSwarmAudit:
        self.agent_runner.recorder = self.recorder
        self.agent_runner.trace_id = self.trace_id
        self.agent_runner.parent_span_id = self.parent_span_id
        pool_tasks = [self._pool_task(lead_plan, subtask) for subtask in lead_plan.tasks]
        pool_runner: ControlledAgentPoolRunner[WorkerResult] = ControlledAgentPoolRunner(
            max_parallel_workers=lead_plan.max_parallel_workers,
            deadline_ms=lead_plan.deadline_ms,
        )
        worker_results = pool_runner.run(pool_tasks)

        contributions = [result.contribution for result in worker_results]
        postflight = validate_agent_contributions(contributions, policy=self.policy)
        harness_validation = HarnessValidationResult(
            passed=not pool_runner.preflight_violations and postflight.passed,
            severity="ok" if not pool_runner.preflight_violations and postflight.passed else "hard_fail",
            violations=[*pool_runner.preflight_violations, *postflight.violations],
        )
        return ShadowSwarmAudit(
            mode="shadow",
            decision_effect="none",
            lead_plan=lead_plan,
            worker_results=worker_results,
            harness_validation=harness_validation,
        )

    def _pool_task(self, lead_plan: LeadPlan, subtask: SubTask) -> AgentPoolTask[WorkerResult]:
        run_request = subtask.to_agent_run_request(run_id=lead_plan.plan_id)
        return AgentPoolTask(
            task_id=subtask.task_id,
            timeout_seconds=subtask.timeout_seconds,
            preflight=validate_agent_run_request_contract(self.policy, run_request),
            run=lambda: self._run_one(subtask),
            rejected_result=lambda violations: preflight_rejected_worker_result(subtask, violations),
            timeout_result=lambda: timeout_worker_result(subtask),
        )

    def _run_one(self, subtask: SubTask) -> WorkerResult:
        return self._call_worker(subtask, catch_exceptions=True)

    def _call_worker(self, subtask: SubTask, *, catch_exceptions: bool) -> WorkerResult:
        worker = self.workers.get(subtask.agent_name)
        if worker is None:
            return not_configured_worker_result(subtask)
        request = subtask.to_agent_run_request(run_id=f"shadow:{self.trace_id or subtask.trace_ref}")
        adapter = _SubTaskWorkerAdapter(subtask, worker)
        try:
            output = self.agent_runner.run_one(
                request,
                adapter,
                catch_exceptions=catch_exceptions,
                span_name="shadow_swarm.worker",
                span_metadata={"mode": "shadow", "failure_policy": subtask.failure_policy},
            )
        except Exception as exc:  # noqa: BLE001 - worker failure must become an explicit audit artifact.
            if not catch_exceptions:
                raise
            return failed_worker_result(subtask, exc)
        return WorkerResult(
            task_id=subtask.task_id,
            agent_name=subtask.agent_name,
            status=output.result.status,
            trace_ref=subtask.trace_ref,
            contribution=output.contribution,
            failure_policy_applied=output.result.failure_policy_applied,
            required=subtask.required,
            agent_run_result=output.result,
            error=output.result.error,
        )


class _SubTaskWorkerAdapter:
    def __init__(self, subtask: SubTask, worker: WorkerAgent):
        self.subtask = subtask
        self.worker = worker

    def run(self, request: AgentRunRequest) -> AgentContribution:
        return self.worker.run(self.subtask, copy.deepcopy(request.input_view))
