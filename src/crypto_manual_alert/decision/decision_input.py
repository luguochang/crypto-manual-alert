from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from crypto_manual_alert.artifacts.contributions import (
    contribution_safety_ref_fields,
    tool_call_artifact_ref_fields,
)
from crypto_manual_alert.decision.decision_input_policy import (
    REQUIRED_SHADOW_WORKER_AGENTS,
    blocked_actions as _blocked_actions,
    confidence_policy as _confidence_policy,
    conflicts as _conflicts,
    is_execution_blocked as _is_execution_blocked,
    missing_facts as _missing_facts,
    required_dropped_contributions,
    validation_summary as _validation_summary,
    worker_hard_block_contributions,
)


CANONICAL_ACTIONS: tuple[str, ...] = (
    "open long",
    "open short",
    "hold long",
    "hold short",
    "close long",
    "close short",
    "flip long to short",
    "flip short to long",
    "trigger long",
    "trigger short",
    "no trade",
)

@dataclass(frozen=True)
class DecisionInputCandidate:
    """Audit-only candidate for the future DecisionInput path.

    This object does not feed the FinalDecisionAgent yet. It records the
    evidence refs, contribution refs, action clipping, and lead synthesis needed
    to compare the future path against the current legacy prompt path.
    """

    schema_version: int
    mode: str
    decision_effect: str
    trace_id: str
    symbol: str
    input_ref: str
    input_hash: str
    evidence_refs: list[dict[str, Any]]
    facts_gate: dict[str, Any]
    contribution_refs: list[dict[str, Any]]
    lead_synthesis: dict[str, Any]
    effective_allowed_actions: list[str]
    blocked_actions: list[dict[str, str]]
    execution_mode: str
    confidence_policy: dict[str, Any]
    missing_facts: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    legacy_decision_ref: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "decision_effect": self.decision_effect,
            "trace_id": self.trace_id,
            "symbol": self.symbol,
            "input_ref": self.input_ref,
            "input_hash": self.input_hash,
            "evidence_refs": self.evidence_refs,
            "facts_gate": self.facts_gate,
            "contribution_refs": self.contribution_refs,
            "lead_synthesis": self.lead_synthesis,
            "effective_allowed_actions": self.effective_allowed_actions,
            "blocked_actions": self.blocked_actions,
            "execution_mode": self.execution_mode,
            "confidence_policy": self.confidence_policy,
            "missing_facts": list(self.missing_facts),
            "conflicts": list(self.conflicts),
            "legacy_decision_ref": self.legacy_decision_ref,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class PreFinalDecisionInput:
    """Structured input candidate that can be built before FinalDecisionAgent.

    It contains only normalized evidence references, worker contribution refs,
    Lead synthesis, and action/control policies. It does not include the legacy
    final plan, raw evidence values, raw snippets, or risk verdict.
    """

    schema_version: int
    mode: str
    decision_effect: str
    trace_id: str
    symbol: str
    input_ref: str
    input_hash: str
    evidence_refs: list[dict[str, Any]]
    facts_gate: dict[str, Any]
    contribution_refs: list[dict[str, Any]]
    lead_synthesis: dict[str, Any]
    effective_allowed_actions: list[str]
    blocked_actions: list[dict[str, str]]
    execution_mode: str
    confidence_policy: dict[str, Any]
    missing_facts: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "decision_effect": self.decision_effect,
            "trace_id": self.trace_id,
            "symbol": self.symbol,
            "input_ref": self.input_ref,
            "input_hash": self.input_hash,
            "evidence_refs": self.evidence_refs,
            "facts_gate": self.facts_gate,
            "contribution_refs": self.contribution_refs,
            "lead_synthesis": self.lead_synthesis,
            "effective_allowed_actions": self.effective_allowed_actions,
            "blocked_actions": self.blocked_actions,
            "execution_mode": self.execution_mode,
            "confidence_policy": self.confidence_policy,
            "missing_facts": list(self.missing_facts),
            "conflicts": list(self.conflicts),
            "validation": self.validation,
        }


