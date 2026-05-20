from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SideEffectGateResult:
    """Side-effect permission result for production persistence.

    The gate reads the immutable run-context policy summary and fails closed
    when the policy is missing. It does not write journal rows, send
    notifications, or alter risk verdicts.
    """

    allow_production_journal_write: bool
    allow_notification_intent: bool
    skip_reason: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "allow_production_journal_write": self.allow_production_journal_write,
            "allow_notification_intent": self.allow_notification_intent,
            "skip_reason": self.skip_reason,
        }


def evaluate_side_effect_gate(run_context_summary: dict[str, Any] | None) -> SideEffectGateResult:
    policy = run_context_summary.get("side_effect_policy") if isinstance(run_context_summary, dict) else None
    if not isinstance(policy, dict):
        return SideEffectGateResult(
            allow_production_journal_write=False,
            allow_notification_intent=False,
            skip_reason="side_effect_policy_missing",
        )
    return SideEffectGateResult(
        allow_production_journal_write=bool(policy.get("allow_production_journal_write")),
        allow_notification_intent=bool(policy.get("allow_notification_intent")),
        skip_reason="side_effect_policy",
    )
