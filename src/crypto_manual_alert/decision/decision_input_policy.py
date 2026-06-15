from __future__ import annotations

from typing import Any


ACTION_CLASS_MAP = {
    "opening": {"open long", "open short"},
    "trigger": {"trigger long", "trigger short"},
    "flip": {"flip long to short", "flip short to long"},
}
REQUIRED_SHADOW_WORKER_AGENTS = (
    "LiveFactAgent",
    "DerivativesAgent",
    "MacroEventAgent",
    "RootCauseAgent",
    "MarketSentimentAgent",
    "DataQualityAgent",
    "ExecutionRiskAgent",
)


def missing_facts(facts_gate: dict[str, Any], agent_contributions: list[dict[str, Any]]) -> list[str]:
    values = [str(item) for item in facts_gate.get("missing_execution_facts") or []]
    values.extend(str(item) for item in facts_gate.get("missing_auxiliary_facts") or [])
    values.extend(str(item) for item in facts_gate.get("missing_event_facts") or [])
    values.extend(str(item) for item in facts_gate.get("missing_macro_facts") or [])
    for contribution in agent_contributions:
        values.extend(str(item) for item in contribution.get("missing_facts") or [])
    return _dedupe(values)


def conflicts(facts_gate: dict[str, Any], agent_contributions: list[dict[str, Any]]) -> list[str]:
    values = [str(item) for item in facts_gate.get("reasons") or []]
    for contribution in agent_contributions:
        values.extend(str(item) for item in contribution.get("conflicts") or [])
    return _dedupe(values)


def blocked_actions(facts_gate: dict[str, Any]) -> list[dict[str, str]]:
    blocked: list[dict[str, str]] = []
    reasons = facts_gate.get("reasons") or []
    reason = "; ".join(str(item) for item in reasons) or "blocked by facts gate"
    for action_class in facts_gate.get("blocked_action_classes") or []:
        for action in ACTION_CLASS_MAP.get(str(action_class), set()):
            blocked.append({"action": action, "reason": reason})
    for action in ACTION_CLASS_MAP["flip"]:
        if not any(item["action"] == action for item in blocked):
            blocked.append({"action": action, "reason": "flip actions require explicit human confirmation"})
    return sorted(blocked, key=lambda item: item["action"])


def confidence_policy(
    evidence_packets: list[dict[str, Any]],
    agent_contributions: list[dict[str, Any]],
    facts_gate: dict[str, Any],
) -> dict[str, Any]:
    caps: list[tuple[float, str]] = []
    for packet in evidence_packets:
        cap = _as_float(packet.get("confidence_cap"))
        if cap is not None:
            evidence_id = packet.get("evidence_id") or packet.get("name") or "evidence"
            caps.append((cap, f"evidence:{evidence_id}"))
    for contribution in agent_contributions:
        constraints = contribution.get("constraints") or {}
        cap = _as_float(contribution.get("confidence_cap"))
        if cap is None:
            cap = _as_float(constraints.get("confidence_cap"))
        if cap is not None:
            agent_name = contribution.get("agent_name") or "agent"
            caps.append((cap, f"contribution:{agent_name}"))
    facts_gate_cap = _as_float(facts_gate.get("confidence_cap"))
    if facts_gate_cap is not None:
        reasons = facts_gate.get("confidence_cap_reasons") or ["facts_gate:confidence_cap"]
        for reason in reasons:
            caps.append((facts_gate_cap, str(reason)))
    if is_execution_blocked(facts_gate):
        caps.append((0.58, "facts_gate:execution_facts_missing"))
    if not caps:
        return {"max_probability": None, "cap_reasons": [], "cap_applied_by_gate": False}
    min_cap = min(cap for cap, _reason in caps)
    return {
        "max_probability": min_cap,
        "cap_reasons": [reason for cap, reason in caps if cap == min_cap],
        "cap_applied_by_gate": True,
    }


