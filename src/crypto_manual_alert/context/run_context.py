from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from crypto_manual_alert.artifacts.hashing import stable_hash
from crypto_manual_alert.artifacts.contributions import (
    contribution_safety_ref_fields,
    tool_call_artifact_ref_fields,
)
from crypto_manual_alert.context.request import DecisionRequest
from crypto_manual_alert.context.memory_firewall import sanitize_memory_snapshot


RESERVED_SECTIONS = {"final_decision", "risk_verdict", "journal", "notification"}
APPEND_WRITER_ROLES = {"workflow", "tool", "worker"}
LEAD_PLAN_WRITER_ROLES = {"lead"}
DECISION_INPUT_WRITER_ROLES = {"decision_input_builder"}
GATE_RESULT_WRITER_ROLES = {"gate"}
MEMORY_SNAPSHOT_WRITER_ROLES = {"session_memory", "workflow"}
RESERVED_SECTION_WRITER_ROLES = {"final"}


class ReservedContextWriteError(ValueError):
    def __init__(self, section_name: str, writer_role: str):
        super().__init__(f"{writer_role} cannot write reserved context section: {section_name}")
        self.section_name = section_name
        self.writer_role = writer_role


@dataclass(frozen=True)
class SideEffectPolicy:
    """Side-effect boundary for one run.

    manual/scheduled runs may use the legacy production path; eval, replay,
    and postmortem runs must remain side-effect free.
    """

    allow_production_journal_write: bool
    allow_notification_intent: bool

    @classmethod
    def from_run_type(cls, run_type: str) -> "SideEffectPolicy":
        allows_production_side_effects = run_type in {"manual", "scheduled"}
        return cls(
            allow_production_journal_write=allows_production_side_effects,
            allow_notification_intent=allows_production_side_effects,
        )

    def to_public_dict(self) -> dict[str, bool]:
        return {
            "allow_production_journal_write": self.allow_production_journal_write,
            "allow_notification_intent": self.allow_notification_intent,
        }


@dataclass
class DecisionRunContext:
    """Single context object for one decision run.

    It carries request semantics, side-effect policy, and orchestration
    artifacts. It does not fetch market data, call LLMs, or make trade
    decisions.
    """

    run_id: str
    request: DecisionRequest
    side_effect_policy: SideEffectPolicy
    _evidence_packets: list[dict[str, Any]] = field(default_factory=list)
    _agent_contributions: list[dict[str, Any]] = field(default_factory=list)
    _lead_plan: dict[str, Any] | None = None
    _decision_input: dict[str, Any] | None = None
    _gate_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    _reserved_sections: dict[str, Any] = field(default_factory=dict)
    _memory_snapshot: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, request: DecisionRequest) -> "DecisionRunContext":
        return cls(
            run_id=f"run_{uuid4().hex}",
            request=request,
            side_effect_policy=SideEffectPolicy.from_run_type(request.run_type),
            _memory_snapshot=_empty_memory_snapshot(request),
        )

    @property
    def symbol(self) -> str:
        return self.request.symbol

    @property
    def query_text(self) -> str:
        return self.request.query_text

    @property
    def horizon(self) -> str | None:
        return self.request.horizon

    @property
    def session_id(self) -> str | None:
        return self.request.session_id

    @property
    def evidence_packets(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._evidence_packets)

    @property
    def agent_contributions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._agent_contributions)

    @property
    def lead_plan(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._lead_plan)

    @property
    def decision_input(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._decision_input)

    @property
    def gate_results(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._gate_results)

    @property
    def reserved_sections(self) -> dict[str, Any]:
        return copy.deepcopy(self._reserved_sections)

    @property
    def memory_snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._memory_snapshot)

    def append_evidence(self, evidence_packet: dict[str, Any], *, writer_role: str | None = None) -> None:
        self._validate_append_writer("evidence_store", writer_role)
        self._evidence_packets.append(copy.deepcopy(evidence_packet))

    def append_contribution(self, contribution: dict[str, Any], *, writer_role: str | None = None) -> None:
        self._validate_append_writer("contribution_store", writer_role)
        self._agent_contributions.append(copy.deepcopy(contribution))

    def set_lead_plan(self, lead_plan: dict[str, Any], *, writer_role: str | None = None) -> None:
        self._validate_named_writer("lead_plan", writer_role, LEAD_PLAN_WRITER_ROLES)
        self._lead_plan = copy.deepcopy(lead_plan)

    def set_decision_input(self, decision_input: dict[str, Any], *, writer_role: str | None = None) -> None:
        self._validate_named_writer("decision_input", writer_role, DECISION_INPUT_WRITER_ROLES)
        self._decision_input = copy.deepcopy(decision_input)

    def set_gate_result(
        self,
        gate_name: str,
        gate_result: dict[str, Any],
        *,
        writer_role: str | None = None,
    ) -> None:
        self._validate_named_writer(str(gate_name), writer_role, GATE_RESULT_WRITER_ROLES)
        if str(gate_name) in RESERVED_SECTIONS:
            raise ReservedContextWriteError(str(gate_name), writer_role or "unknown")
        self._gate_results[str(gate_name)] = copy.deepcopy(gate_result)

    def set_memory_snapshot(self, memory_snapshot: dict[str, Any], *, writer_role: str | None = None) -> None:
        self._validate_named_writer("memory_snapshot", writer_role, MEMORY_SNAPSHOT_WRITER_ROLES)
        self._memory_snapshot = copy.deepcopy(_safe_memory_snapshot(memory_snapshot))

    def write_section(self, section_name: str, payload: dict[str, Any], *, writer_role: str) -> None:
        if writer_role == "worker":
            raise ReservedContextWriteError(section_name, writer_role)
        if section_name == "lead_plan":
            self.set_lead_plan(payload, writer_role=writer_role)
            return
        if section_name == "decision_input":
            self.set_decision_input(payload, writer_role=writer_role)
            return
        if section_name in RESERVED_SECTIONS:
            self._validate_named_writer(section_name, writer_role, RESERVED_SECTION_WRITER_ROLES)
            self._reserved_sections[section_name] = copy.deepcopy(payload)
            return
        self.set_gate_result(section_name, payload, writer_role=writer_role)

    def _validate_append_writer(self, section_name: str, writer_role: str | None) -> None:
        role = writer_role or "unknown"
        if role not in APPEND_WRITER_ROLES:
            raise ReservedContextWriteError(section_name, role)

    def _validate_named_writer(self, section_name: str, writer_role: str | None, allowed_roles: set[str]) -> None:
        role = writer_role or "unknown"
        if role not in allowed_roles:
            raise ReservedContextWriteError(section_name, role)

    def to_public_summary(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "run_type": self.request.run_type,
            "symbol": self.request.symbol,
            "query_text": self.request.query_text,
            "query_semantics": self.request.query_semantics(),
            "horizon": self.request.horizon,
            "session_id": self.request.session_id,
            "manual_only": self.request.manual_only,
            "position": copy.deepcopy(self.request.position),
            "risk_mode": self.request.risk_mode,
            "memory_snapshot": copy.deepcopy(self._memory_snapshot),
            "side_effect_policy": self.side_effect_policy.to_public_dict(),
        }

    def to_artifact_summary(self) -> dict[str, object]:
        return {
            "evidence_count": len(self._evidence_packets),
            "contribution_count": len(self._agent_contributions),
            "has_lead_plan": self._lead_plan is not None,
            "has_decision_input": self._decision_input is not None,
            "gate_result_names": sorted(self._gate_results),
            "reserved_sections": sorted(self._reserved_sections),
            "evidence_refs": [_evidence_ref(packet) for packet in self._evidence_packets],
            "contribution_refs": [
                _contribution_ref(contribution)
                for contribution in self._agent_contributions
            ],
            "lead_plan_ref": _lead_plan_ref(self._lead_plan),
            "decision_input_ref": _input_ref(self._decision_input),
            "gate_result_refs": {
                name: _gate_result_ref(result)
                for name, result in sorted(self._gate_results.items())
                if _gate_result_ref(result)
            },
        }


