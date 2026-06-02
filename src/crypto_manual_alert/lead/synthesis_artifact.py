from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


RAW_FIELD_NAMES = {
    "payload",
    "raw",
    "raw_payload",
    "raw_snippet",
    "raw_decision",
    "raw_prompt",
}


@dataclass(frozen=True)
class LeadSynthesisArtifact:
    """Replayable audit artifact for lead synthesis candidate output."""

    schema_version: int
    artifact_type: str
    artifact_ref: str
    decision_effect: str
    input_ref: str
    input_hash: str
    lead_plan_ref: str | None
    lead_plan_hash: str
    worker_manifest_hash: str
    included_contribution_refs: list[dict[str, Any]]
    dropped_contribution_refs: list[dict[str, Any]]
    counter_thesis_refs: list[dict[str, Any]]
    strongest_counter_thesis_ref: dict[str, Any] | None
    conflict_refs: list[dict[str, Any]]
    counter_thesis_count: int
    conflict_count: int
    policy_version: str
    required_worker_status: list[dict[str, Any]] = field(default_factory=list)
    missing_fact_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type,
            "artifact_ref": self.artifact_ref,
            "decision_effect": self.decision_effect,
            "input_ref": self.input_ref,
            "input_hash": self.input_hash,
            "lead_plan_ref": self.lead_plan_ref,
            "lead_plan_hash": self.lead_plan_hash,
            "worker_manifest_hash": self.worker_manifest_hash,
            "included_contribution_refs": self.included_contribution_refs,
            "dropped_contribution_refs": self.dropped_contribution_refs,
            "counter_thesis_refs": self.counter_thesis_refs,
            "strongest_counter_thesis_ref": self.strongest_counter_thesis_ref,
            "conflict_refs": self.conflict_refs,
            "counter_thesis_count": self.counter_thesis_count,
            "conflict_count": self.conflict_count,
            "policy_version": self.policy_version,
            "required_worker_status": self.required_worker_status,
            "missing_fact_refs": self.missing_fact_refs,
        }


def build_lead_synthesis_artifact(
    *,
    input_ref: str,
    lead_synthesis: dict[str, Any],
    lead_plan: dict[str, Any] | None,
    worker_manifest: list[dict[str, Any]] | None,
    required_workers: list[str] | tuple[str, ...] = (),
    policy_version: str = "lead_synthesis_artifact.v1",
) -> LeadSynthesisArtifact:
    safe_synthesis = _strip_raw_fields(lead_synthesis)
    safe_lead_plan = _strip_raw_fields(lead_plan or {})
    safe_worker_manifest = [_strip_raw_fields(item) for item in worker_manifest or [] if isinstance(item, dict)]

    lead_plan_ref = _lead_plan_ref(safe_lead_plan)
    lead_plan_hash = _existing_hash(safe_lead_plan, ("lead_plan_hash", "plan_hash", "input_hash")) or _hash_payload(
        safe_lead_plan
    )
    worker_manifest_hash = _hash_payload(safe_worker_manifest)
    included_contribution_refs = _included_contribution_refs(safe_synthesis, safe_worker_manifest)
    required_worker_status = _required_worker_status(required_workers, safe_worker_manifest)
    dropped_contribution_refs = _dropped_contribution_refs(safe_synthesis, required_worker_status)
    counter_thesis_refs = _counter_thesis_refs(safe_synthesis)
    strongest_counter_thesis_ref = _strongest_counter_thesis_ref(
        safe_synthesis,
        counter_thesis_refs=counter_thesis_refs,
    )
    conflict_refs = _conflict_refs(safe_synthesis)
    missing_fact_refs = _missing_fact_refs(safe_synthesis)
    input_hash = _hash_payload(
        {
            "lead_synthesis": safe_synthesis,
            "lead_plan": safe_lead_plan,
            "worker_manifest": safe_worker_manifest,
        }
    )

    return LeadSynthesisArtifact(
        schema_version=1,
        artifact_type="lead_synthesis",
        artifact_ref="candidate:lead_synthesis",
        decision_effect="none",
        input_ref=input_ref,
        input_hash=input_hash,
        lead_plan_ref=lead_plan_ref,
        lead_plan_hash=lead_plan_hash,
        worker_manifest_hash=worker_manifest_hash,
        included_contribution_refs=included_contribution_refs,
        dropped_contribution_refs=dropped_contribution_refs,
        counter_thesis_refs=counter_thesis_refs,
        strongest_counter_thesis_ref=strongest_counter_thesis_ref,
        conflict_refs=conflict_refs,
        counter_thesis_count=_list_count(safe_synthesis.get("counter_thesis")) or len(counter_thesis_refs),
        conflict_count=_list_count(safe_synthesis.get("conflicts")) or len(conflict_refs),
        policy_version=policy_version,
        required_worker_status=required_worker_status,
        missing_fact_refs=missing_fact_refs,
    )


