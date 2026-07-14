from collections.abc import Mapping

from crypto_alert_v2.domain.models import (
    OPENING_ACTIONS,
    EvidenceVerdict,
    MarketAnalysis,
    RiskBudget,
    RiskVerdict,
)


def apply_risk_policy(
    analysis: MarketAnalysis | Mapping[str, object],
    evidence_verdict: EvidenceVerdict | Mapping[str, object],
    risk_budget: RiskBudget | Mapping[str, object] | None = None,
) -> RiskVerdict:
    """Apply deterministic product and risk-budget rules without altering evidence cap."""
    validated_analysis = _validate_analysis(analysis)
    evidence = _validate_evidence(evidence_verdict)
    budget = _validate_budget(risk_budget)

    blocked_reasons: list[str] = []
    warnings = list(evidence.warnings)

    if not evidence.sufficient:
        blocked_reasons.append(
            f"evidence.insufficient:{','.join(evidence.missing_required)}"
        )

    if not validated_analysis.manual_execution_required:
        blocked_reasons.append("execution.manual_required")

    if validated_analysis.main_action in OPENING_ACTIONS:
        if validated_analysis.entry_trigger is None:
            blocked_reasons.append("analysis.entry_trigger.required")
        if validated_analysis.stop_price is None:
            blocked_reasons.append("analysis.stop_price.required")
        if not validated_analysis.invalidation.strip():
            blocked_reasons.append("analysis.invalidation.required")

    if budget.auto_order_enabled:
        blocked_reasons.append("budget.auto_order_disabled")
    if validated_analysis.instrument not in budget.allowed_symbols:
        blocked_reasons.append(
            f"budget.symbol_not_allowed:{validated_analysis.instrument}"
        )
    if validated_analysis.max_leverage > budget.max_leverage:
        blocked_reasons.append(
            "budget.max_leverage_exceeded:"
            f"actual={validated_analysis.max_leverage},limit={budget.max_leverage}"
        )
    if validated_analysis.risk_pct > budget.max_risk_pct:
        blocked_reasons.append(
            "budget.max_risk_pct_exceeded:"
            f"actual={validated_analysis.risk_pct},limit={budget.max_risk_pct}"
        )

    if evidence.sufficient and validated_analysis.probability > evidence.confidence_cap:
        blocked_reasons.append(
            "analysis.confidence_cap_exceeded:"
            f"actual={validated_analysis.probability:g},limit={evidence.confidence_cap:g}"
        )

    return RiskVerdict(
        allowed=not blocked_reasons,
        blocked_reasons=blocked_reasons,
        warnings=warnings,
        confidence_cap=evidence.confidence_cap,
    )


def _validate_analysis(value: MarketAnalysis | Mapping[str, object]) -> MarketAnalysis:
    if isinstance(value, MarketAnalysis):
        return value
    return MarketAnalysis.model_validate(value)


def _validate_evidence(
    value: EvidenceVerdict | Mapping[str, object],
) -> EvidenceVerdict:
    if isinstance(value, EvidenceVerdict):
        return value
    return EvidenceVerdict.model_validate(value)


def _validate_budget(
    value: RiskBudget | Mapping[str, object] | None,
) -> RiskBudget:
    if value is None:
        return RiskBudget()
    if isinstance(value, RiskBudget):
        return value
    return RiskBudget.model_validate(value)
