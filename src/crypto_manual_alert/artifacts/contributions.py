"""Legacy leader-summary contribution adapter.

This module converts the current leader_summary reviewer keys into minimal
AgentContribution objects. It does not run independent worker agents, provide a
Harness, or complete Agent Swarm; migration_stage stays
"legacy_contribution_wrapper" until a controlled worker-agent runner replaces
this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


MIGRATION_STAGE = "legacy_contribution_wrapper"
REVIEWER_KEYS = (
    "bull_reviewer",
    "bear_reviewer",
    "data_quality_reviewer",
    "execution_risk_reviewer",
)
FORBIDDEN_EXECUTABLE_FIELDS = (
    "main_action",
    "entry",
    "entry_trigger",
    "stop",
    "stop_price",
    "target",
    "target_1",
    "target_2",
    "max_leverage",
    "risk_pct",
    "leverage",
    "position_size",
    "order_payload",
    "risk_verdict",
)


@dataclass(frozen=True)
class AgentContribution:
    contribution_id: str
    agent_name: str
    status: str
    required: bool
    summary: str
    task_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    confidence_cap: float | None = None
    blocked_actions: list[str] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    input_ref: str | None = None
    output_hash: str = ""
    failure_policy_applied: str = "none"
    trace_ref: str | None = None
    tool_call_artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    migration_stage: str = MIGRATION_STAGE

    def __post_init__(self) -> None:
        if self.task_id is None:
            object.__setattr__(self, "task_id", _task_id_from_contribution_id(self.contribution_id))
        if not self.evidence_ids:
            object.__setattr__(self, "evidence_ids", _evidence_ids_from_claims(self.claims))
        if self.confidence_cap is None:
            cap = _as_float(self.constraints.get("confidence_cap"))
            if cap is not None:
                object.__setattr__(self, "confidence_cap", cap)
        if not self.blocked_actions:
            object.__setattr__(self, "blocked_actions", _blocked_actions_from_constraints(self.constraints))

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "contribution_id": self.contribution_id,
            "agent_name": self.agent_name,
            "task_id": self.task_id,
            "status": self.status,
            "required": self.required,
            "summary": self.summary,
            "evidence_ids": list(self.evidence_ids),
            "confidence_cap": self.confidence_cap,
            "blocked_actions": list(self.blocked_actions),
            "claims": list(self.claims),
            "constraints": self.constraints,
            "conflicts": list(self.conflicts),
            "missing_facts": list(self.missing_facts),
            "input_ref": self.input_ref,
            "output_hash": self.output_hash,
            "failure_policy_applied": self.failure_policy_applied,
            "trace_ref": self.trace_ref,
            "tool_call_artifact_refs": list(self.tool_call_artifact_refs),
            "migration_stage": self.migration_stage,
        }


def contribution_safety_ref_fields(contribution: dict[str, Any]) -> dict[str, Any]:
    """Project shared safety fields for DecisionInput and context artifact refs."""

    constraints = contribution.get("constraints") if isinstance(contribution.get("constraints"), dict) else {}
    action_class_reduction = contribution.get(
        "allowed_action_class_reduction",
        constraints.get("allowed_action_class_reduction"),
    )
    blocked_actions = contribution.get("blocked_actions", constraints.get("blocked_actions"))
    return {
        "confidence_cap": contribution.get("confidence_cap", constraints.get("confidence_cap")),
        "confidence_cap_reasons": _string_list(
            contribution.get("confidence_cap_reasons", constraints.get("confidence_cap_reasons"))
        ),
        "blocked_actions": _action_list(blocked_actions),
        "hard_block": bool(contribution.get("hard_block", constraints.get("hard_block", False))),
        "hard_block_reasons": _string_list(
            contribution.get("hard_block_reasons", constraints.get("hard_block_reasons"))
        ),
        "manual_review_reminders": _string_list(
            contribution.get("manual_review_reminders", constraints.get("manual_review_reminders"))
        ),
        "allowed_action_class_reduction": (
            dict(action_class_reduction) if isinstance(action_class_reduction, dict) else {}
        ),
        "required_confirmations": _string_list(
            contribution.get("required_confirmations", constraints.get("required_confirmations"))
        ),
    }


def tool_call_artifact_ref_fields(contribution: dict[str, Any]) -> list[dict[str, Any]]:
    """Project canonical tool call artifacts as refs only."""

    allowed_keys = (
        "tool_call_id",
        "skill_name",
        "status",
        "source_type",
        "source_tier",
        "retrieved_at",
        "freshness_status",
        "result_ref",
        "output_hash",
        "can_satisfy_execution_fact",
        "fact_refs",
        "result_count",
        "error_type",
    )
    refs: list[dict[str, Any]] = []
    for item in contribution.get("tool_call_artifact_refs") or []:
        if not isinstance(item, dict):
            continue
        ref = {
            key: item.get(key)
            for key in allowed_keys
            if key in item and item.get(key) is not None
        }
        if ref:
            refs.append(ref)
    return refs


def from_leader_summary(
    leader_summary: dict[str, Any], *, input_ref: str | None = None, trace_ref: str | None = None
) -> list[AgentContribution]:
    return [
        _from_reviewer(agent_name, leader_summary.get(agent_name), input_ref=input_ref, trace_ref=trace_ref)
        for agent_name in REVIEWER_KEYS
    ]


def _from_reviewer(
    agent_name: str, payload: Any, *, input_ref: str | None, trace_ref: str | None
) -> AgentContribution:
    if payload is None:
        return _failed_contribution(
            agent_name,
            "missing_reviewer_key",
            input_ref=input_ref,
            trace_ref=trace_ref,
        )
    if not isinstance(payload, dict):
        return _failed_contribution(
            agent_name,
            "invalid_reviewer_payload",
            input_ref=input_ref,
            trace_ref=trace_ref,
            payload=payload,
        )

    forbidden = [field_name for field_name in FORBIDDEN_EXECUTABLE_FIELDS if field_name in payload]
    constraints = _constraints_from_payload(payload)
    conflicts: list[str] = []
    if forbidden:
        constraints["forbidden_executable_fields"] = forbidden
        conflicts.extend(f"non_final_executable_field:{field_name}" for field_name in forbidden)

    claims = [
        _claim(agent_name, key, value)
        for key, value in payload.items()
        if key not in _non_claim_fields() and key not in forbidden
    ]
    missing_facts = _missing_facts_from_payload(payload)
    if not payload:
        conflicts.append("empty_reviewer_payload")
        missing_facts.append(agent_name)
    status = "partial" if forbidden or not payload else "ok"

    return AgentContribution(
        contribution_id=f"{MIGRATION_STAGE}:{agent_name}",
        agent_name=agent_name,
        status=status,
        required=True,
        summary=_summary_from_payload(payload),
        claims=claims,
        constraints=constraints,
        conflicts=conflicts,
        missing_facts=missing_facts,
        input_ref=input_ref,
        output_hash=_hash_payload(payload),
        failure_policy_applied="soft_downgrade" if forbidden or not payload else "none",
        trace_ref=trace_ref,
    )


def _failed_contribution(
    agent_name: str,
    reason: str,
    *,
    input_ref: str | None,
    trace_ref: str | None,
    payload: Any = None,
) -> AgentContribution:
    failure_payload = {"agent_name": agent_name, "reason": reason, "payload": payload}
    return AgentContribution(
        contribution_id=f"{MIGRATION_STAGE}:{agent_name}",
        agent_name=agent_name,
        status="failed",
        required=True,
        summary=reason,
        claims=[],
        constraints={"blocked_actions": [], "required_confirmations": []},
        conflicts=[reason],
        missing_facts=[agent_name],
        input_ref=input_ref,
        output_hash=_hash_payload(failure_payload),
        failure_policy_applied="hard_block",
        trace_ref=trace_ref,
    )


def _summary_from_payload(payload: dict[str, Any]) -> str:
    for key in ("summary", "root_cause_chain", "quality", "risk"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _constraints_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    constraints: dict[str, Any] = {"blocked_actions": [], "required_confirmations": []}
    if "confidence_cap_hint" in payload:
        constraints["confidence_cap"] = payload["confidence_cap_hint"]
    if "confirmation" in payload:
        constraints["required_confirmations"].append(payload["confirmation"])
    if "required_before_trade" in payload and isinstance(payload["required_before_trade"], list):
        constraints["required_confirmations"].extend(payload["required_before_trade"])
    if payload.get("manual_only") is True:
        constraints["allowed_action_classes"] = ["manual_review_only"]
    return constraints


def _missing_facts_from_payload(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("gaps", "missing_or_failed", "missing_facts", "required_before_trade"):
        value = payload.get(key)
        if isinstance(value, list):
            missing.extend(str(item) for item in value)
        elif isinstance(value, str):
            missing.append(value)
    return missing


def _claim(agent_name: str, key: str, value: Any) -> dict[str, Any]:
    return {
        "claim": f"{key}: {value}",
        "claim_type": "inference",
        "side": _side_for_agent(agent_name),
        "evidence_ids": [],
        "confidence": "low",
        "freshness": "mixed",
    }


def _side_for_agent(agent_name: str) -> str:
    if agent_name == "bull_reviewer":
        return "bullish"
    if agent_name == "bear_reviewer":
        return "bearish"
    return "neutral"


def _non_claim_fields() -> set[str]:
    return {
        "confidence_cap_hint",
        "gaps",
        "missing_or_failed",
        "missing_facts",
        "required_before_trade",
        "manual_only",
    }


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _task_id_from_contribution_id(contribution_id: str) -> str:
    if ":" in contribution_id:
        return contribution_id.split(":", 1)[1]
    return contribution_id


def _evidence_ids_from_claims(claims: list[dict[str, Any]]) -> list[str]:
    evidence_ids: list[str] = []
    for claim_payload in claims:
        if not isinstance(claim_payload, dict):
            continue
        value = claim_payload.get("evidence_ids")
        if isinstance(value, list):
            evidence_ids.extend(str(item) for item in value if item)
        elif isinstance(value, str) and value:
            evidence_ids.append(value)
    return list(dict.fromkeys(evidence_ids))


def _blocked_actions_from_constraints(constraints: dict[str, Any]) -> list[str]:
    value = constraints.get("blocked_actions")
    return _action_list(value)


def _action_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    actions: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("action"):
            actions.append(str(item["action"]))
        elif isinstance(item, str) and item:
            actions.append(item)
    return list(dict.fromkeys(actions))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
