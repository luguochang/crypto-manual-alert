from __future__ import annotations

import copy
from typing import Any


SAFE_MEMORY_ALLOWED_FIELDS = {
    "asset_focus",
    "current_position",
    "default_assets",
    "explicit_constraints",
    "focus_assets",
    "language",
    "last_missing_facts",
    "last_plan_summary",
    "position",
    "position_slots",
    "preferred_horizon",
    "risk_preference",
    "time_horizon_preference",
    "user_position",
    "user_preferences",
}

FACT_LIKE_MEMORY_FIELDS = {
    "basis",
    "current_price",
    "etf_flow",
    "funding",
    "funding_rate",
    "index",
    "index_price",
    "last_model_conclusion",
    "last_price",
    "liquidation_heatmap",
    "macro_event_status",
    "mark",
    "mark_price",
    "news_status",
    "oi",
    "open_interest",
    "order_book",
    "previous_decision",
    "previous_final_action",
    "price",
    "ticker",
    "volume",
}

FACT_QUARANTINE_WARNING = (
    "memory_snapshot.quarantined_fact_like_fields: memory is context only, not live market evidence"
)


def sanitize_memory_snapshot(memory_snapshot: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = memory_snapshot.get("allowed_fields")
    long_term_refs = memory_snapshot.get("long_term_memory_refs")
    sanitized_fields, quarantined_fields = sanitize_memory_allowed_fields(allowed_fields)
    safe: dict[str, Any] = {
        "snapshot_id": memory_snapshot.get("snapshot_id"),
        "session_id": memory_snapshot.get("session_id"),
        "allowed_fields": sanitized_fields,
        "recent_turn_count": (
            memory_snapshot.get("recent_turn_count")
            if isinstance(memory_snapshot.get("recent_turn_count"), int)
            else 0
        ),
        "summary": memory_snapshot.get("summary") if isinstance(memory_snapshot.get("summary"), str) else None,
        "long_term_memory_refs": [
            {
                key: ref.get(key)
                for key in ("memory_id", "memory_hash", "score")
                if isinstance(ref, dict) and ref.get(key) is not None
            }
            for ref in long_term_refs
            if isinstance(ref, dict)
        ]
        if isinstance(long_term_refs, list)
        else [],
    }
    if quarantined_fields:
        safe["quarantined_fields"] = quarantined_fields
        safe["memory_warnings"] = _memory_warnings(memory_snapshot, include_quarantine_warning=True)
    else:
        warnings = _memory_warnings(memory_snapshot, include_quarantine_warning=False)
        if warnings:
            safe["memory_warnings"] = warnings
    return safe


def sanitize_memory_allowed_fields(allowed_fields: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(allowed_fields, dict):
        return {}, []

    safe: dict[str, Any] = {}
    quarantined: list[str] = []
    for key in sorted(allowed_fields):
        key_name = str(key)
        path = f"allowed_fields.{key_name}"
        if key_name not in SAFE_MEMORY_ALLOWED_FIELDS or _is_fact_like_field(key_name):
            quarantined.append(path)
            continue
        sanitized_value = _sanitize_allowed_value(allowed_fields[key], path, quarantined)
        if sanitized_value is not _QUARANTINED:
            safe[key_name] = sanitized_value
    return safe, sorted(set(quarantined))


_QUARANTINED = object()


def _sanitize_allowed_value(value: Any, path: str, quarantined: list[str]) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key in sorted(value):
            key_name = str(key)
            child_path = f"{path}.{key_name}"
            if _is_fact_like_field(key_name):
                quarantined.append(child_path)
                continue
            sanitized = _sanitize_allowed_value(value[key], child_path, quarantined)
            if sanitized is not _QUARANTINED:
                safe[key_name] = sanitized
        return safe
    if isinstance(value, list):
        return [
            sanitized
            for index, item in enumerate(value)
            if (sanitized := _sanitize_allowed_value(item, f"{path}[{index}]", quarantined)) is not _QUARANTINED
        ]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    quarantined.append(path)
    return _QUARANTINED


def _is_fact_like_field(field_name: str) -> bool:
    normalized = field_name.strip().lower()
    return normalized in FACT_LIKE_MEMORY_FIELDS


def _memory_warnings(memory_snapshot: dict[str, Any], *, include_quarantine_warning: bool) -> list[str]:
    raw_warnings = memory_snapshot.get("memory_warnings")
    warnings = []
    if isinstance(raw_warnings, list):
        warnings = [warning for warning in raw_warnings if isinstance(warning, str) and warning.strip()]
    if include_quarantine_warning:
        warnings.append(FACT_QUARANTINE_WARNING)
    return sorted(set(warnings))
