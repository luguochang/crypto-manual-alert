from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalFrozenInput:
    frozen_input_hash: str
    schema_version: int
    kind: str
    source_trace_id: str
    source_badcase_id: int
    input_payload: dict[str, Any]
    public_summary: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalReplayOutput:
    replay_id: str
    case_id: str
    source_trace_id: str
    source_badcase_id: int
    frozen_input_hash: str
    status: str
    mode: str
    final_action: str | None = None
    allowed: bool | None = None
    output_hash: str | None = None
    reason_summary: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    output_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "case_id": self.case_id,
            "source_trace_id": self.source_trace_id,
            "source_badcase_id": self.source_badcase_id,
            "frozen_input_hash": self.frozen_input_hash,
            "status": self.status,
            "mode": self.mode,
            "final_action": self.final_action,
            "allowed": self.allowed,
            "output_hash": self.output_hash,
            "reason_summary": self.reason_summary,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EvalCase:
    """一次可评估样本的冻结摘要。

    首版 case 来源是 badcase + trace detail，不复制 raw_decision 或完整 LLM payload。
    """

    case_id: str
    dataset_name: str
    source_trace_id: str
    source_badcase_id: int
    created_at: str
    symbol: str
    horizon: str | None
    failure_category: str
    severity: str
    expected_behavior: str
    actual_behavior: str
    summary: str
    status: str
    frozen_input_hash: str
    input_summary: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalScore:
    """单个 judge 对单个 case 的结构化评分。"""

    score_id: str
    eval_run_id: str
    case_id: str
    source_trace_id: str
    source_badcase_id: int
    judge_name: str
    judge_type: str
    passed: bool
    severity: str
    failure_category: str
    reason_summary: str
    evidence_refs: list[str]
    score: float | None = None
    needs_human_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalRun:
    """旁路 eval run 摘要。"""

    eval_run_id: str
    dataset_name: str
    mode: str
    status: str
    started_at: str
    ended_at: str | None
    case_count: int
    pass_count: int
    fail_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