def _evidence_ref(packet: dict[str, Any]) -> dict[str, Any]:
    ref = {
        key: packet.get(key)
        for key in ("evidence_id", "data_type", "source_type", "source_url", "observed_at", "retrieved_at")
        if packet.get(key) is not None
    }
    ref["artifact_hash"] = stable_hash(packet)
    return ref


def _contribution_ref(contribution: dict[str, Any]) -> dict[str, Any]:
    ref = {
        key: contribution.get(key)
        for key in (
            "contribution_id",
            "agent_name",
            "task_id",
            "status",
            "required",
            "input_ref",
            "output_hash",
            "trace_ref",
        )
        if contribution.get(key) is not None
    }
    if isinstance(contribution.get("evidence_ids"), list):
        ref["evidence_ids"] = [str(item) for item in contribution.get("evidence_ids") or []]
    tool_refs = tool_call_artifact_ref_fields(contribution)
    if tool_refs:
        ref["tool_call_artifact_refs"] = tool_refs
    ref.update(contribution_safety_ref_fields(contribution))
    if contribution.get("migration_stage") is not None:
        ref["migration_stage"] = contribution.get("migration_stage")
    ref["artifact_hash"] = stable_hash(contribution)
    return ref


def _lead_plan_ref(lead_plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(lead_plan, dict):
        return None
    ref = {key: lead_plan.get(key) for key in ("plan_id", "mode", "decision_effect") if lead_plan.get(key) is not None}
    ref["artifact_hash"] = stable_hash(lead_plan)
    return ref


def _input_ref(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    ref = {
        key: payload.get(key)
        for key in (
            "artifact_ref",
            "input_ref",
            "input_hash",
            "mode",
            "decision_effect",
            "production_final_input",
            "passed",
            "ready",
        )
        if payload.get(key) is not None
    }
    if not ref:
        return None
    ref["artifact_hash"] = stable_hash(payload)
    return ref


def _gate_result_ref(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    ref = _input_ref(payload)
    if ref:
        return ref
    return {"artifact_hash": stable_hash(payload)}


def _empty_memory_snapshot(request: DecisionRequest) -> dict[str, Any]:
    return {
        "snapshot_id": f"memory:{request.session_id or 'none'}:empty",
        "session_id": request.session_id,
        "allowed_fields": {},
        "recent_turn_count": 0,
        "summary": None,
        "long_term_memory_refs": [],
    }


def _safe_memory_snapshot(memory_snapshot: dict[str, Any]) -> dict[str, Any]:
    return sanitize_memory_snapshot(memory_snapshot)
