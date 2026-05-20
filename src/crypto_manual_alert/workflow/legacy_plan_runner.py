from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from crypto_manual_alert.config import Config
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.domain import DecisionPlan, RiskVerdict, RuleHit
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.workflow.legacy_decision_workflow import (
    LegacyDecisionWorkflow,
    LegacyDecisionWorkflowResult,
    LegacyDecisionWorkflowState,
)
from crypto_manual_alert.market.providers import FixtureMarketDataProvider, MarketDataProvider, OkxPublicMarketDataProvider
from crypto_manual_alert.notification.sinks import BarkNotificationSink, NoopNotificationSink, NotificationSink
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.research_pipeline import (
    LeaderResearchSynthesizer,
    ResearchPlanner,
    SearchAdapter,
    build_leader_synthesizer,
    build_research_planner,
    build_search_adapter,
)
from crypto_manual_alert.decision.final_engine import (
    CommandDecisionEngine,
    DecisionEngine,
    FixtureDecisionEngine,
    OpenAICompatibleDecisionEngine,
)
from crypto_manual_alert.skills.context_loader import (
    SkillRuntime,
)
from crypto_manual_alert.workflow.persistence_payload import run_context_for_audit
from crypto_manual_alert.workflow.run_persistence_step import persist_run_result
from crypto_manual_alert.workflow.results import DecisionStepResult


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
        self.legacy_decision_workflow = LegacyDecisionWorkflow(
            config=self.config,
            skill_runtime=self.skill_runtime,
            decision_engine=self.decision_engine,
            research_planner=self.research_planner,
            search_adapter=self.search_adapter,
            leader_synthesizer=self.leader_synthesizer,
        )

    def run_once(
        self,
        symbol: str,
        *,
        run_context: DecisionRunContext | None = None,
        run_context_summary: dict[str, Any] | None = None,
    ) -> DecisionStepResult:
        recorder = ObservabilityRecorder(self.journal)
        run_context_summary = run_context.to_public_summary() if run_context else run_context_summary
        trace_metadata = _trace_metadata(run_context_summary)
        trace_id = recorder.start_trace(
            run_type=str(run_context_summary.get("run_type") or "manual") if run_context_summary else "manual",
            symbol=symbol,
            horizon=(
                str(run_context_summary.get("horizon"))
                if run_context_summary and run_context_summary.get("horizon")
                else None
            ),
            metadata=trace_metadata,
        )
        workflow_state = LegacyDecisionWorkflowState()
        workflow_result: LegacyDecisionWorkflowResult | None = None

        try:
            workflow_result = self.legacy_decision_workflow.run(
                symbol=symbol,
                trace_id=trace_id,
                recorder=recorder,
                market_provider=self.market_provider,
                run_context=run_context,
                workflow_state=workflow_state,
            )
            plan = workflow_result.plan
            verdict = workflow_result.verdict

        except Exception as exc:  # noqa: BLE001 - persist a blocked audit plan on pipeline failure.
            logger.exception("plan pipeline failed")
            plan, verdict = self._blocked_failure_plan(symbol, exc)
            run_context_summary = _current_run_context_summary(run_context, run_context_summary)
            trace_metadata = _trace_metadata(run_context_summary)
            legacy_final_input_result = workflow_state.legacy_final_input_result
            persist_run_result(
                config=self.config,
                journal=self.journal,
                notifier=self.notifier,
                recorder=recorder,
                trace_id=trace_id,
                plan=plan,
                verdict=verdict,
                snapshot=workflow_state.snapshot,
                raw_decision=workflow_state.raw_decision,
                prompt_packet=workflow_state.prompt_packet or {},
                research_audit=workflow_state.research_audit,
                frozen_input=legacy_final_input_result.frozen_input if legacy_final_input_result else None,
                shadow_swarm_audit=workflow_state.shadow_swarm_audit,
                final_input_selection=workflow_state.final_input_selection,
                run_context_summary=run_context_summary,
                audit_payload=workflow_state.audit_payload,
                pre_final_decision_input=workflow_state.pre_final_decision_input,
                candidate_audit=workflow_state.candidate_audit,
                production_control_verdict=workflow_state.production_control_verdict,
                trace_metadata=trace_metadata,
                error={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
            )
            return DecisionStepResult(trace_id=trace_id, plan=plan, verdict=verdict)

        run_context_summary = _current_run_context_summary(run_context, run_context_summary)
        trace_metadata = _trace_metadata(run_context_summary)
        persist_run_result(
            config=self.config,
            journal=self.journal,
            notifier=self.notifier,
            recorder=recorder,
            trace_id=trace_id,
            plan=plan,
            verdict=verdict,
            snapshot=workflow_result.snapshot,
            raw_decision=workflow_result.raw_decision,
            prompt_packet=workflow_result.prompt_packet,
            research_audit=workflow_result.research_audit,
            frozen_input=(
                workflow_result.legacy_final_input_result.frozen_input
                if workflow_result.legacy_final_input_result
                else None
            ),
            shadow_swarm_audit=workflow_result.shadow_swarm_audit,
            final_input_selection=workflow_result.final_input_selection,
            run_context_summary=run_context_summary,
            audit_payload=workflow_result.audit_payload,
            pre_final_decision_input=workflow_result.pre_final_decision_input,
            candidate_audit=workflow_result.candidate_audit,
            production_control_verdict=workflow_result.production_control_verdict,
            trace_metadata=trace_metadata,
        )
        return DecisionStepResult(trace_id=trace_id, plan=plan, verdict=verdict)

    def _blocked_failure_plan(self, symbol: str, exc: Exception) -> tuple[DecisionPlan, RiskVerdict]:
        now = datetime.now(timezone.utc)
        error_message = f"{type(exc).__name__}: {exc}"
        failure_reason = "Decision pipeline failed; manual trading is blocked for this run."
        payload: dict[str, Any] = {
            "instrument": symbol,
            "main_action": "no trade",
            "horizon": "unknown",
            "manual_execution_required": True,
            "expires_in_seconds": 0,
            "why_not_opposite": "The pipeline failed before a reliable plan was generated.",
            "invalidation": "Retry only after market data, skill context, model output, and parser are healthy.",
            "unavailable_data": [error_message],
            "notes": "System failure; do not manually trade from this run output.",
        }
        plan = DecisionPlan.from_payload(payload, generated_at=now)
        return plan, RiskVerdict(
            allowed=False,
            reasons=[failure_reason],
            warnings=plan.unavailable_data,
            rule_hits=[
                RuleHit(
                    rule_id="pipeline.decision_engine.error",
                    passed=False,
                    severity="critical",
                    message=failure_reason,
                    blocking=True,
                    evidence_refs=["error.type", "error.message"],
                    details={"error_type": type(exc).__name__, "error_message": str(exc)},
                )
            ],
        )


def build_market_provider(
    config: Config,
    *,
    http_get: Callable[[str, dict[str, str]], Any] | None = None,
) -> MarketDataProvider:
    if config.market_data.provider == "fixture":
        return FixtureMarketDataProvider()
    if config.market_data.provider == "okx_public":
        return OkxPublicMarketDataProvider(config, http_get=http_get)
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
            "rule_hits": [hit.to_public_dict() for hit in verdict.rule_hits],
            "expires_at": plan.expires_at.isoformat(),
            "manual_execution_required": plan.manual_execution_required,
        },
        ensure_ascii=False,
        indent=2,
    )


def _trace_metadata(run_context_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not run_context_summary:
        return {
            "legacy_direct_invocation": {
                "entrypoint": "PlanRunner.run_once",
                "side_effect_policy": "missing",
            }
        }
    return {"run_context": run_context_for_audit(run_context_summary)}


def _current_run_context_summary(
    run_context: DecisionRunContext | None,
    fallback_summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if run_context is None:
        return fallback_summary
    summary = run_context.to_public_summary()
    summary["artifacts"] = run_context.to_artifact_summary()
    return summary

