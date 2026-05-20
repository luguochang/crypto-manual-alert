from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.context.artifacts import record_orchestration_artifacts
from crypto_manual_alert.decision.pre_final_bundle import build_pre_final_bundle
from crypto_manual_alert.decision.pre_final_input import build_pre_final_input_payload
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.artifacts.orchestration_inputs import build_audit_artifacts
from crypto_manual_alert.research_pipeline import ResearchAudit
from crypto_manual_alert.orchestration.shadow_audit import run_shadow_swarm_audit


@dataclass(frozen=True)
class PreFinalOrchestrationResult:
    """Audit-only orchestration artifacts built before FinalDecisionAgent.

    This step does not feed FinalDecisionAgent and does not write journals or
    notifications. It prepares the controlled swarm audit and pre-final
    DecisionInput candidate for later candidate gates and replay.
    """

    audit_payload: dict[str, Any]
    shadow_swarm_audit: dict[str, Any]
    pre_final_decision_input: dict[str, Any]
    pre_final_bundle: dict[str, Any]
    pre_final_summary: dict[str, Any]


def run_pre_final_orchestration(
    *,
    symbol: str,
    trace_id: str,
    recorder: ObservabilityRecorder,
    snapshot: MarketSnapshot | None,
    research_audit: ResearchAudit | None,
    run_context: DecisionRunContext | None,
    config: object | None = None,
    tool_executor: Any | None = None,
) -> PreFinalOrchestrationResult:
    audit_payload = build_audit_artifacts(
        trace_id=trace_id,
        snapshot=snapshot,
        research_audit=research_audit,
    )
    shadow_swarm_audit = run_shadow_swarm_audit(
        symbol=symbol,
        trace_id=trace_id,
        recorder=recorder,
        snapshot=snapshot,
        research_audit=research_audit,
        config=config,
        tool_executor=tool_executor,
        audit_payload=audit_payload,
    )
    record_orchestration_artifacts(
        run_context,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
    )
    pre_final_decision_input = build_pre_final_input_payload(
        trace_id=trace_id,
        symbol=symbol,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
    )
    pre_final_bundle = build_pre_final_bundle(
        trace_id=trace_id,
        symbol=symbol,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        pre_final_decision_input=pre_final_decision_input,
    )
    record_orchestration_artifacts(
        run_context,
        pre_final_decision_input=pre_final_decision_input,
        pre_final_bundle=pre_final_bundle,
    )
    return PreFinalOrchestrationResult(
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        pre_final_decision_input=pre_final_decision_input,
        pre_final_bundle=pre_final_bundle,
        pre_final_summary={
            "mode": pre_final_decision_input.get("mode"),
            "decision_effect": pre_final_decision_input.get("decision_effect"),
            "validation_passed": (pre_final_decision_input.get("validation") or {}).get("passed"),
            "bundle_ref": pre_final_bundle.get("artifact_ref"),
        },
    )
