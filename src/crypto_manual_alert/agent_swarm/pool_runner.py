from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
import time
from typing import Any, Callable, Generic, TypeVar

from crypto_manual_alert.orchestration.harness import HarnessValidationResult


ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class AgentPoolTask(Generic[ResultT]):
    """One schedulable controlled agent task.

    The pool runner owns preflight, bounded concurrency, timeout handling, and
    result ordering. It does not know trading semantics, build contributions, or
    write shared context.
    """

    task_id: str
    timeout_seconds: float
    preflight: HarnessValidationResult
    run: Callable[[], ResultT]
    rejected_result: Callable[[list[dict[str, Any]]], ResultT]
    timeout_result: Callable[[], ResultT]


@dataclass
class ControlledAgentPoolRunner:
    """Run controlled agent tasks with deterministic ordering and bounded parallelism."""

    max_parallel_workers: int = 1
    deadline_ms: int | None = None
    preflight_violations: list[dict[str, Any]] = field(default_factory=list, init=False)

    def run(self, tasks: list[AgentPoolTask[ResultT]]) -> list[ResultT]:
        self.preflight_violations = []
        if not tasks:
            return []

        results_by_task_id: dict[str, ResultT] = {}
        runnable_tasks: list[AgentPoolTask[ResultT]] = []
        for task in tasks:
            if task.preflight.passed:
                runnable_tasks.append(task)
                continue
            self.preflight_violations.extend(task.preflight.violations)
            results_by_task_id[task.task_id] = task.rejected_result(list(task.preflight.violations))

        if runnable_tasks:
            max_workers = max(1, min(len(runnable_tasks), int(self.max_parallel_workers or 1)))
            deadline_at = self._deadline_at()
            executor = ThreadPoolExecutor(max_workers=max_workers)
            try:
                future_by_task_id = {task.task_id: executor.submit(task.run) for task in runnable_tasks}
                for task in tasks:
                    if task.task_id in results_by_task_id:
                        continue
                    future = future_by_task_id[task.task_id]
                    if future.done():
                        results_by_task_id[task.task_id] = future.result(timeout=0)
                        continue
                    remaining_deadline = self._remaining_deadline_seconds(deadline_at)
                    if remaining_deadline is not None and remaining_deadline <= 0:
                        future.cancel()
                        results_by_task_id[task.task_id] = task.timeout_result()
                        continue
                    try:
                        timeout_seconds = task.timeout_seconds
                        if remaining_deadline is not None:
                            timeout_seconds = min(timeout_seconds, remaining_deadline)
                        results_by_task_id[task.task_id] = future.result(timeout=timeout_seconds)
                    except FutureTimeoutError:
                        future.cancel()
                        results_by_task_id[task.task_id] = task.timeout_result()
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return [results_by_task_id[task.task_id] for task in tasks]

    def _deadline_at(self) -> float | None:
        if self.deadline_ms is None:
            return None
        return time.perf_counter() + max(0.0, float(self.deadline_ms) / 1000.0)

    @staticmethod
    def _remaining_deadline_seconds(deadline_at: float | None) -> float | None:
        if deadline_at is None:
            return None
        return deadline_at - time.perf_counter()
