from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .final_input import select_final_input


@dataclass(frozen=True)
class FinalDecisionStepResult:
    raw_decision: str
    final_input_selection: dict[str, Any]

    @property
    def output_summary(self) -> dict[str, int]:
        return {"raw_decision_chars": len(str(self.raw_decision))}


def run_final_decision_step(
    *,
    decision_engine: Any,
    final_input_mode: str,
    legacy_prompt_packet: dict[str, Any],
    decision_input_candidate: dict[str, Any] | None = None,
    switch_readiness: dict[str, Any] | None = None,
) -> FinalDecisionStepResult:
    selected_final_input = select_final_input(
        final_input_mode=final_input_mode,
        legacy_prompt_packet=legacy_prompt_packet,
        decision_input_candidate=decision_input_candidate,
        switch_readiness=switch_readiness,
    )
    raw_decision = decision_engine.run(selected_final_input.input_payload)
    return FinalDecisionStepResult(
        raw_decision=str(raw_decision),
        final_input_selection=selected_final_input.to_public_dict(),
    )