def build_pre_final_decision_input(
    *,
    symbol: str,
    trace_id: str,
    evidence_packets: list[dict[str, Any]],
    facts_gate: dict[str, Any],
    agent_contributions: list[dict[str, Any]],
    lead_synthesis: dict[str, Any],
) -> PreFinalDecisionInput:
    evidence_refs = [_evidence_ref(packet) for packet in evidence_packets]
    contribution_refs = [_contribution_ref(contribution) for contribution in agent_contributions]
    missing_facts = _missing_facts(facts_gate, agent_contributions)
    conflicts = _conflicts(facts_gate, agent_contributions)
    blocked_actions = _blocked_actions(facts_gate)
    blocked_action_names = {item["action"] for item in blocked_actions}
    effective_allowed_actions = [
        action for action in CANONICAL_ACTIONS if action not in blocked_action_names
    ]
    confidence_policy = _confidence_policy(evidence_packets, agent_contributions, facts_gate)
    execution_mode = "blocked" if _is_execution_blocked(facts_gate) else "executable"
    validation = _validation_summary(
        evidence_refs=evidence_refs,
        contribution_refs=contribution_refs,
        facts_gate=facts_gate,
        lead_synthesis=lead_synthesis,
        missing_facts=missing_facts,
        required_agent_names=REQUIRED_SHADOW_WORKER_AGENTS,
    )
    input_ref = f"trace:{trace_id}:pre_final_decision_input"
    input_hash = _hash_payload(
        {
            "symbol": symbol,
            "evidence_refs": evidence_refs,
            "facts_gate": facts_gate,
            "contribution_refs": contribution_refs,
            "lead_synthesis": lead_synthesis,
            "effective_allowed_actions": effective_allowed_actions,
            "blocked_actions": blocked_actions,
            "confidence_policy": confidence_policy,
            "missing_facts": missing_facts,
            "conflicts": conflicts,
        }
    )
    return PreFinalDecisionInput(
        schema_version=1,
        mode="pre_final_candidate",
        decision_effect="none",
        trace_id=trace_id,
        symbol=symbol,
        input_ref=input_ref,
        input_hash=input_hash,
        evidence_refs=evidence_refs,
        facts_gate=dict(facts_gate),
        contribution_refs=contribution_refs,
        lead_synthesis=lead_synthesis,
        effective_allowed_actions=effective_allowed_actions,
        blocked_actions=blocked_actions,
        execution_mode=execution_mode,
        confidence_policy=confidence_policy,
        missing_facts=missing_facts,
        conflicts=conflicts,
        validation=validation,
    )


