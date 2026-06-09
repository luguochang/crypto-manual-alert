from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from typing import Any


_ALLOWED_SOURCE_TYPES = {"exchange_native", "official_or_event_pool", "search_derived", "fixture"}
_ALLOWED_SOURCE_TIERS = {"exchange", "official", "search", "fixture"}
_ALLOWED_STATUSES = {"ok", "partial", "error", "failed"}
_ALLOWED_FRESHNESS = {"fresh", "stale", "unknown"}


@dataclass(frozen=True)
class ToolCallArtifact:
    """Replayable ref/hash envelope for one controlled skill call."""

    tool_call_id: str
    skill_name: str
    status: str
    source_type: str
    source_tier: str
    retrieved_at: datetime
    freshness_status: str
    result_ref: str
    output_hash: str
    can_satisfy_execution_fact: bool
    fact_refs: dict[str, str] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    @classmethod
    def from_skill_result(
        cls,
        skill_result: Any,
        *,
        tool_call_id: str,
        result_ref: str,
        retrieved_at: datetime,
        source_tier: str,
        freshness_status: str,
    ) -> "ToolCallArtifact":
        public_result = skill_result.to_public_dict()
        return cls(
            tool_call_id=tool_call_id,
            skill_name=str(public_result.get("skill_name")),
            status=str(public_result.get("status")),
            source_type=str(public_result.get("source_type")),
            source_tier=source_tier,
            retrieved_at=retrieved_at,
            freshness_status=freshness_status,
            result_ref=result_ref,
            output_hash=_stable_output_hash(public_result),
            can_satisfy_execution_fact=bool(public_result.get("can_satisfy_execution_fact")),
            fact_refs=_string_mapping(public_result.get("fact_refs")),
            error=None,
        )

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "tool_call_id": self.tool_call_id,
            "skill_name": self.skill_name,
            "status": self.status,
            "source_type": self.source_type,
            "source_tier": self.source_tier,
            "retrieved_at": self.retrieved_at.isoformat(),
            "freshness_status": self.freshness_status,
            "result_ref": self.result_ref,
            "output_hash": self.output_hash,
            "can_satisfy_execution_fact": self.can_satisfy_execution_fact,
        }
        if self.fact_refs:
            payload["fact_refs"] = dict(self.fact_refs)
        if self.error:
            payload["error_type"] = str(self.error.get("type") or "ToolCallError")
            payload["error_hash"] = _stable_output_hash(self.error)
        return payload

    def __post_init__(self) -> None:
        _ensure_string("tool_call_id", self.tool_call_id)
        _ensure_string("skill_name", self.skill_name)
        _ensure_string("status", self.status)
        _ensure_string("source_type", self.source_type)
        _ensure_string("source_tier", self.source_tier)
        _ensure_string("freshness_status", self.freshness_status)
        _ensure_string("result_ref", self.result_ref)
        _ensure_string("output_hash", self.output_hash)
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError("status is not allowed for ToolCallArtifact")
        if self.source_type not in _ALLOWED_SOURCE_TYPES:
            raise ValueError("source_type is not allowed for ToolCallArtifact")
        if self.source_tier not in _ALLOWED_SOURCE_TIERS:
            raise ValueError("source_tier is not allowed for ToolCallArtifact")
        if self.freshness_status not in _ALLOWED_FRESHNESS:
            raise ValueError("freshness_status is not allowed for ToolCallArtifact")
        if not isinstance(self.can_satisfy_execution_fact, bool):
            raise ValueError("can_satisfy_execution_fact must be a boolean")
        for key, value in self.fact_refs.items():
            _ensure_string("fact_refs.key", key)
            _ensure_string(f"fact_refs.{key}", value)
        if self.can_satisfy_execution_fact and self.source_type != "exchange_native":
            raise ValueError("execution fact satisfaction requires exchange_native source_type")
        if self.can_satisfy_execution_fact and self.freshness_status != "fresh":
            raise ValueError("execution fact satisfaction requires fresh source data")


def _stable_output_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _ensure_string(field_name: str, value: Any) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def _string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if key is not None and item is not None
    }
