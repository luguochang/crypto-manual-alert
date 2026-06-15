from __future__ import annotations

import pytest

from crypto_manual_alert.decision.plan_parser import PlanParseError
from crypto_manual_alert.decision.plan_parse_step import run_plan_parse_step


def test_plan_parse_step_returns_plan_and_summary():
    raw_decision = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "reference_price": 3500,
  "entry_trigger": null,
  "stop_price": null,
  "target_1": null,
  "target_2": null,
  "probability": 0.51,
  "position_size_class": "none",
  "max_leverage": 0,
  "risk_pct": 0,
  "expires_in_seconds": 90,
  "why_not_opposite": "No confirmed setup.",
  "invalidation": "Re-run after market structure changes.",
  "unavailable_data": [],
  "manual_execution_required": true
}
"""

    result = run_plan_parse_step(raw_decision)

    assert result.plan.instrument == "ETH-USDT-SWAP"
    assert result.plan.main_action == "no trade"
    assert result.parse_summary == {
        "plan_id": result.plan.plan_id,
        "main_action": "no trade",
    }


def test_plan_parse_step_propagates_parser_errors():
    with pytest.raises(PlanParseError):
        run_plan_parse_step('{"instrument": "ETH-USDT-SWAP"}')