def validation_summary(
    *,
    evidence_refs: list[dict[str, Any]],
    contribution_refs: list[dict[str, Any]],
    facts_gate: dict[str, Any],
    lead_synthesis: dict[str, Any],
    missing_facts: list[str],
    required_agent_names: tuple[str, ...] = (),
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    if facts_gate.get("severity") == "hard_fail" or facts_gate.get("passed") is False:
        violations.append(
            {
                "rule_id": "decision_input.facts_gate_hard_fail",
                "severity": "hard_fail",
                "message": "facts gate did not pass",
            }
        )
    dropped_required_contributions = required_dropped_contributions(
        lead_synthesis=lead_synthesis,
        contribution_refs=contribution_refs,
    )
    if dropped_required_contributions:
        violations.append(
            {
                "rule_id": "decision_input.required_worker_missing_or_failed",
                "severity": "hard_fail",
                "message": "required worker contribution missing or failed",
                "dropped_contributions": dropped_required_contributions,
            }
        )
    missing_required_agents = missing_required_worker_refs(
        contribution_refs=contribution_refs,
        required_agent_names=required_agent_names,
    )
    if missing_required_agents:
        violations.append(
            {
                "rule_id": "decision_input.required_worker_refs_missing",
                "severity": "hard_fail",
                "message": "required worker contribution refs are missing",
                "missing_required_agents": missing_required_agents,
            }
        )
    worker_hard_blocks = worker_hard_block_contributions(contribution_refs)
    if worker_hard_blocks:
        violations.append(
            {
                "rule_id": "decision_input.worker_hard_block",
                "severity": "hard_fail",
                "message": "worker contribution reported a hard block",
                "worker_hard_blocks": worker_hard_blocks,
            }
        )
    if missing_facts:
        violations.append(
            {
                "rule_id": "decision_input.missing_facts_present",
                "severity": "medium",
                "message": "decision input contains unresolved missing facts",
                "missing_facts": list(missing_facts),
            }
        )
    passed = not any(violation["severity"] == "hard_fail" for violation in violations)
    return {
        "passed": passed,
        "severity": "ok" if passed else "hard_fail",
        "violations": violations,
        "forbidden_payload_policy": "raw_values_and_raw_snippets_excluded",
        "evidence_ref_count": len(evidence_refs),
        "contribution_ref_count": len(contribution_refs),
    }


def required_dropped_contributions(
    *,
    lead_synthesis: dict[str, Any],
    contribution_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    required_agents = {
        str(contribution.get("agent_name"))
        for contribution in contribution_refs
        if contribution.get("required") is True and contribution.get("agent_name")
    }
    required_dropped: list[dict[str, Any]] = []
    for dropped in lead_synthesis.get("dropped_contributions") or []:
        if not isinstance(dropped, dict):
            continue
        reason = str(dropped.get("reason") or "")
        agent_name = str(dropped.get("agent_name") or "")
        if (
            reason == "missing_required_contribution"
            or agent_name in required_agents
            or dropped.get("required") is True
            or dropped.get("failure_policy_applied") == "hard_block"
        ):
            required_dropped.append(dict(dropped))
    return required_dropped


def missing_required_worker_refs(
    *,
    contribution_refs: list[dict[str, Any]],
    required_agent_names: tuple[str, ...],
) -> list[str]:
    if not required_agent_names:
        return []
    observed = {
        str(contribution.get("agent_name"))
        for contribution in contribution_refs
        if isinstance(contribution, dict) and contribution.get("agent_name")
    }
    return [agent_name for agent_name in required_agent_names if agent_name not in observed]


def worker_hard_block_contributions(
    contribution_refs: list[dict[str, Any]],
    *,
    include_llm_tool_shadow_worker: bool = True,
) -> list[dict[str, Any]]:
    hard_blocks: list[dict[str, Any]] = []
    for contribution in contribution_refs:
        if not isinstance(contribution, dict) or contribution.get("hard_block") is not True:
            continue
        if not include_llm_tool_shadow_worker and contribution.get("migration_stage") == "llm_tool_shadow_worker":
            continue
        hard_blocks.append(
            {
                "contribution_id": contribution.get("contribution_id"),
                "agent_name": contribution.get("agent_name"),
                "reasons": [str(reason) for reason in contribution.get("hard_block_reasons") or []],
            }
        )
    return hard_blocks


def is_execution_blocked(facts_gate: dict[str, Any]) -> bool:
    return bool(facts_gate.get("blocked_action_classes")) or facts_gate.get("severity") == "hard_fail"


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
