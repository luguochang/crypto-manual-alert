from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.hashing import stable_hash

from .candidate_artifact_validation import CANDIDATE_ARTIFACT_TYPES


def artifact_snapshot_consistency(
    *,
    candidate_artifacts: dict[str, dict[str, Any]],
    decision_input: dict[str, Any],
    replayable_input: dict[str, Any],
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    expected = {
        "decision_input_candidate": decision_input,
        "replayable_input_candidate": replayable_input,
    }
    for artifact_type in CANDIDATE_ARTIFACT_TYPES:
        artifact = candidate_artifacts.get(artifact_type)
        if not isinstance(artifact, dict):
            violations.append({"rule_id": "candidate_artifact_snapshot_missing", "artifact_type": artifact_type})
            continue
        if artifact_type in expected:
            expected_ref = expected[artifact_type].get("input_ref")
            expected_hash = expected[artifact_type].get("input_hash")
            if artifact.get("input_ref") != expected_ref:
                violations.append(
                    {
                        "rule_id": "candidate_artifact_ref_mismatch",
                        "artifact_type": artifact_type,
                        "expected": expected_ref,
                        "observed": artifact.get("input_ref"),
                    }
                )
            if expected_hash and artifact.get("input_hash") != expected_hash:
                violations.append(
                    {
                        "rule_id": "candidate_artifact_input_hash_mismatch",
                        "artifact_type": artifact_type,
                        "expected": expected_hash,
                        "observed": artifact.get("input_hash"),
                    }
                )
        elif artifact.get("artifact_ref") != f"candidate:{artifact_type}":
            violations.append(
                {
                    "rule_id": "candidate_artifact_ref_mismatch",
                    "artifact_type": artifact_type,
                    "expected": f"candidate:{artifact_type}",
                    "observed": artifact.get("artifact_ref"),
                }
            )
        if not artifact.get("artifact_hash"):
            violations.append(
                {
                    "rule_id": "candidate_artifact_hash_missing",
                    "artifact_type": artifact_type,
                }
            )
        stored_hash = artifact.get("stored_artifact_hash")
        if stored_hash and stable_hash(without_store_metadata(artifact)) != stored_hash:
            violations.append(
                {
                    "rule_id": "candidate_artifact_store_hash_mismatch",
                    "artifact_type": artifact_type,
                    "expected": stored_hash,
                    "observed": stable_hash(without_store_metadata(artifact)),
                }
            )
    return {
        "passed": not violations,
        "violations": violations,
        "artifact_types": CANDIDATE_ARTIFACT_TYPES,
    }


def without_store_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in artifact.items()
        if key not in {"case_id", "artifact_type", "stored_artifact_hash", "created_at"}
    }
