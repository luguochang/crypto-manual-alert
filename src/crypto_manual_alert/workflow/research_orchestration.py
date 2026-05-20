from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder, use_observability
from crypto_manual_alert.research_pipeline import (
    LeaderResearchSynthesizer,
    ResearchAudit,
    ResearchPlanner,
    SearchAdapter,
    candle_max_age_seconds,
    execute_research,
    needs_research_fallback,
    synthesize_search_evidence,
)


@dataclass(frozen=True)
class ResearchOrchestrationResult:
    """Result of the optional research fallback step.

    This step may enrich audit evidence and the legacy prompt snapshot. It does
    not create worker contributions, decide trades, or write journals.
    """

    snapshot: MarketSnapshot
    research_audit: ResearchAudit | None
    used_fallback: bool
    public_summary: dict[str, Any]


def run_research_orchestration(
    *,
    config: Config,
    recorder: ObservabilityRecorder | None,
    trace_id: str,
    snapshot: MarketSnapshot,
    skill_context: dict[str, Any],
    research_planner: ResearchPlanner,
    search_adapter: SearchAdapter,
    leader_synthesizer: LeaderResearchSynthesizer,
) -> ResearchOrchestrationResult:
    """Run controlled research fallback when market data is missing or stale."""

    if not config.research.enabled:
        return ResearchOrchestrationResult(
            snapshot=snapshot,
            research_audit=None,
            used_fallback=False,
            public_summary={"used_fallback": False, "reason": "research_disabled"},
        )
    if not needs_research_fallback(
        snapshot,
        max_age_seconds=config.market_data.stale_market_data_seconds,
        candle_max_age_seconds=candle_max_age_seconds(
            config.market_data.candle_bar,
            config.market_data.stale_market_data_seconds,
        ),
    ):
        return ResearchOrchestrationResult(
            snapshot=snapshot,
            research_audit=None,
            used_fallback=False,
            public_summary={"used_fallback": False, "reason": "market_data_sufficient"},
        )

    research_plan = _plan_research(
        recorder=recorder,
        trace_id=trace_id,
        snapshot=snapshot,
        skill_context=skill_context,
        research_planner=research_planner,
    )
    research_audit = _search_research(
        config=config,
        recorder=recorder,
        trace_id=trace_id,
        research_plan=research_plan,
        search_adapter=search_adapter,
    )
    enriched_snapshot = _synthesize_evidence(
        recorder=recorder,
        trace_id=trace_id,
        snapshot=snapshot,
        research_audit=research_audit,
    )
    research_audit = _leader_review(
        recorder=recorder,
        trace_id=trace_id,
        snapshot=enriched_snapshot,
        research_audit=research_audit,
        leader_synthesizer=leader_synthesizer,
    )
    return ResearchOrchestrationResult(
        snapshot=enriched_snapshot,
        research_audit=research_audit,
        used_fallback=True,
        public_summary={
            "used_fallback": True,
            "result_names": sorted(research_audit.results),
            "unavailable": list(research_audit.unavailable),
        },
    )


def _plan_research(
    *,
    recorder: ObservabilityRecorder | None,
    trace_id: str,
    snapshot: MarketSnapshot,
    skill_context: dict[str, Any],
    research_planner: ResearchPlanner,
):
    if recorder is None:
        return research_planner.plan(snapshot, skill_context=skill_context)
    with recorder.span(
        trace_id,
        "research.plan",
        "research.plan",
        input_summary={"symbol": snapshot.symbol, "unavailable": snapshot.unavailable},
    ) as span:
        with use_observability(recorder, trace_id):
            research_plan = research_planner.plan(snapshot, skill_context=skill_context)
        span.set_output(research_plan.to_public_dict())
        return research_plan


def _search_research(
    *,
    config: Config,
    recorder: ObservabilityRecorder | None,
    trace_id: str,
    research_plan,
    search_adapter: SearchAdapter,
) -> ResearchAudit:
    if recorder is None:
        return execute_research(
            research_plan,
            search_adapter,
            max_workers=config.research.max_workers,
        )
    with recorder.span(
        trace_id,
        "research.search",
        "research.search",
        input_summary={"queries": [query.__dict__ for query in research_plan.queries]},
    ) as span:
        with use_observability(recorder, trace_id):
            research_audit = execute_research(
                research_plan,
                search_adapter,
                max_workers=config.research.max_workers,
                recorder=recorder,
                trace_id=trace_id,
                parent_span_id=span.span_id,
            )
        span.set_output({"result_names": sorted(research_audit.results), "unavailable": research_audit.unavailable})
        return research_audit


def _synthesize_evidence(
    *,
    recorder: ObservabilityRecorder | None,
    trace_id: str,
    snapshot: MarketSnapshot,
    research_audit: ResearchAudit,
) -> MarketSnapshot:
    if recorder is None:
        return synthesize_search_evidence(snapshot, research_audit)
    with recorder.span(trace_id, "evidence.synthesize", "evidence.synthesize") as span:
        enriched_snapshot = synthesize_search_evidence(snapshot, research_audit)
        span.set_output(
            {
                "symbol": enriched_snapshot.symbol,
                "point_names": sorted(enriched_snapshot.points),
                "unavailable": list(enriched_snapshot.unavailable),
            }
        )
        return enriched_snapshot


def _leader_review(
    *,
    recorder: ObservabilityRecorder | None,
    trace_id: str,
    snapshot: MarketSnapshot,
    research_audit: ResearchAudit,
    leader_synthesizer: LeaderResearchSynthesizer,
) -> ResearchAudit:
    if recorder is None:
        return leader_synthesizer.synthesize(snapshot, research_audit)
    with recorder.span(trace_id, "leader.review", "leader.review") as span:
        with use_observability(recorder, trace_id):
            reviewed_audit = leader_synthesizer.synthesize(snapshot, research_audit)
        span.set_output({"leader_summary_keys": sorted(reviewed_audit.leader_summary)})
        return reviewed_audit
