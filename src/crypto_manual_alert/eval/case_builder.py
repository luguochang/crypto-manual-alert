from __future__ import annotations

import hashlib
import json
from typing import Any

from crypto_manual_alert.decision.frozen_input import frozen_input_from_plan_payload, stable_hash
from crypto_manual_alert.storage.journal import Journal

from .candidate_artifact_snapshots import artifact_snapshot_summary
from .context_artifact_summary import context_artifacts_summary
from .replayable_input_summary import (
    replayable_artifact_refs_summary,
    replayable_coverage_summary,
)
from .schema import EvalCase, EvalFrozenInput


SECRET_KEY_HINTS = (
    "api_key",
    "authorization",
    "secret",
    "token",
    "passphrase",
    "device_key",
    "bark",
    "raw_decision",
    "raw_candidate_decision",
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
        self.last_frozen_inputs: list[EvalFrozenInput] = []

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
            detail["_journal"] = self.journal
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
        frozen_inputs: list[EvalFrozenInput] = []
        clean_limit = max(_normalize_limit(limit), len(badcase_ids or []), 1)
        for badcase in self.journal.list_badcases(limit=clean_limit, ids=badcase_ids, dataset=dataset):
            detail = self.journal.get_trace_detail(str(badcase["trace_id"]), include_payloads=False)
            if detail is None:
                continue
            detail["_journal"] = self.journal
            case = _case_from_detail(badcase, detail)
            cases.append(case)
            frozen = _frozen_input_from_detail(badcase, detail)
            if frozen:
                frozen_inputs.append(frozen)
            if len(cases) >= _normalize_limit(limit) and not badcase_ids:
                break
        self.last_frozen_inputs = frozen_inputs
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
    frozen = _frozen_input_from_detail(badcase, detail)
    frozen_hash = frozen.frozen_input_hash if frozen else _hash(input_summary)
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
            "frozen_input_available": frozen is not None,
        },
    )


def _frozen_input_from_detail(badcase: dict[str, Any], detail: dict[str, Any]) -> EvalFrozenInput | None:
    trace = detail["trace"]
    plan = detail.get("plan_run") or {}
    plan_id = badcase.get("plan_id") or plan.get("plan_id") or trace.get("final_plan_id")
    full_payload = None
    journal = detail.get("_journal")
    if plan_id and isinstance(journal, Journal):
        full_payload = journal.get_plan_run_payload(str(plan_id))
    frozen = frozen_input_from_plan_payload(
        full_payload or plan,
        source_trace_id=str(trace["trace_id"]),
        source_badcase_id=int(badcase["id"]),
    )
    if frozen is None:
        return None
    row = frozen.to_store_row()
    return EvalFrozenInput(
        frozen_input_hash=row["frozen_input_hash"],
        schema_version=row["schema_version"],
        kind=row["kind"],
        source_trace_id=row["source_trace_id"],
        source_badcase_id=row["source_badcase_id"],
        input_payload=row["input_payload"],
        public_summary=row["public_summary"],
        metadata=row["metadata"],
    )


