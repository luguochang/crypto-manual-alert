from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution


VALID_CONTRIBUTION_STATUSES = {"ok", "partial", "failed", "skipped"}
LEGACY_REVIEWER_AGENTS = (
    "bull_reviewer",
    "bear_reviewer",
    "data_quality_reviewer",
    "execution_risk_reviewer",
)
SHADOW_WORKER_AGENTS = (
    "LiveFactAgent",
    "DerivativesAgent",
    "MacroEventAgent",
    "RootCauseAgent",
    "MarketSentimentAgent",
    "DataQualityAgent",
    "ExecutionRiskAgent",
)
FINAL_AGENT_NAME = "FinalDecisionAgent"


@dataclass(frozen=True)
class HarnessValidationResult:
    """Validation result for runtime agent boundaries.

    This module validates contracts only. It does not repair model output, run
    agents, write journals, send notifications, or replace risk gates.
    """

    passed: bool
    severity: str
    violations: list[dict[str, Any]] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "violations": list(self.violations),
        }


@dataclass(frozen=True)
class AgentPolicy:
    """Runtime limits for one enabled agent."""

    agent_name: str
    allowed_tools: tuple[str, ...] = ()
    required: bool = True
    timeout_seconds: int = 20


@dataclass(frozen=True)
class HarnessPolicy:
    """Executable policy for a controlled agent run mode.

    The first implementation is deliberately code-defined instead of YAML. YAML
    can be added later as a stricter loader, but it must not be able to loosen
    these runtime boundaries.
    """

    run_mode: str
    agents: dict[str, AgentPolicy]
    allow_journal_write: bool
    allow_notification: bool
    max_parallel_workers: int = 4
    deadline_ms: int = 60_000
    max_tool_calls: int = 0
    non_final_forbidden_fields: tuple[str, ...] = (
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
        "journal",
        "notification",
    )

    def agent_policy(self, agent_name: str) -> AgentPolicy:
        return self.agents[agent_name]


def load_harness_policy(run_mode: str) -> HarnessPolicy:
    """Load the built-in harness policy for a known run mode."""

    if run_mode == "production_decision":
        return HarnessPolicy(
            run_mode=run_mode,
            agents={
                **{
                    agent_name: AgentPolicy(agent_name, timeout_seconds=10)
                    for agent_name in LEGACY_REVIEWER_AGENTS
                },
                FINAL_AGENT_NAME: AgentPolicy(FINAL_AGENT_NAME, timeout_seconds=20),
            },
            allow_journal_write=True,
            allow_notification=True,
        )
    if run_mode == "shadow_audit":
        return HarnessPolicy(
            run_mode=run_mode,
            agents={
                "LiveFactAgent": AgentPolicy(
                    "LiveFactAgent", allowed_tools=("realtime_search",), timeout_seconds=10
                ),
                "DerivativesAgent": AgentPolicy("DerivativesAgent", timeout_seconds=10),
                "MacroEventAgent": AgentPolicy(
                    "MacroEventAgent", allowed_tools=("macro_event",), timeout_seconds=10
                ),
                "RootCauseAgent": AgentPolicy(
                    "RootCauseAgent", allowed_tools=("root_cause_search",), timeout_seconds=30
                ),
                "MarketSentimentAgent": AgentPolicy(
                    "MarketSentimentAgent", allowed_tools=("market_sentiment",), timeout_seconds=20
                ),
                "DataQualityAgent": AgentPolicy("DataQualityAgent", timeout_seconds=10),
                "ExecutionRiskAgent": AgentPolicy(
                    "ExecutionRiskAgent", allowed_tools=("liquidity_order_book",), timeout_seconds=10
                ),
                FINAL_AGENT_NAME: AgentPolicy(FINAL_AGENT_NAME, timeout_seconds=20),
            },
            allow_journal_write=False,
            allow_notification=False,
            max_tool_calls=1,
        )
    raise ValueError("run_mode must be one of: production_decision, shadow_audit")


