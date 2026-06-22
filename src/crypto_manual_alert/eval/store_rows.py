from __future__ import annotations

import json
from typing import Any, Mapping

from .schema import EvalCase, EvalFrozenInput


def dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def load_json(text: str | None) -> Any:
    if not text:
        return None
    return json.loads(text)


def run_row(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = load_json(data.pop("metadata_json"))
    return data


def case_to_row(case: EvalCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "dataset_name": case.dataset_name,
        "source_trace_id": case.source_trace_id,
        "source_badcase_id": case.source_badcase_id,
        "created_at": case.created_at,
        "symbol": case.symbol,
        "horizon": case.horizon,
        "failure_category": case.failure_category,
        "severity": case.severity,
        "expected_behavior": case.expected_behavior,
        "actual_behavior": case.actual_behavior,
        "summary": case.summary,
        "status": case.status,
        "frozen_input_hash": case.frozen_input_hash,
        "input_summary": case.input_summary,
        "metadata": case.metadata,
    }


def case_row(row: Mapping[str, Any]) -> EvalCase:
    return EvalCase(
        case_id=str(row["case_id"]),
        dataset_name=str(row["dataset_name"]),
        source_trace_id=str(row["source_trace_id"]),
        source_badcase_id=int(row["source_badcase_id"]),
        created_at=str(row["created_at"]),
        symbol=str(row["symbol"]),
        horizon=row["horizon"],
        failure_category=str(row["failure_category"]),
        severity=str(row["severity"]),
        expected_behavior=str(row["expected_behavior"]),
        actual_behavior=str(row["actual_behavior"]),
        summary=str(row["summary"]),
        status=str(row["status"]),
        frozen_input_hash=str(row["frozen_input_hash"]),
        input_summary=load_json(row["input_summary_json"]) or {},
        metadata=load_json(row["metadata_json"]) or {},
    )


def frozen_input_row(row: Mapping[str, Any]) -> EvalFrozenInput:
    return EvalFrozenInput(
        frozen_input_hash=str(row["frozen_input_hash"]),
        schema_version=int(row["schema_version"]),
        kind=str(row["kind"]),
        source_trace_id=str(row["source_trace_id"]),
        source_badcase_id=int(row["source_badcase_id"]),
        input_payload=load_json(row["input_json"]) or {},
        public_summary=load_json(row["public_summary_json"]) or {},
        metadata=load_json(row["metadata_json"]) or {},
    )


def replay_row(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["allowed"] = None if data.get("allowed") is None else bool(data["allowed"])
    data["output_payload"] = load_json(data.pop("output_json")) or {}
    data["metadata"] = load_json(data.pop("metadata_json")) or {}
    data.pop("created_at", None)
    return data


def not_run_replay_result(case_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "not_run",
        "mode": "none",
        "case_id": case_payload.get("case_id"),
        "source_trace_id": case_payload.get("source_trace_id"),
        "source_badcase_id": case_payload.get("source_badcase_id"),
        "frozen_input_hash": case_payload.get("frozen_input_hash"),
        "final_action": None,
        "allowed": None,
        "output_hash": None,
        "reason_summary": None,
        "error_message": None,
        "duration_ms": None,
        "metadata": {},
    }


def score_row(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["passed"] = bool(data["passed"])
    data["needs_human_review"] = bool(data["needs_human_review"])
    data["evidence_refs"] = load_json(data.pop("evidence_refs_json")) or []
    data["metadata"] = load_json(data.pop("metadata_json"))
    return data
