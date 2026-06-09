from __future__ import annotations

from .._shared import build_constraints, build_skill_result
from ..contracts import ALLOWED_SENTIMENT_OUTPUTS, SkillTaskContext, SkillToolResult


class MarketSentimentSkill:
    skill_name = "market_sentiment"

    def run(self, context: SkillTaskContext) -> SkillToolResult:
        return build_skill_result(
            context,
            skill_name=self.skill_name,
            result_type="sentiment_crowding_candidates",
            source_type="search_derived",
            can_satisfy_execution_fact=False,
            constraints=build_constraints(
                context,
                separate_objective_facts_from_crowding=True,
                outputs=ALLOWED_SENTIMENT_OUTPUTS,
            ),
        )
