from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any, Protocol

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.runtime import AgentRunRequest, AgentRunResult
from crypto_manual_alert.orchestration.harness import HarnessValidationResult


@dataclass(frozen=True)
class SubTask:
    """One independent worker task in the controlled shadow swarm.

    A SubTask may only produce audit artifacts. It cannot write the final plan,
    risk verdict, journal, or notification.
    """

    task_id: str
    agent_name: str
    role: str
    input_ref: str
    input_view: dict[str, Any]
    required: bool
    timeout_seconds: int
    failure_policy: str
    trace_ref: str
    requested_tools: tuple[str, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "input_ref": self.input_ref,
            "input_view": copy.deepcopy(self.input_view),
            "required": self.required,
            "timeout_seconds": self.timeout_seconds,
            "failure_policy": self.failure_policy,
            "trace_ref": self.trace_ref,
            "requested_tools": list(self.requested_tools),
        }

    def to_agent_run_request(self, *, run_id: str) -> AgentRunRequest:
        return AgentRunRequest(
            run_id=run_id,
            task_id=self.task_id,
            agent_name=self.agent_name,
            role=self.role,
            input_ref=self.input_ref,
            input_view=copy.deepcopy(self.input_view),
            requested_tools=self.requested_tools,
            timeout_seconds=self.timeout_seconds,
            required=self.required,
            failure_policy=self.failure_policy,
            trace_ref=self.trace_ref,
            decision_effect="none",
        )


@dataclass(frozen=True)
class LeadPlan:
    """Enumerated controlled worker plan.

    This is not a free-form planner. It only selects fixed worker tasks from the
    harness policy and has no production decision effect.
    """

    plan_id: str
    mode: str
    decision_effect: str
    tasks: tuple[SubTask, ...]
    max_parallel_workers: int = 4
    deadline_ms: int = 60_000
    max_tool_calls: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "mode": self.mode,
            "decision_effect": self.decision_effect,
            "resource_limits": {
                "max_parallel_workers": self.max_parallel_workers,
                "deadline_ms": self.deadline_ms,
                "max_tool_calls": self.max_tool_calls,
            },
            "tasks": [task.to_public_dict() for task in self.tasks],
        }


class WorkerAgent(Protocol):
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        ...


@dataclass(frozen=True)
class WorkerResult:
    task_id: str
    agent_name: str
    status: str
    trace_ref: str
    contribution: AgentContribution
    failure_policy_applied: str
    required: bool
    agent_run_result: AgentRunResult | None = None
    error: dict[str, Any] | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "status": self.status,
            "trace_ref": self.trace_ref,
            "contribution": self.contribution.to_public_dict(),
            "agent_run_result": self.to_agent_run_result().to_public_dict(),
            "failure_policy_applied": self.failure_policy_applied,
            "required": self.required,
            "error": self.error,
        }

    def to_agent_run_result(self) -> AgentRunResult:
        if self.agent_run_result is not None:
            return self.agent_run_result
        return AgentRunResult(
            task_id=self.task_id,
            agent_name=self.agent_name,
            status=self.status,
            contribution_ref=str(self.contribution.input_ref or ""),
            output_hash=self.contribution.output_hash,
            trace_ref=self.trace_ref,
            failure_policy_applied=self.failure_policy_applied,
            required=self.required,
            decision_effect="none",
            error=self.error,
        )


@dataclass(frozen=True)
class ShadowSwarmAudit:
    """Audit-only result from the controlled shadow swarm runner."""

    mode: str
    decision_effect: str
    lead_plan: LeadPlan
    worker_results: list[WorkerResult]
    harness_validation: HarnessValidationResult

    @property
    def worker_count(self) -> int:
        return len(self.worker_results)

    @property
    def failed_workers(self) -> list[str]:
        return [result.agent_name for result in self.worker_results if result.status in {"failed", "skipped"}]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "decision_effect": self.decision_effect,
            "lead_plan": self.lead_plan.to_public_dict(),
            "worker_count": self.worker_count,
            "failed_workers": self.failed_workers,
            "worker_results": [result.to_public_dict() for result in self.worker_results],
            "harness_validation": self.harness_validation.to_public_dict(),
        }
