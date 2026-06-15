from __future__ import annotations

from typing import Any

from crypto_manual_alert.context.memory_firewall import sanitize_memory_snapshot
from crypto_manual_alert.decision.replay_sanitization import hash_payload, rule_ids, strip_raw_fields


def observed_run_refs(trace_id: str, artifacts: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifacts, dict):
        return {}
    refs: dict[str, Any] = {}
    final_raw_ref = _final_decision_output_ref(trace_id, artifacts.get("final_decision_output"))
    if final_raw_ref:
        refs["final_decision_output"] = final_raw_ref
    final_input_ref = _final_input_selection_ref(artifacts.get("final_input_selection"))
    if final_input_ref:
        refs["final_input_selection"] = final_input_ref
    parsed_plan_ref = _parsed_plan_ref(trace_id, artifacts.get("parsed_plan"))
    if parsed_plan_ref:
        refs["parsed_plan"] = parsed_plan_ref
    production_control_ref = _gate_ref(
        trace_id,
        "production_control_gate",
        artifacts.get("production_control_gate"),
    )
    if production_control_ref:
        refs["production_control_gate"] = production_control_ref
    risk_gate_ref = _gate_ref(trace_id, "risk_gate_result", artifacts.get("risk_gate_result"))
    if risk_gate_ref:
        refs["risk_gate_result"] = risk_gate_ref
    side_effect_ref = _side_effect_policy_ref(artifacts.get("side_effect_policy"))
    if side_effect_ref:
        refs["side_effect_policy"] = side_effect_ref
    context_ref = _context_artifact_summary_ref(artifacts.get("context_artifact_summary"))
    if context_ref:
        refs["context_artifact_summary"] = context_ref
    version_lock_ref = _version_lock_ref(trace_id, artifacts.get("version_lock"))
    if version_lock_ref:
        refs["version_lock"] = version_lock_ref
    telemetry_ref = _telemetry_refs(trace_id, artifacts.get("telemetry_refs"))
    if telemetry_ref:
        refs["telemetry_refs"] = telemetry_ref
    evidence_ref = _evidence_snapshot_refs(trace_id, artifacts.get("evidence_snapshot_refs"))
    if evidence_ref:
        refs["evidence_snapshot_refs"] = evidence_ref
    memory_ref = _memory_snapshot_refs(trace_id, artifacts.get("memory_snapshot"))
    if memory_ref:
        refs["memory_snapshot_refs"] = memory_ref
    span_tree_ref = _span_tree_refs(trace_id, artifacts.get("span_tree_refs"))
    if span_tree_ref:
        refs["span_tree_refs"] = span_tree_ref
    return refs


def span_tree_parent_complete(span_tree_ref: Any) -> bool | None:
    if not isinstance(span_tree_ref, dict):
        return None
    value = span_tree_ref.get("parent_complete")
    return value if isinstance(value, bool) else None


def span_tree_missing_parent_count(span_tree_ref: Any) -> int | None:
    if not isinstance(span_tree_ref, dict):
        return None
    missing = span_tree_ref.get("missing_parent_span_ids")
    return len(missing) if isinstance(missing, list) else None


def _final_decision_output_ref(trace_id: str, raw_decision: Any) -> dict[str, Any] | None:
    if raw_decision is None:
        return None
    raw_text = str(raw_decision)
    return {
        "output_ref": f"trace:{trace_id}:final_decision_output",
        "output_hash": hash_payload(raw_text),
        "char_count": len(raw_text),
        "stored_raw": False,
    }


def _final_input_selection_ref(selection: Any) -> dict[str, Any] | None:
    if not isinstance(selection, dict):
        return None
    safe = strip_raw_fields(selection)
    ref = {
        key: safe.get(key)
        for key in ("mode", "source_ref", "decision_effect", "readiness_ready")
        if safe.get(key) is not None
    }
    if not ref:
        return None
    ref["selection_hash"] = hash_payload(safe)
    return ref


