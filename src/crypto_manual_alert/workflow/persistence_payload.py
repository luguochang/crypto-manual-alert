from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crypto_manual_alert.artifacts.orchestration_inputs import build_audit_artifacts
from crypto_manual_alert.decision.candidate_audit import build_candidate_audit_payload
from crypto_manual_alert.decision.frozen_input import FrozenInput
from crypto_manual_alert.domain import DecisionPlan, MarketSnapshot, RiskVerdict
from crypto_manual_alert.research_pipeline import ResearchAudit

if TYPE_CHECKING:
    from crypto_manual_alert.config import Config


def build_plan_payload(
    *,
    trace_id: str,
    plan: DecisionPlan,
    snapshot: MarketSnapshot | None,
    raw_decision: str | None,
    verdict: RiskVerdict,
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
    config: "Config | None" = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit_payload = audit_payload or build_audit_artifacts(
        trace_id=trace_id,
        snapshot=snapshot,
        research_audit=research_audit,
    )
    candidate_audit = candidate_audit or build_candidate_audit_payload(
        trace_id=trace_id,
        symbol=plan.instrument,
        legacy_plan=plan.raw,
        verdict=verdict.to_public_dict(),
        frozen_input_hash=frozen_input.frozen_input_hash if frozen_input else None,
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        raw_decision=raw_decision,
        final_input_selection=final_input_selection,
        production_control_verdict=(
            production_control_verdict.to_public_dict()
            if production_control_verdict
            else None
        ),
        run_context_summary=run_context_summary,
    )
    payload = {
        "trace_id": trace_id,
        "plan": plan.raw,
        "snapshot": snapshot.to_public_dict() if snapshot else None,
        "evidence_snapshot": snapshot.to_public_dict() if snapshot else None,
        "raw_decision": raw_decision,
        "parsed_plan": plan.raw,
        "verdict": verdict.to_public_dict(),
        "skill": prompt_packet.get("skill"),
        "research": research_audit.to_public_dict() if research_audit else None,
        "evidence_packets": audit_payload["evidence_packets"],
        "facts_gate": audit_payload["facts_gate"],
        "harness_validation": audit_payload["harness_validation"],
        "agent_contributions": audit_payload["agent_contributions"],
        "shadow_swarm_audit": shadow_swarm_audit,
        "pre_final_decision_input": pre_final_decision_input,
        "final_input_selection": final_input_selection,
        "main_path_contract": _main_path_contract(
            plan=plan,
            final_input_selection=final_input_selection,
            run_context_summary=run_context_summary,
            config=config,
        ),
        "legacy_prompt_lifecycle": _legacy_prompt_lifecycle(final_input_selection),
        **candidate_audit,
        "production_control_gate": (
            production_control_verdict.to_public_dict()
            if production_control_verdict
            else {"allowed": True, "reasons": [], "warnings": [], "rule_hits": []}
        ),
        "analysis": _analysis_summary(snapshot, research_audit, plan, verdict),
        "redaction": _redaction_policy(frozen_input),
        "frozen_input": frozen_input.to_plan_payload() if frozen_input else None,
        "frozen_input_hash": frozen_input.frozen_input_hash if frozen_input else None,
    }
    payload["audit_only"] = _audit_only_namespace(
        audit_payload=audit_payload,
        shadow_swarm_audit=shadow_swarm_audit,
        pre_final_decision_input=pre_final_decision_input,
        candidate_audit=candidate_audit,
    )
    if run_context_summary:
        payload["run_context"] = run_context_for_audit(run_context_summary)
    if error:
        payload["error"] = error
    return payload


def _main_path_contract(
    *,
    plan: DecisionPlan,
    final_input_selection: dict[str, Any] | None,
    run_context_summary: dict[str, Any] | None,
    config: "Config | None",
) -> dict[str, Any]:
    selection = final_input_selection if isinstance(final_input_selection, dict) else {}
    context = run_context_summary if isinstance(run_context_summary, dict) else {}
    side_effect_policy = context.get("side_effect_policy")
    if not isinstance(side_effect_policy, dict):
        side_effect_policy = {}
    mode = str(selection.get("mode") or "legacy_prompt")
    audit_only = mode.endswith("_audit_only") or selection.get("production_final_input") is False
    candidate_sidecar_mode = (
        str(config.decision.candidate_sidecar_mode)
        if config is not None
        else str(selection.get("candidate_sidecar_mode") or "unknown")
    )
    auto_order_enabled = (
        config.trading.auto_order_enabled is True
        if config is not None
        else side_effect_policy.get("auto_order_enabled") is True
    )
    return {
        "schema_version": "2026-07-09.main-path-contract.v1",
        "runtime_role": "production_blocking_audit" if audit_only else "production_main",
        "proof_level": _proof_level_for_contract(config=config, audit_only=audit_only),
        "production_success": False,
        "hosted_proof_required": True,
        "does_not_prove": "hosted_prod_actionable",
        "final_input_contract": {
            "mode": mode,
            "production_final_input_mode": mode,
            "legacy_prompt_required": mode == "legacy_prompt" and not audit_only,
            "candidate_sidecar_mode": candidate_sidecar_mode,
            "candidate_sidecar_can_replace_final_input": False,
        },
        "manual_only": {
            "manual_execution_required": plan.manual_execution_required is True,
            "auto_order_enabled": auto_order_enabled,
            "order_submission": "disabled",
        },
        "query_contract": {
            "mode": "audit_note",
            "drives_final_input": False,
            "drives_execution_facts": False,
        },
    }


def _proof_level_for_contract(*, config: "Config | None", audit_only: bool) -> str:
    if audit_only:
        return "audit-sidecar-contract"
    if config is None:
        return "local-main-flow-contract"
    if config.decision.engine == "fixture":
        return "fixture"
    if _is_mock_decision_config(config):
        return "mock"
    if (
        config.decision.engine == "openai_compatible"
        and config.market_data.provider == "okx_public"
        and config.notification.enabled is True
        and config.macro_event.provider == "no_active_event"
        and config.decision.final_input_mode == "legacy_prompt"
        and config.decision.candidate_sidecar_mode == "disabled"
        and config.workflow.execution_mode == "legacy_baseline"
        and config.trading.manual_execution_required is True
        and config.trading.auto_order_enabled is False
    ):
        return "production-intent-contract"
    return "local-main-flow-contract"


def _is_mock_decision_config(config: "Config") -> bool:
    model = str(config.decision.openai_model or "").strip().lower()
    base_url = str(config.decision.openai_base_url or "").strip().lower()
    return (
        model.startswith("mock-")
        or "localhost" in base_url
        or "127.0.0.1" in base_url
    )


def run_context_for_audit(run_context_summary: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "run_id",
        "run_type",
        "symbol",
        "query_text",
        "query_semantics",
        "horizon",
        "session_id",
        "manual_only",
        "position",
        "risk_mode",
        "side_effect_policy",
        "artifacts",
    }
    return {key: run_context_summary.get(key) for key in sorted(allowed_keys) if key in run_context_summary}


def _audit_only_namespace(
    *,
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any] | None,
    pre_final_decision_input: dict[str, Any] | None,
    candidate_audit: dict[str, Any],
) -> dict[str, Any]:
    mirrored_fields = [
        "evidence_packets",
        "facts_gate",
        "harness_validation",
        "agent_contributions",
        "shadow_swarm_audit",
        "pre_final_decision_input",
        "decision_input_candidate",
        "candidate_final_decision",
        "replayable_input_candidate",
        "lead_synthesis_artifact",
        "gate_candidate",
        "plan_semantic_candidate",
        "final_decision_switch_readiness",
    ]
    return {
        "schema_version": 1,
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "mirrored_legacy_fields": mirrored_fields,
        "evidence_packets": audit_payload["evidence_packets"],
        "facts_gate": audit_payload["facts_gate"],
        "harness_validation": audit_payload["harness_validation"],
        "agent_contributions": audit_payload["agent_contributions"],
        "shadow_swarm_audit": shadow_swarm_audit,
        "pre_final_decision_input": pre_final_decision_input,
        "decision_input_candidate": candidate_audit.get("decision_input_candidate"),
        "candidate_final_decision": candidate_audit.get("candidate_final_decision"),
        "replayable_input_candidate": candidate_audit.get("replayable_input_candidate"),
        "lead_synthesis_artifact": candidate_audit.get("lead_synthesis_artifact"),
        "gate_candidate": candidate_audit.get("gate_candidate"),
        "plan_semantic_candidate": candidate_audit.get("plan_semantic_candidate"),
        "final_decision_switch_readiness": candidate_audit.get("final_decision_switch_readiness"),
    }


