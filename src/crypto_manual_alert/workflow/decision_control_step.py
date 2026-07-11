from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.config import Config
from crypto_manual_alert.decision.candidate_audit import build_candidate_audit_payload
from crypto_manual_alert.decision.production_control_gate import check_production_control_gate
from crypto_manual_alert.domain import DecisionPlan, MarketSnapshot, RiskVerdict, RuleHit
from crypto_manual_alert.decision.risk import check_plan
from crypto_manual_alert.workflow.candidate_sidecar_step import run_candidate_sidecar_step
from crypto_manual_alert.workflow.risk_merge_policy import merge_risk_verdicts


@dataclass(frozen=True)
class DecisionControlStepResult:
    """Result of the post-final controlled decision gates.

    This step does not run the FinalDecisionAgent and does not write journals or
    notifications. It builds audit-only candidate artifacts, promotes eligible
    candidate failures into production risk rules, and merges them with the
    legacy RiskGate verdict.
    """

    candidate_audit: dict[str, Any]
    production_control_verdict: RiskVerdict
    final_verdict: RiskVerdict
    production_control_summary: dict[str, Any]
    risk_summary: dict[str, Any]


def run_decision_control_step(
    *,
    trace_id: str,
    plan: DecisionPlan,
    snapshot: MarketSnapshot,
    config: Config,
    frozen_input_hash: str | None,
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any] | None,
    raw_decision: str | None = None,
    final_input_selection: dict[str, Any] | None = None,
    candidate_decision_engine: Any | None = None,
    pre_final_decision_input: dict[str, Any] | None = None,
    run_context_summary: dict[str, Any] | None = None,
    telemetry_refs: dict[str, Any] | None = None,
    span_tree_refs: dict[str, Any] | None = None,
) -> DecisionControlStepResult:
    """Run candidate audit, production control, and legacy risk checks.

    The order is intentional: production_control_gate observes the candidate
    audit before legacy RiskGate, then candidate audit is rebuilt with the final
    merged verdict so replay/eval can see the actual legacy decision reference.
    """

    candidate_run_context_summary = _with_observability_refs(
        run_context_summary,
        telemetry_refs=telemetry_refs,
        span_tree_refs=span_tree_refs,
    )
    symbol_consistency = _symbol_consistency(
        request_symbol=_symbol_from_run_context(run_context_summary),
        snapshot_symbol=snapshot.symbol,
        plan_instrument=plan.instrument,
    )
    candidate_final_decision = run_candidate_sidecar_step(
        candidate_decision_engine=candidate_decision_engine,
        pre_final_decision_input=pre_final_decision_input,
    )
    candidate_audit = build_candidate_audit_payload(
        trace_id=trace_id,
        symbol=plan.instrument,
        legacy_plan=plan.raw,
        verdict={"allowed": True, "reasons": [], "warnings": [], "rule_hits": []},
        frozen_input_hash=frozen_input_hash,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        raw_decision=raw_decision,
        final_input_selection=final_input_selection,
        run_context_summary=candidate_run_context_summary,
        candidate_final_decision=candidate_final_decision,
    )
    candidate_audit["symbol_consistency"] = symbol_consistency
    production_control_verdict = check_production_control_gate(
        plan,
        candidate_audit=candidate_audit,
        shadow_swarm_audit=shadow_swarm_audit,
    )
    symbol_consistency_verdict = _symbol_consistency_verdict(symbol_consistency)
    final_verdict = merge_risk_verdicts(
        production_control_verdict,
        symbol_consistency_verdict,
        check_plan(plan, snapshot, config),
    )
    final_candidate_audit = build_candidate_audit_payload(
        trace_id=trace_id,
        symbol=plan.instrument,
        legacy_plan=plan.raw,
        verdict=final_verdict.to_public_dict(),
        frozen_input_hash=frozen_input_hash,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        raw_decision=raw_decision,
        final_input_selection=final_input_selection,
        production_control_verdict=production_control_verdict.to_public_dict(),
        run_context_summary=candidate_run_context_summary,
        candidate_final_decision=candidate_final_decision,
    )
    final_candidate_audit["symbol_consistency"] = symbol_consistency
    return DecisionControlStepResult(
        candidate_audit=final_candidate_audit,
        production_control_verdict=production_control_verdict,
        final_verdict=final_verdict,
        production_control_summary=production_control_verdict.to_public_dict(),
        risk_summary=final_verdict.to_public_dict(),
    )


def _symbol_from_run_context(run_context_summary: dict[str, Any] | None) -> str | None:
    if not isinstance(run_context_summary, dict):
        return None
    value = run_context_summary.get("symbol")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _symbol_consistency(
    *,
    request_symbol: str | None,
    snapshot_symbol: str | None,
    plan_instrument: str | None,
) -> dict[str, Any]:
    values = {
        "request_symbol": _clean_symbol(request_symbol),
        "snapshot_symbol": _clean_symbol(snapshot_symbol),
        "plan_instrument": _clean_symbol(plan_instrument),
    }
    present = [value for value in values.values() if value]
    return {
        **values,
        "consistent": len(set(present)) <= 1,
    }


def _symbol_consistency_verdict(symbol_consistency: dict[str, Any]) -> RiskVerdict:
    if symbol_consistency.get("consistent") is True:
        return RiskVerdict(allowed=True, reasons=[])
    message = "request, snapshot, and final plan symbols do not match"
    return RiskVerdict(
        allowed=False,
        reasons=[message],
        rule_hits=[
            RuleHit(
                rule_id="production_control.symbol_consistency.mismatch",
                passed=False,
                severity="critical",
                message=message,
                blocking=True,
                evidence_refs=["run_context.symbol", "snapshot.symbol", "plan.instrument"],
                details=dict(symbol_consistency),
            )
        ],
    )


def _clean_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _with_observability_refs(
    run_context_summary: dict[str, Any] | None,
    *,
    telemetry_refs: dict[str, Any] | None,
    span_tree_refs: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(run_context_summary, dict):
        return None
    if not telemetry_refs and not span_tree_refs:
        return run_context_summary
    merged = dict(run_context_summary)
    if telemetry_refs:
        merged["telemetry_refs"] = telemetry_refs
    if span_tree_refs:
        merged["span_tree_refs"] = span_tree_refs
    return merged
