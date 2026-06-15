from __future__ import annotations

import hashlib
import json
from typing import Any


def hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def strip_raw_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_raw_fields(item)
            for key, item in value.items()
            if not _is_raw_field(key)
        }
    if isinstance(value, list):
        return [strip_raw_fields(item) for item in value]
    return value


def rule_ids(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for hit in payload.get("rule_hits") or []:
        if isinstance(hit, dict) and hit.get("rule_id"):
            ids.append(str(hit["rule_id"]))
    return ids


def _is_raw_field(key: Any) -> bool:
    normalized = str(key).lower()
    return normalized.startswith("raw") or normalized in {"payload", "prompt", "completion"}
