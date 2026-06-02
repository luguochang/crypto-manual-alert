from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from crypto_manual_alert.agent_swarm.runtime import RuntimeWorker
from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.contracts import SubTask
from crypto_manual_alert.orchestration.runtime import AgentRunRequest
from crypto_manual_alert.skills.facade import SkillTaskContext
from crypto_manual_alert.skills.tool_budget import ToolBudget


class LlmShadowClient(Protocol):
    def complete(self, payload: dict[str, Any], *, timeout_seconds: float | None = None) -> str:
        ...


class SkillToolExecutor(Protocol):
    def execute(
        self,
        *,
        worker_name: str,
        context: SkillTaskContext,
        budget: ToolBudget,
    ) -> Any:
        ...


class LlmWorkerOutputError(ValueError):
    pass


RESERVED_MODEL_CONSTRAINT_KEYS = {
    "decision_effect",
    "requested_skills",
    "requested_tools",
    "tool" + "_audit_results",
    "tool_call_artifact_refs",
    "tool_call_artifacts",
    "tool_execution_mode",
}


@dataclass(frozen=True)
class LlmToolShadowWorker:
    """Shadow-only LLM/tool worker adapter.

    This adapter converts one bounded worker task into one AgentContribution.
    It does not make final decisions, place orders, write journals, or feed the
    FinalDecisionAgent. Tool access remains governed by the SubTask requested
    tools and Harness validation.
    """

    client: LlmShadowClient
    tool_executor: SkillToolExecutor | None = None
    max_tool_calls: int = 0
    clock: Callable[[], float] = time.monotonic

    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        request_payload = _request_payload(subtask, input_view, tool_executor=self.tool_executor)
        deadline_at = _deadline_at(self.clock, subtask.timeout_seconds)
        raw_output = self.client.complete(request_payload, timeout_seconds=subtask.timeout_seconds)
        payload = _parse_output(raw_output)
        summary = _required_text(payload, "summary")
        claims = _list_of_dicts(payload.get("claims"), field_name="claims")
        constraints = _sanitize_model_constraints(_dict_or_empty(payload.get("constraints")))
        tool_call_artifact_refs = _execute_skill_requests(
            _requested_skill_calls(payload),
            subtask=subtask,
            input_view=input_view,
            tool_executor=self.tool_executor,
            timeout_seconds=subtask.timeout_seconds,
            deadline_at=deadline_at,
            max_tool_calls=self.max_tool_calls,
            clock=self.clock,
        )
        conflicts = [str(item) for item in payload.get("conflicts") or []]
        missing_facts = [str(item) for item in payload.get("missing_facts") or []]
        normalized_constraints = {
            "requested_tools": list(subtask.requested_tools),
            "tool_execution_mode": "executor" if self.tool_executor is not None else "disabled",
            **constraints,
            "decision_effect": "none",
        }
        output_payload = {
            "agent_name": subtask.agent_name,
            "task_id": subtask.task_id,
            "summary": summary,
            "claims": claims,
            "constraints": normalized_constraints,
            "conflicts": conflicts,
            "missing_facts": missing_facts,
            "tool_call_artifact_refs": tool_call_artifact_refs,
        }
        return AgentContribution(
            contribution_id=f"llm_tool_shadow:{subtask.task_id}",
            agent_name=subtask.agent_name,
            status=str(payload.get("status") or "ok"),
            required=subtask.required,
            summary=summary,
            claims=claims,
            constraints=normalized_constraints,
            conflicts=conflicts,
            missing_facts=missing_facts,
            input_ref=subtask.input_ref,
            output_hash=_hash_payload(output_payload),
            failure_policy_applied=str(payload.get("failure_policy_applied") or "none"),
            trace_ref=subtask.trace_ref,
            tool_call_artifact_refs=tool_call_artifact_refs,
            migration_stage="llm_tool_shadow_worker",
        )

    def as_runtime_worker(self, subtask: SubTask) -> RuntimeWorker:
        return _RuntimeAdapter(self, subtask)


class _RuntimeAdapter:
    def __init__(self, worker: LlmToolShadowWorker, subtask: SubTask):
        self.worker = worker
        self.subtask = subtask

    def run(self, request: AgentRunRequest) -> AgentContribution:
        subtask = SubTask(
            task_id=self.subtask.task_id,
            agent_name=self.subtask.agent_name,
            role=self.subtask.role,
            input_ref=self.subtask.input_ref,
            input_view=dict(request.input_view),
            required=self.subtask.required,
            timeout_seconds=request.timeout_seconds,
            failure_policy=self.subtask.failure_policy,
            trace_ref=self.subtask.trace_ref,
            requested_tools=self.subtask.requested_tools,
        )
        return self.worker.run(subtask, dict(request.input_view))


