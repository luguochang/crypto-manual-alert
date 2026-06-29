from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .domain import DecisionPlan, MarketSnapshot, NotificationResult, RiskVerdict
from .journal import Journal
from .market_data import FixtureMarketDataProvider, MarketDataProvider, OkxPublicMarketDataProvider
from .notifier import BarkNotificationSink, NoopNotificationSink, NotificationSink
from .observability import ObservabilityRecorder, use_observability
from .plan_parser import parse_decision_plan
from .research import (
    LeaderResearchSynthesizer,
    ResearchAudit,
    ResearchPlanner,
    SearchAdapter,
    build_leader_synthesizer,
    build_research_planner,
    build_search_adapter,
    candle_max_age_seconds,
    execute_research,
    needs_research_fallback,
    synthesize_search_evidence,
)
from .risk import check_plan
from .skill_runtime import CommandDecisionEngine, DecisionEngine, FixtureDecisionEngine, OpenAICompatibleDecisionEngine, SkillRuntime


logger = logging.getLogger(__name__)


class PlanRunner:
    def __init__(
        self,
        config: Config,
        journal: Journal,
        market_provider: MarketDataProvider | None = None,
        decision_engine: DecisionEngine | None = None,
        notifier: NotificationSink | None = None,
        research_planner: ResearchPlanner | None = None,
        search_adapter: SearchAdapter | None = None,
        leader_synthesizer: LeaderResearchSynthesizer | None = None,
    ):
        self.config = config
        self.journal = journal
        self.market_provider = market_provider or build_market_provider(config)
        self.skill_runtime = SkillRuntime(config)
        self.decision_engine = decision_engine or build_decision_engine(config)
        self.notifier = notifier or build_notifier(config)
        self.research_planner = research_planner or build_research_planner(config)
        self.search_adapter = search_adapter or build_search_adapter(config)
        self.leader_synthesizer = leader_synthesizer or build_leader_synthesizer(config)

    def run_once(self, symbol: str) -> tuple[DecisionPlan, RiskVerdict]:
        recorder = ObservabilityRecorder(self.journal)
        trace_id = recorder.start_trace(run_type="manual", symbol=symbol)
        snapshot: MarketSnapshot | None = None
        research_audit: ResearchAudit | None = None
        prompt_packet: dict[str, object] = {}
        try:
            with recorder.span(trace_id, "market.fetch", "market.fetch", input_summary={"symbol": symbol}) as span:
                snapshot = self.market_provider.fetch_snapshot(symbol)
                span.set_output(_snapshot_summary(snapshot))
            with recorder.span(trace_id, "skill.load", "skill.load") as span:
                skill_context = self.skill_runtime.load_context()
                span.set_output(
                    {
                        "name": skill_context.name,
                        "sha256": skill_context.sha256,
                        "required_references": list(skill_context.references),
                    }
                )
            if self.config.research.enabled and needs_research_fallback(
                snapshot,
                max_age_seconds=self.config.market_data.stale_market_data_seconds,
                candle_max_age_seconds=candle_max_age_seconds(
                    self.config.market_data.candle_bar,
                    self.config.market_data.stale_market_data_seconds,
                ),
            ):
                with recorder.span(
                    trace_id,
                    "research.plan",
                    "research.plan",
                    input_summary={"symbol": snapshot.symbol, "unavailable": snapshot.unavailable},
                ) as span:
                    with use_observability(recorder, trace_id):
                        research_plan = self.research_planner.plan(snapshot, skill_context=skill_context.to_prompt_dict())
                    span.set_output(research_plan.to_public_dict())
                with recorder.span(
                    trace_id,
                    "research.search",
                    "research.search",
                    input_summary={"queries": [query.__dict__ for query in research_plan.queries]},
                ) as span:
                    with use_observability(recorder, trace_id):
                        research_audit = execute_research(
                            research_plan,
                            self.search_adapter,
                            max_workers=self.config.research.max_workers,
                        )
                    span.set_output(
                        {
                            "result_names": sorted(research_audit.results),
                            "unavailable": research_audit.unavailable,
                        }
                    )
                with recorder.span(trace_id, "evidence.synthesize", "evidence.synthesize") as span:
                    snapshot = synthesize_search_evidence(snapshot, research_audit)
                    span.set_output(_snapshot_summary(snapshot))
                with recorder.span(trace_id, "leader.review", "leader.review") as span:
                    with use_observability(recorder, trace_id):
                        research_audit = self.leader_synthesizer.synthesize(snapshot, research_audit)
                    span.set_output({"leader_summary_keys": sorted(research_audit.leader_summary)})
            with recorder.span(trace_id, "prompt.build", "prompt.build") as span:
                prompt_packet = self.skill_runtime.build_prompt_packet(snapshot, context=skill_context)
                span.set_output({"keys": sorted(prompt_packet)})
            if research_audit:
                prompt_packet["research"] = research_audit.to_public_dict()
            with recorder.span(trace_id, "decision.final", "decision.llm") as span:
                with use_observability(recorder, trace_id):
                    raw_decision = self.decision_engine.run(prompt_packet)
                span.set_output({"raw_decision_chars": len(str(raw_decision))})
            with recorder.span(trace_id, "parser.strict_json", "parser.strict_json") as span:
                plan = parse_decision_plan(raw_decision)
                span.set_output({"plan_id": plan.plan_id, "main_action": plan.main_action})
            with recorder.span(trace_id, "risk.check", "risk.check") as span:
                verdict = check_plan(plan, snapshot, self.config)
                span.set_output({"allowed": verdict.allowed, "reasons": verdict.reasons, "warnings": verdict.warnings})
        except Exception as exc:  # noqa: BLE001 - 失败时必须生成禁止交易的 blocked plan 并留审计。
            logger.exception("plan pipeline failed")
            plan, verdict = self._blocked_failure_plan(symbol, exc)
            payload = {
                    "trace_id": trace_id,
                    "plan": plan.raw,
                    "snapshot": snapshot.to_public_dict() if snapshot else None,
                    "evidence_snapshot": snapshot.to_public_dict() if snapshot else None,
                    "raw_decision": None,
                    "parsed_plan": plan.raw,
                    "verdict": {"allowed": verdict.allowed, "reasons": verdict.reasons, "warnings": verdict.warnings},
                    "skill": prompt_packet.get("skill"),
                    "research": research_audit.to_public_dict() if research_audit else None,
                    "analysis": _analysis_summary(snapshot, research_audit, plan, verdict),
                    "redaction": _redaction_policy(),
                    "error": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
                }
            with recorder.span(trace_id, "journal.write", "journal.write") as span:
                self.journal.append_plan_run(plan.plan_id, "blocked", payload)
                span.set_output({"plan_id": plan.plan_id, "status": "blocked"})
            recorder.finish_trace(
                trace_id,
                status="blocked",
                final_plan_id=plan.plan_id,
                final_action=plan.main_action,
                allowed=verdict.allowed,
                metadata={"error_type": type(exc).__name__},
            )
            if self.config.notification.enabled and self.config.notification.send_failure_alerts:
                self._send_notification(plan, verdict, recorder=recorder, trace_id=trace_id)
            return plan, verdict

        payload = {
                "trace_id": trace_id,
                "plan": plan.raw,
                "snapshot": snapshot.to_public_dict(),
                "evidence_snapshot": snapshot.to_public_dict(),
                "raw_decision": raw_decision,
                "verdict": {"allowed": verdict.allowed, "reasons": verdict.reasons, "warnings": verdict.warnings},
                "skill": prompt_packet["skill"],
                "parsed_plan": plan.raw,
                "research": research_audit.to_public_dict() if research_audit else None,
                "analysis": _analysis_summary(snapshot, research_audit, plan, verdict),
                "redaction": _redaction_policy(),
            }
        status = "allowed" if verdict.allowed else "blocked"
        with recorder.span(trace_id, "journal.write", "journal.write") as span:
            self.journal.append_plan_run(plan.plan_id, status, payload)
            span.set_output({"plan_id": plan.plan_id, "status": status})
        recorder.finish_trace(
            trace_id,
            status=status,
            final_plan_id=plan.plan_id,
            final_action=plan.main_action,
            allowed=verdict.allowed,
        )
        if self.config.notification.enabled:
            self._send_notification(plan, verdict, recorder=recorder, trace_id=trace_id)
        return plan, verdict

    def _send_notification(
        self,
        plan: DecisionPlan,
        verdict: RiskVerdict,
        recorder: ObservabilityRecorder | None = None,
        trace_id: str | None = None,
    ) -> None:
        def send() -> NotificationResult:
            try:
                return self.notifier.send(plan, verdict)
            except Exception as exc:  # noqa: BLE001 - 通知失败不能改变已经计算出的风控结论。
                logger.exception("notification failed")
                return NotificationResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        if recorder and trace_id:
            with recorder.span(
                trace_id,
                "notification.send",
                "notification.send",
                input_summary={"plan_id": plan.plan_id, "allowed": verdict.allowed},
            ) as span:
                result = send()
                self.journal.append_notification(plan.plan_id, result.ok, result.status_code, result.error)
                span.set_output({"ok": result.ok, "status_code": result.status_code, "error": result.error})
            return

        result = send()
        self.journal.append_notification(plan.plan_id, result.ok, result.status_code, result.error)

    def _blocked_failure_plan(self, symbol: str, exc: Exception) -> tuple[DecisionPlan, RiskVerdict]:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "instrument": symbol,
            "main_action": "no trade",
            "horizon": "unknown",
            "manual_execution_required": True,
            "expires_in_seconds": 0,
            "why_not_opposite": "决策管线在生成可靠交易计划前失败，不能比较反向方案。",
            "invalidation": "只有行情、skill 上下文、模型输出和解析器全部恢复后才能重试。",
            "unavailable_data": [f"{type(exc).__name__}: {exc}"],
            "notes": "系统失败，不能执行；请不要按本次输出手动下单。",
        }
        plan = DecisionPlan.from_payload(payload, generated_at=now)
        verdict = RiskVerdict(allowed=False, reasons=["决策管线失败，禁止按本次结果手动交易"], warnings=plan.unavailable_data)
        return plan, verdict


