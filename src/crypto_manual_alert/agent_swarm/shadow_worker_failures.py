from __future__ import annotations

import hashlib
import json
from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.contracts import SubTask, WorkerResult


__all__ = [
    "failed_worker_result",
    "not_configured_worker_result",
    "preflight_rejected_worker_result",
    "timeout_worker_result",
]


def failed_worker_result(subtask: SubTask, exc: Exception) -> WorkerResult:
    contribution = _failed_contribution(subtask, exc)
    return WorkerResult(
        task_id=subtask.task_id,
        agent_name=subtask.agent_name,
        status="failed",
        trace_ref=subtask.trace_ref,
        contribution=contribution,
        failure_policy_applied=subtask.failure_policy,
        required=subtask.required,
        error={"type": type(exc).__name__, "message": str(exc)},
    )


def preflight_rejected_worker_result(subtask: SubTask, violations: list[dict[str, Any]]) -> WorkerResult:
    reason = ",".join(str(violation.get("rule_id")) for violation in violations) or "harness.preflight_rejected"
    contribution = _failed_contribution(
        subtask,
        HarnessPreflightRejected(reason, violations),
    )
    return WorkerResult(
        task_id=subtask.task_id,
        agent_name=subtask.agent_name,
        status="failed",
        trace_ref=subtask.trace_ref,
        contribution=contribution,
        failure_policy_applied=subtask.failure_policy,
        required=subtask.required,
        error={"type": "HarnessPreflightRejected", "message": reason},
    )


def timeout_worker_result(subtask: SubTask) -> WorkerResult:
    message = f"worker timed out after {subtask.timeout_seconds}s"
    contribution = _timeout_contribution(subtask, message)
    return WorkerResult(
        task_id=subtask.task_id,
        agent_name=subtask.agent_name,
        status="failed",
        trace_ref=subtask.trace_ref,
        contribution=contribution,
        failure_policy_applied=subtask.failure_policy,
        required=subtask.required,
        error={
            "type": "TimeoutError",
            "message": message,
            "cancellation_scope": "audit_result_only",
        },
    )


def not_configured_worker_result(subtask: SubTask) -> WorkerResult:
    contribution = _not_configured_contribution(subtask)
    return WorkerResult(
        task_id=subtask.task_id,
        agent_name=subtask.agent_name,
        status="skipped",
        trace_ref=subtask.trace_ref,
        contribution=contribution,
        failure_policy_applied=subtask.failure_policy,
        required=subtask.required,
        error={"type": "WorkerNotConfigured", "message": "shadow worker implementation is not configured"},
    )


def _failed_contribution(subtask: SubTask, exc: Exception) -> AgentContribution:
    payload = {
        "agent_name": subtask.agent_name,
        "task_id": subtask.task_id,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
    conflicts = [f"worker_error:{type(exc).__name__}"]
    if isinstance(exc, HarnessPreflightRejected):
        conflicts.extend(str(violation.get("rule_id")) for violation in exc.violations)

    return AgentContribution(
        contribution_id=f"shadow_swarm:{subtask.task_id}",
        agent_name=subtask.agent_name,
        status="failed",
        required=subtask.required,
        summary=f"{type(exc).__name__}: {exc}",
        claims=[],
        constraints={"requested_tools": list(subtask.requested_tools)},
        conflicts=conflicts,
        missing_facts=[subtask.agent_name],
        input_ref=subtask.input_ref,
        output_hash=_hash_payload(payload),
        failure_policy_applied=subtask.failure_policy,
        trace_ref=subtask.trace_ref,
        migration_stage="shadow_swarm",
    )


class HarnessPreflightRejected(Exception):
    def __init__(self, reason: str, violations: list[dict[str, Any]]):
        super().__init__(reason)
        self.violations = violations


def _timeout_contribution(subtask: SubTask, message: str) -> AgentContribution:
    payload = {
        "agent_name": subtask.agent_name,
        "task_id": subtask.task_id,
        "error_type": "TimeoutError",
        "error_message": message,
    }
    return AgentContribution(
        contribution_id=f"shadow_swarm:{subtask.task_id}",
        agent_name=subtask.agent_name,
        status="failed",
        required=subtask.required,
        summary=f"TimeoutError: {message}",
        claims=[],
        constraints={"requested_tools": list(subtask.requested_tools)},
        conflicts=["worker_timeout"],
        missing_facts=[subtask.agent_name],
        input_ref=subtask.input_ref,
        output_hash=_hash_payload(payload),
        failure_policy_applied=subtask.failure_policy,
        trace_ref=subtask.trace_ref,
        migration_stage="shadow_swarm",
    )


def _not_configured_contribution(subtask: SubTask) -> AgentContribution:
    payload = {
        "agent_name": subtask.agent_name,
        "task_id": subtask.task_id,
        "error_type": "WorkerNotConfigured",
    }
    return AgentContribution(
        contribution_id=f"shadow_swarm:{subtask.task_id}",
        agent_name=subtask.agent_name,
        status="skipped",
        required=subtask.required,
        summary="shadow worker implementation is not configured",
        claims=[],
        constraints={"requested_tools": list(subtask.requested_tools)},
        conflicts=["worker.not_configured"],
        missing_facts=[subtask.agent_name],
        input_ref=subtask.input_ref,
        output_hash=_hash_payload(payload),
        failure_policy_applied=subtask.failure_policy,
        trace_ref=subtask.trace_ref,
        migration_stage="shadow_swarm",
    )


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