def validate_agent_run_request(
    policy: HarnessPolicy, *, agent_name: str, requested_tools: list[str] | tuple[str, ...]
) -> HarnessValidationResult:
    """Validate pre-agent execution permissions before a worker can run."""

    violations: list[dict[str, Any]] = []
    agent_policy = policy.agents.get(agent_name)
    if agent_policy is None:
        violations.append(
            {
                "agent_name": agent_name,
                "rule_id": "agent.not_enabled",
            }
        )
        allowed_tools: tuple[str, ...] = ()
    else:
        allowed_tools = agent_policy.allowed_tools

    requested = list(requested_tools)
    if agent_name == FINAL_AGENT_NAME and requested:
        violations.append(
            {
                "agent_name": agent_name,
                "rule_id": "final_agent.tool_request_forbidden",
                "requested_tools": requested,
            }
        )

    disallowed_tools = [tool for tool in requested if tool not in allowed_tools]
    if disallowed_tools:
        violations.append(
            {
                "agent_name": agent_name,
                "rule_id": "agent.tool_not_allowed",
                "requested_tools": disallowed_tools,
                "allowed_tools": list(allowed_tools),
            }
        )

    return _result(violations)


def validate_agent_contributions(
    contributions: list[AgentContribution], policy: HarnessPolicy | None = None
) -> HarnessValidationResult:
    """Validate post-agent contributions against executable runtime boundaries."""

    active_policy = policy or load_harness_policy("production_decision")
    violations: list[dict[str, Any]] = []
    for contribution in contributions:
        violations.extend(_agent_identity_violations(contribution, active_policy))
        violations.extend(_schema_violations(contribution))
        violations.extend(_decision_effect_violations(contribution))
        violations.extend(_required_status_violations(contribution))
        violations.extend(_failure_envelope_violations(contribution))
        violations.extend(_tool_policy_violations(contribution, active_policy))
        violations.extend(_skill_tool_result_payload_violations(contribution))
        violations.extend(_non_final_executable_field_violations(contribution, active_policy))
    return _result(violations)


def _agent_identity_violations(contribution: AgentContribution, policy: HarnessPolicy) -> list[dict[str, Any]]:
    if contribution.agent_name in policy.agents:
        return []
    return [
        {
            "agent_name": contribution.agent_name,
            "rule_id": "agent.not_enabled",
        }
    ]


def _schema_violations(contribution: AgentContribution) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if contribution.status not in VALID_CONTRIBUTION_STATUSES:
        violations.append(
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.status.invalid",
                "status": contribution.status,
            }
        )
    if not contribution.input_ref:
        violations.append(
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.schema.input_ref_missing",
            }
        )
    if not contribution.output_hash:
        violations.append(
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.schema.output_hash_missing",
            }
        )
    if not contribution.failure_policy_applied:
        violations.append(
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.schema.failure_policy_missing",
            }
        )
    if not contribution.trace_ref:
        violations.append(
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.schema.trace_ref_missing",
            }
        )
    return violations


def _required_status_violations(contribution: AgentContribution) -> list[dict[str, Any]]:
    if contribution.required and contribution.status in {"failed", "partial"}:
        return [
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.required_contribution.failed",
                "status": contribution.status,
            }
        ]
    return []


def _failure_envelope_violations(contribution: AgentContribution) -> list[dict[str, Any]]:
    if contribution.status == "ok" and contribution.failure_policy_applied not in {"none", ""}:
        return [
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.failure_envelope.status_mismatch",
            }
        ]
    return []


def _decision_effect_violations(contribution: AgentContribution) -> list[dict[str, Any]]:
    decision_effect = contribution.constraints.get("decision_effect")
    if decision_effect in (None, "none"):
        return []
    return [
        {
            "agent_name": contribution.agent_name,
            "rule_id": "agent.constraints.decision_effect_not_none",
            "decision_effect": decision_effect,
        }
    ]


