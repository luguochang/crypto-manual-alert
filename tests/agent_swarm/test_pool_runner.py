from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from crypto_manual_alert.agent_swarm.pool_runner import AgentPoolTask, ControlledAgentPoolRunner
from crypto_manual_alert.orchestration.harness import HarnessValidationResult


@dataclass(frozen=True)
class PoolResult:
    task_id: str
    status: str
    error: str | None = None


def test_controlled_agent_pool_runner_preserves_order_and_limits_parallelism():
    active = 0
    max_active = 0
    lock = threading.Lock()

    def run(task_id: str) -> PoolResult:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return PoolResult(task_id=task_id, status="ok")

    tasks = [
        AgentPoolTask(
            task_id=f"task-{index}",
            timeout_seconds=1,
            preflight=HarnessValidationResult(passed=True, severity="ok"),
            run=lambda task_id=f"task-{index}": run(task_id),
            rejected_result=lambda violations, task_id=f"task-{index}": PoolResult(task_id, "rejected"),
            timeout_result=lambda task_id=f"task-{index}": PoolResult(task_id, "timeout"),
        )
        for index in range(4)
    ]

    results = ControlledAgentPoolRunner(max_parallel_workers=2).run(tasks)

    assert [result.task_id for result in results] == ["task-0", "task-1", "task-2", "task-3"]
    assert [result.status for result in results] == ["ok", "ok", "ok", "ok"]
    assert max_active <= 2


def test_controlled_agent_pool_runner_rejects_preflight_without_running_task():
    calls: list[str] = []
    violation = {"agent_name": "RootCauseAgent", "rule_id": "agent.tool_not_allowed"}
    tasks = [
        AgentPoolTask(
            task_id="task-rejected",
            timeout_seconds=1,
            preflight=HarnessValidationResult(passed=False, severity="hard_fail", violations=[violation]),
            run=lambda: calls.append("ran") or PoolResult("task-rejected", "ok"),
            rejected_result=lambda violations: PoolResult(
                task_id="task-rejected",
                status="rejected",
                error=str(violations[0]["rule_id"]),
            ),
            timeout_result=lambda: PoolResult("task-rejected", "timeout"),
        )
    ]

    results = ControlledAgentPoolRunner(max_parallel_workers=1).run(tasks)

    assert calls == []
    assert results == [PoolResult(task_id="task-rejected", status="rejected", error="agent.tool_not_allowed")]


def test_controlled_agent_pool_runner_times_out_without_waiting_for_slow_task():
    tasks = [
        AgentPoolTask(
            task_id="task-slow",
            timeout_seconds=0.01,
            preflight=HarnessValidationResult(passed=True, severity="ok"),
            run=lambda: time.sleep(0.2) or PoolResult("task-slow", "late"),
            rejected_result=lambda violations: PoolResult("task-slow", "rejected"),
            timeout_result=lambda: PoolResult("task-slow", "timeout", "worker timed out"),
        )
    ]

    started = time.perf_counter()
    results = ControlledAgentPoolRunner(max_parallel_workers=1).run(tasks)
    duration = time.perf_counter() - started

    assert duration < 0.15
    assert results == [PoolResult(task_id="task-slow", status="timeout", error="worker timed out")]


def test_controlled_agent_pool_runner_timeout_is_audit_envelope_not_external_call_cancellation():
    completed = threading.Event()

    def slow_external_call() -> PoolResult:
        time.sleep(0.08)
        completed.set()
        return PoolResult("task-slow", "late")

    tasks = [
        AgentPoolTask(
            task_id="task-slow",
            timeout_seconds=0.01,
            preflight=HarnessValidationResult(passed=True, severity="ok"),
            run=slow_external_call,
            rejected_result=lambda violations: PoolResult("task-slow", "rejected"),
            timeout_result=lambda: PoolResult("task-slow", "timeout", "worker timed out"),
        )
    ]

    results = ControlledAgentPoolRunner(max_parallel_workers=1).run(tasks)

    assert results == [PoolResult(task_id="task-slow", status="timeout", error="worker timed out")]
    assert completed.wait(timeout=0.3) is True


def test_controlled_agent_pool_runner_applies_global_deadline_across_tasks():
    tasks = [
        AgentPoolTask(
            task_id=f"task-{index}",
            timeout_seconds=1,
            preflight=HarnessValidationResult(passed=True, severity="ok"),
            run=lambda index=index: time.sleep(0.2) or PoolResult(f"task-{index}", "late"),
            rejected_result=lambda violations, index=index: PoolResult(f"task-{index}", "rejected"),
            timeout_result=lambda index=index: PoolResult(f"task-{index}", "timeout", "global deadline exceeded"),
        )
        for index in range(2)
    ]

    started = time.perf_counter()
    results = ControlledAgentPoolRunner(max_parallel_workers=1, deadline_ms=50).run(tasks)
    duration = time.perf_counter() - started

    assert duration < 0.15
    assert [result.status for result in results] == ["timeout", "timeout"]
    assert {result.error for result in results} == {"global deadline exceeded"}


def test_controlled_agent_pool_runner_keeps_done_result_after_deadline_is_spent():
    fast_started = threading.Event()

    def slow_task() -> PoolResult:
        fast_started.wait(timeout=0.2)
        time.sleep(0.08)
        return PoolResult("task-slow", "late")

    def fast_task() -> PoolResult:
        fast_started.set()
        return PoolResult("task-fast", "ok")

    tasks = [
        AgentPoolTask(
            task_id="task-slow",
            timeout_seconds=1,
            preflight=HarnessValidationResult(passed=True, severity="ok"),
            run=slow_task,
            rejected_result=lambda violations: PoolResult("task-slow", "rejected"),
            timeout_result=lambda: PoolResult("task-slow", "timeout", "global deadline exceeded"),
        ),
        AgentPoolTask(
            task_id="task-fast",
            timeout_seconds=1,
            preflight=HarnessValidationResult(passed=True, severity="ok"),
            run=fast_task,
            rejected_result=lambda violations: PoolResult("task-fast", "rejected"),
            timeout_result=lambda: PoolResult("task-fast", "timeout", "global deadline exceeded"),
        ),
    ]

    results = ControlledAgentPoolRunner(max_parallel_workers=2, deadline_ms=20).run(tasks)

    assert results == [
        PoolResult("task-slow", "timeout", "global deadline exceeded"),
        PoolResult("task-fast", "ok"),
    ]
