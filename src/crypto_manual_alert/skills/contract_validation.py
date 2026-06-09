from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .contract_policy import (
    ALLOWED_FACTOR_TYPES,
    ALLOWED_MACRO_FIELDS,
    ALLOWED_MISSING_INPUTS,
    ALLOWED_RESULT_TYPES,
    ALLOWED_SENTIMENT_OUTPUTS,
    ALLOWED_SKILL_NAMES,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_STATUSES,
    ALLOWED_TASK_IDS,
    EXECUTION_FACTS,
    _FORBIDDEN_PUBLIC_VALUE_TOKENS,
    _SKILL_CONTRACTS,
)


def validate_skill_tool_result(result: Any) -> None:
    ensure_string("skill_name", result.skill_name)
    ensure_string("task_id", result.task_id)
    ensure_string("status", result.status)
    ensure_string("result_type", result.result_type)
    ensure_string("source_type", result.source_type)
    ensure_optional_string("trace_ref", result.trace_ref)
    ensure_string("decision_effect", result.decision_effect)
    if result.skill_name not in ALLOWED_SKILL_NAMES:
        raise ValueError(f"skill_name is not allowed for skill tool results: {result.skill_name}")
    if result.task_id not in ALLOWED_TASK_IDS:
        raise ValueError(f"task_id is not allowed for skill tool results: {result.task_id}")
    _validate_trace_ref(result.trace_ref, result.task_id)
    if not isinstance(result.can_satisfy_execution_fact, bool):
        raise ValueError("can_satisfy_execution_fact must be a boolean")
    if result.status not in ALLOWED_STATUSES:
        raise ValueError(f"status is not allowed for skill tool results: {result.status}")
    if result.result_type not in ALLOWED_RESULT_TYPES:
        raise ValueError(f"result_type is not allowed for skill tool results: {result.result_type}")
    if result.source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"source_type is not allowed for skill tool results: {result.source_type}")
    if result.can_satisfy_execution_fact and result.source_type != "exchange_native":
        raise ValueError("execution fact satisfaction requires exchange_native source_type")
    if result.decision_effect != "none":
        raise ValueError("decision_effect must be none for skill tool results")
    _validate_skill_contract(result)


def coerce_optional_evidence_candidates(
    candidates: Sequence[Any] | None,
    *,
    candidate_type: type,
) -> tuple[Any, ...]:
    if candidates is None:
        return ()
    if isinstance(candidates, Mapping) or not isinstance(candidates, (list, tuple)):
        raise ValueError("evidence_candidates must be a list or tuple of EvidenceCandidate objects")
    if not all(type(candidate) is candidate_type for candidate in candidates):
        raise ValueError("evidence_candidates must contain EvidenceCandidate objects")
    return tuple(candidates)


def coerce_constraints(constraints: Any | None, *, constraints_type: type) -> Any:
    if constraints is None:
        return constraints_type()
    if type(constraints) is not constraints_type:
        raise ValueError("constraints must be a SkillConstraints object")
    return constraints


def coerce_optional_missing_inputs(missing_inputs: Sequence[str] | None) -> tuple[str, ...]:
    if missing_inputs is None:
        return ()
    if isinstance(missing_inputs, Mapping) or not isinstance(missing_inputs, (list, tuple)):
        raise ValueError("missing_inputs must be a list or tuple of strings")
    if not all(type(item) is str for item in missing_inputs):
        raise ValueError("missing_inputs must be a list of strings")
    unknown = [item for item in missing_inputs if item not in ALLOWED_MISSING_INPUTS]
    if unknown:
        raise ValueError(f"missing_inputs contains unapproved values: {unknown}")
    return tuple(missing_inputs)


def coerce_optional_fact_refs(fact_refs: Mapping[str, Any] | None) -> dict[str, str]:
    if fact_refs is None:
        return {}
    if not isinstance(fact_refs, Mapping):
        raise ValueError("fact_refs must be a mapping")
    refs: dict[str, str] = {}
    for key, value in fact_refs.items():
        key_text = str(key)
        if key_text not in EXECUTION_FACTS:
            raise ValueError(f"fact_refs contains unapproved key: {key_text}")
        ensure_string(f"fact_refs.{key_text}", value)
        ensure_safe_public_value(f"fact_refs.{key_text}", value)
        refs[key_text] = str(value)
    return refs


