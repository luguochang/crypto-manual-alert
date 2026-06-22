from __future__ import annotations

from typing import Any


def worker_manifest_consistency(
    *,
    coverage: dict[str, Any],
    artifact_refs: dict[str, Any],
    decision_input: dict[str, Any] | None = None,
    candidate_artifacts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = artifact_refs.get("worker_result_manifest")
    worker_refs = artifact_refs.get("shadow_workers")
    manifest_items = manifest if isinstance(manifest, list) else []
    worker_ref_items = worker_refs if isinstance(worker_refs, list) else []
    violations: list[dict[str, Any]] = []
    expected_manifest_count = coverage.get("worker_manifest_count")
    if expected_manifest_count is None:
        expected_manifest_count = coverage.get("worker_artifact_count")
    if isinstance(expected_manifest_count, int) and len(manifest_items) != expected_manifest_count:
        violations.append(
            {
                "rule_id": "worker_manifest_count_mismatch",
                "expected": expected_manifest_count,
                "observed": len(manifest_items),
            }
        )
    expected_worker_count = coverage.get("worker_artifact_count")
    if isinstance(expected_worker_count, int) and len(worker_ref_items) != expected_worker_count:
        violations.append(
            {
                "rule_id": "worker_artifact_count_mismatch",
                "expected": expected_worker_count,
                "observed": len(worker_ref_items),
            }
        )
    for item in manifest_items:
        if not isinstance(item, dict):
            continue
        agent_run_result = (
            item.get("agent_run_result")
            if isinstance(item.get("agent_run_result"), dict)
            else {}
        )
        if (
            item.get("input_hash")
            and agent_run_result.get("input_view_hash")
            and item.get("input_hash") != agent_run_result.get("input_view_hash")
        ):
            violations.append(
                {
                    "rule_id": "worker_input_hash_mismatch",
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                }
            )
        if (
            item.get("agent_run_request_hash")
            and agent_run_result.get("agent_run_request_hash")
            and item.get("agent_run_request_hash") != agent_run_result.get("agent_run_request_hash")
        ):
            violations.append(
                {
                    "rule_id": "agent_run_request_hash_mismatch",
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                }
            )
        if (
            "required" in item
            and "required" in agent_run_result
            and bool(item.get("required")) != bool(agent_run_result.get("required"))
        ):
            violations.append(
                {
                    "rule_id": "worker_required_flag_mismatch",
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                    "expected": bool(agent_run_result.get("required")),
                    "observed": bool(item.get("required")),
                }
            )
        if (
            item.get("failure_policy_applied")
            and agent_run_result.get("failure_policy_applied")
            and item.get("failure_policy_applied") != agent_run_result.get("failure_policy_applied")
        ):
            violations.append(
                {
                    "rule_id": "worker_failure_policy_mismatch",
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                    "expected": agent_run_result.get("failure_policy_applied"),
                    "observed": item.get("failure_policy_applied"),
                }
            )
    lead_synthesis = lead_synthesis_payload(
        decision_input=decision_input or {},
        candidate_artifacts=candidate_artifacts or {},
    )
    violations.extend(
        lead_synthesis_worker_drop_violations(
            manifest_items=manifest_items,
            lead_synthesis=lead_synthesis,
        )
    )
    advisories = lead_synthesis_optional_worker_drop_advisories(
        manifest_items=manifest_items,
        lead_synthesis=lead_synthesis,
    )
    return {
        "passed": not violations,
        "violations": violations,
        "advisories": advisories,
        "manifest_count": len(manifest_items),
        "worker_ref_count": len(worker_ref_items),
    }


def lead_synthesis_payload(
    *,
    decision_input: dict[str, Any],
    candidate_artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    artifact = candidate_artifacts.get("lead_synthesis")
    if isinstance(artifact, dict) and isinstance(artifact.get("lead_synthesis"), dict):
        return artifact["lead_synthesis"]
    synthesis = decision_input.get("lead_synthesis")
    return synthesis if isinstance(synthesis, dict) else {}


def lead_synthesis_artifact(candidate_artifacts: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    artifact = candidate_artifacts.get("lead_synthesis")
    return artifact if isinstance(artifact, dict) else None


def lead_synthesis_artifact_counter_conflict_violations(
    artifact: dict[str, Any] | None,
    *,
    counter_count: int,
    conflict_count: int,
) -> list[dict[str, Any]]:
    if not isinstance(artifact, dict) or artifact.get("artifact_ref") != "candidate:lead_synthesis":
        return []
    violations: list[dict[str, Any]] = []
    artifact_counter_count = artifact_count(artifact, "counter_thesis_count", counter_count)
    artifact_counter_ref_count = artifact_ref_count(artifact, "counter_thesis_refs")
    if artifact_counter_count and artifact_counter_ref_count < artifact_counter_count:
        violations.append(
            {
                "rule_id": "lead_synthesis_artifact_counter_thesis_refs_missing",
                "counter_thesis_count": artifact_counter_count,
            }
        )
    if artifact_counter_count and not isinstance(artifact.get("strongest_counter_thesis_ref"), dict):
        violations.append(
            {
                "rule_id": "lead_synthesis_artifact_strongest_counter_missing",
                "counter_thesis_count": artifact_counter_count,
            }
        )
    artifact_conflict_count = artifact_count(artifact, "conflict_count", conflict_count)
    artifact_conflict_ref_count = artifact_ref_count(artifact, "conflict_refs")
    if artifact_conflict_count and artifact_conflict_ref_count < artifact_conflict_count:
        violations.append(
            {
                "rule_id": "lead_synthesis_artifact_conflict_refs_missing",
                "conflict_count": artifact_conflict_count,
            }
        )
    return violations


def artifact_count(artifact: dict[str, Any], key: str, fallback: int) -> int:
    value = artifact.get(key)
    return value if isinstance(value, int) and value >= 0 else fallback


def artifact_ref_count(artifact: dict[str, Any] | None, key: str) -> int:
    if not isinstance(artifact, dict):
        return 0
    refs = artifact.get(key)
    return len(refs) if isinstance(refs, list) else 0


def lead_synthesis_worker_drop_violations(
    *,
    manifest_items: list[Any],
    lead_synthesis: dict[str, Any],
) -> list[dict[str, Any]]:
    dropped = lead_synthesis.get("dropped_contributions")
    if not isinstance(dropped, list):
        dropped = []
    violations: list[dict[str, Any]] = []
    for item in manifest_items:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"failed", "skipped"}:
            continue
        if not manifest_item_required(item):
            continue
        matching_drop = matching_dropped_contribution(item, dropped)
        if matching_drop is None:
            violations.append(
                {
                    "rule_id": "lead_synthesis_missing_failed_worker_drop",
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                    "failure_policy_applied": manifest_failure_policy(item),
                }
            )
            continue
        expected_policy = manifest_failure_policy(item)
        observed_policy = matching_drop.get("failure_policy_applied")
        if expected_policy and observed_policy and expected_policy != observed_policy:
            violations.append(
                {
                    "rule_id": "lead_synthesis_failed_worker_failure_policy_mismatch",
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                    "expected": expected_policy,
                    "observed": observed_policy,
                }
            )
        if matching_drop.get("required") is not True:
            violations.append(
                {
                    "rule_id": "lead_synthesis_failed_worker_required_flag_mismatch",
                    "task_id": item.get("task_id"),
                    "agent_name": item.get("agent_name"),
                    "expected": True,
                    "observed": matching_drop.get("required"),
                }
            )
    return violations


def lead_synthesis_optional_worker_drop_advisories(
    *,
    manifest_items: list[Any],
    lead_synthesis: dict[str, Any],
) -> list[dict[str, Any]]:
    dropped = lead_synthesis.get("dropped_contributions")
    if not isinstance(dropped, list):
        dropped = []
    advisories: list[dict[str, Any]] = []
    for item in manifest_items:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"failed", "skipped"}:
            continue
        if manifest_item_required(item):
            continue
        if matching_dropped_contribution(item, dropped) is not None:
            continue
        advisories.append(
            {
                "rule_id": "lead_synthesis_missing_optional_worker_drop",
                "task_id": item.get("task_id"),
                "agent_name": item.get("agent_name"),
                "failure_policy_applied": manifest_failure_policy(item),
            }
        )
    return advisories


def matching_dropped_contribution(
    manifest_item: dict[str, Any],
    dropped: list[Any],
) -> dict[str, Any] | None:
    agent_name = manifest_item.get("agent_name")
    for item in dropped:
        if not isinstance(item, dict):
            continue
        if item.get("agent_name") == agent_name:
            return item
    return None


def manifest_item_required(item: dict[str, Any]) -> bool:
    if "required" in item:
        return bool(item.get("required"))
    agent_run_result = item.get("agent_run_result") if isinstance(item.get("agent_run_result"), dict) else {}
    if "required" in agent_run_result:
        return bool(agent_run_result.get("required"))
    return False


def manifest_failure_policy(item: dict[str, Any]) -> Any:
    if item.get("failure_policy_applied"):
        return item.get("failure_policy_applied")
    agent_run_result = item.get("agent_run_result") if isinstance(item.get("agent_run_result"), dict) else {}
    return agent_run_result.get("failure_policy_applied")