def _request_payload(
    subtask: SubTask,
    input_view: dict[str, Any],
    *,
    tool_executor: SkillToolExecutor | None,
) -> dict[str, Any]:
    return {
        "decision_effect": "none",
        "agent_name": subtask.agent_name,
        "task_id": subtask.task_id,
        "role": subtask.role,
        "input_ref": subtask.input_ref,
        "trace_ref": subtask.trace_ref,
        "requested_tools": list(subtask.requested_tools),
        "tool_execution_policy": {
            "mode": "executor" if tool_executor is not None else "disabled",
            "requested_tools": list(subtask.requested_tools),
            "decision_effect": "none",
        },
            "allowed_output_contract": {
                "required_keys": ["summary"],
            "optional_keys": [
                "claims",
                "constraints",
                "conflicts",
                "missing_facts",
                "status",
                "skill_requests",
            ],
            "forbidden": ["main_action", "entry_trigger", "stop_price", "target_1", "target_2", "risk_verdict"],
        },
        "input_view": json.loads(json.dumps(input_view, ensure_ascii=False, default=str)),
    }


def _parse_output(raw_output: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(raw_output).strip())
    except json.JSONDecodeError as exc:
        raise LlmWorkerOutputError("LLM worker output must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise LlmWorkerOutputError("LLM worker output must be a JSON object")
    return payload


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LlmWorkerOutputError(f"{key} is required")
    return value.strip()


def _list_of_dicts(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise LlmWorkerOutputError(f"{field_name} must be a list of objects")
    return [dict(item) for item in value]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LlmWorkerOutputError("constraints must be an object")
    return dict(value)


def _sanitize_model_constraints(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in RESERVED_MODEL_CONSTRAINT_KEYS
    }


def _requested_skill_calls(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    legacy_field_name = "tool" + "_requests"
    if legacy_field_name in payload:
        raise LlmWorkerOutputError("legacy tool calls are no longer supported; use skill_requests")
    field_name = "skill_requests"
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise LlmWorkerOutputError(f"{field_name} must be a list of objects")
    return [dict(item) for item in value] or None


def _execute_skill_requests(
    value: Any,
    *,
    subtask: SubTask,
    input_view: dict[str, Any],
    tool_executor: SkillToolExecutor | None,
    timeout_seconds: float | None,
    deadline_at: float | None,
    max_tool_calls: int,
    clock: Callable[[], float],
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise LlmWorkerOutputError("skill_requests must be a list of objects")
    if not value:
        return []
    if tool_executor is None:
        raise LlmWorkerOutputError("skill execution is disabled")
    allowed_call_count = max(0, int(max_tool_calls))
    if len(value) > allowed_call_count:
        raise LlmWorkerOutputError("skill request count exceeds budget")

    allowed_tools = set(subtask.requested_tools)
    tool_call_artifact_refs: list[dict[str, Any]] = []
    skill_budget = ToolBudget(max_calls=allowed_call_count)
    for request in value:
        remaining_timeout = _remaining_timeout(clock, deadline_at, fallback=timeout_seconds)
        skill_name = str(request.get("skill_name") or "")
        if skill_name:
            if skill_name not in allowed_tools:
                raise LlmWorkerOutputError(f"skill is not requested for this worker: {skill_name}")
            artifact = tool_executor.execute(
                worker_name=subtask.agent_name,
                context=SkillTaskContext(
                    skill_name=skill_name,
                    task_id=f"skill:{skill_name}",
                    symbol=str(input_view.get("symbol") or subtask.input_view.get("symbol") or ""),
                    trace_id=str(input_view.get("trace_id") or _trace_id_from_subtask(subtask)),
                    query=str((request.get("arguments") or {}).get("query") or input_view.get("query") or ""),
                    input_view=dict(input_view),
                    timeout_seconds=max(1, int(remaining_timeout or timeout_seconds or subtask.timeout_seconds)),
                ),
                budget=skill_budget,
            )
            if not hasattr(artifact, "to_public_dict"):
                raise LlmWorkerOutputError("skill executor result must be a ToolCallArtifact")
            tool_call_artifact_refs.append(artifact.to_public_dict())
            continue
        raise LlmWorkerOutputError("skill_requests[].skill_name is required")
    return tool_call_artifact_refs


def _deadline_at(clock: Callable[[], float], timeout_seconds: float | None) -> float | None:
    if timeout_seconds is None:
        return None
    return clock() + max(0.0, float(timeout_seconds))


def _remaining_timeout(
    clock: Callable[[], float],
    deadline_at: float | None,
    *,
    fallback: float | None,
) -> float | None:
    if deadline_at is None:
        return fallback
    remaining = deadline_at - clock()
    if remaining <= 0:
        raise LlmWorkerOutputError("skill request deadline expired")
    return remaining


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _trace_id_from_subtask(subtask: SubTask) -> str:
    if ":shadow:" in subtask.trace_ref:
        return subtask.trace_ref.split(":shadow:", 1)[0]
    return subtask.trace_ref.split(":", 1)[0]
