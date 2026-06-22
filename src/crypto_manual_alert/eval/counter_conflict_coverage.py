from __future__ import annotations

from typing import Any

from .worker_manifest_consistency import (
    artifact_count,
    artifact_ref_count,
    lead_synthesis_artifact_counter_conflict_violations,
)


def counter_conflict_coverage(
    lead_synthesis: dict[str, Any],
    *,
    lead_synthesis_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counter_thesis = lead_synthesis.get("counter_thesis")
    counter_refs = lead_synthesis.get("counter_thesis_refs")
    strongest_counter = lead_synthesis.get("strongest_counter_thesis_ref")
    conflicts = lead_synthesis.get("conflicts")
    conflict_refs = lead_synthesis.get("conflict_refs")

    counter_count = len(counter_thesis) if isinstance(counter_thesis, list) else 0
    counter_ref_count = len(counter_refs) if isinstance(counter_refs, list) else 0
    conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
    conflict_ref_count = len(conflict_refs) if isinstance(conflict_refs, list) else 0
    violations: list[dict[str, Any]] = []

    if counter_count and counter_ref_count < counter_count:
        violations.append(
            {
                "rule_id": "lead_synthesis_counter_thesis_refs_missing",
                "counter_thesis_count": counter_count,
            }
        )
    if counter_count and not isinstance(strongest_counter, dict):
        violations.append(
            {
                "rule_id": "lead_synthesis_strongest_counter_missing",
                "counter_thesis_count": counter_count,
            }
        )
    if conflict_count and conflict_ref_count < conflict_count:
        violations.append(
            {
                "rule_id": "lead_synthesis_conflict_refs_missing",
                "conflict_count": conflict_count,
            }
        )
    violations.extend(
        lead_synthesis_artifact_counter_conflict_violations(
            lead_synthesis_artifact,
            counter_count=counter_count,
            conflict_count=conflict_count,
        )
    )

    artifact_counter_count = artifact_count(lead_synthesis_artifact or {}, "counter_thesis_count", counter_count)
    artifact_counter_ref_count = artifact_ref_count(lead_synthesis_artifact, "counter_thesis_refs")
    artifact_conflict_count = artifact_count(lead_synthesis_artifact or {}, "conflict_count", conflict_count)
    artifact_conflict_ref_count = artifact_ref_count(lead_synthesis_artifact, "conflict_refs")

    return {
        "passed": not violations,
        "violations": violations,
        "counter_thesis_count": max(counter_count, artifact_counter_count),
        "counter_thesis_ref_count": max(counter_ref_count, artifact_counter_ref_count),
        "conflict_count": max(conflict_count, artifact_conflict_count),
        "conflict_ref_count": max(conflict_ref_count, artifact_conflict_ref_count),
    }
