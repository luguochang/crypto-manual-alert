from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .contract_policy import (
    ALLOWED_FACTOR_TYPES,
    ALLOWED_MACRO_FIELDS,
    ALLOWED_SENTIMENT_OUTPUTS,
    EXECUTION_FACTS,
)
from .contract_validation import (
    coerce_constraints,
    coerce_optional_evidence_candidates,
    coerce_optional_fact_refs,
    coerce_optional_missing_inputs,
    ensure_bool,
    ensure_positive_int,
    ensure_safe_public_value,
    ensure_safe_token,
    ensure_string,
    safe_evidence_text,
    set_tuple,
    validate_skill_tool_result,
)


@dataclass(frozen=True)
class SkillTaskContext:
    """Controlled input passed from worker runtime to a skill facade."""

    skill_name: str
    task_id: str
    symbol: str
    trace_id: str
    query: str
    input_view: dict[str, Any]
    max_depth: int = 1
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        ensure_string("skill_name", self.skill_name)
        ensure_string("task_id", self.task_id)
        ensure_string("symbol", self.symbol)
        ensure_string("trace_id", self.trace_id)
        ensure_string("query", self.query)
        ensure_safe_token("trace_id", self.trace_id)
        ensure_positive_int("max_depth", self.max_depth)
        ensure_positive_int("timeout_seconds", self.timeout_seconds)
        object.__setattr__(self, "input_view", deepcopy(self.input_view))

    @property
    def trace_ref(self) -> str:
        return f"{self.trace_id}:{self.task_id}"


@dataclass(frozen=True)
class EvidenceCandidate:
    title: str
    url: str
    snippet_ref: str
    source_type: str = "search_derived"

    def __post_init__(self) -> None:
        ensure_string("title", self.title)
        ensure_string("url", self.url)
        ensure_string("snippet_ref", self.snippet_ref)
        ensure_string("source_type", self.source_type)
        ensure_safe_public_value("title", self.title)
        ensure_safe_public_value("url", self.url)
        ensure_safe_public_value("snippet_ref", self.snippet_ref)
        if self.source_type != "search_derived":
            raise ValueError("evidence candidate source_type must be search_derived")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet_ref": self.snippet_ref,
            "source_type": self.source_type,
        }


@dataclass(frozen=True)
class SkillConstraints:
    must_pass_facts_gate: bool = True
    max_depth: int = 1
    timeout_seconds: int = 10
    raw_snippets_redacted: bool = False
    recursive_factor_search: bool = False
    allowed_factor_types: tuple[str, ...] = ()
    separate_objective_facts_from_crowding: bool = False
    outputs: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    search_derived_cannot_satisfy_execution_fact: bool = False
    required_execution_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ensure_bool("must_pass_facts_gate", self.must_pass_facts_gate)
        ensure_positive_int("max_depth", self.max_depth)
        ensure_positive_int("timeout_seconds", self.timeout_seconds)
        ensure_bool("raw_snippets_redacted", self.raw_snippets_redacted)
        ensure_bool("recursive_factor_search", self.recursive_factor_search)
        ensure_bool("separate_objective_facts_from_crowding", self.separate_objective_facts_from_crowding)
        ensure_bool(
            "search_derived_cannot_satisfy_execution_fact",
            self.search_derived_cannot_satisfy_execution_fact,
        )
        set_tuple("allowed_factor_types", self.allowed_factor_types, ALLOWED_FACTOR_TYPES)
        set_tuple("outputs", self.outputs, ALLOWED_SENTIMENT_OUTPUTS)
        set_tuple("required_fields", self.required_fields, ALLOWED_MACRO_FIELDS)
        set_tuple("required_execution_facts", self.required_execution_facts, EXECUTION_FACTS)

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "must_pass_facts_gate": self.must_pass_facts_gate,
            "max_depth": self.max_depth,
            "timeout_seconds": self.timeout_seconds,
        }
        if self.raw_snippets_redacted:
            payload["raw_snippets_redacted"] = True
        if self.recursive_factor_search:
            payload["recursive_factor_search"] = True
        if self.allowed_factor_types:
            payload["allowed_factor_types"] = list(self.allowed_factor_types)
        if self.separate_objective_facts_from_crowding:
            payload["separate_objective_facts_from_crowding"] = True
        if self.outputs:
            payload["outputs"] = list(self.outputs)
        if self.required_fields:
            payload["required_fields"] = list(self.required_fields)
        if self.search_derived_cannot_satisfy_execution_fact:
            payload["search_derived_cannot_satisfy_execution_fact"] = True
        if self.required_execution_facts:
            payload["required_execution_facts"] = list(self.required_execution_facts)
        return payload


@dataclass(frozen=True, init=False)
class SkillToolResult:
    """Structured skill result boundary."""

    skill_name: str
    task_id: str
    status: str
    result_type: str
    source_type: str
    can_satisfy_execution_fact: bool
    trace_ref: str | None
    decision_effect: str
    _evidence_candidates: tuple[EvidenceCandidate, ...]
    _constraints: SkillConstraints
    _missing_inputs: tuple[str, ...]
    _fact_refs: dict[str, str]

    def __init__(
        self,
        *,
        skill_name: str,
        task_id: str,
        status: str,
        result_type: str,
        source_type: str,
        can_satisfy_execution_fact: bool,
        evidence_candidates: Sequence[EvidenceCandidate] | None = None,
        fact_refs: Mapping[str, Any] | None = None,
        constraints: SkillConstraints | None = None,
        missing_inputs: Sequence[str] | None = None,
        trace_ref: str | None = None,
        decision_effect: str = "none",
    ) -> None:
        object.__setattr__(self, "skill_name", skill_name)
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "result_type", result_type)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "can_satisfy_execution_fact", can_satisfy_execution_fact)
        object.__setattr__(self, "trace_ref", trace_ref)
        object.__setattr__(self, "decision_effect", decision_effect)
        object.__setattr__(
            self,
            "_evidence_candidates",
            coerce_optional_evidence_candidates(evidence_candidates, candidate_type=EvidenceCandidate),
        )
        object.__setattr__(
            self,
            "_constraints",
            coerce_constraints(constraints, constraints_type=SkillConstraints),
        )
        object.__setattr__(self, "_missing_inputs", coerce_optional_missing_inputs(missing_inputs))
        object.__setattr__(self, "_fact_refs", coerce_optional_fact_refs(fact_refs))
        validate_skill_tool_result(self)

    @property
    def evidence_candidates(self) -> tuple[EvidenceCandidate, ...]:
        return self._evidence_candidates

    @property
    def constraints(self) -> dict[str, Any]:
        return self._constraints.to_public_dict()

    @property
    def missing_inputs(self) -> tuple[str, ...]:
        return self._missing_inputs

    @property
    def fact_refs(self) -> dict[str, str]:
        return dict(self._fact_refs)

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "skill_name": self.skill_name,
            "task_id": self.task_id,
            "status": self.status,
            "decision_effect": self.decision_effect,
            "result_type": self.result_type,
            "source_type": self.source_type,
            "can_satisfy_execution_fact": self.can_satisfy_execution_fact,
            "evidence_candidates": [candidate.to_public_dict() for candidate in self._evidence_candidates],
            "constraints": self._constraints.to_public_dict(),
            "missing_inputs": list(self._missing_inputs),
            "trace_ref": self.trace_ref,
        }
        if self._fact_refs:
            payload["fact_refs"] = dict(self._fact_refs)
        return payload
