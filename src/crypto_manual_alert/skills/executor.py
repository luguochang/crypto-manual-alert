from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from crypto_manual_alert.skills.facade import SkillTaskContext
from crypto_manual_alert.skills.source_freshness import SourceFreshness
from crypto_manual_alert.skills.tool_budget import ToolBudget
from crypto_manual_alert.skills.tool_call_artifact import ToolCallArtifact


_SOURCE_TIER_BY_TYPE = {
    "exchange_native": "exchange",
    "official_or_event_pool": "official",
    "search_derived": "search",
    "fixture": "fixture",
}
_SOURCE_TYPE_BY_SKILL = {
    "liquidity_order_book": "exchange_native",
    "macro_event": "official_or_event_pool",
    "market_sentiment": "search_derived",
    "realtime_search": "search_derived",
    "root_cause_search": "search_derived",
}


@dataclass(frozen=True)
class SkillExecutor:
    """Controlled executor that converts skill results into artifact refs."""

    registry: Mapping[str, Any]
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    max_age_seconds: int = 60

    def execute(
        self,
        *,
        worker_name: str,
        context: SkillTaskContext,
        budget: ToolBudget,
    ) -> ToolCallArtifact:
        skill = self.registry.get(context.skill_name)
        if skill is None:
            raise ValueError(f"skill is not registered: {context.skill_name}")
        now = self.clock()
        ticket = budget.reserve(worker_name=worker_name, skill_name=context.skill_name, now=now)
        call_number = budget.max_calls - int(ticket["remaining_calls"])
        try:
            skill_result = skill.run(context)
        except Exception as exc:  # noqa: BLE001 - tool failures must remain audit-visible.
            return self._failed_artifact(
                worker_name=worker_name,
                context=context,
                call_number=call_number,
                now=now,
                exc=exc,
            )
        public_result = skill_result.to_public_dict()
        source_type = str(public_result.get("source_type"))
        source_tier = _SOURCE_TIER_BY_TYPE.get(source_type)
        if source_tier is None:
            raise ValueError(f"source_type is not supported by SkillExecutor: {source_type}")
        freshness_status = SourceFreshness(
            retrieved_at=now,
            now=now,
            max_age_seconds=self.max_age_seconds,
        ).status
        return ToolCallArtifact.from_skill_result(
            skill_result,
            tool_call_id=f"tool:{context.trace_id}:{worker_name}:{context.skill_name}:{call_number}",
            result_ref=f"skill_result:{context.trace_id}:{worker_name}:{context.skill_name}:{call_number}",
            retrieved_at=now,
            source_tier=source_tier,
            freshness_status=freshness_status,
        )

    def _failed_artifact(
        self,
        *,
        worker_name: str,
        context: SkillTaskContext,
        call_number: int,
        now: datetime,
        exc: Exception,
    ) -> ToolCallArtifact:
        source_type = _SOURCE_TYPE_BY_SKILL.get(context.skill_name, "search_derived")
        source_tier = _SOURCE_TIER_BY_TYPE[source_type]
        error = {"type": type(exc).__name__, "message": str(exc)}
        return ToolCallArtifact(
            tool_call_id=f"tool:{context.trace_id}:{worker_name}:{context.skill_name}:{call_number}",
            skill_name=context.skill_name,
            status="failed",
            source_type=source_type,
            source_tier=source_tier,
            retrieved_at=now,
            freshness_status="unknown",
            result_ref=f"skill_error:{context.trace_id}:{worker_name}:{context.skill_name}:{call_number}",
            output_hash=_stable_hash(
                {
                    "skill_name": context.skill_name,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                }
            ),
            can_satisfy_execution_fact=False,
            error=error,
        )


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