def _parsed_plan_ref(trace_id: str, parsed_plan: Any) -> dict[str, Any] | None:
    if not isinstance(parsed_plan, dict):
        return None
    safe = strip_raw_fields(parsed_plan)
    return {
        "plan_ref": f"trace:{trace_id}:parsed_plan",
        "plan_id": safe.get("plan_id"),
        "main_action": safe.get("main_action"),
        "plan_hash": hash_payload(safe),
    }


def _gate_ref(trace_id: str, gate_name: str, gate_result: Any) -> dict[str, Any] | None:
    if not isinstance(gate_result, dict):
        return None
    safe = strip_raw_fields(gate_result)
    return {
        "gate_ref": f"trace:{trace_id}:{gate_name}",
        "gate_hash": hash_payload(safe),
        "allowed": safe.get("allowed"),
        "rule_ids": rule_ids(safe),
    }


def _side_effect_policy_ref(policy: Any) -> dict[str, Any] | None:
    if not isinstance(policy, dict):
        return None
    safe = strip_raw_fields(policy)
    ref = {
        key: bool(safe.get(key))
        for key in ("allow_production_journal_write", "allow_notification_intent")
        if key in safe
    }
    if not ref:
        return None
    ref["policy_hash"] = hash_payload(safe)
    return ref


def _context_artifact_summary_ref(summary: Any) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    safe = strip_raw_fields(summary)
    ref = {
        key: safe.get(key)
        for key in ("evidence_count", "contribution_count", "has_lead_plan", "has_decision_input")
        if safe.get(key) is not None
    }
    for key in ("lead_plan_ref", "decision_input_ref", "gate_result_refs"):
        if isinstance(safe.get(key), (dict, list)):
            ref[key] = safe[key]
    if not ref:
        return None
    ref["artifact_hash"] = hash_payload(safe)
    return ref


def _version_lock_ref(trace_id: str, version_lock: Any) -> dict[str, Any] | None:
    if not isinstance(version_lock, dict):
        return None
    safe = strip_raw_fields(version_lock)
    ref = {
        key: safe.get(key)
        for key in (
            "config_hash",
            "skill_hashes",
            "prompt_hashes",
            "model",
            "rule_hashes",
            "redaction_policy_hash",
        )
        if safe.get(key) is not None
    }
    if not ref:
        return None
    ref["version_lock_ref"] = f"trace:{trace_id}:version_lock"
    ref["version_lock_hash"] = hash_payload(safe)
    return {
        key: ref[key]
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
        if key in ref
    }


def _telemetry_refs(trace_id: str, telemetry: Any) -> dict[str, Any] | None:
    if not isinstance(telemetry, dict):
        return None
    span_refs = _span_refs(telemetry.get("spans"))
    llm_refs = _llm_interaction_refs(trace_id, telemetry.get("llm_interactions"))
    if not span_refs and not llm_refs:
        return None
    safe = {
        "telemetry_ref": f"trace:{trace_id}:telemetry",
        "span_count": len(span_refs),
        "llm_interaction_count": len(llm_refs),
        "total_duration_ms": _sum_numeric([*span_refs, *llm_refs], "duration_ms"),
        "total_prompt_tokens": _sum_numeric(llm_refs, "prompt_tokens"),
        "total_completion_tokens": _sum_numeric(llm_refs, "completion_tokens"),
        "total_tokens": _sum_numeric(llm_refs, "total_tokens"),
        "total_cost_usd": _sum_numeric(llm_refs, "cost_usd"),
        "span_refs": span_refs,
        "llm_interaction_refs": llm_refs,
    }
    safe["telemetry_hash"] = hash_payload(safe)
    return safe


