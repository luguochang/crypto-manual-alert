from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import tool_call_artifact_ref_fields


def project_tool_calls(worker_results: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in _list(worker_results):
        result = _mapping(item)
        contribution = _mapping(result.get("contribution"))
        worker = result.get("agent_name") or contribution.get("agent_name")
        task_id = result.get("task_id") or contribution.get("task_id")
        for ref in tool_call_artifact_ref_fields(contribution):
            calls.append(
                _drop_none(
                    {
                        "worker": worker,
                        "task_id": task_id,
                        **ref,
                    }
                )
            )
    return calls


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
