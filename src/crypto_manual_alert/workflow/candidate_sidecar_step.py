from __future__ import annotations

from typing import Any

from crypto_manual_alert.decision.candidate_final_decision import run_candidate_final_decision_sidecar
from crypto_manual_alert.decision.pre_final_input_gate import evaluate_pre_final_input_gate


def run_candidate_sidecar_step(
    *,
    candidate_decision_engine: Any | None,
    pre_final_decision_input: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Run the audit-only candidate final sidecar when explicitly configured."""

    if candidate_decision_engine is None:
        return None
    input_gate = evaluate_pre_final_input_gate(pre_final_decision_input)
    return run_candidate_final_decision_sidecar(
        decision_engine=candidate_decision_engine,
        pre_final_decision_input=pre_final_decision_input,
        input_gate=input_gate,
    )
