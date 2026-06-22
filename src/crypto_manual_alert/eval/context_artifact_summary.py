from __future__ import annotations

from typing import Any


def context_artifacts_summary(plan: dict[str, Any]) -> dict[str, Any]:
    run_context = plan.get("run_context") if isinstance(plan.get("run_context"), dict) else {}
    artifacts = run_context.get("artifacts") if isinstance(run_context.get("artifacts"), dict) else {}
    if not artifacts:
        return {}
    return {
        "evidence_count": artifacts.get("evidence_count"),
        "contribution_count": artifacts.get("contribution_count"),
        "has_lead_plan": artifacts.get("has_lead_plan"),
        "has_decision_input": artifacts.get("has_decision_input"),
        "lead_plan_ref": _lead_plan_ref(artifacts.get("lead_plan_ref")),
        "decision_input_ref": _decision_input_ref(artifacts.get("decision_input_ref")),
        "gate_result_refs": _gate_result_refs(artifacts.get("gate_result_refs")),
        "evidence_refs": _evidence_refs(artifacts.get("evidence_refs")),
        "contribution_refs": _contribution_refs(artifacts.get("contribution_refs")),
    }


def _lead_plan_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {key: ref.get(key) for key in ("plan_id", "artifact_hash") if ref.get(key) is not None}


def _decision_input_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    return {
        "input_ref": ref.get("input_ref"),
        "input_hash": ref.get("input_hash"),
    }


def _gate_result_refs(refs: Any) -> dict[str, Any]:
    if not isinstance(refs, dict):
        return {}
    safe_refs: dict[str, Any] = {}
    for name, ref in refs.items():
        if not isinstance(ref, dict):
            continue
        safe_refs[str(name)] = {
            key: ref.get(key)
            for key in ("artifact_ref", "input_ref", "input_hash", "artifact_hash", "decision_effect", "passed", "ready")
            if ref.get(key) is not None
        }
    return safe_refs


def _evidence_refs(refs: Any) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    safe_refs = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        safe_refs.append(
            {
                key: ref.get(key)
                for key in ("evidence_id", "data_type", "source_type", "source_url")
                if ref.get(key) is not None
            }
        )
    return safe_refs


def _contribution_refs(refs: Any) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    safe_refs = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        safe_refs.append(
            {
                key: ref.get(key)
                for key in ("contribution_id", "agent_name", "status", "input_ref", "output_hash")
                if ref.get(key) is not None
            }
        )
    return safe_refs
