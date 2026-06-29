from __future__ import annotations

import hashlib
import json
from typing import Any

from crypto_manual_alert.journal import Journal

from .schema import EvalCase


SECRET_KEY_HINTS = (
    "api_key",
    "authorization",
    "secret",
    "token",
    "passphrase",
    "device_key",
    "bark",
    "raw_decision",
    "raw_payload",
    "request_json",
    "response_json",
)
SAFE_PARSED_PLAN_KEYS = {
    "instrument",
    "main_action",
    "horizon",
    "reference_price",
    "entry_trigger",
    "stop_price",
    "target_1",
    "target_2",
    "probability",
    "position_size_class",
    "max_leverage",
    "risk_pct",
    "manual_execution_required",
    "why_not_opposite",
    "invalidation",
    "unavailable_data",
    "notes",
}


class EvalCaseBuilder:
    """从生产 badcase/trace 构建旁路 eval case。"""

    def __init__(self, journal: Journal):
        self.journal = journal

    def list_candidates(
        self,
        *,
        dataset: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for badcase in self.journal.list_badcases(
            limit=_normalize_limit(limit),
            dataset=dataset,
            status=status,
            severity=severity,
        ):
            detail = self.journal.get_trace_detail(str(badcase["trace_id"]), include_payloads=False)
            if detail is None:
                continue
            candidates.append(_candidate_from_detail(badcase, detail))
            if len(candidates) >= _normalize_limit(limit):
                break
        return candidates

    def build_cases(
        self,
        *,
        dataset: str | None = None,
        badcase_ids: list[int] | None = None,
        limit: int = 50,
    ) -> list[EvalCase]:
        cases: list[EvalCase] = []
        clean_limit = max(_normalize_limit(limit), len(badcase_ids or []), 1)
        for badcase in self.journal.list_badcases(limit=clean_limit, ids=badcase_ids, dataset=dataset):
            detail = self.journal.get_trace_detail(str(badcase["trace_id"]), include_payloads=False)
            if detail is None:
                continue
            cases.append(_case_from_detail(badcase, detail))
            if len(cases) >= _normalize_limit(limit) and not badcase_ids:
                break
        return cases


def _candidate_from_detail(badcase: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    trace = detail["trace"]
    return {
        "id": badcase["id"],
        "trace_id": badcase["trace_id"],
        "plan_id": badcase.get("plan_id"),
        "span_id": badcase.get("span_id"),
        "llm_interaction_id": badcase.get("llm_interaction_id"),
        "created_at": badcase["created_at"],
        "category": badcase["category"],
        "severity": badcase["severity"],
        "status": badcase.get("status") or "open",
        "source": badcase.get("source") or "developer",
        "summary": badcase.get("summary") or "",
        "comment": badcase.get("comment") or "",
        "expected_behavior": badcase.get("expected_behavior"),
        "actual_behavior": badcase.get("actual_behavior"),
        "eval_dataset_name": badcase.get("eval_dataset_name"),
        "input_snapshot_hash": badcase.get("input_snapshot_hash"),
        "input_ref": _sanitize(badcase.get("input_ref") or {}),
        "evidence_refs": _sanitize(badcase.get("evidence_refs") or []),
        "metadata": _sanitize(badcase.get("metadata") or {}),
        "trace": {
            "trace_id": trace["trace_id"],
            "symbol": trace["symbol"],
            "horizon": trace.get("horizon"),
            "run_type": trace["run_type"],
            "status": trace["status"],
            "final_action": trace.get("final_action"),
            "allowed": trace.get("allowed"),
            "created_at": trace["created_at"],
            "span_count": len(detail.get("spans") or []),
            "llm_interaction_count": len(detail.get("llm_interactions") or []),
        },
        "plan_summary": _plan_summary(detail),
    }


def _case_from_detail(badcase: dict[str, Any], detail: dict[str, Any]) -> EvalCase:
    trace = detail["trace"]
    input_summary = _frozen_summary(badcase, detail)
    frozen_hash = _hash(input_summary)
    badcase_id = int(badcase["id"])
    return EvalCase(
        case_id=f"badcase-{badcase_id}",
        dataset_name=str(badcase.get("eval_dataset_name") or "default"),
        source_trace_id=str(badcase["trace_id"]),
        source_badcase_id=badcase_id,
        created_at=str(badcase["created_at"]),
        symbol=str(trace["symbol"]),
        horizon=trace.get("horizon"),
        failure_category=str(badcase["category"]),
        severity=str(badcase["severity"]),
        expected_behavior=str(badcase.get("expected_behavior") or badcase.get("summary") or ""),
        actual_behavior=str(badcase.get("actual_behavior") or badcase.get("comment") or ""),
        summary=str(badcase.get("summary") or ""),
        status=str(badcase.get("status") or "open"),
        frozen_input_hash=frozen_hash,
        input_summary=input_summary,
        metadata={
            "source": "badcase",
            "input_snapshot_hash": badcase.get("input_snapshot_hash"),
            "evidence_refs": badcase.get("evidence_refs") or [],
        },
    )


def _frozen_summary(badcase: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    trace = detail["trace"]
    plan = detail.get("plan_run") or {}
    spans = detail.get("spans") or []
    llm_interactions = detail.get("llm_interactions") or []
    return {
        "source": {
            "trace_id": trace["trace_id"],
            "plan_id": badcase.get("plan_id") or trace.get("final_plan_id"),
            "badcase_id": badcase["id"],
        },
        "trace": {
            "run_type": trace["run_type"],
            "symbol": trace["symbol"],
            "horizon": trace.get("horizon"),
            "status": trace["status"],
            "final_action": trace.get("final_action"),
            "allowed": trace.get("allowed"),
            "created_at": trace["created_at"],
        },
        "observed_output": {
            "parsed_plan": _public_plan(plan.get("parsed_plan") or {}),
            "verdict": _sanitize(plan.get("verdict") or {}),
            "analysis": _sanitize(detail.get("analysis") or {}),
        },
        "trace_summary": {
            "span_names": [span.get("span_name") for span in spans],
            "llm_interactions": [
                {
                    "id": item.get("id"),
                    "component": item.get("component"),
                    "provider": item.get("provider"),
                    "model": item.get("model"),
                    "status": item.get("status"),
                    "input_hash": item.get("input_hash"),
                    "output_hash": item.get("output_hash"),
                    "input_summary": item.get("input_summary"),
                    "output_summary": item.get("output_summary"),
                }
                for item in llm_interactions
            ],
        },
        "expected": {
            "behavior": badcase.get("expected_behavior") or "",
            "actual": badcase.get("actual_behavior") or badcase.get("comment") or "",
        },
    }


def _plan_summary(detail: dict[str, Any]) -> dict[str, Any]:
    plan = detail.get("plan_run") or {}
    parsed = _public_plan(plan.get("parsed_plan") or {})
    verdict = _sanitize(plan.get("verdict") or {})
    return {
        "plan_id": plan.get("plan_id"),
        "main_action": parsed.get("main_action"),
        "probability": parsed.get("probability"),
        "allowed": verdict.get("allowed"),
        "risk_reasons": verdict.get("reasons") or [],
    }


def _hash(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_limit(limit: int) -> int:
    return max(1, min(int(limit), 100))


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize(value) for key, value in plan.items() if key in SAFE_PARSED_PLAN_KEYS}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(hint in normalized for hint in SECRET_KEY_HINTS):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
