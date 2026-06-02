from __future__ import annotations

from crypto_manual_alert.agent_swarm.runtime import (
    AgentRunner,
    AgentRunRequest,
    AgentRunResult,
    hash_agent_run_request,
    hash_agent_run_request_input_view,
    validate_agent_run_request_contract,
)
from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.harness import load_harness_policy
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder


def test_agent_run_request_public_dict_keeps_worker_runtime_contract_clear():
    request = AgentRunRequest(
        run_id="run-1",
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:1:shadow_input",
        input_view={"symbol": "ETH-USDT-SWAP"},
        requested_tools=(),
        timeout_seconds=10,
        required=True,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:DataQualityAgent",
        decision_effect="none",
    )

    assert request.to_public_dict() == {
        "run_id": "run-1",
        "task_id": "shadow:DataQualityAgent",
        "agent_name": "DataQualityAgent",
        "role": "data_quality_review",
        "input_ref": "trace:1:shadow_input",
        "input_view": {"symbol": "ETH-USDT-SWAP"},
        "requested_tools": [],
        "timeout_seconds": 10,
        "required": True,
        "failure_policy": "soft_downgrade",
        "trace_ref": "trace-1:shadow:DataQualityAgent",
        "decision_effect": "none",
    }


def test_agent_run_request_hashes_cover_safe_input_view():
    request = AgentRunRequest(
        run_id="run-1",
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:1:shadow_input",
        input_view={"symbol": "ETH-USDT-SWAP", "facts_gate": {"missing": []}},
        requested_tools=(),
        timeout_seconds=10,
        required=True,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:DataQualityAgent",
    )
    changed_request = AgentRunRequest(
        run_id="run-1",
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:1:shadow_input",
        input_view={"symbol": "ETH-USDT-SWAP", "facts_gate": {"missing": ["mark"]}},
        requested_tools=(),
        timeout_seconds=10,
        required=True,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:DataQualityAgent",
    )

    assert hash_agent_run_request_input_view(request).startswith("sha256:")
    assert hash_agent_run_request(request).startswith("sha256:")
    assert hash_agent_run_request_input_view(request) != hash_agent_run_request_input_view(changed_request)
    assert hash_agent_run_request(request) != hash_agent_run_request(changed_request)


def test_agent_run_request_contract_uses_harness_preflight():
    policy = load_harness_policy("shadow_audit")
    request = AgentRunRequest(
        run_id="run-1",
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:1:shadow_input",
        input_view={"symbol": "ETH-USDT-SWAP"},
        requested_tools=("web_search",),
        timeout_seconds=10,
        required=True,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:DataQualityAgent",
    )

    result = validate_agent_run_request_contract(policy, request)

    assert result.passed is False
    assert result.violations == [
        {
            "agent_name": "DataQualityAgent",
            "rule_id": "agent.tool_not_allowed",
            "requested_tools": ["web_search"],
            "allowed_tools": [],
        }
    ]


def test_agent_run_result_records_artifact_ref_without_raw_output():
    result = AgentRunResult(
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        status="ok",
        contribution_ref="trace:1:worker:DataQualityAgent",
        output_hash="sha256:worker",
        trace_ref="trace-1:shadow:DataQualityAgent",
        failure_policy_applied="none",
        required=True,
        decision_effect="none",
    )

    assert result.to_public_dict() == {
        "task_id": "shadow:DataQualityAgent",
        "agent_name": "DataQualityAgent",
        "status": "ok",
        "contribution_ref": "trace:1:worker:DataQualityAgent",
        "input_view_hash": None,
        "agent_run_request_hash": None,
        "output_hash": "sha256:worker",
        "trace_ref": "trace-1:shadow:DataQualityAgent",
        "failure_policy_applied": "none",
        "required": True,
        "decision_effect": "none",
        "error": None,
    }


class StubRuntimeWorker:
    def run(self, request: AgentRunRequest) -> AgentContribution:
        return AgentContribution(
            contribution_id=f"runtime:{request.task_id}",
            agent_name=request.agent_name,
            status="ok",
            required=request.required,
            summary=f"ran:{request.input_view['symbol']}",
            input_ref=request.input_ref,
            output_hash="sha256:runtime",
            failure_policy_applied="none",
            trace_ref=request.trace_ref,
            migration_stage="agent_runtime",
        )


class ExplodingRuntimeWorker:
    def run(self, request: AgentRunRequest) -> AgentContribution:
        raise RuntimeError(f"{request.agent_name} crashed")


class MismatchedRuntimeWorker:
    def run(self, request: AgentRunRequest) -> AgentContribution:
        return AgentContribution(
            contribution_id=f"runtime:{request.task_id}",
            agent_name="RootCauseAgent",
            status="ok",
            required=request.required,
            summary="returned another worker identity",
            input_ref="trace:other:shadow_input",
            output_hash="sha256:mismatch",
            failure_policy_applied="none",
            trace_ref="trace-other:shadow:RootCauseAgent",
            migration_stage="agent_runtime",
        )


