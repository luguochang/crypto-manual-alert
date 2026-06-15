from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.decision.decision_input import required_dropped_contributions, worker_hard_block_contributions


REQUIRED_SHADOW_WORKER_COUNT = 7


@dataclass(frozen=True)
class FinalDecisionSwitchReadiness:
    """Audit-only readiness check for switching FinalDecisionAgent input."""

    ready: bool
    decision_effect: str
    blocking_reasons: list[str]
    required_shadow_worker_count: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "decision_effect": self.decision_effect,
            "blocking_reasons": list(self.blocking_reasons),
            "required_shadow_worker_count": self.required_shadow_worker_count,
        }


def evaluate_final_decision_switch_readiness(
    *,
    decision_input_candidate: dict[str, Any],
    replayable_input_candidate: dict[str, Any],
    gate_candidate: dict[str, Any],
    plan_semantic_candidate: dict[str, Any],
    shadow_swarm_audit: dict[str, Any],
) -> FinalDecisionSwitchReadiness:
    reasons: list[str] = []
    if not _validation_passed(decision_input_candidate):
        reasons.append("decision_input_candidate_invalid")
    if not _validation_passed(replayable_input_candidate):
        reasons.append("replayable_input_candidate_invalid")
    if gate_candidate.get("passed") is not True:
        reasons.append("candidate_gate_failed")
    if plan_semantic_candidate.get("passed") is not True:
        reasons.append("plan_semantic_candidate_failed")
    harness_validation = shadow_swarm_audit.get("harness_validation") if isinstance(shadow_swarm_audit, dict) else None
    if not isinstance(harness_validation, dict) or harness_validation.get("passed") is not True:
        reasons.append("shadow_swarm_harness_failed")

    lead_synthesis = decision_input_candidate.get("lead_synthesis") or {}
    dropped = required_dropped_contributions(
        lead_synthesis=lead_synthesis,
        contribution_refs=list(decision_input_candidate.get("contribution_refs") or []),
    )
    if dropped:
        reasons.append("required_worker_missing_or_failed")
    hard_blocks = worker_hard_block_contributions(
        list(decision_input_candidate.get("contribution_refs") or [])
    )
    if hard_blocks:
        reasons.append("worker_hard_block")

    coverage = replayable_input_candidate.get("coverage") or {}
    if coverage.get("has_legacy_frozen_input") is not True:
        reasons.append("legacy_frozen_input_missing")
    if coverage.get("has_decision_input_candidate") is not True:
        reasons.append("decision_input_artifact_missing")
    if int(coverage.get("worker_artifact_count") or 0) < REQUIRED_SHADOW_WORKER_COUNT:
        reasons.append("worker_artifact_coverage_incomplete")

    deduped = list(dict.fromkeys(reasons))
    return FinalDecisionSwitchReadiness(
        ready=not deduped,
        decision_effect="none",
        blocking_reasons=deduped,
        required_shadow_worker_count=REQUIRED_SHADOW_WORKER_COUNT,
    )


def failed_final_decision_switch_readiness(exc: Exception) -> dict[str, Any]:
    return {
        "ready": False,
        "decision_effect": "none",
        "blocking_reasons": ["switch_readiness_check_failed"],
        "required_shadow_worker_count": REQUIRED_SHADOW_WORKER_COUNT,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }


def _validation_passed(payload: dict[str, Any]) -> bool:
    validation = payload.get("validation") if isinstance(payload, dict) else None
    return isinstance(validation, dict) and validation.get("passed") is True
