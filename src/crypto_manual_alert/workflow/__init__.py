"""Controlled workflow package namespace."""

import importlib
from typing import Any


_SUBMODULE_EXPORTS = {"legacy_adapter", "legacy_plan_runner", "pre_final_orchestration"}

__all__ = [
    "ControlledSwarmAuditAdapter",
    "JobLock",
    "LegacyPlanRunnerAdapter",
    "RunExecutor",
    "RunResult",
    "run_scheduler",
]


def __getattr__(name: str) -> Any:
    if name in {"RunExecutor", "RunResult"}:
        from .executor import RunExecutor, RunResult

        return {"RunExecutor": RunExecutor, "RunResult": RunResult}[name]
    if name == "ControlledSwarmAuditAdapter":
        from .controlled_adapter import ControlledSwarmAuditAdapter

        return ControlledSwarmAuditAdapter
    if name == "LegacyPlanRunnerAdapter":
        from .legacy_adapter import LegacyPlanRunnerAdapter

        return LegacyPlanRunnerAdapter
    if name in {"JobLock", "run_scheduler"}:
        from .scheduler import JobLock, run_scheduler

        return {"JobLock": JobLock, "run_scheduler": run_scheduler}[name]
    if name in _SUBMODULE_EXPORTS:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
