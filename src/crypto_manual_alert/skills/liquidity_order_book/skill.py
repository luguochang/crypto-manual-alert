from __future__ import annotations

from .._shared import build_constraints, build_skill_result
from ..contracts import EXECUTION_FACTS, SkillTaskContext, SkillToolResult
from .providers import OrderBookProvider, OrderBookRequest


class LiquidityOrderBookSkill:
    skill_name = "liquidity_order_book"

    def __init__(self, *, provider: OrderBookProvider | None = None) -> None:
        self.provider = provider

    def run(self, context: SkillTaskContext) -> SkillToolResult:
        return build_skill_result(
            context,
            skill_name=self.skill_name,
            result_type="exchange_execution_fact_candidates",
            source_type="exchange_native",
            can_satisfy_execution_fact=True,
            fact_refs=self._fact_refs(context),
            constraints=build_constraints(
                context,
                search_derived_cannot_satisfy_execution_fact=True,
                required_execution_facts=EXECUTION_FACTS,
            ),
        )

    def _fact_refs(self, context: SkillTaskContext) -> dict[str, str]:
        if self.provider is None:
            return {}
        return self.provider.fetch(
            OrderBookRequest(
                symbol=context.symbol,
                trace_id=context.trace_id,
                task_id=context.task_id,
            )
        ).to_fact_refs()