def build_market_provider(config: Config) -> MarketDataProvider:
    if config.market_data.provider == "fixture":
        return FixtureMarketDataProvider()
    if config.market_data.provider == "okx_public":
        return OkxPublicMarketDataProvider(config)
    raise ValueError(f"Unsupported market_data.provider: {config.market_data.provider}")


def build_decision_engine(config: Config) -> DecisionEngine:
    if config.decision.engine == "fixture":
        return FixtureDecisionEngine(config.decision.fixture_plan_path)
    if config.decision.engine == "command":
        return CommandDecisionEngine(config.decision.command, config.decision.timeout_seconds)
    if config.decision.engine == "openai_compatible":
        return OpenAICompatibleDecisionEngine.from_config(config)
    raise ValueError(f"Unsupported decision.engine: {config.decision.engine}")


def build_notifier(config: Config) -> NotificationSink:
    if not config.notification.enabled:
        return NoopNotificationSink()
    if config.notification.provider == "bark":
        return BarkNotificationSink(config)
    raise ValueError(f"Unsupported notification.provider: {config.notification.provider}")


def journal_path(config: Config) -> Path:
    return Path(config.app.data_dir) / "crypto-alert.db"


def plan_to_json(plan: DecisionPlan, verdict: RiskVerdict) -> str:
    return json.dumps(
        {
            "plan_id": plan.plan_id,
            "instrument": plan.instrument,
            "main_action": plan.main_action,
            "allowed": verdict.allowed,
            "reasons": verdict.reasons,
            "warnings": verdict.warnings,
            "expires_at": plan.expires_at.isoformat(),
            "manual_execution_required": plan.manual_execution_required,
        },
        ensure_ascii=False,
        indent=2,
    )


