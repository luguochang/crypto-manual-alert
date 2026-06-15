from __future__ import annotations

from typing import Any

from crypto_manual_alert.decision.decision_input_policy import REQUIRED_SHADOW_WORKER_AGENTS


EXECUTION_FACT_TYPES = {"mark", "index", "order_book"}
REQUIRED_SCHEMA_FIELDS = (
    "schema_version",
    "mode",
    "decision_effect",
    "trace_id",
    "symbol",
    "input_ref",
    "input_hash",
    "evidence_refs",
    "facts_gate",
    "contribution_refs",
    "lead_synthesis",
    "effective_allowed_actions",
    "blocked_actions",
    "execution_mode",
    "confidence_policy",
    "missing_facts",
    "conflicts",
    "validation",
)
SIDE_EFFECT_FIELDS = {
    "production_final_input",
    "notification_input",
    "journal",
    "notification",
    "order_payload",
    "live_order",
}


def evaluate_pre_final_input_gate(pre_final_decision_input: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the pre-final DecisionInput candidate before any candidate final can consume it.

    The gate is audit-only. A passed gate means the payload is structurally
    usable for later candidate-final experiments, not that production may switch
    away from the legacy prompt.
    """

    violations: list[dict[str, Any]] = []
    payload = pre_final_decision_input if isinstance(pre_final_decision_input, dict) else {}
    violations.extend(_schema_violations(payload))
    violations.extend(_validation_violations(payload))
    violations.extend(_missing_required_worker_violations(payload))
    violations.extend(_execution_fact_source_violations(payload))
    violations.extend(_tool_artifact_execution_fact_source_violations(payload))
    violations.extend(_worker_hard_block_violations(payload))
    violations.extend(_side_effect_violations(payload))

    passed = not violations
    return {
        "passed": passed,
        "severity": "ok" if passed else "hard_fail",
        "decision_effect": "none",
        "violations": violations,
        "checks": {
            "schema_version": payload.get("schema_version"),
            "mode": payload.get("mode"),
            "required_worker_ref_count": _required_worker_ref_count(payload),
            "validation_passed": _validation_passed(payload),
            "side_effect_safe": not _side_effect_violations(payload),
        },
    }


def _schema_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    missing_fields = [field for field in REQUIRED_SCHEMA_FIELDS if field not in payload]
    if missing_fields:
        violations.append(
            {
                "rule_id": "pre_final_input.schema_missing_fields",
                "severity": "hard_fail",
                "missing_fields": missing_fields,
            }
        )
    if payload.get("schema_version") != 1:
        violations.append(
            {
                "rule_id": "pre_final_input.schema_version_invalid",
                "severity": "hard_fail",
                "expected": 1,
                "observed": payload.get("schema_version"),
            }
        )
    if payload.get("mode") != "pre_final_candidate":
        violations.append(
            {
                "rule_id": "pre_final_input.mode_invalid",
                "severity": "hard_fail",
                "expected": "pre_final_candidate",
                "observed": payload.get("mode"),
            }
        )
    if payload.get("decision_effect") != "none":
        violations.append(
            {
                "rule_id": "pre_final_input.decision_effect_not_none",
                "severity": "hard_fail",
                "observed": payload.get("decision_effect"),
            }
        )
    return violations


def _validation_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if _validation_passed(payload):
        return []
    return [
        {
            "rule_id": "pre_final_input.validation_failed",
            "severity": "hard_fail",
        }
    ]


def _missing_required_worker_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    missing = _missing_required_workers(payload)
    if not missing:
        return []
    return [
        {
            "rule_id": "pre_final_input.required_worker_refs_missing",
            "severity": "hard_fail",
            "missing_required_agents": missing,
        }
    ]


def _execution_fact_source_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_refs = payload.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        return []
    invalid_refs = []
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("data_type") not in EXECUTION_FACT_TYPES:
            continue
        if ref.get("can_satisfy_execution_fact") is not True:
            continue
        if ref.get("source_type") == "exchange_native":
            continue
        invalid_refs.append(
            {
                "evidence_id": ref.get("evidence_id"),
                "data_type": ref.get("data_type"),
                "source_type": ref.get("source_type"),
            }
        )
    if not invalid_refs:
        return []
    return [
        {
            "rule_id": "pre_final_input.execution_fact_source_invalid",
            "severity": "hard_fail",
            "invalid_refs": invalid_refs,
        }
    ]


def _tool_artifact_execution_fact_source_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    invalid_refs = []
    for contribution in payload.get("contribution_refs") or []:
        if not isinstance(contribution, dict):
            continue
        for ref in contribution.get("tool_call_artifact_refs") or []:
            if not isinstance(ref, dict):
                continue
            if ref.get("can_satisfy_execution_fact") is not True:
                continue
            if ref.get("source_type") == "exchange_native" and ref.get("freshness_status") == "fresh":
                continue
            invalid_refs.append(
                {
                    "agent_name": contribution.get("agent_name"),
                    "tool_call_id": ref.get("tool_call_id"),
                    "skill_name": ref.get("skill_name"),
                    "source_type": ref.get("source_type"),
                    "freshness_status": ref.get("freshness_status"),
                }
            )
    if not invalid_refs:
        return []
    return [
        {
            "rule_id": "pre_final_input.tool_artifact_execution_fact_source_invalid",
            "severity": "hard_fail",
            "invalid_refs": invalid_refs,
        }
    ]


def _worker_hard_block_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    hard_blocks = []
    for contribution in payload.get("contribution_refs") or []:
        if not isinstance(contribution, dict) or contribution.get("hard_block") is not True:
            continue
        hard_blocks.append(
            {
                "contribution_id": contribution.get("contribution_id"),
                "agent_name": contribution.get("agent_name"),
                "reasons": [str(reason) for reason in contribution.get("hard_block_reasons") or []],
            }
        )
    if not hard_blocks:
        return []
    return [
        {
            "rule_id": "pre_final_input.worker_hard_block",
            "severity": "hard_fail",
            "worker_hard_blocks": hard_blocks,
        }
    ]


def _side_effect_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [
        field
        for field in sorted(SIDE_EFFECT_FIELDS)
        if field in payload and payload.get(field) not in (False, None, "none")
    ]
    if not fields:
        return []
    return [
        {
            "rule_id": "pre_final_input.side_effect_field_present",
            "severity": "hard_fail",
            "fields": fields,
        }
    ]


def _validation_passed(payload: dict[str, Any]) -> bool:
    validation = payload.get("validation")
    return isinstance(validation, dict) and validation.get("passed") is True


def _required_worker_ref_count(payload: dict[str, Any]) -> int:
    observed = _observed_worker_agents(payload)
    return len([agent_name for agent_name in REQUIRED_SHADOW_WORKER_AGENTS if agent_name in observed])


def _missing_required_workers(payload: dict[str, Any]) -> list[str]:
    observed = _observed_worker_agents(payload)
    return [agent_name for agent_name in REQUIRED_SHADOW_WORKER_AGENTS if agent_name not in observed]


def _observed_worker_agents(payload: dict[str, Any]) -> set[str]:
    contribution_refs = payload.get("contribution_refs")
    if not isinstance(contribution_refs, list):
        return set()
    return {
        str(contribution.get("agent_name"))
        for contribution in contribution_refs
        if isinstance(contribution, dict) and contribution.get("agent_name")
    }
