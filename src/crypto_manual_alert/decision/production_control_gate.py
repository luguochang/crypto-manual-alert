from __future__ import annotations

from typing import Any

from crypto_manual_alert.decision.decision_input import required_dropped_contributions, worker_hard_block_contributions
from crypto_manual_alert.domain import OPENING_ACTIONS, DecisionPlan, RiskVerdict, RuleHit


def check_production_control_gate(
    plan: DecisionPlan,
    *,
    candidate_audit: dict[str, Any],
    shadow_swarm_audit: dict[str, Any] | None,
) -> RiskVerdict:
    """Promote selected candidate audit failures into production risk rules.

    This gate does not change the final LLM input and does not decide trades.
    It only blocks executable actions when structured orchestration artifacts
    show that the action is outside policy, over confidence cap, semantically
    invalid, or based on failed required worker evidence.
    """

    reasons: list[str] = []
    warnings: list[str] = []
    rule_hits: list[RuleHit] = []
    executable_action = plan.main_action in OPENING_ACTIONS

    _apply_candidate_gate(
        plan,
        candidate_audit.get("gate_candidate") or {},
        executable_action=executable_action,
        reasons=reasons,
        warnings=warnings,
        rule_hits=rule_hits,
    )
    _apply_semantic_gate(
        plan,
        candidate_audit.get("plan_semantic_candidate") or {},
        reasons,
        warnings,
        rule_hits,
    )
    _apply_worker_readiness(
        executable_action=executable_action,
        decision_input_candidate=candidate_audit.get("decision_input_candidate") or {},
        shadow_swarm_audit=shadow_swarm_audit or {},
        reasons=reasons,
        warnings=warnings,
        rule_hits=rule_hits,
    )

    return RiskVerdict(
        allowed=not any(hit.blocking for hit in rule_hits),
        reasons=reasons,
        warnings=warnings,
        rule_hits=rule_hits,
    )


def _apply_candidate_gate(
    plan: DecisionPlan,
    gate_candidate: dict[str, Any],
    *,
    executable_action: bool,
    reasons: list[str],
    warnings: list[str],
    rule_hits: list[RuleHit],
) -> None:
    violations = gate_candidate.get("violations") or []
    blocked_actions = {str(item) for item in gate_candidate.get("blocked_actions") or []}
    for violation in violations:
        if not isinstance(violation, dict):
            continue
        rule_id = str(violation.get("rule_id") or "candidate.unknown")
        message = str(violation.get("message") or rule_id)
        blocking = executable_action and (
            rule_id == "candidate.confidence_cap_exceeded" or plan.main_action in blocked_actions
        )
        _append_hit(
            reasons,
            warnings,
            rule_hits,
            rule_id=f"production_control.{rule_id}",
            message=message,
            blocking=blocking,
            evidence_refs=["gate_candidate", "decision_input_candidate"],
            details={
                "legacy_action": plan.main_action,
                "blocked_actions": sorted(blocked_actions),
                "missing_facts": list(gate_candidate.get("missing_facts") or []),
                "cap_reasons": list(violation.get("cap_reasons") or []),
            },
        )


def _apply_semantic_gate(
    plan: DecisionPlan,
    plan_semantic_candidate: dict[str, Any],
    reasons: list[str],
    warnings: list[str],
    rule_hits: list[RuleHit],
) -> None:
    for violation in plan_semantic_candidate.get("violations") or []:
        if not isinstance(violation, dict):
            continue
        rule_id = str(violation.get("rule_id") or "plan_semantic.unknown")
        message = str(violation.get("message") or rule_id)
        _append_hit(
            reasons,
            warnings,
            rule_hits,
            rule_id=f"production_control.{rule_id}",
            message=message,
            blocking=plan.main_action in OPENING_ACTIONS,
            evidence_refs=["plan_semantic_candidate"],
            details={"legacy_action": plan.main_action},
        )


def _apply_worker_readiness(
    *,
    executable_action: bool,
    decision_input_candidate: dict[str, Any],
    shadow_swarm_audit: dict[str, Any],
    reasons: list[str],
    warnings: list[str],
    rule_hits: list[RuleHit],
) -> None:
    lead_synthesis = decision_input_candidate.get("lead_synthesis") or {}
    dropped = required_dropped_contributions(
        lead_synthesis=lead_synthesis,
        contribution_refs=list(decision_input_candidate.get("contribution_refs") or []),
    )
    if dropped:
        _append_hit(
            reasons,
            warnings,
            rule_hits,
            rule_id="production_control.required_worker_missing_or_failed",
            message="required worker contribution missing or failed",
            blocking=executable_action,
            evidence_refs=["decision_input_candidate.lead_synthesis"],
            details={"dropped_contributions": dropped},
        )
    hard_blocks = worker_hard_block_contributions(
        list(decision_input_candidate.get("contribution_refs") or []),
        include_llm_tool_shadow_worker=False,
    )
    if hard_blocks:
        _append_hit(
            reasons,
            warnings,
            rule_hits,
            rule_id="production_control.worker_hard_block",
            message="worker contribution reported a hard block",
            blocking=executable_action,
            evidence_refs=["decision_input_candidate.contribution_refs"],
            details={"worker_hard_blocks": hard_blocks},
        )

    harness_validation = shadow_swarm_audit.get("harness_validation") if isinstance(shadow_swarm_audit, dict) else None
    if not isinstance(harness_validation, dict) or harness_validation.get("passed") is not True:
        message = "shadow swarm harness validation failed"
        if not executable_action:
            message = f"{message}; kept as warning because action is no trade"
        _append_hit(
            reasons,
            warnings,
            rule_hits,
            rule_id="production_control.shadow_swarm_harness_failed",
            message=message,
            blocking=executable_action,
            evidence_refs=["shadow_swarm_audit.harness_validation"],
            details={"harness_validation": harness_validation or {}},
        )


def _append_hit(
    reasons: list[str],
    warnings: list[str],
    rule_hits: list[RuleHit],
    *,
    rule_id: str,
    message: str,
    blocking: bool,
    evidence_refs: list[str],
    details: dict[str, Any],
) -> None:
    if blocking:
        reasons.append(message)
    else:
        warnings.append(message)
    rule_hits.append(
        RuleHit(
            rule_id=rule_id,
            passed=not blocking,
            severity="critical" if blocking else "medium",
            message=message,
            blocking=blocking,
            evidence_refs=evidence_refs,
            details=details,
        )
    )
