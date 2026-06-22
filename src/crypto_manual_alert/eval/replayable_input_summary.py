from __future__ import annotations

from typing import Any


def replayable_coverage_summary(coverage: Any) -> dict[str, Any]:
    if not isinstance(coverage, dict):
        return {}
    allowed_keys = {
        "has_decision_input_candidate",
        "has_lead_synthesis_artifact",
        "has_final_decision_output",
        "has_final_input_selection",
        "has_parsed_plan",
        "has_production_control_gate",
        "has_risk_gate_result",
        "has_side_effect_policy",
        "has_context_artifact_summary",
        "has_version_lock",
        "has_telemetry_refs",
        "has_evidence_snapshot_refs",
        "has_memory_snapshot_refs",
        "has_span_tree_refs",
        "span_tree_parent_complete",
        "span_tree_missing_parent_count",
        "worker_artifact_count",
        "worker_manifest_count",
        "worker_manifest_complete",
        "worker_manifest_missing_fields",
        "evidence_ref_count",
        "included_contribution_count",
        "dropped_contribution_count",
    }
    return {key: _sanitize(coverage.get(key)) for key in sorted(allowed_keys) if key in coverage}


def replayable_artifact_refs_summary(artifact_refs: Any) -> dict[str, Any]:
    if not isinstance(artifact_refs, dict):
        return {}
    summary = {
        "decision_input_candidate": _decision_input_candidate_ref(
            artifact_refs.get("decision_input_candidate")
        ),
        "shadow_workers": _shadow_worker_refs(artifact_refs.get("shadow_workers")),
        "worker_result_manifest": _worker_result_manifest_refs(
            artifact_refs.get("worker_result_manifest")
        ),
    }
    optional_refs = {
        "final_decision_output": _final_decision_output_ref(artifact_refs.get("final_decision_output")),
        "final_input_selection": _final_input_selection_ref(
            artifact_refs.get("final_input_selection")
        ),
        "parsed_plan": _parsed_plan_ref(artifact_refs.get("parsed_plan")),
        "production_control_gate": _gate_ref(artifact_refs.get("production_control_gate")),
        "risk_gate_result": _gate_ref(artifact_refs.get("risk_gate_result")),
        "side_effect_policy": _side_effect_policy_ref(artifact_refs.get("side_effect_policy")),
        "context_artifact_summary": _context_artifact_summary_ref(
            artifact_refs.get("context_artifact_summary")
        ),
        "version_lock": _version_lock_ref(artifact_refs.get("version_lock")),
        "telemetry_refs": _telemetry_refs(artifact_refs.get("telemetry_refs")),
        "evidence_snapshot_refs": _evidence_snapshot_refs(artifact_refs.get("evidence_snapshot_refs")),
        "memory_snapshot_refs": _memory_snapshot_refs(artifact_refs.get("memory_snapshot_refs")),
        "span_tree_refs": _span_tree_refs(artifact_refs.get("span_tree_refs")),
    }
    summary.update({key: value for key, value in optional_refs.items() if value is not None})
    return summary


def _decision_input_candidate_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {
        "input_ref": ref.get("input_ref"),
        "input_hash": ref.get("input_hash"),
    }


def _shadow_worker_refs(refs: Any) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    safe_refs = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        safe_refs.append(
            {
                "task_id": ref.get("task_id"),
                "agent_name": ref.get("agent_name"),
                "status": ref.get("status"),
                "contribution_id": ref.get("contribution_id"),
                "output_hash": ref.get("output_hash"),
                "input_ref": ref.get("input_ref"),
            }
        )
    return safe_refs


def _worker_result_manifest_refs(refs: Any) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    safe_refs = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        agent_run_result = (
            ref.get("agent_run_result")
            if isinstance(ref.get("agent_run_result"), dict)
            else {}
        )
        item = {
            "task_id": ref.get("task_id"),
            "agent_name": ref.get("agent_name"),
            "status": ref.get("status"),
            "input_ref": ref.get("input_ref"),
            "input_hash": ref.get("input_hash"),
            "agent_run_request_hash": ref.get("agent_run_request_hash"),
            "output_hash": ref.get("output_hash"),
            "trace_ref": ref.get("trace_ref"),
            "failure_policy_applied": ref.get("failure_policy_applied"),
            "agent_run_result": {
                key: agent_run_result.get(key)
                for key in ("input_view_hash", "agent_run_request_hash", "output_hash")
                if key in agent_run_result
            },
        }
        tool_call_refs = _tool_call_artifact_refs(ref.get("tool_call_artifact_refs"))
        if tool_call_refs:
            item["tool_call_artifact_refs"] = tool_call_refs
        safe_refs.append(item)
    return safe_refs


def _tool_call_artifact_refs(refs: Any) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    allowed_keys = (
        "tool_call_id",
        "skill_name",
        "status",
        "source_type",
        "source_tier",
        "retrieved_at",
        "freshness_status",
        "result_ref",
        "output_hash",
        "can_satisfy_execution_fact",
        "result_count",
        "error_type",
        "error_hash",
    )
    safe_refs = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        item = {key: ref.get(key) for key in allowed_keys if key in ref and ref.get(key) is not None}
        if item:
            safe_refs.append(item)
    return safe_refs


