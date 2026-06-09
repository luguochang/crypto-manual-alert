from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolBudget:
    """Small per-worker budget guard for controlled SkillExecutor calls."""

    max_calls: int
    deadline_at: datetime | None = None
    _used_calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if type(self.max_calls) is not int or self.max_calls < 0:
            raise ValueError("max_calls must be a non-negative integer")

    def reserve(self, *, worker_name: str, skill_name: str, now: datetime) -> dict[str, object]:
        if self.deadline_at is not None and now > self.deadline_at:
            raise ValueError("tool budget deadline expired")
        if self._used_calls >= self.max_calls:
            raise ValueError("tool budget exceeded")
        self._used_calls += 1
        return {
            "worker_name": worker_name,
            "skill_name": skill_name,
            "remaining_calls": self.max_calls - self._used_calls,
        }
