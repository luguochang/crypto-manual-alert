from __future__ import annotations

import json
import threading
import time
from dataclasses import replace

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.harness import load_harness_policy
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.orchestration.contracts import LeadPlan, SubTask
from crypto_manual_alert.agent_swarm.shadow_runner import (
    ShadowSwarmRunner,
    build_default_lead_plan,
)


class StubWorker:
    def __init__(self, summary: str):
        self.summary = summary

    def run(self, subtask: SubTask, input_view: dict[str, object]) -> AgentContribution:
        return AgentContribution(
            contribution_id=f"stub:{subtask.task_id}",
            agent_name=subtask.agent_name,
            status="ok",
            required=subtask.required,
            summary=f"{self.summary}:{input_view['symbol']}",
            input_ref=subtask.input_ref,
            output_hash="sha256:stub",
            failure_policy_applied="none",
            trace_ref=subtask.trace_ref,
            migration_stage="shadow_swarm",
        )


class FailingWorker:
    def run(self, subtask: SubTask, input_view: dict[str, object]) -> AgentContribution:
        raise RuntimeError(f"{subtask.agent_name} failed")


class BarrierWorker:
    def __init__(self, barrier: threading.Barrier):
        self.barrier = barrier

    def run(self, subtask: SubTask, input_view: dict[str, object]) -> AgentContribution:
        self.barrier.wait(timeout=1)
        return AgentContribution(
            contribution_id=f"barrier:{subtask.task_id}",
            agent_name=subtask.agent_name,
            status="ok",
            required=subtask.required,
            summary=f"parallel:{subtask.agent_name}",
            input_ref=subtask.input_ref,
            output_hash="sha256:barrier",
            failure_policy_applied="none",
            trace_ref=subtask.trace_ref,
            migration_stage="shadow_swarm",
        )


class CountingWorker:
    def __init__(self):
        self.calls = 0

    def run(self, subtask: SubTask, input_view: dict[str, object]) -> AgentContribution:
        self.calls += 1
        return AgentContribution(
            contribution_id=f"counting:{subtask.task_id}",
            agent_name=subtask.agent_name,
            status="ok",
            required=subtask.required,
            summary="should not run when preflight fails",
            input_ref=subtask.input_ref,
            output_hash="sha256:counting",
            failure_policy_applied="none",
            trace_ref=subtask.trace_ref,
            migration_stage="shadow_swarm",
        )


class SlowWorker:
    def __init__(self, sleep_seconds: float):
        self.sleep_seconds = sleep_seconds

    def run(self, subtask: SubTask, input_view: dict[str, object]) -> AgentContribution:
        time.sleep(self.sleep_seconds)
        return AgentContribution(
            contribution_id=f"slow:{subtask.task_id}",
            agent_name=subtask.agent_name,
            status="ok",
            required=subtask.required,
            summary="late result",
            input_ref=subtask.input_ref,
            output_hash="sha256:slow",
            failure_policy_applied="none",
            trace_ref=subtask.trace_ref,
            migration_stage="shadow_swarm",
        )


class MutatingWorker:
    def run(self, subtask: SubTask, input_view: dict[str, object]) -> AgentContribution:
        snapshot = input_view["snapshot"]
        assert isinstance(snapshot, dict)
        unavailable = snapshot["unavailable"]
        assert isinstance(unavailable, list)
        unavailable.append("mark: mutated by worker")
        points = snapshot["points"]
        assert isinstance(points, dict)
        mark = points["mark"]
        assert isinstance(mark, dict)
        mark["value"] = -1
        return AgentContribution(
            contribution_id=f"mutating:{subtask.task_id}",
            agent_name=subtask.agent_name,
            status="ok",
            required=subtask.required,
            summary="mutated local input view",
            input_ref=subtask.input_ref,
            output_hash="sha256:mutating",
            failure_policy_applied="none",
            trace_ref=subtask.trace_ref,
            migration_stage="shadow_swarm",
        )


