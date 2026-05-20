from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import DecisionPlan, MarketSnapshot, NotificationResult, RiskVerdict
from crypto_manual_alert.decision.frozen_input import FrozenInput
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.notification.sinks import NotificationSink
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.research_pipeline import ResearchAudit
from crypto_manual_alert.workflow.persistence_payload import build_plan_payload
from crypto_manual_alert.workflow.side_effect_gate import evaluate_side_effect_gate


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunPersistenceStepResult:
    """Durable record result for one legacy decision run.

    This step owns plan payload assembly, trace completion, journal writes, and
    notification audit rows. It does not parse plans, run gates, or change the
    supplied RiskVerdict.
    """

    plan: DecisionPlan
    verdict: RiskVerdict
    status: str
    payload: dict[str, Any]
    notification_result: NotificationResult | None = None


def persist_run_result(
    *,
    config: Config,
    journal: Journal,
    notifier: NotificationSink,
    recorder: ObservabilityRecorder,
    trace_id: str,
    plan: DecisionPlan,
    verdict: RiskVerdict,
    snapshot: MarketSnapshot | None,
    raw_decision: str | None,
    prompt_packet: dict[str, Any],
    research_audit: ResearchAudit | None,
    frozen_input: FrozenInput | None,
    shadow_swarm_audit: dict[str, Any] | None = None,
    final_input_selection: dict[str, Any] | None = None,
    run_context_summary: dict[str, Any] | None = None,
    audit_payload: dict[str, Any] | None = None,
    pre_final_decision_input: dict[str, Any] | None = None,
    candidate_audit: dict[str, Any] | None = None,
    production_control_verdict: RiskVerdict | None = None,
    trace_metadata: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> RunPersistenceStepResult:
    payload = build_plan_payload(
        trace_id=trace_id,
        plan=plan,
        snapshot=snapshot,
        raw_decision=raw_decision,
        verdict=verdict,
        prompt_packet=prompt_packet,
        research_audit=research_audit,
        frozen_input=frozen_input,
        shadow_swarm_audit=shadow_swarm_audit,
        final_input_selection=final_input_selection,
        run_context_summary=run_context_summary,
        audit_payload=audit_payload,
        pre_final_decision_input=pre_final_decision_input,
        candidate_audit=candidate_audit,
        production_control_verdict=production_control_verdict,
        error=error,
    )
    status = "blocked" if error or not verdict.allowed else "allowed"
    side_effect_gate = evaluate_side_effect_gate(run_context_summary)
    with recorder.span(trace_id, "journal.write", "journal.write") as span:
        if side_effect_gate.allow_production_journal_write:
            journal.append_plan_run(plan.plan_id, status, payload)
            span.set_output({"plan_id": plan.plan_id, "status": status})
        else:
            span.set_output(
                {
                    "plan_id": plan.plan_id,
                    "status": status,
                    "skipped": side_effect_gate.skip_reason,
                }
            )

    finish_metadata = dict(trace_metadata or {})
    if error and error.get("type"):
        finish_metadata["error_type"] = error["type"]
    recorder.finish_trace(
        trace_id,
        status=status,
        final_plan_id=plan.plan_id,
        final_action=plan.main_action,
        allowed=verdict.allowed,
        metadata=finish_metadata,
    )

    notification_result = _maybe_send_notification(
        config=config,
        journal=journal,
        notifier=notifier,
        recorder=recorder,
        trace_id=trace_id,
        plan=plan,
        verdict=verdict,
        is_failure=bool(error),
        allow_notification_intent=side_effect_gate.allow_notification_intent,
    )
    return RunPersistenceStepResult(
        plan=plan,
        verdict=verdict,
        status=status,
        payload=payload,
        notification_result=notification_result,
    )


def _maybe_send_notification(
    *,
    config: Config,
    journal: Journal,
    notifier: NotificationSink,
    recorder: ObservabilityRecorder,
    trace_id: str,
    plan: DecisionPlan,
    verdict: RiskVerdict,
    is_failure: bool,
    allow_notification_intent: bool = True,
) -> NotificationResult | None:
    if not allow_notification_intent:
        return None
    if not config.notification.enabled:
        return None
    if is_failure and not config.notification.send_failure_alerts:
        return None
    with recorder.span(
        trace_id,
        "notification.send",
        "notification.send",
        input_summary={"plan_id": plan.plan_id, "allowed": verdict.allowed},
    ) as span:
        result = _send_notification(notifier, plan, verdict)
        journal.append_notification(plan.plan_id, result.ok, result.status_code, result.error)
        span.set_output({"ok": result.ok, "status_code": result.status_code, "error": result.error})
        return result


def _send_notification(
    notifier: NotificationSink,
    plan: DecisionPlan,
    verdict: RiskVerdict,
) -> NotificationResult:
    try:
        return notifier.send(plan, verdict)
    except Exception as exc:  # noqa: BLE001 - notification failures must not mutate the risk verdict.
        logger.exception("notification failed")
        return NotificationResult(ok=False, error=f"{type(exc).__name__}: {exc}")