def _tool_policy_violations(contribution: AgentContribution, policy: HarnessPolicy) -> list[dict[str, Any]]:
    requested_tools = list(contribution.constraints.get("requested_tools") or [])
    if not requested_tools:
        return []
    if contribution.agent_name == FINAL_AGENT_NAME:
        return [
            {
                "agent_name": contribution.agent_name,
                "rule_id": "final_agent.tool_request_forbidden",
                "requested_tools": requested_tools,
            }
        ]
    result = validate_agent_run_request(policy, agent_name=contribution.agent_name, requested_tools=requested_tools)
    return list(result.violations)


def _skill_tool_result_payload_violations(contribution: AgentContribution) -> list[dict[str, Any]]:
    paths = _raw_skill_tool_result_paths(
        {
            "claims": contribution.claims,
            "constraints": contribution.constraints,
            "conflicts": contribution.conflicts,
            "missing_facts": contribution.missing_facts,
        }
    )
    if not paths:
        return []
    return [
        {
            "agent_name": contribution.agent_name,
            "rule_id": "agent.skill_tool_result_direct_payload",
            "paths": paths,
        }
    ]


def _raw_skill_tool_result_paths(value: Any, *, path: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        if _is_raw_skill_tool_result_payload(value):
            paths.append(path or "$")
            return paths
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            paths.extend(_raw_skill_tool_result_paths(item, path=child_path))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            paths.extend(_raw_skill_tool_result_paths(item, path=child_path))
    elif _is_raw_skill_tool_result_object(value):
        paths.append(path or "$")
    return paths


def _is_raw_skill_tool_result_object(value: Any) -> bool:
    return (
        value.__class__.__name__ == "SkillToolResult"
        and hasattr(value, "to_public_dict")
        and all(
            hasattr(value, attr)
            for attr in (
                "skill_name",
                "task_id",
                "status",
                "result_type",
                "source_type",
                "can_satisfy_execution_fact",
                "decision_effect",
            )
        )
    )


def _is_raw_skill_tool_result_payload(value: dict[str, Any]) -> bool:
    required_keys = {
        "skill_name",
        "task_id",
        "status",
        "decision_effect",
        "result_type",
        "source_type",
        "can_satisfy_execution_fact",
        "evidence_candidates",
        "constraints",
        "missing_inputs",
        "trace_ref",
    }
    return required_keys.issubset(value.keys())


def _non_final_executable_field_violations(
    contribution: AgentContribution, policy: HarnessPolicy
) -> list[dict[str, Any]]:
    if contribution.agent_name == FINAL_AGENT_NAME:
        return []

    fields = _forbidden_fields_from_contribution(contribution, policy)
    if fields:
        return [
            {
                "agent_name": contribution.agent_name,
                "rule_id": "agent.non_final.executable_fields",
                "fields": fields,
            }
        ]
    return []


def _forbidden_fields_from_contribution(contribution: AgentContribution, policy: HarnessPolicy) -> list[str]:
    fields: list[str] = []
    value = contribution.constraints.get("forbidden_executable_fields")
    if value:
        fields.extend(str(item) for item in value)

    searchable = {
        "summary": contribution.summary,
        "claims": contribution.claims,
        "constraints": contribution.constraints,
        "conflicts": contribution.conflicts,
        "missing_facts": contribution.missing_facts,
    }
    flattened = _flatten_forbidden_scan(searchable)
    for field_name in policy.non_final_forbidden_fields:
        if _contains_field_token(flattened, field_name):
            fields.append(field_name)

    return list(dict.fromkeys(fields))


def _flatten_forbidden_scan(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            parts.append(str(key))
            parts.append(_flatten_forbidden_scan(item))
    elif isinstance(value, list | tuple | set):
        for item in value:
            parts.append(_flatten_forbidden_scan(item))
    else:
        parts.append(str(value))
    return "\n".join(parts).lower()


def _contains_field_token(text: str, field_name: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(field_name.lower())}(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None


def _result(violations: list[dict[str, Any]]) -> HarnessValidationResult:
    return HarnessValidationResult(
        passed=not violations,
        severity="ok" if not violations else "hard_fail",
        violations=violations,
    )
