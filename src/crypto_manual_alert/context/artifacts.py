from __future__ import annotations

from typing import Any

from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import RiskVerdict


def record_orchestration_artifacts(
    context: DecisionRunContext | None,
    *,
    audit_payload: dict[str, Any] | None = None,
    shadow_swarm_audit: dict[str, Any] | None = None,
    pre_final_decision_input: dict[str, Any] | None = None,
    pre_final_bundle: dict[str, Any] | None = None,
    candidate_audit: dict[str, Any] | None = None,
    production_control_verdict: RiskVerdict | None = None,
) -> None:
    """Copy controlled orchestration artifacts into DecisionRunContext.

    This is an append-only audit boundary. It does not decide trades, run
    agents, write journals, or send notifications.
    """

    if context is None:
        return
    _record_audit_artifacts(context, audit_payload)
    _record_shadow_swarm(context, shadow_swarm_audit)
    _record_pre_final_input(context, pre_final_decision_input)
    _record_pre_final_bundle(context, pre_final_bundle)
    _record_candidate_audit(context, candidate_audit)
    _record_production_control(context, production_control_verdict)


def _record_audit_artifacts(context: DecisionRunContext, audit_payload: dict[str, Any] | None) -> None:
    if not audit_payload:
        return
    for packet in audit_payload.get("evidence_packets") or []:
        context.append_evidence(packet, writer_role="workflow")
    for contribution in audit_payload.get("agent_contributions") or []:
        context.append_contribution(contribution, writer_role="workflow")
    facts_gate = audit_payload.get("facts_gate")
    if isinstance(facts_gate, dict):
        context.set_gate_result("facts_gate", facts_gate, writer_role="gate")


def _record_shadow_swarm(context: DecisionRunContext, shadow_swarm_audit: dict[str, Any] | None) -> None:
    if not isinstance(shadow_swarm_audit, dict):
        return
    lead_plan = shadow_swarm_audit.get("lead_plan")
    if isinstance(lead_plan, dict):
        context.set_lead_plan(lead_plan, writer_role="lead")
    for result in shadow_swarm_audit.get("worker_results") or []:
        if isinstance(result, dict) and isinstance(result.get("contribution"), dict):
            context.append_contribution(result["contribution"], writer_role="worker")


def _record_pre_final_input(
    context: DecisionRunContext, pre_final_decision_input: dict[str, Any] | None
) -> None:
    if isinstance(pre_final_decision_input, dict):
        context.set_decision_input(pre_final_decision_input, writer_role="decision_input_builder")


def _record_pre_final_bundle(context: DecisionRunContext, pre_final_bundle: dict[str, Any] | None) -> None:
    if isinstance(pre_final_bundle, dict):
        context.set_gate_result("pre_final_bundle", pre_final_bundle, writer_role="gate")


def _record_candidate_audit(context: DecisionRunContext, candidate_audit: dict[str, Any] | None) -> None:
    if not isinstance(candidate_audit, dict):
        return
    for gate_name in (
        "decision_input_candidate",
        "candidate_final_decision",
        "lead_synthesis_artifact",
        "gate_candidate",
        "plan_semantic_candidate",
        "final_decision_switch_readiness",
        "replayable_input_candidate",
    ):
        gate_result = candidate_audit.get(gate_name)
        if isinstance(gate_result, dict):
            context.set_gate_result(gate_name, gate_result, writer_role="gate")


def _record_production_control(context: DecisionRunContext, verdict: RiskVerdict | None) -> None:
    if verdict is not None:
        context.set_gate_result("production_control_gate", verdict.to_public_dict(), writer_role="gate")