def _included_contribution_refs(
    lead_synthesis: dict[str, Any],
    worker_manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {
        item.get("contribution_id"): item
        for item in worker_manifest
        if item.get("contribution_id") not in {None, ""}
    }
    refs = []
    for contribution_id in lead_synthesis.get("included_contribution_ids") or []:
        ref = {"contribution_id": contribution_id}
        manifest_item = by_id.get(contribution_id)
        if isinstance(manifest_item, dict):
            for key in ("output_hash", "input_ref", "trace_ref"):
                if manifest_item.get(key):
                    ref[key] = manifest_item[key]
        refs.append(ref)
    return refs


def _dropped_contribution_refs(
    lead_synthesis: dict[str, Any],
    required_worker_status: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    dropped_agent_names: set[str] = set()
    for item in lead_synthesis.get("dropped_contributions") or []:
        if not isinstance(item, dict):
            continue
        ref = {
            key: item.get(key)
            for key in (
                "contribution_id",
                "agent_name",
                "reason",
                "required",
                "failure_policy_applied",
                "error_type",
                "summary",
            )
            if key in item
        }
        if ref:
            refs.append(ref)
        agent_name = item.get("agent_name")
        if agent_name:
            dropped_agent_names.add(str(agent_name))
    for item in required_worker_status:
        agent_name = item.get("agent_name")
        if item.get("status") == "missing" and agent_name not in dropped_agent_names:
            refs.append(
                {
                    "contribution_id": None,
                    "agent_name": agent_name,
                    "reason": "missing_required_worker",
                }
            )
    return refs


def _conflict_refs(lead_synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    refs = []
    source_conflicts = lead_synthesis.get("conflict_refs") or lead_synthesis.get("conflicts") or []
    for item in source_conflicts:
        if isinstance(item, dict):
            ref = {
                key: item.get(key)
                for key in ("conflict_id", "summary", "sides", "contribution_refs")
                if key in item
            }
            if "conflict_id" not in ref and ref.get("summary"):
                ref["conflict_id"] = _hash_payload(ref["summary"])
            if ref:
                refs.append(ref)
        else:
            refs.append({"conflict_id": str(item), "summary": str(item)})
    return refs


def _counter_thesis_refs(lead_synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    source_refs = lead_synthesis.get("counter_thesis_refs")
    if isinstance(source_refs, list):
        for item in source_refs:
            if not isinstance(item, dict):
                continue
            ref = {
                key: item.get(key)
                for key in ("contribution_id", "agent_name", "claim", "side", "evidence_ids")
                if key in item
            }
            if ref:
                refs.append(ref)
    if refs:
        return refs
    for item in lead_synthesis.get("counter_thesis") or []:
        if item:
            refs.append({"claim": str(item), "side": "bearish"})
    return refs


def _strongest_counter_thesis_ref(
    lead_synthesis: dict[str, Any],
    *,
    counter_thesis_refs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    ref = lead_synthesis.get("strongest_counter_thesis_ref")
    if isinstance(ref, dict):
        return {
            key: ref.get(key)
            for key in ("contribution_id", "agent_name", "claim", "side", "evidence_ids", "strength")
            if key in ref
        }
    return counter_thesis_refs[0] if counter_thesis_refs else None


def _missing_fact_refs(lead_synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    refs = []
    for item in lead_synthesis.get("missing_facts") or []:
        if isinstance(item, dict):
            ref = {key: item.get(key) for key in ("fact_ref", "summary", "reason") if key in item}
            if "fact_ref" not in ref and ref.get("summary"):
                ref["fact_ref"] = _hash_payload(ref["summary"])
            if ref:
                refs.append(ref)
        else:
            refs.append({"fact_ref": str(item)})
    return refs


def _required_worker_status(
    required_workers: list[str] | tuple[str, ...],
    worker_manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observed = {str(item.get("agent_name")) for item in worker_manifest if item.get("agent_name")}
    return [
        {"agent_name": worker, "status": "present" if worker in observed else "missing"}
        for worker in required_workers
    ]


def _lead_plan_ref(lead_plan: dict[str, Any]) -> str | None:
    for key in ("lead_plan_ref", "plan_ref", "input_ref", "plan_id"):
        if lead_plan.get(key):
            return str(lead_plan[key])
    return None


def _existing_hash(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _strip_raw_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_raw_fields(item)
            for key, item in value.items()
            if key not in RAW_FIELD_NAMES and not str(key).startswith("raw_")
        }
    if isinstance(value, list):
        return [_strip_raw_fields(item) for item in value]
    return value


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
