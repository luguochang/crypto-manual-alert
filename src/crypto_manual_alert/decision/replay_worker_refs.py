from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import tool_call_artifact_ref_fields
from crypto_manual_alert.decision.replay_sanitization import hash_payload


def shadow_lead_plan_ref(shadow_swarm_audit: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(shadow_swarm_audit, dict):
        return None
    lead_plan = shadow_swarm_audit.get("lead_plan")
    if not isinstance(lead_plan, dict):
        return None
    return {"plan_id": lead_plan.get("plan_id")}


def shadow_worker_refs(shadow_swarm_audit: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(shadow_swarm_audit, dict):
        return []
    refs = []
    for result in shadow_swarm_audit.get("worker_results") or []:
        if not isinstance(result, dict):
            continue
        contribution = result.get("contribution") if isinstance(result.get("contribution"), dict) else {}
        refs.append(
            {
                "task_id": result.get("task_id"),
                "agent_name": result.get("agent_name"),
                "status": result.get("status"),
                "contribution_id": contribution.get("contribution_id"),
                "output_hash": contribution.get("output_hash"),
                "input_ref": contribution.get("input_ref"),
            }
        )
    return refs


def worker_result_manifest(shadow_swarm_audit: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(shadow_swarm_audit, dict):
        return []
    manifest = []
    for result in shadow_swarm_audit.get("worker_results") or []:
        if not isinstance(result, dict):
            continue
        contribution = result.get("contribution") if isinstance(result.get("contribution"), dict) else {}
        agent_run_result = (
            result.get("agent_run_result")
            if isinstance(result.get("agent_run_result"), dict)
            else {}
        )
        item = {
            "task_id": result.get("task_id") or agent_run_result.get("task_id"),
            "agent_name": result.get("agent_name") or agent_run_result.get("agent_name"),
            "status": result.get("status") or agent_run_result.get("status"),
            "input_ref": contribution.get("input_ref"),
            "input_hash": agent_run_result.get("input_view_hash")
            or _legacy_worker_input_ref_hash(result, agent_run_result, contribution),
            "agent_run_request_hash": agent_run_result.get("agent_run_request_hash"),
            "output_hash": contribution.get("output_hash") or agent_run_result.get("output_hash"),
            "trace_ref": result.get("trace_ref") or contribution.get("trace_ref") or agent_run_result.get("trace_ref"),
            "failure_policy_applied": (
                result.get("failure_policy_applied")
                or contribution.get("failure_policy_applied")
                or agent_run_result.get("failure_policy_applied")
            ),
            "required": _required_from_result(result, contribution, agent_run_result),
            "agent_run_result": _agent_run_result_ref(agent_run_result),
        }
        tool_call_artifact_refs = tool_call_artifact_ref_fields(contribution)
        if tool_call_artifact_refs:
            item["tool_call_artifact_refs"] = tool_call_artifact_refs
        manifest.append(item)
    return manifest


def worker_manifest_missing_fields(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required_fields = (
        "task_id",
        "agent_name",
        "status",
        "input_ref",
        "input_hash",
        "agent_run_request_hash",
        "output_hash",
        "trace_ref",
        "failure_policy_applied",
    )
    missing_items: list[dict[str, Any]] = []
    for item in manifest:
        missing_fields = [field for field in required_fields if item.get(field) in {None, ""}]
        if missing_fields:
            missing_items.append(
                {
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                    "missing_fields": missing_fields,
                }
            )
    return missing_items


def _agent_run_result_ref(agent_run_result: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "task_id",
        "agent_name",
        "status",
        "contribution_ref",
        "input_view_hash",
        "agent_run_request_hash",
        "output_hash",
        "trace_ref",
        "failure_policy_applied",
        "required",
        "decision_effect",
    )
    return {key: agent_run_result.get(key) for key in allowed_keys if key in agent_run_result}


def _required_from_result(
    result: dict[str, Any],
    contribution: dict[str, Any],
    agent_run_result: dict[str, Any],
) -> bool | None:
    for payload in (result, agent_run_result, contribution):
        if "required" in payload:
            return bool(payload.get("required"))
    return None


def _legacy_worker_input_ref_hash(
    result: dict[str, Any],
    agent_run_result: dict[str, Any],
    contribution: dict[str, Any],
) -> str:
    return hash_payload(
        {
            "task_id": result.get("task_id") or agent_run_result.get("task_id"),
            "agent_name": result.get("agent_name") or agent_run_result.get("agent_name"),
            "input_ref": contribution.get("input_ref"),
        }
    )
