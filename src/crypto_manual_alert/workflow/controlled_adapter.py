from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from crypto_manual_alert.config import Config
from crypto_manual_alert.context.run_context import DecisionRunContext
from crypto_manual_alert.context.artifacts import record_orchestration_artifacts
from crypto_manual_alert.decision.candidate_audit import build_candidate_audit_payload
from crypto_manual_alert.decision.candidate_final_decision import run_candidate_final_decision_sidecar
from crypto_manual_alert.decision.pre_final_input_gate import evaluate_pre_final_input_gate
from crypto_manual_alert.domain import DecisionPlan, RiskVerdict, RuleHit
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.workflow.legacy_plan_runner import build_decision_engine
from crypto_manual_alert.workflow.persistence_payload import build_plan_payload, run_context_for_audit
from crypto_manual_alert.workflow.pre_final_orchestration import run_pre_final_orchestration
from crypto_manual_alert.workflow.results import DecisionStepResult


@dataclass
class ControlledSwarmAuditAdapter:
    """Controlled Agent Swarm adapter skeleton.

    This adapter exercises the controlled worker orchestration boundary and
    writes audit artifacts into DecisionRunContext. It does not replace the
    production legacy decision chain, call FinalDecisionAgent, write the
    production journal, or send notifications.
    """

    config: Config
    journal: Journal

    def run(self, context: DecisionRunContext) -> DecisionStepResult:
        execution_mode = _execution_mode(self.config)
        reason = _audit_only_reason(execution_mode)
        trace_id = f"{_trace_prefix(execution_mode)}-{context.run_id}"
        recorder = ObservabilityRecorder(self.journal)
        recorder.start_trace(
            trace_id=trace_id,
            run_type=context.request.run_type,
            symbol=context.symbol,
            horizon=context.horizon,
            metadata={
                "execution_mode": execution_mode,
                "audit_only": True,
                "run_context": run_context_for_audit(context.to_public_summary()),
            },
        )
        pre_final = run_pre_final_orchestration(
            symbol=context.symbol,
            trace_id=trace_id,
            recorder=recorder,
            snapshot=None,
            research_audit=None,
            run_context=context,
            config=self.config,
        )
        plan = _audit_only_plan(symbol=context.symbol, horizon=context.horizon, reason=reason)
        verdict = _audit_only_verdict(reason)
        candidate_final_decision = _candidate_final_sidecar(
            config=self.config,
            pre_final_decision_input=pre_final.pre_final_decision_input,
            enabled=execution_mode == "production_candidate_swarm",
        )
        candidate_audit = build_candidate_audit_payload(
            trace_id=trace_id,
            symbol=context.symbol,
            legacy_plan=plan.raw,
            verdict=verdict.to_public_dict(),
            frozen_input_hash=None,
            audit_payload=pre_final.audit_payload,
            shadow_swarm_audit=pre_final.shadow_swarm_audit,
            candidate_final_decision=candidate_final_decision,
        )
        record_orchestration_artifacts(
            context,
            candidate_audit=candidate_audit,
            production_control_verdict=verdict,
        )
        run_context_summary = context.to_public_summary()
        run_context_summary["artifacts"] = context.to_artifact_summary()
        payload = build_plan_payload(
            trace_id=trace_id,
            plan=plan,
            snapshot=None,
            raw_decision=None,
            verdict=verdict,
            prompt_packet={"skill": {"mode": f"{execution_mode}_audit_only"}},
            research_audit=None,
            frozen_input=None,
            shadow_swarm_audit=pre_final.shadow_swarm_audit,
            final_input_selection={
                "mode": f"{execution_mode}_audit_only",
                "decision_effect": "none",
                "production_final_input": False,
                "notification_input": False,
            },
            run_context_summary=run_context_summary,
            audit_payload=pre_final.audit_payload,
            pre_final_decision_input=pre_final.pre_final_decision_input,
            candidate_audit=candidate_audit,
            production_control_verdict=verdict,
        )
        controlled_shadow = {
            "mode": execution_mode,
            "status": "blocked",
            "audit_only": True,
            "production_candidate": False,
            "blocked": True,
            "production_final_input": False,
            "notification_input": False,
            "reason": reason,
        }
        payload["controlled_shadow"] = controlled_shadow
        if isinstance(payload.get("audit_only"), dict):
            payload["audit_only"]["controlled_shadow"] = controlled_shadow
            mirrored = payload["audit_only"].setdefault("mirrored_legacy_fields", [])
            if "controlled_shadow" not in mirrored:
                mirrored.append("controlled_shadow")
        with recorder.span(
            trace_id,
            "journal.write",
            "journal.write",
            input_summary={"mode": "controlled_shadow", "plan_id": plan.plan_id},
        ) as span:
            self.journal.append_plan_run(plan.plan_id, "blocked", payload)
            span.set_output({"plan_id": plan.plan_id, "status": "blocked", "audit_only": True})
        recorder.finish_trace(
            trace_id,
            status="blocked",
            final_plan_id=plan.plan_id,
            final_action=plan.main_action,
            allowed=verdict.allowed,
            metadata={
                "execution_mode": execution_mode,
                "audit_only": True,
                "run_context": run_context_for_audit(run_context_summary),
            },
        )
        return DecisionStepResult(trace_id=trace_id, plan=plan, verdict=verdict)


def _execution_mode(config: Config) -> str:
    mode = str(getattr(getattr(config, "workflow", None), "execution_mode", "controlled_shadow"))
    if mode == "production_candidate_swarm":
        return mode
    return "controlled_shadow"


def _trace_prefix(execution_mode: str) -> str:
    if execution_mode == "production_candidate_swarm":
        return "production-candidate-swarm"
    return "controlled-audit"


def _audit_only_reason(execution_mode: str) -> str:
    if execution_mode == "production_candidate_swarm":
        return "production_candidate_swarm_audit_only"
    return "controlled_swarm_audit_only"


def _audit_only_plan(*, symbol: str, horizon: str | None, reason: str) -> DecisionPlan:
    now = datetime.now(timezone.utc)
    raw = {
        "instrument": symbol,
        "main_action": "no trade",
        "horizon": horizon or "unknown",
        "manual_execution_required": True,
        "invalidation": f"{reason} adapter is not promoted for production decisions",
        "notes": reason,
    }
    return DecisionPlan(
        plan_id=DecisionPlan.build_id(raw, now),
        instrument=symbol,
        main_action="no trade",
        horizon=horizon or "unknown",
        manual_execution_required=True,
        generated_at=now,
        expires_at=now + timedelta(seconds=90),
        invalidation=str(raw["invalidation"]),
        notes=str(raw["notes"]),
        raw=raw,
    )


def _audit_only_verdict(reason: str) -> RiskVerdict:
    return RiskVerdict(
        allowed=False,
        reasons=[reason],
        rule_hits=[
            RuleHit(
                rule_id=f"{reason}.blocked",
                passed=False,
                severity="critical",
                message=f"{reason} adapter is not promoted for production decisions",
                blocking=True,
            )
        ],
    )


def _candidate_final_sidecar(
    *,
    config: Config,
    pre_final_decision_input: dict[str, object] | None,
    enabled: bool,
) -> dict[str, object] | None:
    if not enabled:
        return None
    return run_candidate_final_decision_sidecar(
        decision_engine=build_decision_engine(config),
        pre_final_decision_input=pre_final_decision_input,
        input_gate=evaluate_pre_final_input_gate(pre_final_decision_input),
    )
