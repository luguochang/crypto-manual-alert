from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRunRequest:
    """Explicit worker-agent runtime contract."""

    run_id: str
    task_id: str
    agent_name: str
    role: str
    input_ref: str
    input_view: dict[str, Any]
    requested_tools: tuple[str, ...]
    timeout_seconds: int
    required: bool
    failure_policy: str
    trace_ref: str
    decision_effect: str = "none"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "input_ref": self.input_ref,
            "input_view": dict(self.input_view),
            "requested_tools": list(self.requested_tools),
            "timeout_seconds": self.timeout_seconds,
            "required": self.required,
            "failure_policy": self.failure_policy,
            "trace_ref": self.trace_ref,
            "decision_effect": self.decision_effect,
        }


@dataclass(frozen=True)
class AgentRunResult:
    """Replayable result envelope for one worker-agent run."""

    task_id: str
    agent_name: str
    status: str
    contribution_ref: str
    output_hash: str
    trace_ref: str
    failure_policy_applied: str
    required: bool
    decision_effect: str = "none"
    input_view_hash: str | None = None
    agent_run_request_hash: str | None = None
    error: dict[str, Any] | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "status": self.status,
            "contribution_ref": self.contribution_ref,
            "input_view_hash": self.input_view_hash,
            "agent_run_request_hash": self.agent_run_request_hash,
            "output_hash": self.output_hash,
            "trace_ref": self.trace_ref,
            "failure_policy_applied": self.failure_policy_applied,
            "required": self.required,
            "decision_effect": self.decision_effect,
            "error": self.error,
        }
