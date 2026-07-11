from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.config import Config
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.context.artifacts import record_orchestration_artifacts
from crypto_manual_alert.decision.frozen_input import stable_hash
from crypto_manual_alert.decision.final_decision_step import run_final_decision_step
from crypto_manual_alert.decision.legacy_final_input_step import LegacyFinalInputStepResult, build_legacy_final_input_step
from crypto_manual_alert.decision.plan_parse_step import run_plan_parse_step
from crypto_manual_alert.decision.pre_final_switch_readiness import build_pre_final_switch_readiness
from crypto_manual_alert.domain import DecisionPlan, MarketSnapshot, RiskVerdict
from crypto_manual_alert.market.event_status import EventStatusProvider, build_event_status_provider
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder, use_observability
from crypto_manual_alert.research_pipeline import LeaderResearchSynthesizer, ResearchAudit, ResearchPlanner, SearchAdapter
from crypto_manual_alert.decision.final_engine import DecisionEngine
from crypto_manual_alert.skills.context_loader import SkillRuntime
from crypto_manual_alert.workflow.decision_control_step import DecisionControlStepResult, run_decision_control_step
from crypto_manual_alert.workflow.market_context_step import MarketContextStepResult, load_market_context_step
from crypto_manual_alert.workflow.pre_final_orchestration import PreFinalOrchestrationResult, run_pre_final_orchestration
from crypto_manual_alert.workflow.research_orchestration import run_research_orchestration


@dataclass(frozen=True)
class LegacyDecisionWorkflowResult:
    """Artifacts produced by the current legacy production decision chain.

    This is not the target Agent Swarm implementation. It isolates the old
    step sequence so PlanRunner can remain a compatibility shell while the
    controlled workflow is replaced behind a clear boundary.
    """

    plan: DecisionPlan
    verdict: RiskVerdict
    snapshot: MarketSnapshot | None
    research_audit: ResearchAudit | None
    prompt_packet: dict[str, Any]
    legacy_final_input_result: LegacyFinalInputStepResult | None
    final_input_selection: dict[str, Any] | None
    raw_decision: str | None
    shadow_swarm_audit: dict[str, Any] | None
    audit_payload: dict[str, Any] | None
    pre_final_decision_input: dict[str, Any] | None
    candidate_audit: dict[str, Any] | None
    production_control_verdict: RiskVerdict | None
    decision_control_result: DecisionControlStepResult | None
    pre_final_orchestration_result: PreFinalOrchestrationResult | None
    market_context_result: MarketContextStepResult | None


@dataclass
class LegacyDecisionWorkflowState:
    """Mutable checkpoint state for failure persistence in the legacy workflow."""

    market_context_result: MarketContextStepResult | None = None
    snapshot: MarketSnapshot | None = None
    research_audit: ResearchAudit | None = None
    prompt_packet: dict[str, Any] | None = None
    legacy_final_input_result: LegacyFinalInputStepResult | None = None
    pre_final_orchestration_result: PreFinalOrchestrationResult | None = None
    audit_payload: dict[str, Any] | None = None
    shadow_swarm_audit: dict[str, Any] | None = None
    pre_final_decision_input: dict[str, Any] | None = None
    raw_decision: str | None = None
    final_input_selection: dict[str, Any] | None = None
    decision_control_result: DecisionControlStepResult | None = None
    candidate_audit: dict[str, Any] | None = None
    production_control_verdict: RiskVerdict | None = None


