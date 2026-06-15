from __future__ import annotations

import logging
from typing import Any

from .decision_input import build_decision_input_candidate, failed_decision_input_candidate
from .gate_candidate import evaluate_gate_candidate, failed_gate_candidate
from crypto_manual_alert.lead.synthesis_artifact import build_lead_synthesis_artifact
from .plan_semantic_candidate import (
    evaluate_plan_semantic_candidate,
    failed_plan_semantic_candidate,
)
from .replayable_input import build_replayable_input_candidate, failed_replayable_input_candidate
from .switch_readiness import (
    evaluate_final_decision_switch_readiness,
    failed_final_decision_switch_readiness,
)


logger = logging.getLogger(__name__)


def build_candidate_audit_payload(
    *,
    trace_id: str,
    symbol: str,
    legacy_plan: dict[str, Any],
    verdict: dict[str, Any],
    frozen_input_hash: str | None,
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any] | None,
    raw_decision: str | None = None,
    final_input_selection: dict[str, Any] | None = None,
    production_control_verdict: dict[str, Any] | None = None,
    run_context_summary: dict[str, Any] | None = None,
    candidate_final_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision_input_candidate = _safe_decision_input_candidate(
        trace_id=trace_id,
        symbol=symbol,
        legacy_plan=legacy_plan,
        verdict=verdict,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
    )
    lead_synthesis_artifact = _safe_lead_synthesis_artifact(
        trace_id=trace_id,
        shadow_swarm_audit=shadow_swarm_audit,
    )
    gate_candidate = _safe_gate_candidate(
        decision_input_candidate=decision_input_candidate,
        legacy_plan=legacy_plan,
    )
    plan_semantic_candidate = _safe_plan_semantic_candidate(legacy_plan=legacy_plan)
    replayable_input_candidate = _safe_replayable_input_candidate(
        trace_id=trace_id,
        frozen_input_hash=frozen_input_hash,
        decision_input_candidate=decision_input_candidate,
        shadow_swarm_audit=shadow_swarm_audit,
        lead_synthesis_artifact=lead_synthesis_artifact,
        observed_run_artifacts={
            "final_decision_output": raw_decision,
            "final_input_selection": final_input_selection,
            "parsed_plan": legacy_plan,
            "production_control_gate": production_control_verdict,
            "risk_gate_result": verdict,
            "side_effect_policy": (
                run_context_summary.get("side_effect_policy")
                if isinstance(run_context_summary, dict)
                else None
            ),
            "context_artifact_summary": (
                run_context_summary.get("artifacts")
                if isinstance(run_context_summary, dict)
                else None
            ),
            "version_lock": (
                run_context_summary.get("version_lock")
                if isinstance(run_context_summary, dict)
                else None
            ),
            "telemetry_refs": (
                run_context_summary.get("telemetry_refs")
                if isinstance(run_context_summary, dict)
                else None
            ),
            "evidence_snapshot_refs": {
                "evidence_packets": audit_payload.get("evidence_packets") or [],
                "facts_gate": audit_payload.get("facts_gate") or {},
            },
            "memory_snapshot": (
                run_context_summary.get("memory_snapshot")
                if isinstance(run_context_summary, dict)
                else None
            ),
            "span_tree_refs": (
                run_context_summary.get("span_tree_refs")
                if isinstance(run_context_summary, dict)
                else None
            ),
        },
    )
    final_decision_switch_readiness = _safe_final_decision_switch_readiness(
        decision_input_candidate=decision_input_candidate,
        replayable_input_candidate=replayable_input_candidate,
        gate_candidate=gate_candidate,
        plan_semantic_candidate=plan_semantic_candidate,
        shadow_swarm_audit=shadow_swarm_audit,
    )
    payload = {
        "decision_input_candidate": decision_input_candidate,
        "replayable_input_candidate": replayable_input_candidate,
        "lead_synthesis_artifact": lead_synthesis_artifact,
        "gate_candidate": gate_candidate,
        "plan_semantic_candidate": plan_semantic_candidate,
        "final_decision_switch_readiness": final_decision_switch_readiness,
    }
    if candidate_final_decision is not None:
        payload["candidate_final_decision"] = _safe_candidate_final_decision(candidate_final_decision)
    return payload


