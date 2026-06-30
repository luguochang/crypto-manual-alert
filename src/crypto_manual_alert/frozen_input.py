from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION = 1
KIND_DECISION_PROMPT_PACKET = "decision_prompt_packet"
SECRET_KEY_HINTS = (
    "api_key",
    "authorization",
    "secret",
    "token",
    "passphrase",
    "device_key",
    "bark",
    "raw_decision",
    "raw_payload",
    "request_json",
    "response_json",
)


@dataclass(frozen=True)
class FrozenInput:
    """可回放输入快照。payload 只保存送入决策模型的脱敏结构化输入。"""

    frozen_input_hash: str
    input_payload: dict[str, Any]
    public_summary: dict[str, Any]
    source_trace_id: str | None = None
    source_badcase_id: int | None = None
    schema_version: int = SCHEMA_VERSION
    kind: str = KIND_DECISION_PROMPT_PACKET
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_plan_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "sha256": self.frozen_input_hash,
            "payload": self.input_payload,
            "public_summary": self.public_summary,
        }

    def to_store_row(self) -> dict[str, Any]:
        return {
            "frozen_input_hash": self.frozen_input_hash,
            "schema_version": self.schema_version,
            "kind": self.kind,
            "source_trace_id": self.source_trace_id or "",
            "source_badcase_id": self.source_badcase_id or 0,
            "input_payload": self.input_payload,
            "public_summary": self.public_summary,
            "metadata": self.metadata,
        }


def freeze_decision_prompt_packet(
    prompt_packet: dict[str, Any],
    *,
    source_trace_id: str | None = None,
    source_badcase_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> FrozenInput:
    payload = sanitize_for_frozen_input(prompt_packet)
    frozen_hash = stable_hash(payload)
    return FrozenInput(
        frozen_input_hash=frozen_hash,
        input_payload=payload,
        public_summary=_public_summary(payload),
        source_trace_id=source_trace_id,
        source_badcase_id=source_badcase_id,
        metadata=metadata or {},
    )


def frozen_input_from_plan_payload(
    plan_payload: dict[str, Any],
    *,
    source_trace_id: str,
    source_badcase_id: int,
) -> FrozenInput | None:
    frozen = plan_payload.get("frozen_input")
    if not isinstance(frozen, dict):
        return None
    payload = frozen.get("payload")
    if not isinstance(payload, dict):
        return None
    clean_payload = sanitize_for_frozen_input(payload)
    frozen_hash = str(frozen.get("sha256") or plan_payload.get("frozen_input_hash") or stable_hash(clean_payload))
    return FrozenInput(
        frozen_input_hash=frozen_hash,
        input_payload=clean_payload,
        public_summary=_public_summary(clean_payload),
        source_trace_id=source_trace_id,
        source_badcase_id=source_badcase_id,
        schema_version=int(frozen.get("schema_version") or SCHEMA_VERSION),
        kind=str(frozen.get("kind") or KIND_DECISION_PROMPT_PACKET),
        metadata={"source": "plan_run.payload.frozen_input"},
    )


def sanitize_for_frozen_input(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(hint in normalized for hint in SECRET_KEY_HINTS):
                sanitized[str(key)] = "<redacted>"
            else:
                sanitized[str(key)] = sanitize_for_frozen_input(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_frozen_input(item) for item in value]
    return copy.deepcopy(value)


def stable_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _public_summary(payload: dict[str, Any]) -> dict[str, Any]:
    market = payload.get("market_snapshot") if isinstance(payload, dict) else {}
    skill = payload.get("skill") if isinstance(payload, dict) else {}
    research = payload.get("research") if isinstance(payload, dict) else None
    points = market.get("points") if isinstance(market, dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": market.get("symbol") if isinstance(market, dict) else None,
        "point_names": sorted(points) if isinstance(points, dict) else [],
        "unavailable": market.get("unavailable") if isinstance(market, dict) else [],
        "skill": {
            "name": skill.get("name") if isinstance(skill, dict) else None,
            "sha256": skill.get("sha256") if isinstance(skill, dict) else None,
        },
        "has_research": isinstance(research, dict),
        "top_level_keys": sorted(payload),
    }