class LegacyDecisionWorkflow:
    """Current production step sequence behind the legacy prompt path.

    It still feeds FinalDecisionAgent with the legacy frozen prompt. It does
    not promote shadow worker output to production final input.
    """

    def __init__(
        self,
        *,
        config: Config,
        skill_runtime: SkillRuntime,
        decision_engine: DecisionEngine,
        research_planner: ResearchPlanner,
        search_adapter: SearchAdapter,
        leader_synthesizer: LeaderResearchSynthesizer,
        event_status_provider: EventStatusProvider | None = None,
    ):
        self.config = config
        self.skill_runtime = skill_runtime
        self.decision_engine = decision_engine
        self.research_planner = research_planner
        self.search_adapter = search_adapter
        self.leader_synthesizer = leader_synthesizer
        self.event_status_provider = event_status_provider or build_event_status_provider(config)

    def run(
        self,
        *,
        symbol: str,
        trace_id: str,
        recorder: ObservabilityRecorder,
        market_provider: Any,
        run_context: DecisionRunContext | None,
        workflow_state: LegacyDecisionWorkflowState | None = None,
    ) -> LegacyDecisionWorkflowResult:
        workflow_state = workflow_state if workflow_state is not None else LegacyDecisionWorkflowState()
        snapshot: MarketSnapshot | None = None
        research_audit: ResearchAudit | None = None
        prompt_packet: dict[str, Any] = {}
        legacy_final_input_result: LegacyFinalInputStepResult | None = None
        final_input_selection: dict[str, Any] | None = None
        raw_decision: str | None = None
        shadow_swarm_audit: dict[str, Any] | None = None
        audit_payload: dict[str, Any] | None = None
        pre_final_decision_input: dict[str, Any] | None = None
        candidate_audit: dict[str, Any] | None = None
        production_control_verdict: RiskVerdict | None = None
        decision_control_result: DecisionControlStepResult | None = None
        pre_final_orchestration_result: PreFinalOrchestrationResult | None = None
        market_context_result: MarketContextStepResult | None = None

        with recorder.span(trace_id, "market.fetch", "market.fetch", input_summary={"symbol": symbol}) as span:
            market_context_result = load_market_context_step(
                symbol=symbol,
                market_provider=market_provider,
                skill_runtime=self.skill_runtime,
                event_status_provider=self.event_status_provider,
            )
            snapshot = market_context_result.snapshot
            skill_context = market_context_result.skill_context
            workflow_state.market_context_result = market_context_result
            workflow_state.snapshot = snapshot
            span.set_output(market_context_result.market_summary)

        with recorder.span(trace_id, "skill.load", "skill.load") as span:
            span.set_output(market_context_result.skill_summary)

        research_result = run_research_orchestration(
            config=self.config,
            recorder=recorder,
            trace_id=trace_id,
            snapshot=snapshot,
            skill_context=skill_context.to_prompt_dict(),
            research_planner=self.research_planner,
            search_adapter=self.search_adapter,
            leader_synthesizer=self.leader_synthesizer,
        )
        snapshot = research_result.snapshot
        research_audit = research_result.research_audit
        workflow_state.snapshot = snapshot
        workflow_state.research_audit = research_audit

        with recorder.span(trace_id, "prompt.build", "prompt.build") as span:
            legacy_final_input_result = build_legacy_final_input_step(
                trace_id=trace_id,
                skill_runtime=self.skill_runtime,
                skill_context=skill_context,
                snapshot=snapshot,
                research_audit=research_audit,
            )
            prompt_packet = legacy_final_input_result.prompt_packet
            workflow_state.legacy_final_input_result = legacy_final_input_result
            workflow_state.prompt_packet = prompt_packet
            span.set_output(legacy_final_input_result.prompt_summary)

        with recorder.span(trace_id, "input.freeze", "input.freeze") as span:
            span.set_output(legacy_final_input_result.freeze_summary)

        with recorder.span(trace_id, "decision_input.pre_final", "decision_input.pre_final") as span:
            pre_final_orchestration_result = run_pre_final_orchestration(
                symbol=symbol,
                trace_id=trace_id,
                recorder=recorder,
                snapshot=snapshot,
                research_audit=research_audit,
                run_context=run_context,
                config=self.config,
            )
            audit_payload = pre_final_orchestration_result.audit_payload
            shadow_swarm_audit = pre_final_orchestration_result.shadow_swarm_audit
            pre_final_decision_input = pre_final_orchestration_result.pre_final_decision_input
            workflow_state.pre_final_orchestration_result = pre_final_orchestration_result
            workflow_state.audit_payload = audit_payload
            workflow_state.shadow_swarm_audit = shadow_swarm_audit
            workflow_state.pre_final_decision_input = pre_final_decision_input
            span.set_output(pre_final_orchestration_result.pre_final_summary)

        with recorder.span(trace_id, "decision.final", "decision.llm") as span:
            with use_observability(recorder, trace_id):
                decision_step_result = run_final_decision_step(
                    decision_engine=self.decision_engine,
                    final_input_mode=self.config.decision.final_input_mode,
                    legacy_prompt_packet=legacy_final_input_result.frozen_input.input_payload,
                    decision_input_candidate=pre_final_decision_input,
                    switch_readiness=build_pre_final_switch_readiness(pre_final_decision_input),
                )
            raw_decision = decision_step_result.raw_decision
            final_input_selection = decision_step_result.final_input_selection
            workflow_state.raw_decision = raw_decision
            workflow_state.final_input_selection = final_input_selection
            span.set_output(decision_step_result.output_summary)

        with recorder.span(trace_id, "parser.strict_json", "parser.strict_json") as span:
            plan_parse_result = run_plan_parse_step(raw_decision)
            plan = plan_parse_result.plan
            span.set_output(plan_parse_result.parse_summary)

        if audit_payload is None:
            raise RuntimeError("pre-final orchestration did not produce audit payload")
        with recorder.span(trace_id, "production_control.check", "production_control.check") as span:
            decision_control_result = run_decision_control_step(
                trace_id=trace_id,
                plan=plan,
                snapshot=snapshot,
                config=self.config,
                frozen_input_hash=legacy_final_input_result.frozen_input.frozen_input_hash,
                audit_payload=audit_payload,
                shadow_swarm_audit=shadow_swarm_audit,
                raw_decision=raw_decision,
                final_input_selection=final_input_selection,
                candidate_decision_engine=_candidate_sidecar_engine(self.config, self.decision_engine),
                pre_final_decision_input=pre_final_decision_input,
                run_context_summary=_current_run_context_summary(
                    run_context,
                    config=self.config,
                    skill_context=skill_context,
                    prompt_packet=prompt_packet,
                    legacy_final_input_result=legacy_final_input_result,
                ),
                telemetry_refs=_trace_telemetry_refs(recorder, trace_id),
                span_tree_refs=_trace_span_tree_refs(recorder, trace_id),
            )
            candidate_audit = decision_control_result.candidate_audit
            production_control_verdict = decision_control_result.production_control_verdict
            workflow_state.decision_control_result = decision_control_result
            workflow_state.candidate_audit = candidate_audit
            workflow_state.production_control_verdict = production_control_verdict
            record_orchestration_artifacts(
                run_context,
                candidate_audit=candidate_audit,
                production_control_verdict=production_control_verdict,
            )
            span.set_output(decision_control_result.production_control_summary)

        with recorder.span(trace_id, "risk.check", "risk.check") as span:
            verdict = decision_control_result.final_verdict
            span.set_output(decision_control_result.risk_summary)
        record_orchestration_artifacts(run_context, candidate_audit=candidate_audit)

        return LegacyDecisionWorkflowResult(
            plan=plan,
            verdict=verdict,
            snapshot=snapshot,
            research_audit=research_audit,
            prompt_packet=prompt_packet,
            legacy_final_input_result=legacy_final_input_result,
            final_input_selection=final_input_selection,
            raw_decision=raw_decision,
            shadow_swarm_audit=shadow_swarm_audit,
            audit_payload=audit_payload,
            pre_final_decision_input=pre_final_decision_input,
            candidate_audit=candidate_audit,
            production_control_verdict=production_control_verdict,
            decision_control_result=decision_control_result,
            pre_final_orchestration_result=pre_final_orchestration_result,
            market_context_result=market_context_result,
        )