def _frozen_summary(badcase: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    trace = detail["trace"]
    plan = detail.get("plan_run") or {}
    full_payload = _plan_payload_for_detail(badcase, detail)
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
        "candidate_audit": _candidate_audit_summary(full_payload or plan),
        "trace_summary": {
            "span_names": [span.get("span_name") for span in spans],
            "llm_interactions": [
                {
                    "id": item.get("id"),
                    "component": item.get("component"),
                    "provider": item.get("provider"),
                    "model": item.get("model"),
                    "status": item.get("status"),
                    "span_id": item.get("span_id"),
                    "endpoint": item.get("endpoint"),
                    "duration_ms": item.get("duration_ms"),
                    "prompt_tokens": item.get("prompt_tokens"),
                    "completion_tokens": item.get("completion_tokens"),
                    "total_tokens": item.get("total_tokens"),
                    "cost_usd": item.get("cost_usd"),
                    "finish_reason": item.get("finish_reason"),
                    "retry_count": item.get("retry_count"),
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


def _plan_payload_for_detail(badcase: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any] | None:
    trace = detail["trace"]
    plan = detail.get("plan_run") or {}
    plan_id = badcase.get("plan_id") or plan.get("plan_id") or trace.get("final_plan_id")
    journal = detail.get("_journal")
    if plan_id and isinstance(journal, Journal):
        return journal.get_plan_run_payload(str(plan_id))
    return None


def _candidate_audit_summary(plan: dict[str, Any]) -> dict[str, Any]:
    source = _candidate_audit_source(plan)
    gate_candidate = source.get("gate_candidate") if isinstance(source.get("gate_candidate"), dict) else {}
    plan_semantic_candidate = (
        source.get("plan_semantic_candidate")
        if isinstance(source.get("plan_semantic_candidate"), dict)
        else {}
    )
    switch_readiness = (
        source.get("final_decision_switch_readiness")
        if isinstance(source.get("final_decision_switch_readiness"), dict)
        else {}
    )
    decision_input = (
        source.get("decision_input_candidate")
        if isinstance(source.get("decision_input_candidate"), dict)
        else {}
    )
    replayable_input = (
        source.get("replayable_input_candidate")
        if isinstance(source.get("replayable_input_candidate"), dict)
        else {}
    )
    summary = {
        "decision_input_candidate": {
            "input_ref": decision_input.get("input_ref"),
            "input_hash": decision_input.get("input_hash"),
            "decision_effect": decision_input.get("decision_effect"),
            "contribution_refs": _decision_input_contribution_refs(decision_input),
            "execution_fact_source_violations": _execution_fact_source_violations(decision_input),
        },
        "replayable_input_candidate": {
            "input_ref": replayable_input.get("input_ref"),
            "input_hash": replayable_input.get("input_hash"),
            "decision_effect": replayable_input.get("decision_effect"),
            "coverage": replayable_coverage_summary(replayable_input.get("coverage")),
            "artifact_refs": replayable_artifact_refs_summary(replayable_input.get("artifact_refs")),
        },
        "context_artifacts": context_artifacts_summary(plan),
        "artifact_snapshot": artifact_snapshot_summary(source),
        "gate_candidate": {
            "passed": gate_candidate.get("passed"),
            "severity": gate_candidate.get("severity"),
            "violations": _sanitize(gate_candidate.get("violations") or []),
            "blocked_actions": _sanitize(gate_candidate.get("blocked_actions") or []),
            "missing_facts": _sanitize(gate_candidate.get("missing_facts") or []),
        },
        "plan_semantic_candidate": {
            "passed": plan_semantic_candidate.get("passed"),
            "severity": plan_semantic_candidate.get("severity"),
            "violations": _sanitize(plan_semantic_candidate.get("violations") or []),
        },
        "final_decision_switch_readiness": {
            "ready": switch_readiness.get("ready"),
            "blocking_reasons": _sanitize(switch_readiness.get("blocking_reasons") or []),
        },
    }
    controlled_shadow = _controlled_shadow_summary(source.get("controlled_shadow"))
    if controlled_shadow:
        summary["controlled_shadow"] = controlled_shadow
    candidate_final = source.get("candidate_final_decision")
    if isinstance(candidate_final, dict):
        summary["candidate_final_decision"] = _candidate_final_decision_summary(candidate_final)
    return summary


def _candidate_audit_source(plan: dict[str, Any]) -> dict[str, Any]:
    audit_only = plan.get("audit_only") if isinstance(plan.get("audit_only"), dict) else None
    if isinstance(audit_only, dict) and audit_only.get("decision_effect") == "none":
        return audit_only
    return plan


def _controlled_shadow_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        key: _sanitize(payload.get(key))
        for key in (
            "mode",
            "audit_only",
            "production_final_input",
            "notification_input",
            "reason",
        )
        if payload.get(key) is not None
    }


def _candidate_final_decision_summary(candidate_final: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "candidate_final_decision",
        "mode": candidate_final.get("mode"),
        "decision_effect": candidate_final.get("decision_effect"),
        "production_final_input": candidate_final.get("production_final_input"),
        "input_ref": candidate_final.get("input_ref"),
        "input_hash": candidate_final.get("input_hash"),
        "input_gate_passed": candidate_final.get("input_gate_passed"),
        "candidate_final_summary": _candidate_final_output_summary(candidate_final),
        "candidate_final_output_hash": stable_hash(
            {"raw_candidate_decision": candidate_final.get("raw_candidate_decision")}
        )
        if candidate_final.get("raw_candidate_decision") is not None
        else None,
        "error": _sanitize(candidate_final.get("error")),
    }


def _candidate_final_output_summary(candidate_final: dict[str, Any]) -> dict[str, Any]:
    raw_candidate_decision = candidate_final.get("raw_candidate_decision")
    if isinstance(candidate_final.get("candidate_final_summary"), dict):
        parsed = candidate_final["candidate_final_summary"]
    elif isinstance(raw_candidate_decision, dict):
        parsed = raw_candidate_decision
    else:
        try:
            parsed = json.loads(str(raw_candidate_decision))
        except (TypeError, json.JSONDecodeError):
            parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return {
        key: parsed.get(key)
        for key in ("instrument", "main_action", "probability")
        if parsed.get(key) is not None
    }


def _execution_fact_source_violations(decision_input: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for ref in decision_input.get("evidence_refs") or []:
        if not isinstance(ref, dict):
            continue
        data_type = str(ref.get("data_type") or "")
        source_type = str(ref.get("source_type") or "")
        if (
            data_type in {"mark", "index", "order_book"}
            and source_type in {"search_derived", "web_derived"}
            and ref.get("can_satisfy_execution_fact") is True
        ):
            violations.append(
                {
                    "evidence_id": ref.get("evidence_id"),
                    "data_type": data_type,
                    "source_type": source_type,
                }
            )
    return violations


def _decision_input_contribution_refs(decision_input: dict[str, Any]) -> list[dict[str, Any]]:
    refs = decision_input.get("contribution_refs")
    if not isinstance(refs, list):
        return []
    safe_refs: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        safe_ref = {
            key: ref.get(key)
            for key in (
                "contribution_id",
                "agent_name",
                "status",
                "required",
                "output_hash",
                "input_ref",
                "trace_ref",
                "migration_stage",
                "hard_block",
            )
            if ref.get(key) is not None
        }
        if ref.get("hard_block") is True:
            safe_ref["hard_block_reasons"] = [
                str(reason) for reason in ref.get("hard_block_reasons") or []
            ]
        safe_refs.append(safe_ref)
    return safe_refs


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
