from __future__ import annotations

from crypto_manual_alert.domain import RiskVerdict


def merge_risk_verdicts(*verdicts: RiskVerdict) -> RiskVerdict:
    """Merge deterministic risk verdicts without hiding any blocking signal."""

    reasons: list[str] = []
    warnings: list[str] = []
    rule_hits = []
    for verdict in verdicts:
        reasons.extend(verdict.reasons)
        warnings.extend(verdict.warnings)
        rule_hits.extend(verdict.rule_hits)

    has_blocking_hit = any(hit.blocking for hit in rule_hits)
    all_verdicts_allowed = all(verdict.allowed for verdict in verdicts)
    return RiskVerdict(
        allowed=all_verdicts_allowed and not reasons and not has_blocking_hit,
        reasons=_dedupe(reasons),
        warnings=_dedupe(warnings),
        rule_hits=rule_hits,
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