def _current_run_context_summary(
    run_context: DecisionRunContext | None,
    *,
    config: Config,
    skill_context: Any,
    prompt_packet: dict[str, Any],
    legacy_final_input_result: LegacyFinalInputStepResult | None,
) -> dict[str, Any] | None:
    if run_context is None:
        return None
    summary = run_context.to_public_summary()
    summary["artifacts"] = run_context.to_artifact_summary()
    summary["version_lock"] = _version_lock_summary(
        config=config,
        skill_context=skill_context,
        prompt_packet=prompt_packet,
        legacy_final_input_result=legacy_final_input_result,
    )
    return summary


def _candidate_sidecar_engine(config: Config, decision_engine: DecisionEngine) -> DecisionEngine | None:
    if config.decision.candidate_sidecar_mode == "disabled":
        return None
    return decision_engine


def _version_lock_summary(
    *,
    config: Config,
    skill_context: Any,
    prompt_packet: dict[str, Any],
    legacy_final_input_result: LegacyFinalInputStepResult | None,
) -> dict[str, Any]:
    redaction_policy = {
        "full_prompt_saved": legacy_final_input_result is not None,
        "full_completion_saved": True,
        "llm_interactions_store": "hash_summary_and_sanitized_payload",
        "hidden_reasoning_saved": False,
        "frozen_input_saved": legacy_final_input_result is not None,
        "frozen_input_schema_version": (
            legacy_final_input_result.frozen_input.schema_version
            if legacy_final_input_result is not None
            else None
        ),
    }
    skill_name = str(getattr(skill_context, "name", "crypto-macro-decision"))
    skill_hash = str(getattr(skill_context, "sha256", ""))
    return {
        "config_hash": f"sha256:{stable_hash(config.safe_dict())}",
        "skill_hashes": {skill_name: f"sha256:{skill_hash}"},
        "prompt_hashes": {"legacy_final_prompt": f"sha256:{stable_hash(prompt_packet)}"},
        "model": config.decision.openai_model or config.decision.engine,
        "rule_hashes": {
            "risk_gate": f"sha256:{stable_hash(_risk_rule_version_payload(config))}",
            "production_control_gate": "sha256:production_control_gate.current",
        },
        "redaction_policy_hash": f"sha256:{stable_hash(redaction_policy)}",
    }


def _risk_rule_version_payload(config: Config) -> dict[str, Any]:
    return {
        "allowed_symbols": list(config.trading.allowed_symbols),
        "manual_execution_required": config.trading.manual_execution_required,
        "max_leverage": config.trading.max_leverage,
        "max_risk_per_trade_pct": config.trading.max_risk_per_trade_pct,
        "plan_ttl_seconds": config.trading.plan_ttl_seconds,
    }


def _trace_telemetry_refs(recorder: ObservabilityRecorder, trace_id: str) -> dict[str, Any] | None:
    detail = recorder.journal.get_trace_detail(trace_id, include_payloads=False)
    if not isinstance(detail, dict):
        return None
    spans = detail.get("spans") if isinstance(detail.get("spans"), list) else []
    llm_interactions = (
        detail.get("llm_interactions")
        if isinstance(detail.get("llm_interactions"), list)
        else []
    )
    return {"spans": spans, "llm_interactions": llm_interactions}


def _trace_span_tree_refs(recorder: ObservabilityRecorder, trace_id: str) -> dict[str, Any] | None:
    detail = recorder.journal.get_trace_detail(trace_id, include_payloads=False)
    if not isinstance(detail, dict):
        return None
    spans = detail.get("spans") if isinstance(detail.get("spans"), list) else []
    return {"spans": spans}