def test_agent_runner_executes_worker_and_returns_result_envelope():
    request = AgentRunRequest(
        run_id="run-1",
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:1:shadow_input",
        input_view={"symbol": "ETH-USDT-SWAP"},
        requested_tools=(),
        timeout_seconds=10,
        required=True,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:DataQualityAgent",
    )

    output = AgentRunner().run_one(request, StubRuntimeWorker())

    assert output.result.to_public_dict() == {
        "task_id": "shadow:DataQualityAgent",
        "agent_name": "DataQualityAgent",
        "status": "ok",
        "contribution_ref": "trace:1:shadow_input",
        "input_view_hash": hash_agent_run_request_input_view(request),
        "agent_run_request_hash": hash_agent_run_request(request),
        "output_hash": "sha256:runtime",
        "trace_ref": "trace-1:shadow:DataQualityAgent",
        "failure_policy_applied": "none",
        "required": True,
        "decision_effect": "none",
        "error": None,
    }
    assert output.contribution.summary == "ran:ETH-USDT-SWAP"


def test_agent_runner_turns_worker_exception_into_failed_result():
    request = AgentRunRequest(
        run_id="run-1",
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:1:shadow_input",
        input_view={"symbol": "ETH-USDT-SWAP"},
        requested_tools=(),
        timeout_seconds=10,
        required=True,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:DataQualityAgent",
    )

    output = AgentRunner().run_one(request, ExplodingRuntimeWorker())

    assert output.result.status == "failed"
    assert output.result.error == {"type": "RuntimeError", "message": "DataQualityAgent crashed"}
    assert output.contribution.status == "failed"
    assert output.contribution.failure_policy_applied == "soft_downgrade"
    assert output.contribution.output_hash.startswith("sha256:")


def test_agent_runner_rejects_contribution_identity_or_ref_mismatch():
    request = _runtime_request()

    output = AgentRunner().run_one(request, MismatchedRuntimeWorker())

    assert output.result.status == "failed"
    assert output.result.error == {
        "type": "AgentContributionIdentityMismatch",
        "message": "worker contribution does not match AgentRunRequest",
    }
    assert output.contribution.status == "failed"
    assert output.contribution.agent_name == "DataQualityAgent"
    assert output.contribution.input_ref == "trace:1:shadow_input"
    assert output.contribution.trace_ref == "trace-1:shadow:DataQualityAgent"
    assert "agent_runtime.identity_mismatch" in output.contribution.conflicts
    assert output.contribution.constraints["identity_mismatches"] == [
        {"field": "agent_name", "expected": "DataQualityAgent", "actual": "RootCauseAgent"},
        {"field": "input_ref", "expected": "trace:1:shadow_input", "actual": "trace:other:shadow_input"},
        {
            "field": "trace_ref",
            "expected": "trace-1:shadow:DataQualityAgent",
            "actual": "trace-other:shadow:RootCauseAgent",
        },
    ]


def test_agent_runner_records_observability_span_for_success(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    request = _runtime_request()

    output = AgentRunner(recorder=recorder, trace_id=trace_id).run_one(
        request,
        StubRuntimeWorker(),
        span_name="shadow_swarm.worker",
        span_metadata={"mode": "shadow", "failure_policy": "soft_downgrade"},
    )

    assert output.result.status == "ok"
    with journal.connect() as conn:
        row = conn.execute(
            "SELECT status, input_summary_json, output_summary_json, error_type "
            "FROM trace_spans WHERE span_name = 'shadow_swarm.worker'"
        ).fetchone()
    assert row["status"] == "ok"
    assert row["error_type"] is None
    assert '"agent_name": "DataQualityAgent"' in row["input_summary_json"]
    assert '"status": "ok"' in row["output_summary_json"]


def test_agent_runner_records_error_span_while_returning_failed_result(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    request = _runtime_request()

    output = AgentRunner(recorder=recorder, trace_id=trace_id).run_one(
        request,
        ExplodingRuntimeWorker(),
        span_name="shadow_swarm.worker",
        span_metadata={"mode": "shadow", "failure_policy": "soft_downgrade"},
    )

    assert output.result.status == "failed"
    assert output.result.error == {"type": "RuntimeError", "message": "DataQualityAgent crashed"}
    with journal.connect() as conn:
        row = conn.execute(
            "SELECT status, input_summary_json, output_summary_json, error_type, error_message "
            "FROM trace_spans WHERE span_name = 'shadow_swarm.worker'"
        ).fetchone()
    assert row["status"] == "error"
    assert row["error_type"] == "RuntimeError"
    assert row["error_message"] == "DataQualityAgent crashed"
    import json

    assert json.loads(row["output_summary_json"]) is None


def _runtime_request() -> AgentRunRequest:
    return AgentRunRequest(
        run_id="run-1",
        task_id="shadow:DataQualityAgent",
        agent_name="DataQualityAgent",
        role="data_quality_review",
        input_ref="trace:1:shadow_input",
        input_view={"symbol": "ETH-USDT-SWAP"},
        requested_tools=(),
        timeout_seconds=10,
        required=True,
        failure_policy="soft_downgrade",
        trace_ref="trace-1:shadow:DataQualityAgent",
    )
