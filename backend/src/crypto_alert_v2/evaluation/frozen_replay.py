from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenReplayPacket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["frozen-replay-v1"] = "frozen-replay-v1"
    request: dict[str, Any]
    versions: dict[str, Any]
    market: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    gates: dict[str, Any]
    observed_output: dict[str, Any]
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    allow_live_fetch: Literal[False] = False
    allow_live_side_effects: Literal[False] = False

    @model_validator(mode="after")
    def require_matching_source_hash(self) -> "FrozenReplayPacket":
        if self.source_hash != frozen_replay_hash(self.payload_for_hash()):
            raise ValueError("frozen replay source_hash does not match its payload")
        return self

    def payload_for_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request": self.request,
            "versions": self.versions,
            "market": self.market,
            "evidence": self.evidence,
            "gates": self.gates,
            "observed_output": self.observed_output,
            "allow_live_fetch": self.allow_live_fetch,
            "allow_live_side_effects": self.allow_live_side_effects,
        }


class RuleJudgeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    structure: float = Field(ge=0, le=1)
    evidence: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    product_output: float = Field(ge=0, le=1)
    reasons: tuple[str, ...] = ()


def freeze_replay_packet(
    *,
    request: Mapping[str, Any],
    versions: Mapping[str, Any],
    market: Mapping[str, Any],
    evidence: tuple[Mapping[str, Any], ...],
    gates: Mapping[str, Any],
    observed_output: Mapping[str, Any],
) -> FrozenReplayPacket:
    payload = {
        "schema_version": "frozen-replay-v1",
        "request": dict(request),
        "versions": dict(versions),
        "market": dict(market),
        "evidence": tuple(dict(item) for item in evidence),
        "gates": dict(gates),
        "observed_output": dict(observed_output),
        "allow_live_fetch": False,
        "allow_live_side_effects": False,
    }
    return FrozenReplayPacket(
        **payload,
        source_hash=frozen_replay_hash(payload),
    )


def frozen_replay_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def rule_judge(packet: FrozenReplayPacket) -> RuleJudgeResult:
    reasons: list[str] = []
    terminal_status = packet.observed_output.get("terminal_status")
    structure = 1.0 if terminal_status in {"succeeded", "failed", "blocked"} else 0.0
    if structure == 0:
        reasons.append("missing_terminal_status")

    evidence_gate = packet.gates.get("evidence")
    sufficient = (
        evidence_gate.get("sufficient")
        if isinstance(evidence_gate, Mapping)
        else None
    )
    evidence_score = 1.0 if sufficient is True and packet.evidence else 0.0
    if evidence_score == 0:
        reasons.append("evidence_gate_or_sources_missing")

    risk_gate = packet.gates.get("risk")
    allowed = risk_gate.get("allowed") if isinstance(risk_gate, Mapping) else None
    risk_score = 1.0 if isinstance(allowed, bool) else 0.0
    if risk_score == 0:
        reasons.append("risk_gate_missing")

    action = packet.observed_output.get("main_action")
    product_output = 1.0 if isinstance(action, str) and bool(action) else 0.0
    if product_output == 0:
        reasons.append("main_action_missing")

    return RuleJudgeResult(
        structure=structure,
        evidence=evidence_score,
        risk=risk_score,
        product_output=product_output,
        reasons=tuple(reasons),
    )


__all__ = [
    "FrozenReplayPacket",
    "RuleJudgeResult",
    "freeze_replay_packet",
    "frozen_replay_hash",
    "rule_judge",
]
