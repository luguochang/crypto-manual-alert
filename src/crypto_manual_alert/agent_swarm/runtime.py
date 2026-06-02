from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Protocol

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.harness import HarnessPolicy, HarnessValidationResult, validate_agent_run_request
from crypto_manual_alert.orchestration.runtime import AgentRunRequest, AgentRunResult


@dataclass(frozen=True)
class AgentRunnerOutput:
    result: AgentRunResult
    contribution: AgentContribution


class RuntimeWorker(Protocol):
    def run(self, request: AgentRunRequest) -> AgentContribution:
        ...


@dataclass
class AgentRunner:
    """Execute one worker request and normalize failures into audit artifacts."""

    recorder: Any | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None

    def run_one(
        self,
        request: AgentRunRequest,
        worker: RuntimeWorker,
        *,
        catch_exceptions: bool = True,
        span_name: str | None = None,
        span_metadata: dict[str, Any] | None = None,
    ) -> AgentRunnerOutput:
        if self.recorder is not None and self.trace_id and span_name:
            try:
                with self.recorder.span(
                    self.trace_id,
                    span_name,
                    "agent.worker",
                    input_summary=_span_input_summary(request),
                    parent_span_id=self.parent_span_id,
                    metadata=span_metadata or {},
                ) as span:
                    output = self._run_worker(request, worker, catch_exceptions=False)
                    span.set_output(_span_output_summary(output.result))
                    return output
            except Exception as exc:  # noqa: BLE001 - span records error; output keeps audit non-blocking.
                if not catch_exceptions:
                    raise
                contribution = _failed_contribution(request, exc)
                return AgentRunnerOutput(
                    result=_result_from_contribution(request, contribution, error=exc),
                    contribution=contribution,
                )
        return self._run_worker(request, worker, catch_exceptions=catch_exceptions)

    def _run_worker(
        self,
        request: AgentRunRequest,
        worker: RuntimeWorker,
        *,
        catch_exceptions: bool,
    ) -> AgentRunnerOutput:
        try:
            contribution = worker.run(request)
        except Exception as exc:  # noqa: BLE001 - worker failures must stay inside the result envelope.
            if not catch_exceptions:
                raise
            contribution = _failed_contribution(request, exc)
            return AgentRunnerOutput(
                result=_result_from_contribution(request, contribution, error=exc),
                contribution=contribution,
            )
        mismatch = _identity_mismatches(request, contribution)
        if mismatch:
            exc = AgentContributionIdentityMismatch("worker contribution does not match AgentRunRequest")
            contribution = _identity_mismatch_contribution(request, mismatch)
            return AgentRunnerOutput(
                result=_result_from_contribution(request, contribution, error=exc),
                contribution=contribution,
            )
        return AgentRunnerOutput(
            result=_result_from_contribution(request, contribution, error=None),
            contribution=contribution,
        )


def validate_agent_run_request_contract(
    policy: HarnessPolicy, request: AgentRunRequest
) -> HarnessValidationResult:
    return validate_agent_run_request(
        policy,
        agent_name=request.agent_name,
        requested_tools=request.requested_tools,
    )


def _result_from_contribution(
    request: AgentRunRequest, contribution: AgentContribution, *, error: Exception | None
) -> AgentRunResult:
    return AgentRunResult(
        task_id=request.task_id,
        agent_name=request.agent_name,
        status=contribution.status,
        contribution_ref=str(contribution.input_ref or request.input_ref),
        output_hash=contribution.output_hash,
        trace_ref=contribution.trace_ref or request.trace_ref,
        failure_policy_applied=contribution.failure_policy_applied,
        required=request.required,
        decision_effect=request.decision_effect,
        input_view_hash=hash_agent_run_request_input_view(request),
        agent_run_request_hash=hash_agent_run_request(request),
        error=None if error is None else {"type": type(error).__name__, "message": str(error)},
    )


def _span_input_summary(request: AgentRunRequest) -> dict[str, Any]:
    return {
        "task_id": request.task_id,
        "agent_name": request.agent_name,
        "decision_effect": request.decision_effect,
    }


def _span_output_summary(result: AgentRunResult) -> dict[str, Any]:
    return {
        "task_id": result.task_id,
        "agent_name": result.agent_name,
        "status": result.status,
        "decision_effect": result.decision_effect,
    }


def _failed_contribution(request: AgentRunRequest, exc: Exception) -> AgentContribution:
    payload = {
        "agent_name": request.agent_name,
        "task_id": request.task_id,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
    return AgentContribution(
        contribution_id=f"agent_runtime:{request.task_id}",
        agent_name=request.agent_name,
        status="failed",
        required=request.required,
        summary=f"{type(exc).__name__}: {exc}",
        claims=[],
        constraints={"requested_tools": list(request.requested_tools)},
        conflicts=[f"worker_error:{type(exc).__name__}"],
        missing_facts=[request.agent_name],
        input_ref=request.input_ref,
        output_hash=_hash_payload(payload),
        failure_policy_applied=request.failure_policy,
        trace_ref=request.trace_ref,
        migration_stage="agent_runtime",
    )


class AgentContributionIdentityMismatch(ValueError):
    pass


def _identity_mismatches(request: AgentRunRequest, contribution: AgentContribution) -> list[dict[str, str]]:
    checks = (
        ("agent_name", request.agent_name, contribution.agent_name),
        ("input_ref", request.input_ref, contribution.input_ref),
        ("trace_ref", request.trace_ref, contribution.trace_ref),
    )
    return [
        {"field": field_name, "expected": str(expected), "actual": str(actual)}
        for field_name, expected, actual in checks
        if actual != expected
    ]


def _identity_mismatch_contribution(
    request: AgentRunRequest, mismatches: list[dict[str, str]]
) -> AgentContribution:
    payload = {
        "agent_name": request.agent_name,
        "task_id": request.task_id,
        "error_type": "AgentContributionIdentityMismatch",
        "mismatches": mismatches,
    }
    return AgentContribution(
        contribution_id=f"agent_runtime:{request.task_id}",
        agent_name=request.agent_name,
        status="failed",
        required=request.required,
        summary="AgentContributionIdentityMismatch: worker contribution does not match AgentRunRequest",
        claims=[],
        constraints={
            "requested_tools": list(request.requested_tools),
            "identity_mismatches": mismatches,
        },
        conflicts=["agent_runtime.identity_mismatch"],
        missing_facts=[request.agent_name],
        input_ref=request.input_ref,
        output_hash=_hash_payload(payload),
        failure_policy_applied=request.failure_policy,
        trace_ref=request.trace_ref,
        migration_stage="agent_runtime",
    )


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def hash_agent_run_request_input_view(request: AgentRunRequest) -> str:
    """Hash the safe/redacted worker input view for replay coverage."""

    return _hash_payload(request.input_view)


def hash_agent_run_request(request: AgentRunRequest) -> str:
    """Hash the replay-relevant worker request envelope without raw output."""

    return _hash_payload(request.to_public_dict())
