from __future__ import annotations

from .._shared import build_constraints, build_skill_result
from ..contracts import ALLOWED_MACRO_FIELDS, SkillTaskContext, SkillToolResult


class MacroEventSkill:
    skill_name = "macro_event"

    def run(self, context: SkillTaskContext) -> SkillToolResult:
        return build_skill_result(
            context,
            skill_name=self.skill_name,
            result_type="macro_event_candidates",
            source_type="official_or_event_pool",
            can_satisfy_execution_fact=False,
            constraints=build_constraints(context, required_fields=ALLOWED_MACRO_FIELDS),
        )
