from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
