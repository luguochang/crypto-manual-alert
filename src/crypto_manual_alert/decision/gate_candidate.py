from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GateCandidateResult:
    """Audit-only comparison between legacy plan and candidate gates."""

    decision_effect: str
    passed: bool
    severity: str
    violations: list[dict[str, Any]] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "decision_effect": self.decision_effect,
            "passed": self.passed,
            "severity": self.severity,
            "violations": [dict(item) for item in self.violations],
            "blocked_actions": list(self.blocked_actions),
            "missing_facts": list(self.missing_facts),
        }


def evaluate_gate_candidate(
    *, decision_input_candidate: dict[str, Any], legacy_plan: dict[str, Any]
) -> GateCandidateResult:
    violations: list[dict[str, Any]] = []
    blocked_actions: list[str] = []
    action = str(legacy_plan.get("main_action") or "")
    allowed_actions = set(str(item) for item in decision_input_candidate.get("effective_allowed_actions") or [])
    if action and action not in allowed_actions:
        blocked_actions.append(action)
        violations.append(
            {
                "rule_id": "candidate.action_not_allowed",
                "severity": "hard_fail",
                "message": f"legacy action {action!r} is outside candidate effective_allowed_actions",
            }
        )

    probability = _as_float(legacy_plan.get("probability"))
    confidence_policy = decision_input_candidate.get("confidence_policy") or {}
    max_probability = _as_float(confidence_policy.get("max_probability"))
    if probability is not None and max_probability is not None and probability > max_probability:
        violations.append(
            {
                "rule_id": "candidate.confidence_cap_exceeded",
                "severity": "hard_fail",
                "message": f"legacy probability {probability} exceeds candidate cap {max_probability}",
                "cap_reasons": list(confidence_policy.get("cap_reasons") or []),
            }
        )

    passed = not violations
    return GateCandidateResult(
        decision_effect="none",
        passed=passed,
        severity="ok" if passed else "hard_fail",
        violations=violations,
        blocked_actions=blocked_actions,
        missing_facts=[str(item) for item in decision_input_candidate.get("missing_facts") or []],
    )


def failed_gate_candidate(exc: Exception) -> dict[str, Any]:
    return {
        "decision_effect": "none",
        "passed": False,
        "severity": "hard_fail",
        "violations": [
            {
                "rule_id": "gate_candidate.build_failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        ],
        "blocked_actions": [],
        "missing_facts": [],
    }


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

