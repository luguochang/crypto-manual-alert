from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.decision.final_prompt import build_legacy_final_prompt_packet
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.decision.frozen_input import FrozenInput, freeze_decision_prompt_packet
from crypto_manual_alert.research_pipeline import ResearchAudit


@dataclass(frozen=True)
class LegacyFinalInputStepResult:
    """Legacy final input packet and frozen replay input.

    This step does not choose between legacy prompt and DecisionInput. It only
    prepares the currently allowed legacy prompt packet and freezes the exact
    payload sent to FinalDecisionAgent.
    """

    prompt_packet: dict[str, Any]
    frozen_input: FrozenInput
    prompt_summary: dict[str, Any]
    freeze_summary: dict[str, Any]


def build_legacy_final_input_step(
    *,
    trace_id: str,
    skill_runtime: Any,
    skill_context: Any,
    snapshot: MarketSnapshot,
    research_audit: ResearchAudit | None,
) -> LegacyFinalInputStepResult:
    prompt_packet = build_legacy_final_prompt_packet(
        skill_runtime=skill_runtime,
        snapshot=snapshot,
        skill_context=skill_context,
        research_audit=research_audit,
    )
    frozen_input = freeze_decision_prompt_packet(prompt_packet, source_trace_id=trace_id)
    return LegacyFinalInputStepResult(
        prompt_packet=prompt_packet,
        frozen_input=frozen_input,
        prompt_summary={"keys": sorted(prompt_packet)},
        freeze_summary={
            "frozen_input_hash": frozen_input.frozen_input_hash,
            "schema_version": frozen_input.schema_version,
            "kind": frozen_input.kind,
            "top_level_keys": frozen_input.public_summary["top_level_keys"],
        },
    )