def _evidence_snapshot_refs(trace_id: str, snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    evidence_packets = snapshot.get("evidence_packets") if isinstance(snapshot.get("evidence_packets"), list) else []
    facts_gate = snapshot.get("facts_gate") if isinstance(snapshot.get("facts_gate"), dict) else {}
    refs = [_evidence_ref(packet) for packet in evidence_packets if isinstance(packet, dict)]
    if not refs and not facts_gate:
        return None
    safe_facts_gate = _facts_gate_ref(facts_gate)
    safe = {
        "evidence_snapshot_ref": f"trace:{trace_id}:evidence_snapshot",
        "evidence_count": len(refs),
        "source_type_counts": _counts(refs, "source_type"),
        "data_type_counts": _counts(refs, "data_type"),
        "execution_fact_eligible_count": sum(
            1 for item in refs if item.get("can_satisfy_execution_fact") is True
        ),
        "facts_gate": safe_facts_gate,
        "facts_gate_hash": hash_payload(safe_facts_gate),
        "evidence_refs": refs,
    }
    safe["evidence_snapshot_hash"] = hash_payload(safe)
    return safe


def _memory_snapshot_refs(trace_id: str, snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    snapshot = sanitize_memory_snapshot(snapshot)
    allowed_fields = snapshot.get("allowed_fields") if isinstance(snapshot.get("allowed_fields"), dict) else {}
    long_term_refs = snapshot.get("long_term_memory_refs") if isinstance(snapshot.get("long_term_memory_refs"), list) else []
    safe_long_term_refs = [
        {
            key: ref.get(key)
            for key in ("memory_id", "memory_hash", "score")
            if isinstance(ref, dict) and ref.get(key) is not None
        }
        for ref in long_term_refs
        if isinstance(ref, dict)
    ]
    snapshot_ref = snapshot.get("snapshot_id") or f"trace:{trace_id}:memory_snapshot"
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), str) else None
    safe = {
        "memory_snapshot_ref": snapshot_ref,
        "session_id": snapshot.get("session_id"),
        "allowed_fields": _sorted_dict(allowed_fields),
        "allowed_field_names": sorted(str(key) for key in allowed_fields),
        "recent_turn_count": snapshot.get("recent_turn_count") if isinstance(snapshot.get("recent_turn_count"), int) else 0,
        "long_term_memory_refs": safe_long_term_refs,
    }
    if isinstance(snapshot.get("quarantined_fields"), list):
        safe["quarantined_fields"] = [str(item) for item in snapshot.get("quarantined_fields") or []]
    if isinstance(snapshot.get("memory_warnings"), list):
        safe["memory_warnings"] = [str(item) for item in snapshot.get("memory_warnings") or []]
    if summary is not None:
        safe["summary_hash"] = hash_payload(summary)
    safe["memory_snapshot_hash"] = hash_payload(safe)
    return {
        key: safe[key]
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
        if key in safe
    }


def _evidence_ref(packet: dict[str, Any]) -> dict[str, Any]:
    safe = {
        key: packet.get(key)
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
        )
        if key in packet
    }
    safe["evidence_hash"] = hash_payload(safe)
    return safe


def _facts_gate_ref(facts_gate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: facts_gate.get(key)
        for key in (
            "passed",
            "severity",
            "missing_execution_facts",
            "blocked_action_classes",
        )
        if key in facts_gate
    }


def _span_tree_refs(trace_id: str, snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    spans = snapshot.get("spans")
    if not isinstance(spans, list) or not spans:
        return None
    refs = _span_refs(spans)
    if not refs:
        return None
    span_ids = {str(item.get("span_id")) for item in refs if item.get("span_id")}
    missing_parent_ids = sorted(
        {
            str(item.get("parent_span_id"))
            for item in refs
            if item.get("parent_span_id") and str(item.get("parent_span_id")) not in span_ids
        }
    )
    safe = {
        "span_tree_ref": f"trace:{trace_id}:span_tree",
        "span_count": len(refs),
        "root_span_count": sum(1 for item in refs if not item.get("parent_span_id")),
        "parent_link_count": sum(1 for item in refs if item.get("parent_span_id")),
        "parent_complete": not missing_parent_ids,
        "missing_parent_span_ids": missing_parent_ids,
        "span_refs": refs,
    }
    safe["span_tree_hash"] = hash_payload(safe)
    return safe


def _counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if value is None:
            continue
        value_text = str(value)
        counts[value_text] = counts.get(value_text, 0) + 1
    return counts


def _sorted_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key): payload[key] for key in sorted(payload)}