def _safe_decision_input_candidate(
    *,
    trace_id: str,
    symbol: str,
    legacy_plan: dict[str, Any],
    verdict: dict[str, Any],
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        contributions = _candidate_contributions(audit_payload, shadow_swarm_audit)
        return build_decision_input_candidate(
            symbol=symbol,
            trace_id=trace_id,
            evidence_packets=audit_payload["evidence_packets"],
            facts_gate=audit_payload["facts_gate"],
            agent_contributions=contributions,
            lead_synthesis=_candidate_lead_synthesis(shadow_swarm_audit),
            legacy_plan=legacy_plan,
            verdict=verdict,
        ).to_public_dict()
    except Exception as exc:  # noqa: BLE001 - candidate audit must not affect production.
        logger.exception("decision input candidate failed")
        return failed_decision_input_candidate(trace_id, symbol, exc)


def _safe_candidate_final_decision(candidate_final_decision: dict[str, Any]) -> dict[str, Any]:
    if (
        isinstance(candidate_final_decision, dict)
        and candidate_final_decision.get("artifact_type") == "candidate_final_decision"
        and candidate_final_decision.get("decision_effect") == "none"
        and candidate_final_decision.get("production_final_input") is False
    ):
        return dict(candidate_final_decision)
    return {
        "artifact_type": "candidate_final_decision",
        "mode": "candidate_final_sidecar",
        "decision_effect": "none",
        "production_final_input": False,
        "input_gate_passed": False,
        "raw_candidate_decision": None,
        "error": {"type": "invalid_candidate_final_sidecar"},
    }


def _candidate_contributions(
    audit_payload: dict[str, Any], shadow_swarm_audit: dict[str, Any] | None
) -> list[dict[str, Any]]:
    worker_results = shadow_swarm_audit.get("worker_results") if isinstance(shadow_swarm_audit, dict) else None
    if isinstance(worker_results, list) and worker_results:
        return [
            result.get("contribution")
            for result in worker_results
            if isinstance(result, dict) and isinstance(result.get("contribution"), dict)
        ]
    return list(audit_payload.get("agent_contributions") or [])


def _candidate_lead_synthesis(shadow_swarm_audit: dict[str, Any] | None) -> dict[str, Any]:
    lead_synthesis = shadow_swarm_audit.get("lead_synthesis") if isinstance(shadow_swarm_audit, dict) else None
    if not isinstance(lead_synthesis, dict):
        raise ValueError("shadow_swarm_audit.lead_synthesis is required for DecisionInput candidate")
    return lead_synthesis


def _safe_replayable_input_candidate(
    *,
    trace_id: str,
    frozen_input_hash: str | None,
    decision_input_candidate: dict[str, Any] | None,
    shadow_swarm_audit: dict[str, Any] | None,
    lead_synthesis_artifact: dict[str, Any] | None,
    observed_run_artifacts: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        return build_replayable_input_candidate(
            trace_id=trace_id,
            frozen_input_hash=frozen_input_hash,
            decision_input_candidate=decision_input_candidate,
            shadow_swarm_audit=shadow_swarm_audit,
            lead_synthesis_artifact=lead_synthesis_artifact,
            observed_run_artifacts=observed_run_artifacts,
        ).to_public_dict()
    except Exception as exc:  # noqa: BLE001 - replay candidate must not affect production.
        logger.exception("replayable input candidate failed")
        return failed_replayable_input_candidate(trace_id, frozen_input_hash, exc)


def _safe_lead_synthesis_artifact(
    *,
    trace_id: str,
    shadow_swarm_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        if not isinstance(shadow_swarm_audit, dict):
            raise ValueError("shadow_swarm_audit is required for lead synthesis artifact")
        lead_synthesis = _candidate_lead_synthesis(shadow_swarm_audit)
        lead_plan = shadow_swarm_audit.get("lead_plan") if isinstance(shadow_swarm_audit.get("lead_plan"), dict) else {}
        worker_manifest = _worker_manifest(shadow_swarm_audit)
        required_workers = _required_workers(lead_plan)
        return build_lead_synthesis_artifact(
            input_ref=f"trace:{trace_id}:lead_synthesis",
            lead_synthesis=lead_synthesis,
            lead_plan=lead_plan,
            worker_manifest=worker_manifest,
            required_workers=required_workers,
        ).to_public_dict()
    except Exception as exc:  # noqa: BLE001 - lead synthesis artifact is audit-only.
        logger.exception("lead synthesis artifact failed")
        return {
            "schema_version": 1,
            "artifact_type": "lead_synthesis",
            "artifact_ref": "candidate:lead_synthesis",
            "decision_effect": "none",
            "status": "failed",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _worker_manifest(shadow_swarm_audit: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = []
    for result in shadow_swarm_audit.get("worker_results") or []:
        if not isinstance(result, dict):
            continue
        contribution = result.get("contribution") if isinstance(result.get("contribution"), dict) else {}
        manifest.append(
            {
                "task_id": result.get("task_id"),
                "agent_name": result.get("agent_name"),
                "status": result.get("status"),
                "contribution_id": contribution.get("contribution_id"),
                "output_hash": contribution.get("output_hash"),
                "input_ref": contribution.get("input_ref"),
                "trace_ref": result.get("trace_ref") or contribution.get("trace_ref"),
            }
        )
    return manifest


def _required_workers(lead_plan: dict[str, Any]) -> list[str]:
    workers: list[str] = []
    for task in lead_plan.get("tasks") or []:
        if not isinstance(task, dict) or task.get("required") is not True:
            continue
        agent_name = task.get("agent_name") or task.get("assigned_agent")
        if agent_name:
            workers.append(str(agent_name))
    return workers


def _safe_gate_candidate(
    *, decision_input_candidate: dict[str, Any] | None, legacy_plan: dict[str, Any]
) -> dict[str, Any]:
    try:
        return evaluate_gate_candidate(
            decision_input_candidate=decision_input_candidate or {},
            legacy_plan=legacy_plan,
        ).to_public_dict()
    except Exception as exc:  # noqa: BLE001 - gate candidate is audit-only.
        logger.exception("gate candidate failed")
        return failed_gate_candidate(exc)


def _safe_plan_semantic_candidate(*, legacy_plan: dict[str, Any]) -> dict[str, Any]:
    try:
        return evaluate_plan_semantic_candidate(legacy_plan=legacy_plan).to_public_dict()
    except Exception as exc:  # noqa: BLE001 - semantic candidate is audit-only.
        logger.exception("plan semantic candidate failed")
        return failed_plan_semantic_candidate(exc)


def _safe_final_decision_switch_readiness(
    *,
    decision_input_candidate: dict[str, Any] | None,
    replayable_input_candidate: dict[str, Any] | None,
    gate_candidate: dict[str, Any] | None,
    plan_semantic_candidate: dict[str, Any] | None,
    shadow_swarm_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        return evaluate_final_decision_switch_readiness(
            decision_input_candidate=decision_input_candidate or {},
            replayable_input_candidate=replayable_input_candidate or {},
            gate_candidate=gate_candidate or {},
            plan_semantic_candidate=plan_semantic_candidate or {},
            shadow_swarm_audit=shadow_swarm_audit or {},
        ).to_public_dict()
    except Exception as exc:  # noqa: BLE001 - readiness is audit-only.
        logger.exception("final decision switch readiness failed")
        return failed_final_decision_switch_readiness(exc)
