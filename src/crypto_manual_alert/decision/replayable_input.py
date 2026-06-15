from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crypto_manual_alert.decision.replay_observed_refs import (
    observed_run_refs,
    span_tree_missing_parent_count,
    span_tree_parent_complete,
)
from crypto_manual_alert.decision.replay_sanitization import hash_payload, strip_raw_fields
from crypto_manual_alert.decision.replay_worker_refs import (
    shadow_lead_plan_ref,
    shadow_worker_refs,
    worker_manifest_missing_fields as missing_worker_manifest_fields,
    worker_result_manifest,
)


@dataclass(frozen=True)
class ReplayableInputCandidate:
    """Audit-only complete replay input candidate.

    It records artifact references and hashes for the future complete replay
    input. It intentionally avoids copying raw prompt packets, snippets, raw
    exchange JSON, or full contribution text.
    """

    schema_version: int
    mode: str
    decision_effect: str
    trace_id: str
    legacy_frozen_input_hash: str | None
    input_ref: str
    artifact_refs: dict[str, Any]
    coverage: dict[str, Any]
    input_hash: str
    validation: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "decision_effect": self.decision_effect,
            "trace_id": self.trace_id,
            "legacy_frozen_input_hash": self.legacy_frozen_input_hash,
            "input_ref": self.input_ref,
            "artifact_refs": self.artifact_refs,
            "coverage": self.coverage,
            "input_hash": self.input_hash,
            "validation": self.validation,
        }


def build_replayable_input_candidate(
    *,
    trace_id: str,
    frozen_input_hash: str | None,
    decision_input_candidate: dict[str, Any] | None,
    shadow_swarm_audit: dict[str, Any] | None,
    lead_synthesis_artifact: dict[str, Any] | None = None,
    observed_run_artifacts: dict[str, Any] | None = None,
) -> ReplayableInputCandidate:
    artifact_refs = {
        "legacy_frozen_input": {"frozen_input_hash": frozen_input_hash},
        "decision_input_candidate": _decision_input_ref(decision_input_candidate),
        "lead_synthesis_artifact": _lead_synthesis_artifact_ref(lead_synthesis_artifact),
        "shadow_lead_plan": shadow_lead_plan_ref(shadow_swarm_audit),
        "shadow_workers": shadow_worker_refs(shadow_swarm_audit),
        "worker_result_manifest": worker_result_manifest(shadow_swarm_audit),
    }
    artifact_refs.update(observed_run_refs(trace_id, observed_run_artifacts))
    worker_manifest_missing_fields = missing_worker_manifest_fields(artifact_refs["worker_result_manifest"])
    coverage = {
        "has_legacy_frozen_input": bool(frozen_input_hash),
        "has_decision_input_candidate": bool(artifact_refs["decision_input_candidate"]),
        "has_lead_synthesis_artifact": bool(artifact_refs["lead_synthesis_artifact"]),
        "has_final_decision_output": bool(artifact_refs.get("final_decision_output")),
        "has_final_input_selection": bool(artifact_refs.get("final_input_selection")),
        "has_parsed_plan": bool(artifact_refs.get("parsed_plan")),
        "has_production_control_gate": bool(artifact_refs.get("production_control_gate")),
        "has_risk_gate_result": bool(artifact_refs.get("risk_gate_result")),
        "has_side_effect_policy": bool(artifact_refs.get("side_effect_policy")),
        "has_context_artifact_summary": bool(artifact_refs.get("context_artifact_summary")),
        "has_version_lock": bool(artifact_refs.get("version_lock")),
        "has_telemetry_refs": bool(artifact_refs.get("telemetry_refs")),
        "has_evidence_snapshot_refs": bool(artifact_refs.get("evidence_snapshot_refs")),
        "has_memory_snapshot_refs": bool(artifact_refs.get("memory_snapshot_refs")),
        "has_span_tree_refs": bool(artifact_refs.get("span_tree_refs")),
        "span_tree_parent_complete": span_tree_parent_complete(artifact_refs.get("span_tree_refs")),
        "span_tree_missing_parent_count": span_tree_missing_parent_count(artifact_refs.get("span_tree_refs")),
        "worker_artifact_count": len(artifact_refs["shadow_workers"]),
        "worker_manifest_count": len(artifact_refs["worker_result_manifest"]),
        "worker_manifest_complete": not worker_manifest_missing_fields,
        "worker_manifest_missing_fields": worker_manifest_missing_fields,
        "tool_call_artifact_count": sum(
            len(item.get("tool_call_artifact_refs") or [])
            for item in artifact_refs["worker_result_manifest"]
            if isinstance(item, dict)
        ),
        "evidence_ref_count": len((decision_input_candidate or {}).get("evidence_refs") or []),
        "included_contribution_count": len(
            ((decision_input_candidate or {}).get("lead_synthesis") or {}).get("included_contribution_ids") or []
        ),
        "dropped_contribution_count": len(
            ((decision_input_candidate or {}).get("lead_synthesis") or {}).get("dropped_contributions") or []
        ),
    }
    input_hash = hash_payload({"trace_id": trace_id, "artifact_refs": artifact_refs, "coverage": coverage})
    return ReplayableInputCandidate(
        schema_version=1,
        mode="candidate_audit",
        decision_effect="none",
        trace_id=trace_id,
        legacy_frozen_input_hash=frozen_input_hash,
        input_ref=f"trace:{trace_id}:replayable_input_candidate",
        artifact_refs=artifact_refs,
        coverage=coverage,
        input_hash=input_hash,
        validation={
            "passed": True,
            "severity": "ok",
            "violations": [],
            "payload_policy": "refs_and_hashes_only",
        },
    )


def failed_replayable_input_candidate(trace_id: str, frozen_input_hash: str | None, exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "candidate_audit",
        "decision_effect": "none",
        "trace_id": trace_id,
        "legacy_frozen_input_hash": frozen_input_hash,
        "input_ref": f"trace:{trace_id}:replayable_input_candidate",
        "error": {"type": type(exc).__name__, "message": str(exc)},
        "validation": {
            "passed": False,
            "severity": "hard_fail",
            "violations": [{"rule_id": "replayable_input_candidate.build_failed"}],
        },
    }


def _decision_input_ref(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(candidate, dict) or candidate.get("error"):
        return None
    return {
        "input_ref": candidate.get("input_ref"),
        "input_hash": candidate.get("input_hash"),
    }


def _lead_synthesis_artifact_ref(artifact: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(artifact, dict) or artifact.get("decision_effect") != "none":
        return None
    ref = {
        key: artifact.get(key)
        for key in ("artifact_ref", "input_ref", "input_hash", "decision_effect")
        if artifact.get(key) is not None
    }
    if not ref:
        return None
    ref["artifact_hash"] = hash_payload(strip_raw_fields(artifact))
    return ref