def _final_decision_output_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {
        key: ref.get(key)
        for key in ("output_ref", "output_hash", "char_count", "stored_raw")
        if ref.get(key) is not None
    }


def _final_input_selection_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {
        key: ref.get(key)
        for key in ("mode", "source_ref", "decision_effect", "readiness_ready", "selection_hash")
        if ref.get(key) is not None
    }


def _parsed_plan_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {
        key: ref.get(key)
        for key in ("plan_ref", "plan_id", "main_action", "plan_hash")
        if ref.get(key) is not None
    }


def _gate_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {
        key: _sanitize(ref.get(key))
        for key in ("gate_ref", "gate_hash", "allowed", "rule_ids")
        if ref.get(key) is not None
    }


def _side_effect_policy_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {
        key: ref.get(key)
        for key in ("allow_production_journal_write", "allow_notification_intent", "policy_hash")
        if ref.get(key) is not None
    }


def _context_artifact_summary_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    safe = {
        key: ref.get(key)
        for key in (
            "evidence_count",
            "contribution_count",
            "has_lead_plan",
            "has_decision_input",
            "artifact_hash",
        )
        if ref.get(key) is not None
    }
    for key in ("lead_plan_ref", "decision_input_ref", "gate_result_refs"):
        if isinstance(ref.get(key), dict):
            safe[key] = _sanitize(ref[key])
    return safe


def _version_lock_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    safe = {
        key: _sanitize(ref.get(key))
        for key in (
            "version_lock_ref",
            "version_lock_hash",
            "config_hash",
            "skill_hashes",
            "prompt_hashes",
            "model",
            "rule_hashes",
            "redaction_policy_hash",
        )
        if ref.get(key) is not None
    }
    return safe or None


def _telemetry_refs(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    safe = {
        key: ref.get(key)
        for key in (
            "telemetry_ref",
            "telemetry_hash",
            "span_count",
            "llm_interaction_count",
            "total_duration_ms",
            "total_prompt_tokens",
            "total_completion_tokens",
            "total_tokens",
            "total_cost_usd",
        )
        if ref.get(key) is not None
    }
    if isinstance(ref.get("span_refs"), list):
        safe["span_refs"] = [
            {
                key: item.get(key)
                for key in ("span_id", "parent_span_id", "span_name", "span_type", "status", "duration_ms")
                if isinstance(item, dict) and key in item
            }
            for item in ref["span_refs"]
            if isinstance(item, dict)
        ]
    if isinstance(ref.get("llm_interaction_refs"), list):
        safe["llm_interaction_refs"] = [
            {
                key: item.get(key)
                for key in (
                    "interaction_ref",
                    "span_id",
                    "component",
                    "provider",
                    "model",
                    "endpoint",
                    "status",
                    "input_hash",
                    "output_hash",
                    "duration_ms",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "cost_usd",
                    "finish_reason",
                    "retry_count",
                )
                if isinstance(item, dict) and key in item
            }
            for item in ref["llm_interaction_refs"]
            if isinstance(item, dict)
        ]
    return safe or None


def _evidence_snapshot_refs(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    safe = {
        key: ref.get(key)
        for key in (
            "evidence_snapshot_ref",
            "evidence_snapshot_hash",
            "facts_gate_hash",
            "evidence_count",
            "source_type_counts",
            "data_type_counts",
            "execution_fact_eligible_count",
            "facts_gate",
        )
        if ref.get(key) is not None
    }
    if isinstance(ref.get("evidence_refs"), list):
        safe["evidence_refs"] = [
            {
                key: item.get(key)
                for key in (
                    "evidence_id",
                    "name",
                    "symbol",
                    "data_type",
                    "source_type",
                    "source_name",
                    "source_url",
                    "freshness_status",
                    "can_satisfy_execution_fact",
                    "confidence_cap",
                    "trace_ref",
                    "evidence_hash",
                )
                if isinstance(item, dict) and key in item
            }
            for item in ref["evidence_refs"]
            if isinstance(item, dict)
        ]
    return safe or None


def _memory_snapshot_refs(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    safe = {
        key: _sanitize(ref.get(key))
        for key in (
            "memory_snapshot_ref",
            "memory_snapshot_hash",
            "session_id",
            "allowed_fields",
            "allowed_field_names",
            "recent_turn_count",
            "summary_hash",
            "long_term_memory_refs",
            "quarantined_fields",
            "memory_warnings",
        )
        if ref.get(key) is not None
    }
    return safe or None


def _span_tree_refs(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    safe = {
        key: ref.get(key)
        for key in (
            "span_tree_ref",
            "span_tree_hash",
            "span_count",
            "root_span_count",
            "parent_link_count",
            "parent_complete",
            "missing_parent_span_ids",
        )
        if ref.get(key) is not None
    }
    if isinstance(ref.get("span_refs"), list):
        safe["span_refs"] = [
            {
                key: item.get(key)
                for key in ("span_id", "parent_span_id", "span_name", "span_type", "status", "duration_ms")
                if isinstance(item, dict) and key in item
            }
            for item in ref["span_refs"]
            if isinstance(item, dict)
        ]
    return safe or None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(hint in normalized for hint in _SECRET_KEY_HINTS):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


_SECRET_KEY_HINTS = (
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
