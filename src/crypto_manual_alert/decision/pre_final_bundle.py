from __future__ import annotations

import copy
from typing import Any

from crypto_manual_alert.artifacts.hashing import stable_hash


def build_pre_final_bundle(
    *,
    trace_id: str,
    symbol: str,
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any],
    pre_final_decision_input: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical audit bundle available before FinalDecisionAgent.

    The bundle links pre-final evidence, harness, lead plan, worker manifest,
    and pre-final DecisionInput by refs and hashes only. It is not a production
    final input and must not carry final plan, risk verdict, journal, or
    notification payloads.
    """

    worker_manifest = _worker_manifest(shadow_swarm_audit)
    bundle = {
        "schema_version": 1,
        "artifact_type": "pre_final_bundle",
        "artifact_ref": f"trace:{trace_id}:pre_final_bundle",
        "trace_id": trace_id,
        "symbol": symbol,
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "facts_gate_ref": _facts_gate_ref(audit_payload.get("facts_gate")),
        "harness_validation_ref": _harness_validation_ref(audit_payload, shadow_swarm_audit),
        "pre_final_decision_input_ref": _pre_final_decision_input_ref(pre_final_decision_input),
        "lead_plan_ref": _lead_plan_ref(shadow_swarm_audit.get("lead_plan")),
        "worker_manifest": worker_manifest,
        "coverage": _coverage(
            audit_payload=audit_payload,
            shadow_swarm_audit=shadow_swarm_audit,
            pre_final_decision_input=pre_final_decision_input,
            worker_manifest=worker_manifest,
        ),
    }
    bundle["artifact_hash"] = f"sha256:{stable_hash(bundle)}"
    return bundle


def _facts_gate_ref(facts_gate: Any) -> dict[str, Any] | None:
    if not isinstance(facts_gate, dict):
        return None
    ref = {
        key: copy.deepcopy(facts_gate.get(key))
        for key in ("passed", "severity", "missing_execution_facts", "blocked_action_classes", "reasons")
        if facts_gate.get(key) is not None
    }
    ref["artifact_hash"] = f"sha256:{stable_hash(facts_gate)}"
    return ref


def _harness_validation_ref(
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any],
) -> dict[str, Any] | None:
    harness = shadow_swarm_audit.get("harness_validation")
    if not isinstance(harness, dict):
        harness = audit_payload.get("harness_validation")
    if not isinstance(harness, dict):
        return None
    ref = {
        key: copy.deepcopy(harness.get(key))
        for key in ("passed", "severity", "violations")
        if harness.get(key) is not None
    }
    ref["artifact_hash"] = f"sha256:{stable_hash(harness)}"
    return ref


def _pre_final_decision_input_ref(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    ref = {
        key: payload.get(key)
        for key in ("input_ref", "input_hash", "decision_effect")
        if payload.get(key) is not None
    }
    ref["validation_passed"] = validation.get("passed") is True
    ref["artifact_hash"] = f"sha256:{stable_hash(payload)}"
    return ref


def _lead_plan_ref(lead_plan: Any) -> dict[str, Any] | None:
    if not isinstance(lead_plan, dict):
        return None
    ref = {
        key: lead_plan.get(key)
        for key in ("plan_id", "mode", "decision_effect")
        if lead_plan.get(key) is not None
    }
    tasks = lead_plan.get("tasks")
    if isinstance(tasks, list):
        ref["task_count"] = len(tasks)
        ref["required_task_count"] = sum(
            1 for task in tasks if isinstance(task, dict) and task.get("required") is True
        )
    ref["artifact_hash"] = f"sha256:{stable_hash(lead_plan)}"
    return ref


def _worker_manifest(shadow_swarm_audit: dict[str, Any]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for result in shadow_swarm_audit.get("worker_results") or []:
        if not isinstance(result, dict):
            continue
        contribution = result.get("contribution") if isinstance(result.get("contribution"), dict) else {}
        agent_run_result = (
            result.get("agent_run_result") if isinstance(result.get("agent_run_result"), dict) else {}
        )
        manifest.append(
            {
                key: value
                for key, value in {
                    "task_id": result.get("task_id"),
                    "agent_name": result.get("agent_name"),
                    "status": result.get("status"),
                    "required": result.get("required"),
                    "failure_policy_applied": result.get("failure_policy_applied"),
                    "contribution_id": contribution.get("contribution_id"),
                    "input_ref": contribution.get("input_ref"),
                    "output_hash": contribution.get("output_hash"),
                    "trace_ref": result.get("trace_ref") or contribution.get("trace_ref"),
                    "input_view_hash": result.get("input_view_hash") or agent_run_result.get("input_view_hash"),
                    "agent_run_request_hash": result.get("agent_run_request_hash")
                    or agent_run_result.get("agent_run_request_hash"),
                }.items()
                if value is not None
            }
        )
    return manifest


def _coverage(
    *,
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any],
    pre_final_decision_input: dict[str, Any],
    worker_manifest: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "has_facts_gate": isinstance(audit_payload.get("facts_gate"), dict),
        "has_pre_final_decision_input": isinstance(pre_final_decision_input, dict),
        "has_lead_plan": isinstance(shadow_swarm_audit.get("lead_plan"), dict),
        "worker_count": len(worker_manifest),
        "required_worker_count": sum(1 for item in worker_manifest if item.get("required") is True),
        "failed_worker_count": sum(1 for item in worker_manifest if item.get("status") == "failed"),
    }
