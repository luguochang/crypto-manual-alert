from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any


@dataclass(frozen=True)
class FinalInputSelection:
    mode: str
    input_payload: dict[str, Any]
    source_ref: str
    decision_effect: str
    readiness_ready: bool
    fallback_reason: str | None = None
    fallback_from_mode: str | None = None
    fallback_blocking_reasons: list[str] | None = None
    candidate_input_ref: str | None = None
    candidate_input_hash: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        public = {
            "mode": self.mode,
            "source_ref": self.source_ref,
            "decision_effect": self.decision_effect,
            "readiness_ready": self.readiness_ready,
        }
        if self.fallback_reason is not None:
            public["fallback_reason"] = self.fallback_reason
        if self.fallback_from_mode is not None:
            public["fallback_from_mode"] = self.fallback_from_mode
        if self.fallback_blocking_reasons is not None:
            public["fallback_blocking_reasons"] = list(self.fallback_blocking_reasons)
        if self.candidate_input_ref is not None:
            public["candidate_input_ref"] = self.candidate_input_ref
        if self.candidate_input_hash is not None:
            public["candidate_input_hash"] = self.candidate_input_hash
        return public


def select_final_input(
    *,
    final_input_mode: str,
    legacy_prompt_packet: dict[str, Any],
    decision_input_candidate: dict[str, Any] | None,
    switch_readiness: dict[str, Any] | None,
) -> FinalInputSelection:
    readiness_ready = bool((switch_readiness or {}).get("ready"))
    if final_input_mode == "legacy_prompt":
        return FinalInputSelection(
            mode="legacy_prompt",
            input_payload=legacy_prompt_packet,
            source_ref="legacy_prompt_packet",
            decision_effect="production_final_input",
            readiness_ready=False,
        )
    if final_input_mode == "decision_input":
        return _select_decision_input(
            legacy_prompt_packet=legacy_prompt_packet,
            decision_input_candidate=decision_input_candidate,
            readiness_ready=readiness_ready,
            switch_readiness=switch_readiness or {},
        )
    raise ValueError(f"unsupported final_input_mode: {final_input_mode}")


def _select_decision_input(
    *,
    legacy_prompt_packet: dict[str, Any],
    decision_input_candidate: dict[str, Any] | None,
    readiness_ready: bool,
    switch_readiness: dict[str, Any],
) -> FinalInputSelection:
    candidate_input_ref = _candidate_field(decision_input_candidate, "input_ref")
    candidate_input_hash = _candidate_field(decision_input_candidate, "input_hash")
    if not readiness_ready:
        reasons = switch_readiness.get("blocking_reasons") or []
        return _fallback_to_legacy_prompt(
            legacy_prompt_packet,
            fallback_reason="decision_input_not_ready",
            blocking_reasons=[str(reason) for reason in reasons],
            candidate_input_ref=candidate_input_ref,
            candidate_input_hash=candidate_input_hash,
        )
    if not isinstance(decision_input_candidate, dict):
        return _fallback_to_legacy_prompt(
            legacy_prompt_packet,
            fallback_reason="decision_input_candidate_missing",
            blocking_reasons=[],
            candidate_input_ref=None,
            candidate_input_hash=None,
        )
    validation = decision_input_candidate.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        return _fallback_to_legacy_prompt(
            legacy_prompt_packet,
            fallback_reason="decision_input_candidate_invalid",
            blocking_reasons=_validation_blocking_reasons(validation),
            candidate_input_ref=candidate_input_ref,
            candidate_input_hash=candidate_input_hash,
        )
    source_ref = decision_input_candidate.get("input_ref")
    source_hash = decision_input_candidate.get("input_hash")
    if not source_ref or not source_hash:
        return _fallback_to_legacy_prompt(
            legacy_prompt_packet,
            fallback_reason="decision_input_candidate_ref_missing",
            blocking_reasons=[],
            candidate_input_ref=candidate_input_ref,
            candidate_input_hash=candidate_input_hash,
        )

    input_payload = copy.deepcopy(decision_input_candidate)
    input_payload["mode"] = "production_final_input"
    input_payload["decision_effect"] = "production_final_input"
    input_payload["source_candidate_ref"] = source_ref
    input_payload["source_candidate_hash"] = source_hash
    return FinalInputSelection(
        mode="decision_input",
        input_payload=input_payload,
        source_ref=str(source_ref),
        decision_effect="production_final_input",
        readiness_ready=readiness_ready,
    )


def _fallback_to_legacy_prompt(
    legacy_prompt_packet: dict[str, Any],
    *,
    fallback_reason: str,
    blocking_reasons: list[str],
    candidate_input_ref: str | None,
    candidate_input_hash: str | None,
) -> FinalInputSelection:
    return FinalInputSelection(
        mode="legacy_prompt",
        input_payload=legacy_prompt_packet,
        source_ref="legacy_prompt_packet",
        decision_effect="production_final_input",
        readiness_ready=False,
        fallback_reason=fallback_reason,
        fallback_from_mode="decision_input",
        fallback_blocking_reasons=blocking_reasons,
        candidate_input_ref=candidate_input_ref,
        candidate_input_hash=candidate_input_hash,
    )


def _candidate_field(candidate: dict[str, Any] | None, field_name: str) -> str | None:
    if not isinstance(candidate, dict):
        return None
    value = candidate.get(field_name)
    return str(value) if value else None


def _validation_blocking_reasons(validation: Any) -> list[str]:
    if not isinstance(validation, dict):
        return []
    violations = validation.get("violations")
    if not isinstance(violations, list):
        return []
    return [
        str(violation.get("rule_id"))
        for violation in violations
        if isinstance(violation, dict) and violation.get("rule_id")
    ]
