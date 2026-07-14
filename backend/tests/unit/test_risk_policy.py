from decimal import Decimal
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1]))

from crypto_alert_v2.domain.models import EvidenceVerdict, MarketAnalysis, RiskBudget
from crypto_alert_v2.domain.risk_policy import apply_risk_policy
from tests.fixtures.golden_cases import valid_market_analysis


def _analysis(**overrides: object) -> MarketAnalysis:
    return MarketAnalysis.model_validate(valid_market_analysis(**overrides))


def _sufficient(cap: float = 1.0, optional: list[str] | None = None) -> EvidenceVerdict:
    return EvidenceVerdict(
        sufficient=True,
        confidence_cap=cap,
        missing_optional=optional or [],
    )


def test_valid_plan_with_available_evidence_is_allowed() -> None:
    verdict = apply_risk_policy(_analysis(), _sufficient())

    assert verdict.allowed is True
    assert verdict.blocked_reasons == []
    assert verdict.confidence_cap == 1


def test_risk_verdict_preserves_evidence_cap_without_second_downgrade() -> None:
    evidence = _sufficient(0.70, ["funding_rate", "open_interest"])

    verdict = apply_risk_policy(_analysis(probability=0.65), evidence)

    assert verdict.allowed is True
    assert verdict.confidence_cap == 0.70


def test_risk_policy_does_not_recalculate_cap_from_optional_names() -> None:
    evidence = _sufficient(0.90, ["funding_rate"])

    verdict = apply_risk_policy(_analysis(probability=0.85), evidence)

    assert verdict.allowed is True
    assert verdict.confidence_cap == 0.90


def test_probability_above_evidence_cap_is_blocked_without_changing_cap() -> None:
    verdict = apply_risk_policy(_analysis(probability=0.75), _sufficient(0.70))

    assert verdict.allowed is False
    assert any("confidence_cap" in reason for reason in verdict.blocked_reasons)
    assert verdict.confidence_cap == 0.70


def test_insufficient_evidence_has_explicit_block_reason_and_zero_cap() -> None:
    evidence = EvidenceVerdict(
        sufficient=False,
        confidence_cap=0,
        missing_required=["ticker", "vix"],
    )

    verdict = apply_risk_policy(_analysis(), evidence)

    assert verdict.allowed is False
    assert verdict.blocked_reasons == ["evidence.insufficient:ticker,vix"]
    assert verdict.confidence_cap == 0


def test_manual_execution_boundary_is_explicitly_blocked() -> None:
    verdict = apply_risk_policy(
        _analysis(manual_execution_required=False),
        _sufficient(),
    )

    assert "execution.manual_required" in verdict.blocked_reasons


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("entry_trigger", "analysis.entry_trigger.required"),
        ("stop_price", "analysis.stop_price.required"),
        ("invalidation", "analysis.invalidation.required"),
    ],
)
def test_opening_plan_requires_execution_parameters(field: str, reason: str) -> None:
    value = "" if field == "invalidation" else None

    verdict = apply_risk_policy(_analysis(**{field: value}), _sufficient())

    assert reason in verdict.blocked_reasons


def test_no_trade_does_not_require_opening_parameters() -> None:
    verdict = apply_risk_policy(
        _analysis(
            main_action="no_trade",
            entry_trigger=None,
            stop_price=None,
            invalidation="",
            probability=0,
            position_size_class="none",
            risk_pct=0,
        ),
        _sufficient(),
    )

    assert verdict.allowed is True


def test_leverage_over_budget_is_blocked_with_actual_and_limit() -> None:
    budget = RiskBudget(max_leverage=1, max_risk_pct=Decimal("0.25"))

    verdict = apply_risk_policy(_analysis(max_leverage=2), _sufficient(), budget)

    assert "budget.max_leverage_exceeded:actual=2,limit=1" in verdict.blocked_reasons


def test_risk_percentage_over_budget_is_blocked_with_actual_and_limit() -> None:
    budget = RiskBudget(max_leverage=2, max_risk_pct=Decimal("0.05"))

    verdict = apply_risk_policy(_analysis(risk_pct=0.10), _sufficient(), budget)

    assert "budget.max_risk_pct_exceeded:actual=0.1,limit=0.05" in verdict.blocked_reasons


def test_symbol_outside_workspace_budget_is_blocked() -> None:
    budget = RiskBudget(
        allowed_symbols=("BTC-USDT-SWAP",),
        max_leverage=2,
        max_risk_pct=Decimal("0.25"),
    )

    verdict = apply_risk_policy(
        _analysis(instrument="ETH-USDT-SWAP"),
        _sufficient(),
        budget,
    )

    assert "budget.symbol_not_allowed:ETH-USDT-SWAP" in verdict.blocked_reasons


def test_auto_order_budget_misconfiguration_is_blocked() -> None:
    budget = RiskBudget(
        auto_order_enabled=True,
        max_leverage=2,
        max_risk_pct=Decimal("0.25"),
    )

    verdict = apply_risk_policy(_analysis(), _sufficient(), budget)

    assert "budget.auto_order_disabled" in verdict.blocked_reasons


def test_multiple_budget_failures_are_all_visible() -> None:
    budget = RiskBudget(
        allowed_symbols=("ETH-USDT-SWAP",),
        max_leverage=1,
        max_risk_pct=Decimal("0.05"),
        auto_order_enabled=True,
    )

    verdict = apply_risk_policy(_analysis(), _sufficient(), budget)

    assert verdict.allowed is False
    assert verdict.blocked_reasons == [
        "budget.auto_order_disabled",
        "budget.symbol_not_allowed:BTC-USDT-SWAP",
        "budget.max_leverage_exceeded:actual=2,limit=1",
        "budget.max_risk_pct_exceeded:actual=0.1,limit=0.05",
    ]


@pytest.mark.parametrize(
    "budget",
    [
        {"max_leverage": 0, "max_risk_pct": 0.1},
        {"max_leverage": 2, "max_risk_pct": -0.1},
        {"max_leverage": 2, "max_risk_pct": 0.1, "unknown": True},
    ],
)
def test_invalid_budget_input_raises_pydantic_validation(budget: dict) -> None:
    with pytest.raises(ValidationError):
        apply_risk_policy(_analysis(), _sufficient(), budget)