def _snapshot_summary(snapshot: MarketSnapshot) -> dict[str, Any]:
    return {
        "symbol": snapshot.symbol,
        "point_names": sorted(snapshot.points),
        "unavailable": list(snapshot.unavailable),
    }


def _analysis_summary(
    snapshot: MarketSnapshot | None,
    research_audit: ResearchAudit | None,
    plan: DecisionPlan,
    verdict: RiskVerdict,
) -> dict[str, Any]:
    leader_summary = research_audit.leader_summary if research_audit else {}
    finalizer = leader_summary.get("leader_finalizer") if isinstance(leader_summary, dict) else None
    reasoning_summary = ""
    if isinstance(finalizer, dict):
        reasoning_summary = str(finalizer.get("summary") or "")
    if not reasoning_summary:
        reasoning_summary = plan.notes or plan.why_not_opposite

    return {
        "reasoning_summary": reasoning_summary,
        "decision_ladder": [
            {"stage": "final_decision", "main_action": plan.main_action, "probability": plan.probability},
            {"stage": "risk_gate", "allowed": verdict.allowed, "reasons": verdict.reasons},
        ],
        "evidence_to_claims": _evidence_to_claims(research_audit),
        "opposing_thesis": plan.why_not_opposite,
        "data_gaps": [*(snapshot.unavailable if snapshot else []), *plan.unavailable_data],
        "risk_rule_hits": verdict.reasons,
    }


def _evidence_to_claims(research_audit: ResearchAudit | None) -> list[dict[str, Any]]:
    if not research_audit:
        return []
    mappings: list[dict[str, Any]] = []
    for name, results in sorted(research_audit.results.items()):
        for index, result in enumerate(results[:3]):
            mappings.append(
                {
                    "claim": f"{name} 补充当前上下文",
                    "evidence_ref": f"research.results.{name}[{index}]",
                    "source": result.source,
                    "url": result.url,
                    "relation": "context",
                }
            )
    return mappings


def _redaction_policy() -> dict[str, Any]:
    return {
        "full_prompt_saved": False,
        "full_completion_saved": True,
        "llm_interactions_store": "hash_summary_and_sanitized_payload",
        "hidden_reasoning_saved": False,
    }