def test_default_shadow_lead_plan_builds_independent_worker_tasks():
    policy = load_harness_policy("shadow_audit")

    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1", policy=policy)
    first_request = lead_plan.tasks[0].to_agent_run_request(run_id=lead_plan.plan_id)

    assert isinstance(lead_plan, LeadPlan)
    assert lead_plan.mode == "shadow"
    assert lead_plan.decision_effect == "none"
    assert [task.agent_name for task in lead_plan.tasks] == [
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "MarketSentimentAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    ]
    assert len({task.task_id for task in lead_plan.tasks}) == 7
    assert all(task.input_ref == "trace:trace-1:shadow_swarm_input" for task in lead_plan.tasks)
    assert all(task.failure_policy == "soft_downgrade" for task in lead_plan.tasks)
    assert all(task.timeout_seconds == policy.agent_policy(task.agent_name).timeout_seconds for task in lead_plan.tasks)
    assert all(task.requested_tools == () for task in lead_plan.tasks)
    assert first_request.run_id == lead_plan.plan_id
    assert first_request.agent_name == "LiveFactAgent"
    assert first_request.decision_effect == "none"
    assert first_request.input_ref == "trace:trace-1:shadow_swarm_input"
    assert first_request.requested_tools == ()


def test_shadow_swarm_runner_records_worker_results_without_decision_effect():
    policy = load_harness_policy("shadow_audit")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1", policy=policy)
    workers = {task.agent_name: StubWorker(task.agent_name) for task in lead_plan.tasks}

    audit = ShadowSwarmRunner(policy=policy, workers=workers).run(lead_plan)

    assert audit.mode == "shadow"
    assert audit.decision_effect == "none"
    assert audit.worker_count == 7
    assert audit.failed_workers == []
    assert [result.agent_name for result in audit.worker_results] == [task.agent_name for task in lead_plan.tasks]
    assert all(result.status == "ok" for result in audit.worker_results)
    assert all(result.trace_ref == f"trace-1:{result.task_id}" for result in audit.worker_results)
    assert all(result.contribution.migration_stage == "shadow_swarm" for result in audit.worker_results)
    assert audit.harness_validation.passed is True
    public = audit.to_public_dict()
    assert public["decision_effect"] == "none"
    assert public["lead_plan"]["tasks"][0]["task_id"] == lead_plan.tasks[0].task_id
    assert public["worker_results"][0]["agent_run_result"]["decision_effect"] == "none"
    assert public["worker_results"][0]["agent_run_result"]["output_hash"] == "sha256:stub"


def test_shadow_swarm_runner_turns_worker_exception_into_failed_contribution():
    policy = load_harness_policy("shadow_audit")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1", policy=policy)
    workers = {task.agent_name: StubWorker(task.agent_name) for task in lead_plan.tasks}
    workers["MarketSentimentAgent"] = FailingWorker()

    audit = ShadowSwarmRunner(policy=policy, workers=workers).run(lead_plan)

    assert audit.worker_count == 7
    assert audit.failed_workers == ["MarketSentimentAgent"]
    failed = {result.agent_name: result for result in audit.worker_results}["MarketSentimentAgent"]
    assert failed.status == "failed"
    assert failed.failure_policy_applied == "soft_downgrade"
    assert failed.error == {"type": "RuntimeError", "message": "MarketSentimentAgent failed"}
    assert failed.contribution.status == "failed"
    assert "RuntimeError" in failed.contribution.summary
    assert audit.harness_validation.passed is False


def test_shadow_swarm_runner_records_failed_worker_span_as_error(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    policy = load_harness_policy("shadow_audit")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id=trace_id, policy=policy)
    workers = {task.agent_name: StubWorker(task.agent_name) for task in lead_plan.tasks}
    workers["MarketSentimentAgent"] = FailingWorker()

    audit = ShadowSwarmRunner(policy=policy, workers=workers, recorder=recorder, trace_id=trace_id).run(lead_plan)

    assert audit.worker_count == 7
    assert audit.failed_workers == ["MarketSentimentAgent"]
    with journal.connect() as conn:
        rows = conn.execute(
            "SELECT status, input_summary_json, output_summary_json, error_type, error_message "
            "FROM trace_spans WHERE span_name = 'shadow_swarm.worker'"
        ).fetchall()
    by_agent = {json.loads(row["input_summary_json"])["agent_name"]: row for row in rows}
    assert len(rows) == 7
    for row in rows:
        input_summary = json.loads(row["input_summary_json"])
        assert input_summary["task_id"]
        assert input_summary["agent_name"]
        assert input_summary["decision_effect"] == "none"
    assert by_agent["MarketSentimentAgent"]["status"] == "error"
    assert by_agent["MarketSentimentAgent"]["error_type"] == "RuntimeError"
    assert by_agent["MarketSentimentAgent"]["error_message"] == "MarketSentimentAgent failed"
    ok_agents = {agent for agent, row in by_agent.items() if row["status"] == "ok"}
    assert ok_agents == {
        "LiveFactAgent",
        "DerivativesAgent",
        "MacroEventAgent",
        "RootCauseAgent",
        "DataQualityAgent",
        "ExecutionRiskAgent",
    }
    for agent in ok_agents:
        output_summary = json.loads(by_agent[agent]["output_summary_json"])
        assert output_summary["agent_name"] == agent
        assert output_summary["status"] == "ok"
        assert output_summary["decision_effect"] == "none"


def test_shadow_swarm_runner_rejects_preflight_violation_without_calling_worker():
    policy = load_harness_policy("shadow_audit")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1", policy=policy)
    rejected_task = lead_plan.tasks[0]
    modified_tasks = (
        SubTask(
            task_id=rejected_task.task_id,
            agent_name=rejected_task.agent_name,
            role=rejected_task.role,
            input_ref=rejected_task.input_ref,
            input_view=rejected_task.input_view,
            required=rejected_task.required,
            timeout_seconds=rejected_task.timeout_seconds,
            failure_policy=rejected_task.failure_policy,
            trace_ref=rejected_task.trace_ref,
            requested_tools=("place_order",),
        ),
        *lead_plan.tasks[1:],
    )
    lead_plan = LeadPlan(
        plan_id=lead_plan.plan_id,
        mode=lead_plan.mode,
        decision_effect=lead_plan.decision_effect,
        tasks=modified_tasks,
    )
    counting_worker = CountingWorker()
    workers = {task.agent_name: StubWorker(task.agent_name) for task in lead_plan.tasks}
    workers[rejected_task.agent_name] = counting_worker

    audit = ShadowSwarmRunner(policy=policy, workers=workers).run(lead_plan)

    assert counting_worker.calls == 0
    rejected = audit.worker_results[0]
    assert rejected.agent_name == rejected_task.agent_name
    assert rejected.status == "failed"
    assert rejected.failure_policy_applied == "soft_downgrade"
    assert rejected.error == {
        "type": "HarnessPreflightRejected",
        "message": "agent.tool_not_allowed",
    }
    assert "agent.tool_not_allowed" in rejected.contribution.conflicts
    assert audit.harness_validation.passed is False


def test_shadow_swarm_runner_times_out_slow_worker_without_waiting_for_all_sleep():
    policy = load_harness_policy("shadow_audit")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1", policy=policy)
    slow_task = lead_plan.tasks[0]
    modified_tasks = (
        SubTask(
            task_id=slow_task.task_id,
            agent_name=slow_task.agent_name,
            role=slow_task.role,
            input_ref=slow_task.input_ref,
            input_view=slow_task.input_view,
            required=slow_task.required,
            timeout_seconds=0.01,
            failure_policy=slow_task.failure_policy,
            trace_ref=slow_task.trace_ref,
            requested_tools=slow_task.requested_tools,
        ),
        *lead_plan.tasks[1:],
    )
    lead_plan = LeadPlan(
        plan_id=lead_plan.plan_id,
        mode=lead_plan.mode,
        decision_effect=lead_plan.decision_effect,
        tasks=modified_tasks,
    )
    workers = {task.agent_name: StubWorker(task.agent_name) for task in lead_plan.tasks}
    workers[slow_task.agent_name] = SlowWorker(sleep_seconds=0.2)

    started = time.perf_counter()
    audit = ShadowSwarmRunner(policy=policy, workers=workers).run(lead_plan)
    duration = time.perf_counter() - started

    assert duration < 0.15
    timed_out = audit.worker_results[0]
    assert timed_out.agent_name == slow_task.agent_name
    assert timed_out.status == "failed"
    assert timed_out.error == {
        "type": "TimeoutError",
        "message": "worker timed out after 0.01s",
        "cancellation_scope": "audit_result_only",
    }
    assert timed_out.to_public_dict()["agent_run_result"]["error"] == {
        "type": "TimeoutError",
        "message": "worker timed out after 0.01s",
        "cancellation_scope": "audit_result_only",
    }
    assert "worker_timeout" in timed_out.contribution.conflicts
    assert audit.harness_validation.passed is False


def test_shadow_swarm_runner_executes_workers_concurrently():
    policy = load_harness_policy("shadow_audit")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1", policy=policy)
    lead_plan = replace(lead_plan, max_parallel_workers=len(lead_plan.tasks))
    barrier = threading.Barrier(len(lead_plan.tasks))
    workers = {task.agent_name: BarrierWorker(barrier) for task in lead_plan.tasks}

    audit = ShadowSwarmRunner(policy=policy, workers=workers).run(lead_plan)

    assert audit.worker_count == 7
    assert audit.failed_workers == []
    assert all(result.status == "ok" for result in audit.worker_results)


def test_shadow_swarm_runner_respects_lead_plan_max_parallel_workers():
    policy = load_harness_policy("shadow_audit")
    lead_plan = build_default_lead_plan(symbol="ETH-USDT-SWAP", trace_id="trace-1", policy=policy)
    lead_plan = replace(lead_plan, max_parallel_workers=2)
    active = 0
    max_active = 0
    lock = threading.Lock()

    class MeasuringWorker:
        def run(self, subtask: SubTask, input_view: dict[str, object]) -> AgentContribution:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return AgentContribution(
                contribution_id=f"measure:{subtask.task_id}",
                agent_name=subtask.agent_name,
                status="ok",
                required=subtask.required,
                summary=f"measured:{subtask.agent_name}",
                input_ref=subtask.input_ref,
                output_hash="sha256:measure",
                failure_policy_applied="none",
                trace_ref=subtask.trace_ref,
                migration_stage="shadow_swarm",
            )

    workers = {task.agent_name: MeasuringWorker() for task in lead_plan.tasks}

    audit = ShadowSwarmRunner(policy=policy, workers=workers).run(lead_plan)

    assert audit.failed_workers == []
    assert max_active <= 2


def test_shadow_swarm_runner_isolates_worker_input_from_shared_nested_payload():
    policy = load_harness_policy("shadow_audit")
    base_input_view = {
        "snapshot": {
            "unavailable": [],
            "points": {
                "mark": {"source": "okx_public", "status": "ok", "value": 3500},
            },
        },
        "facts_gate": {
            "missing_execution_facts": [],
            "blocked_action_classes": [],
        },
        "evidence_packets": [],
    }
    lead_plan = build_default_lead_plan(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        policy=policy,
        base_input_view=base_input_view,
    )
    workers = {task.agent_name: StubWorker(task.agent_name) for task in lead_plan.tasks}
    workers["RootCauseAgent"] = MutatingWorker()

    audit = ShadowSwarmRunner(policy=policy, workers=workers).run(lead_plan)

    assert audit.failed_workers == []
    assert base_input_view["snapshot"]["unavailable"] == []
    assert base_input_view["snapshot"]["points"]["mark"]["value"] == 3500
    for task in lead_plan.tasks:
        assert task.input_view["snapshot"]["unavailable"] == []
        assert task.input_view["snapshot"]["points"]["mark"]["value"] == 3500