def ensure_bool(field_name: str, value: Any) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")


def ensure_positive_int(field_name: str, value: Any) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def ensure_string(field_name: str, value: Any) -> None:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a string")


def ensure_optional_string(field_name: str, value: Any) -> None:
    if value is not None and type(value) is not str:
        raise ValueError(f"{field_name} must be a string or None")


def ensure_safe_token(field_name: str, value: str) -> None:
    if ":" in value or _has_forbidden_public_value(value):
        raise ValueError(f"{field_name} contains unsafe semantics")


def ensure_safe_public_value(field_name: str, value: str) -> None:
    if _has_forbidden_public_value(value):
        raise ValueError(f"{field_name} contains unsafe semantics")


def set_tuple(field_name: str, values: Sequence[str], allowed_values: Sequence[str]) -> None:
    if type(values) is not tuple:
        raise ValueError(f"{field_name} must be a tuple of allowed strings")
    if not all(type(item) is str for item in values):
        raise ValueError(f"{field_name} must contain only strings")
    unknown = [item for item in values if item not in allowed_values]
    if unknown:
        raise ValueError(f"{field_name} contains unapproved values: {unknown}")


def safe_evidence_text(value: Any) -> str:
    text = str(value or "")
    return "" if _has_forbidden_public_value(text) else text


def _validate_skill_contract(result: Any) -> None:
    contract = _SKILL_CONTRACTS[result.skill_name]
    if result.task_id not in contract["task_ids"]:
        raise ValueError(f"skill contract mismatch for task_id: {result.task_id}")
    if result.result_type != contract["result_type"]:
        raise ValueError(f"skill contract mismatch for result_type: {result.result_type}")
    if result.source_type != contract["source_type"]:
        raise ValueError(f"skill contract mismatch for source_type: {result.source_type}")
    if result.can_satisfy_execution_fact is not contract["can_satisfy_execution_fact"]:
        raise ValueError("skill contract mismatch for execution fact boundary")
    if result.fact_refs and result.skill_name != "liquidity_order_book":
        raise ValueError("fact_refs are only allowed for liquidity_order_book")
    _validate_constraint_contract(result.skill_name, result._constraints)


def _validate_constraint_contract(skill_name: str, constraints: Any) -> None:
    common = {
        "must_pass_facts_gate": True,
        "max_depth": constraints.max_depth,
        "timeout_seconds": constraints.timeout_seconds,
    }
    expected_by_skill = {
        "liquidity_order_book": {
            **common,
            "search_derived_cannot_satisfy_execution_fact": True,
            "required_execution_facts": list(EXECUTION_FACTS),
        },
        "macro_event": {**common, "required_fields": list(ALLOWED_MACRO_FIELDS)},
        "market_sentiment": {
            **common,
            "separate_objective_facts_from_crowding": True,
            "outputs": list(ALLOWED_SENTIMENT_OUTPUTS),
        },
        "realtime_search": {**common, "raw_snippets_redacted": True},
        "root_cause_search": {
            **common,
            "recursive_factor_search": True,
            "allowed_factor_types": list(ALLOWED_FACTOR_TYPES),
        },
    }
    public_constraints = constraints.to_public_dict()
    if public_constraints != expected_by_skill[skill_name]:
        raise ValueError("skill contract mismatch for constraints")


def _validate_trace_ref(trace_ref: str | None, task_id: str) -> None:
    if trace_ref is None:
        return
    parts = trace_ref.split(":")
    if len(parts) != 3 or parts[1] != "skill" or f"skill:{parts[2]}" != task_id:
        raise ValueError("trace_ref must be '<trace_id>:<task_id>'")
    ensure_safe_token("trace_ref", parts[0])


def _has_forbidden_public_value(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return any(token in normalized for token in _FORBIDDEN_PUBLIC_VALUE_TOKENS)
