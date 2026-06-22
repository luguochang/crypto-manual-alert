from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.hashing import stable_hash


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


def artifact_snapshot_summary(source: dict[str, Any]) -> dict[str, Any]:
    decision_input = source.get("decision_input_candidate")
    replayable_input = source.get("replayable_input_candidate")
    artifact_refs = (
        replayable_input.get("artifact_refs")
        if isinstance(replayable_input, dict) and isinstance(replayable_input.get("artifact_refs"), dict)
        else {}
    )
    lead_synthesis = decision_input.get("lead_synthesis") if isinstance(decision_input, dict) else None
    lead_synthesis_artifact = source.get("lead_synthesis_artifact")
    return {
        "schema_version": 1,
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "decision_input_candidate": artifact_snapshot_ref(decision_input),
        "replayable_input_candidate": artifact_snapshot_ref(replayable_input),
        "lead_synthesis": lead_synthesis_snapshot_ref(lead_synthesis_artifact, fallback_payload=lead_synthesis),
        "worker_result_manifest": worker_manifest_snapshot_ref(artifact_refs.get("worker_result_manifest")),
        "gate_candidate": candidate_gate_snapshot_ref("gate_candidate", source.get("gate_candidate")),
        "plan_semantic_candidate": candidate_gate_snapshot_ref(
            "plan_semantic_candidate",
            source.get("plan_semantic_candidate"),
        ),
        "final_decision_switch_readiness": candidate_gate_snapshot_ref(
            "final_decision_switch_readiness",
            source.get("final_decision_switch_readiness"),
        ),
    }


def artifact_snapshot_ref(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return {
        "input_ref": payload.get("input_ref"),
        "input_hash": payload.get("input_hash"),
        "decision_effect": "none",
        "artifact_hash": stable_hash(sanitize_for_artifact_hash(payload)),
    }


def lead_synthesis_snapshot_ref(payload: Any, *, fallback_payload: Any = None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        payload = fallback_payload
    if not isinstance(payload, dict):
        return None
    if payload.get("artifact_ref") == "candidate:lead_synthesis":
        return {
            "artifact_ref": "candidate:lead_synthesis",
            "decision_effect": payload.get("decision_effect"),
            "input_ref": payload.get("input_ref"),
            "input_hash": payload.get("input_hash"),
            "lead_plan_ref": payload.get("lead_plan_ref"),
            "lead_plan_hash": payload.get("lead_plan_hash"),
            "worker_manifest_hash": payload.get("worker_manifest_hash"),
            "counter_thesis_count": payload.get("counter_thesis_count"),
            "counter_thesis_refs": lead_counter_refs(payload.get("counter_thesis_refs")),
            "strongest_counter_thesis_ref": lead_counter_ref(
                payload.get("strongest_counter_thesis_ref")
            ),
            "conflict_count": payload.get("conflict_count"),
            "conflict_refs": lead_conflict_refs(payload.get("conflict_refs")),
            "artifact_hash": stable_hash(sanitize_for_artifact_hash(payload)),
        }
    return {
        "artifact_ref": "candidate:lead_synthesis",
        "decision_effect": payload.get("decision_effect"),
        "artifact_hash": stable_hash(sanitize_for_artifact_hash(payload)),
    }


def worker_manifest_snapshot_ref(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    return {
        "artifact_ref": "candidate:worker_result_manifest",
        "decision_effect": "none",
        "manifest_count": len(payload),
        "artifact_hash": stable_hash(sanitize_for_artifact_hash(payload)),
    }


def candidate_gate_snapshot_ref(artifact_type: str, payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    ref: dict[str, Any] = {
        "artifact_ref": f"candidate:{artifact_type}",
        "decision_effect": "none",
        "artifact_hash": stable_hash(sanitize_for_artifact_hash(payload)),
    }
    if "passed" in payload:
        ref["passed"] = payload.get("passed")
    if "ready" in payload:
        ref["ready"] = payload.get("ready")
    return ref


def lead_counter_refs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    refs = []
    for item in payload:
        ref = lead_counter_ref(item)
        if ref:
            refs.append(ref)
    return refs


def lead_counter_ref(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    ref = {
        key: payload.get(key)
        for key in ("contribution_id", "agent_name", "claim", "side", "evidence_ids", "strength")
        if payload.get(key) is not None
    }
    return ref or None


def lead_conflict_refs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    refs = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        ref = {
            key: item.get(key)
            for key in ("conflict_id", "summary", "sides", "contribution_refs")
            if item.get(key) is not None
        }
        if ref:
            refs.append(ref)
    return refs


def sanitize_for_artifact_hash(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized.startswith("raw") or any(hint in normalized for hint in SECRET_KEY_HINTS):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = sanitize_for_artifact_hash(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_artifact_hash(item) for item in value]
    return value
