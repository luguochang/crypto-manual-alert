from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_REQUIRED_AGENTS = (
    "LiveFactAgent",
    "DerivativesAgent",
    "MacroEventAgent",
    "RootCauseAgent",
    "MarketSentimentAgent",
    "DataQualityAgent",
    "ExecutionRiskAgent",
)


@dataclass(frozen=True)
class LeadSynthesisCandidate:
    """Audit-only Lead synthesis for candidate DecisionInput construction."""

    decision_effect: str
    included_contribution_ids: list[str]
    dropped_contributions: list[dict[str, Any]]
    supporting_thesis: list[str]
    counter_thesis: list[str]
    conflicts: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    counter_thesis_refs: list[dict[str, Any]] = field(default_factory=list)
    strongest_counter_thesis_ref: dict[str, Any] | None = None
    conflict_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "decision_effect": self.decision_effect,
            "included_contribution_ids": self.included_contribution_ids,
            "dropped_contributions": self.dropped_contributions,
            "supporting_thesis": list(self.supporting_thesis),
            "counter_thesis": list(self.counter_thesis),
            "counter_thesis_refs": list(self.counter_thesis_refs),
            "strongest_counter_thesis_ref": self.strongest_counter_thesis_ref,
            "conflicts": list(self.conflicts),
            "conflict_refs": list(self.conflict_refs),
            "missing_facts": list(self.missing_facts),
        }


def build_lead_synthesis_candidate(
    *,
    agent_contributions: list[dict[str, Any]],
    required_agents: list[str] | tuple[str, ...] = DEFAULT_REQUIRED_AGENTS,
) -> LeadSynthesisCandidate:
    included: list[str] = []
    dropped: list[dict[str, str | None]] = []
    supporting: list[str] = []
    counter: list[str] = []
    counter_refs: list[dict[str, Any]] = []
    conflicts: list[str] = []
    conflict_refs: list[dict[str, Any]] = []
    missing_facts: list[str] = []
    seen_agents: set[str] = set()
    required_agent_set = set(required_agents)

    for contribution in agent_contributions:
        agent_name = _optional_str(contribution.get("agent_name"))
        if agent_name:
            seen_agents.add(agent_name)
        status = contribution.get("status")
        contribution_id = _optional_str(contribution.get("contribution_id"))
        if status in {"ok", "partial"}:
            if contribution_id:
                included.append(contribution_id)
            supporting.extend(_claims_by_side(contribution, {"bullish", "neutral"}))
            counter.extend(_claims_by_side(contribution, {"bearish"}))
            counter_refs.extend(_claim_refs_by_side(contribution, {"bearish"}))
        else:
            dropped.append(
                {
                    "contribution_id": contribution_id,
                    "agent_name": agent_name,
                    "reason": f"status={status or 'unknown'}",
                    "required": _is_required_agent(agent_name, contribution, required_agent_set),
                    "failure_policy_applied": _optional_str(contribution.get("failure_policy_applied")),
                    "error_type": _error_type(contribution),
                }
            )
        conflicts.extend(_conflict_summaries(contribution))
        conflict_refs.extend(_conflict_refs(contribution))
        missing_facts.extend(str(item) for item in contribution.get("missing_facts") or [])

    for required_agent in required_agents:
        if required_agent not in seen_agents:
            dropped.append(
                {
                    "contribution_id": None,
                    "agent_name": required_agent,
                    "reason": "missing_required_contribution",
                    "required": True,
                    "failure_policy_applied": "hard_block",
                    "error_type": None,
                }
            )
            missing_facts.append(required_agent)

    return LeadSynthesisCandidate(
        decision_effect="none",
        included_contribution_ids=included,
        dropped_contributions=dropped,
        supporting_thesis=_dedupe(supporting),
        counter_thesis=_dedupe(counter),
        conflicts=_dedupe(conflicts),
        missing_facts=_dedupe(missing_facts),
        counter_thesis_refs=_dedupe_dicts(counter_refs),
        strongest_counter_thesis_ref=_strongest_counter_ref(_dedupe_dicts(counter_refs)),
        conflict_refs=_dedupe_dicts(conflict_refs),
    )


def _claims_by_side(contribution: dict[str, Any], sides: set[str]) -> list[str]:
    claims = []
    for claim in contribution.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        side = str(claim.get("side") or "neutral")
        text = claim.get("claim")
        if side in sides and text:
            claims.append(str(text))
    if not claims and "neutral" in sides and contribution.get("summary"):
        claims.append(str(contribution["summary"]))
    return claims


def _claim_refs_by_side(contribution: dict[str, Any], sides: set[str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for claim in contribution.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        side = str(claim.get("side") or "neutral")
        text = claim.get("claim")
        if side not in sides or not text:
            continue
        ref: dict[str, Any] = {
            "contribution_id": contribution.get("contribution_id"),
            "agent_name": contribution.get("agent_name"),
            "claim": str(text),
            "side": side,
        }
        evidence_ids = claim.get("evidence_ids")
        if isinstance(evidence_ids, list):
            ref["evidence_ids"] = [str(item) for item in evidence_ids if item]
        strength = _as_float(claim.get("strength") or claim.get("score") or claim.get("confidence"))
        if strength is not None:
            ref["strength"] = strength
        refs.append(ref)
    return refs


def _conflict_summaries(contribution: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in contribution.get("conflicts") or []:
        if isinstance(item, dict):
            summary = item.get("summary") or item.get("conflict_id")
            if summary:
                values.append(str(summary))
            continue
        values.append(str(item))
    return values


def _conflict_refs(contribution: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    contribution_id = contribution.get("contribution_id")
    for item in contribution.get("conflicts") or []:
        if isinstance(item, dict):
            ref = {
                key: item.get(key)
                for key in ("conflict_id", "summary", "sides", "contribution_refs")
                if key in item
            }
            if "conflict_id" not in ref and ref.get("summary"):
                ref["conflict_id"] = str(ref["summary"])
            if "contribution_refs" not in ref and contribution_id:
                ref["contribution_refs"] = [contribution_id]
            if ref:
                refs.append(ref)
            continue
        conflict_id = str(item)
        ref = {"conflict_id": conflict_id, "summary": conflict_id}
        if contribution_id:
            ref["contribution_refs"] = [contribution_id]
        refs.append(ref)
    return refs


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _error_type(contribution: dict[str, Any]) -> str | None:
    error = contribution.get("error")
    if isinstance(error, dict) and error.get("type"):
        return str(error.get("type"))
    if contribution.get("error_type"):
        return str(contribution.get("error_type"))
    return None


def _is_required_agent(
    agent_name: str | None,
    contribution: dict[str, Any],
    required_agents: set[str],
) -> bool:
    if agent_name and agent_name in required_agents:
        return True
    return bool(contribution.get("required"))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _dedupe_dicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = str(sorted(value.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _strongest_counter_ref(counter_refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not counter_refs:
        return None
    return max(counter_refs, key=_counter_ref_score)


def _counter_ref_score(ref: dict[str, Any]) -> tuple[float, int]:
    evidence_ids = ref.get("evidence_ids")
    evidence_count = len(evidence_ids) if isinstance(evidence_ids, list) else 0
    return (_as_float(ref.get("strength")) or 0.0, evidence_count)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
