from __future__ import annotations

from typing import Any

from crypto_manual_alert.lead.agent import LeadAgent
from crypto_manual_alert.orchestration.contracts import LeadPlan
from crypto_manual_alert.orchestration.harness import HarnessPolicy


def build_default_lead_plan(
    *,
    symbol: str,
    trace_id: str,
    policy: HarnessPolicy | None = None,
    base_input_view: dict[str, Any] | None = None,
) -> LeadPlan:
    if policy is None:
        return LeadAgent().plan_tasks(
            symbol=symbol,
            trace_id=trace_id,
            base_input_view=base_input_view,
        )
    return LeadAgent(policy=policy).plan_tasks(
        symbol=symbol,
        trace_id=trace_id,
        base_input_view=base_input_view,
    )