def build_decision_input_candidate(
    *,
    symbol: str,
    trace_id: str,
    evidence_packets: list[dict[str, Any]],
    facts_gate: dict[str, Any],
    agent_contributions: list[dict[str, Any]],
    lead_synthesis: dict[str, Any],
    legacy_plan: dict[str, Any],
    verdict: dict[str, Any],
) -> DecisionInputCandidate:
    evidence_refs = [_evidence_ref(packet) for packet in evidence_packets]
    contribution_refs = [_contribution_ref(contribution) for contribution in agent_contributions]
    missing_facts = _missing_facts(facts_gate, agent_contributions)
    conflicts = _conflicts(facts_gate, agent_contributions)
    blocked_actions = _blocked_actions(facts_gate)
    blocked_action_names = {item["action"] for item in blocked_actions}
    effective_allowed_actions = [
        action for action in CANONICAL_ACTIONS if action not in blocked_action_names
    ]
    confidence_policy = _confidence_policy(evidence_packets, agent_contributions, facts_gate)
    execution_mode = "blocked" if _is_execution_blocked(facts_gate) else "executable"
    validation = _validation_summary(
        evidence_refs=evidence_refs,
        contribution_refs=contribution_refs,
        facts_gate=facts_gate,
        lead_synthesis=lead_synthesis,
        missing_facts=missing_facts,
    )
    input_ref = f"trace:{trace_id}:decision_input_candidate"
    input_hash = _hash_payload(
        {
            "symbol": symbol,
            "evidence_refs": evidence_refs,
            "facts_gate": facts_gate,
            "contribution_refs": contribution_refs,
            "lead_synthesis": lead_synthesis,
            "effective_allowed_actions": effective_allowed_actions,
            "blocked_actions": blocked_actions,
            "confidence_policy": confidence_policy,
            "missing_facts": missing_facts,
            "conflicts": conflicts,
            "legacy_decision_ref": _legacy_decision_ref(legacy_plan, verdict),
        }
    )
    return DecisionInputCandidate(
        schema_version=1,
        mode="candidate_audit",
        decision_effect="none",
        trace_id=trace_id,
        symbol=symbol,
        input_ref=input_ref,
        input_hash=input_hash,
        evidence_refs=evidence_refs,
        facts_gate=dict(facts_gate),
        contribution_refs=contribution_refs,
        lead_synthesis=lead_synthesis,
        effective_allowed_actions=effective_allowed_actions,
        blocked_actions=blocked_actions,
        execution_mode=execution_mode,
        confidence_policy=confidence_policy,
        missing_facts=missing_facts,
        conflicts=conflicts,
        legacy_decision_ref=_legacy_decision_ref(legacy_plan, verdict),
        validation=validation,
    )


def failed_decision_input_candidate(trace_id: str, symbol: str, exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "candidate_audit",
        "decision_effect": "none",
        "trace_id": trace_id,
        "symbol": symbol,
        "error": {"type": type(exc).__name__, "message": str(exc)},
        "validation": {
            "passed": False,
            "severity": "hard_fail",
            "violations": [{"rule_id": "decision_input_candidate.build_failed"}],
        },
    }


def _evidence_ref(packet: dict[str, Any]) -> dict[str, Any]:
    ref = {
        "evidence_id": packet.get("evidence_id"),
        "data_type": packet.get("data_type"),
        "source_type": packet.get("source_type"),
        "freshness_status": packet.get("freshness_status"),
        "can_satisfy_execution_fact": bool(packet.get("can_satisfy_execution_fact")),
        "confidence_cap": packet.get("confidence_cap"),
    }
    if packet.get("fallback_used") is True:
        ref["fallback_used"] = True
        ref["fallback_reason"] = packet.get("fallback_reason")
        if packet.get("source_tier") is not None:
            ref["source_tier"] = packet.get("source_tier")
    return ref


def _contribution_ref(contribution: dict[str, Any]) -> dict[str, Any]:
    ref = {
        "contribution_id": contribution.get("contribution_id"),
        "agent_name": contribution.get("agent_name"),
        "status": contribution.get("status"),
        "required": bool(contribution.get("required")),
        "output_hash": contribution.get("output_hash"),
        "input_ref": contribution.get("input_ref"),
        "trace_ref": contribution.get("trace_ref"),
    }
    if contribution.get("task_id") is not None:
        ref["task_id"] = contribution.get("task_id")
    if isinstance(contribution.get("evidence_ids"), list):
        ref["evidence_ids"] = [str(item) for item in contribution.get("evidence_ids") or []]
    tool_refs = tool_call_artifact_ref_fields(contribution)
    if tool_refs:
        ref["tool_call_artifact_refs"] = tool_refs
    ref.update(contribution_safety_ref_fields(contribution))
    if contribution.get("migration_stage") is not None:
        ref["migration_stage"] = contribution.get("migration_stage")
    return ref

def _legacy_decision_ref(legacy_plan: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    return {
        "main_action": legacy_plan.get("main_action"),
        "probability": legacy_plan.get("probability"),
        "allowed": verdict.get("allowed"),
    }


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