def _legacy_prompt_lifecycle(final_input_selection: dict[str, Any] | None) -> dict[str, Any]:
    selection = final_input_selection if isinstance(final_input_selection, dict) else {}
    mode = selection.get("mode")
    if mode == "decision_input":
        return {
            "status": "replay_and_comparison_only",
            "selected_as_final_input": False,
            "allowed_uses": ["replay_baseline", "legacy_comparison"],
            "replacement_target": "decision_input",
        }
    if mode == "legacy_prompt" and selection.get("fallback_from_mode") == "decision_input":
        lifecycle = {
            "status": "decision_input_fallback",
            "selected_as_final_input": True,
            "allowed_uses": ["decision_input_fallback", "replay_baseline", "legacy_comparison"],
            "replacement_target": "decision_input",
        }
        if selection.get("fallback_reason"):
            lifecycle["fallback_reason"] = selection.get("fallback_reason")
        if isinstance(selection.get("fallback_blocking_reasons"), list):
            lifecycle["fallback_blocking_reasons"] = [
                str(reason)
                for reason in selection.get("fallback_blocking_reasons") or []
            ]
        return lifecycle
    return {
        "status": "legacy_primary_until_switch_review",
        "selected_as_final_input": True,
        "allowed_uses": [
            "production_primary_until_switch_review",
            "replay_baseline",
            "legacy_comparison",
        ],
        "replacement_target": "decision_input",
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
        "risk_rule_hits": [hit.to_public_dict() for hit in verdict.rule_hits],
    }


def _evidence_to_claims(research_audit: ResearchAudit | None) -> list[dict[str, Any]]:
    if not research_audit:
        return []
    mappings: list[dict[str, Any]] = []
    for name, results in sorted(research_audit.results.items()):
        for index, result in enumerate(results[:3]):
            mappings.append(
                {
                    "claim": f"{name} supplemental context",
                    "evidence_ref": f"research.results.{name}[{index}]",
                    "source": result.source,
                    "url": result.url,
                    "relation": "context",
                }
            )
    return mappings


def _redaction_policy(frozen_input: FrozenInput | None = None) -> dict[str, Any]:
    return {
        "full_prompt_saved": bool(frozen_input),
        "full_completion_saved": True,
        "llm_interactions_store": "hash_summary_and_sanitized_payload",
        "hidden_reasoning_saved": False,
        "frozen_input_saved": bool(frozen_input),
        "frozen_input_schema_version": frozen_input.schema_version if frozen_input else None,
    }