def _span_refs(spans: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for span in spans or []:
        if not isinstance(span, dict):
            continue
        ref = {
            "span_id": span.get("span_id"),
            "parent_span_id": span.get("parent_span_id"),
            "span_name": span.get("span_name"),
            "span_type": span.get("span_type"),
            "status": span.get("status"),
            "duration_ms": _number_or_none(span.get("duration_ms")),
        }
        input_ref = _summary_ref(span.get("input_summary"))
        if input_ref:
            ref["span_input_hash"] = input_ref["summary_hash"]
            if input_ref.get("summary_refs"):
                ref["input_refs"] = input_ref["summary_refs"]
        output_ref = _summary_ref(span.get("output_summary"))
        if output_ref:
            ref["span_output_hash"] = output_ref["summary_hash"]
            if output_ref.get("summary_refs"):
                ref["output_refs"] = output_ref["summary_refs"]
        refs.append(ref)
    return refs


def _llm_interaction_refs(trace_id: str, interactions: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for interaction in interactions or []:
        if not isinstance(interaction, dict):
            continue
        interaction_id = interaction.get("id")
        refs.append(
            {
                "interaction_ref": f"trace:{trace_id}:llm_interaction:{interaction_id}",
                "span_id": interaction.get("span_id"),
                "component": interaction.get("component"),
                "provider": interaction.get("provider"),
                "model": interaction.get("model"),
                "endpoint": interaction.get("endpoint"),
                "status": interaction.get("status"),
                "input_hash": interaction.get("input_hash"),
                "output_hash": interaction.get("output_hash"),
                "duration_ms": _number_or_none(interaction.get("duration_ms")),
                "prompt_tokens": _number_or_none(interaction.get("prompt_tokens")),
                "completion_tokens": _number_or_none(interaction.get("completion_tokens")),
                "total_tokens": _number_or_none(interaction.get("total_tokens")),
                "cost_usd": _number_or_none(interaction.get("cost_usd")),
                "finish_reason": interaction.get("finish_reason"),
                "retry_count": _number_or_none(interaction.get("retry_count")),
            }
        )
    return refs


def _summary_ref(summary: Any) -> dict[str, Any] | None:
    if summary is None:
        return None
    safe_refs = _summary_refs(summary)
    return {
        "summary_hash": hash_payload(strip_raw_fields(summary)),
        "summary_refs": safe_refs,
    }


def _summary_refs(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    allowed_keys = {
        "agent_name",
        "bundle_ref",
        "decision_effect",
        "frozen_input_hash",
        "input_hash",
        "input_ref",
        "kind",
        "mode",
        "output_hash",
        "output_ref",
        "plan_id",
        "schema_version",
        "selection_hash",
        "source_ref",
        "status",
        "symbol",
        "task_id",
        "trace_ref",
        "validation_passed",
    }
    refs: dict[str, Any] = {}
    for key, value in summary.items():
        key_text = str(key)
        if _unsafe_summary_ref_key(key_text):
            continue
        if key_text in allowed_keys or key_text.endswith("_ref") or key_text.endswith("_hash"):
            refs[key_text] = value
    return strip_raw_fields(refs) if refs else {}


def _unsafe_summary_ref_key(key: str) -> bool:
    normalized = key.lower()
    return (
        "frozen_input" in normalized
        or normalized.startswith("raw")
        or normalized in {"payload", "prompt", "completion"}
    )


def _sum_numeric(items: list[dict[str, Any]], key: str) -> int | float | None:
    values = [item.get(key) for item in items if isinstance(item.get(key), (int, float))]
    if not values:
        return None
    return sum(values)


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return None
