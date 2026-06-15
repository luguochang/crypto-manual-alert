from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


LONG_OPENING_ACTIONS = {"open long", "trigger long", "flip short to long"}
SHORT_OPENING_ACTIONS = {"open short", "trigger short", "flip long to short"}
CHECKED_FIELDS = ["main_action", "entry_trigger", "stop_price", "target_1", "target_2"]


@dataclass(frozen=True)
class PlanSemanticCandidateResult:
    """Audit-only semantic checks for entry, stop, and target geometry."""

    decision_effect: str
    passed: bool
    severity: str
    violations: list[dict[str, Any]] = field(default_factory=list)
    checked_fields: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "decision_effect": self.decision_effect,
            "passed": self.passed,
            "severity": self.severity,
            "violations": [dict(item) for item in self.violations],
            "checked_fields": list(self.checked_fields),
        }


def evaluate_plan_semantic_candidate(*, legacy_plan: dict[str, Any]) -> PlanSemanticCandidateResult:
    action = str(legacy_plan.get("main_action") or "")
    entry = _as_float(legacy_plan.get("entry_trigger"))
    stop = _as_float(legacy_plan.get("stop_price"))
    target_1 = _as_float(legacy_plan.get("target_1"))
    target_2 = _as_float(legacy_plan.get("target_2"))

    violations: list[dict[str, Any]] = []
    if action in LONG_OPENING_ACTIONS:
        _check_opening_required_fields(
            violations,
            entry=entry,
            stop=stop,
            target_1=target_1,
            invalidation=legacy_plan.get("invalidation"),
        )
        _check_long_geometry(violations, entry=entry, stop=stop, target_1=target_1, target_2=target_2)
    elif action in SHORT_OPENING_ACTIONS:
        _check_opening_required_fields(
            violations,
            entry=entry,
            stop=stop,
            target_1=target_1,
            invalidation=legacy_plan.get("invalidation"),
        )
        _check_short_geometry(violations, entry=entry, stop=stop, target_1=target_1, target_2=target_2)

    passed = not violations
    return PlanSemanticCandidateResult(
        decision_effect="none",
        passed=passed,
        severity="ok" if passed else "hard_fail",
        violations=violations,
        checked_fields=CHECKED_FIELDS,
    )


def failed_plan_semantic_candidate(exc: Exception) -> dict[str, Any]:
    return {
        "decision_effect": "none",
        "passed": False,
        "severity": "hard_fail",
        "violations": [
            {
                "rule_id": "plan_semantic.build_failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        ],
        "checked_fields": CHECKED_FIELDS,
    }


def _check_opening_required_fields(
    violations: list[dict[str, Any]],
    *,
    entry: float | None,
    stop: float | None,
    target_1: float | None,
    invalidation: Any,
) -> None:
    if entry is None:
        violations.append(_violation("plan_semantic.opening_entry_required", "opening action requires entry_trigger"))
    if stop is None:
        violations.append(_violation("plan_semantic.opening_stop_required", "opening action requires stop_price"))
    if target_1 is None:
        violations.append(_violation("plan_semantic.opening_target_required", "opening action requires target_1"))
    if not str(invalidation or "").strip():
        violations.append(
            _violation("plan_semantic.opening_invalidation_required", "opening action requires invalidation")
        )


def _check_long_geometry(
    violations: list[dict[str, Any]],
    *,
    entry: float | None,
    stop: float | None,
    target_1: float | None,
    target_2: float | None,
) -> None:
    if entry is not None and stop is not None and stop >= entry:
        violations.append(
            _violation(
                "plan_semantic.long_stop_not_below_entry",
                "long stop_price must be below entry_trigger",
            )
        )
    if entry is not None and target_1 is not None and target_1 <= entry:
        violations.append(
            _violation(
                "plan_semantic.long_target_not_above_entry",
                "long target_1 must be above entry_trigger",
            )
        )
    if target_1 is not None and target_2 is not None and target_2 < target_1:
        violations.append(
            _violation(
                "plan_semantic.long_target_order_invalid",
                "long target_2 must be greater than or equal to target_1",
            )
        )


def _check_short_geometry(
    violations: list[dict[str, Any]],
    *,
    entry: float | None,
    stop: float | None,
    target_1: float | None,
    target_2: float | None,
) -> None:
    if entry is not None and stop is not None and stop <= entry:
        violations.append(
            _violation(
                "plan_semantic.short_stop_not_above_entry",
                "short stop_price must be above entry_trigger",
            )
        )
    if entry is not None and target_1 is not None and target_1 >= entry:
        violations.append(
            _violation(
                "plan_semantic.short_target_not_below_entry",
                "short target_1 must be below entry_trigger",
            )
        )
    if target_1 is not None and target_2 is not None and target_2 > target_1:
        violations.append(
            _violation(
                "plan_semantic.short_target_order_invalid",
                "short target_2 must be less than or equal to target_1",
            )
        )


def _violation(rule_id: str, message: str) -> dict[str, Any]:
    return {"rule_id": rule_id, "severity": "hard_fail", "message": message}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
