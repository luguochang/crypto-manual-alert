from __future__ import annotations

from crypto_manual_alert.domain import RiskVerdict, RuleHit
from crypto_manual_alert.workflow.risk_merge_policy import merge_risk_verdicts


def test_merge_risk_verdicts_preserves_reasons_warnings_and_rule_hits():
    production = RiskVerdict(
        allowed=False,
        reasons=["production blocked"],
        warnings=[],
        rule_hits=[
            RuleHit(
                rule_id="production_control.worker_hard_block",
                passed=False,
                severity="critical",
                message="worker hard block",
                blocking=True,
                evidence_refs=["decision_input_candidate.contribution_refs"],
            )
        ],
    )
    legacy = RiskVerdict(
        allowed=True,
        reasons=[],
        warnings=["legacy warning"],
        rule_hits=[
            RuleHit(
                rule_id="risk.leverage.warning",
                passed=True,
                severity="medium",
                message="leverage warning",
                blocking=False,
                evidence_refs=["plan.max_leverage"],
            )
        ],
    )

    merged = merge_risk_verdicts(production, legacy)

    assert merged.allowed is False
    assert merged.reasons == ["production blocked"]
    assert merged.warnings == ["legacy warning"]
    assert [hit.rule_id for hit in merged.rule_hits] == [
        "production_control.worker_hard_block",
        "risk.leverage.warning",
    ]


def test_merge_risk_verdicts_blocks_when_a_verdict_has_blocking_hit_even_without_reason():
    inconsistent_block = RiskVerdict(
        allowed=True,
        reasons=[],
        warnings=[],
        rule_hits=[
            RuleHit(
                rule_id="production_control.symbol_consistency.mismatch",
                passed=False,
                severity="critical",
                message="symbol mismatch",
                blocking=True,
                evidence_refs=["run_context.symbol"],
            )
        ],
    )

    merged = merge_risk_verdicts(inconsistent_block)

    assert merged.allowed is False
    assert [hit.rule_id for hit in merged.rule_hits if hit.blocking] == [
        "production_control.symbol_consistency.mismatch"
    ]
