from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.artifacts.evidence import EVENT_CONFIDENCE_CAP, MACRO_CONFIDENCE_CAP, MACRO_REQUIRED_FIELDS
from crypto_manual_alert.orchestration.contracts import SubTask

from .common import claim, contribution, mapping, point_source, required_confirmations, source_type


EVENT_STATUS_FACT = "active_event_status"
MACRO_EVENT_FACT = "macro_event"
DEFAULT_BLOCKED_ACTION_CLASSES = ("opening", "trigger", "flip")


class MacroEventAgent:
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        snapshot = mapping(input_view.get("snapshot"))
        facts_gate = mapping(input_view.get("facts_gate"))
        points = mapping(snapshot.get("points"))
        evidence_packets = _evidence_packets_by_type(input_view.get("evidence_packets"))

        event_point = _point_or_packet(points, evidence_packets, EVENT_STATUS_FACT)
        macro_point = _point_or_packet(points, evidence_packets, MACRO_EVENT_FACT)
        event_status = _event_status_payload(event_point)
        macro_event = _macro_event_payload(macro_point)

        missing_event_facts = _missing_event_facts(facts_gate, event_point)
        missing_macro_facts = _missing_macro_facts(facts_gate, macro_point)
        missing_facts = [*missing_event_facts, *missing_macro_facts]
        blocked_action_classes = list(facts_gate.get("blocked_action_classes") or [])
        if missing_event_facts and not blocked_action_classes:
            blocked_action_classes = list(DEFAULT_BLOCKED_ACTION_CLASSES)

        confidence_cap = _confidence_cap(facts_gate, missing_event_facts, missing_macro_facts)
        confidence_cap_reasons = _confidence_cap_reasons(facts_gate, missing_event_facts, missing_macro_facts)

        claims = _claims(event_point, macro_point)
        constraints: dict[str, Any] = {
            "decision_effect": "none",
            "event_status": event_status,
            "macro_event": macro_event,
            "surprise": macro_event.get("surprise"),
            "market_reaction": macro_event.get("market_reaction"),
            "event_compression": _event_compression(missing_event_facts, missing_macro_facts, event_status, macro_event),
            "missing_event_facts": missing_event_facts,
            "missing_macro_facts": missing_macro_facts,
            "blocked_action_classes": blocked_action_classes,
            "required_confirmations": required_confirmations(missing_facts),
        }
        if confidence_cap is not None:
            constraints["confidence_cap"] = confidence_cap
        if confidence_cap_reasons:
            constraints["confidence_cap_reasons"] = confidence_cap_reasons

        conflicts = [
            *(f"missing_event_fact:{name}" for name in missing_event_facts),
            *(f"missing_macro_fact:{name}" for name in missing_macro_facts),
        ]
        return contribution(
            subtask,
            status="ok",
            summary=f"macro event audit missing={','.join(missing_facts) or 'none'}",
            claims=claims,
            constraints=constraints,
            conflicts=conflicts,
            missing_facts=missing_facts,
        )


def _evidence_packets_by_type(value: Any) -> dict[str, dict[str, Any]]:
    packets: dict[str, dict[str, Any]] = {}
    if not isinstance(value, list):
        return packets
    for item in value:
        packet = mapping(item)
        data_type = str(packet.get("data_type") or packet.get("name") or "")
        if data_type in {EVENT_STATUS_FACT, MACRO_EVENT_FACT} and data_type not in packets:
            packets[data_type] = packet
    return packets


def _point_or_packet(
    points: dict[str, Any],
    packets: dict[str, dict[str, Any]],
    name: str,
) -> dict[str, Any]:
    if name in points:
        return mapping(points.get(name))
    packet = packets.get(name)
    if not packet:
        return {}
    return {
        "value": packet.get("value"),
        "source": packet.get("source_type") or packet.get("source_name"),
        "status": packet.get("freshness_status") or "unknown",
        "evidence_id": packet.get("evidence_id"),
    }


def _event_status_payload(point: dict[str, Any]) -> dict[str, Any]:
    if not point:
        return {}
    value = mapping(point.get("value"))
    return {
        "status": value.get("status"),
        "refreshed_at": value.get("refreshed_at"),
        "source": source_type(str(point.get("source") or "")),
        "point_status": str(point.get("status") or "unknown"),
    }


def _macro_event_payload(point: dict[str, Any]) -> dict[str, Any]:
    if not point:
        return {}
    value = mapping(point.get("value"))
    payload = {field_name: value.get(field_name) for field_name in MACRO_REQUIRED_FIELDS}
    payload["source"] = source_type(str(point.get("source") or ""))
    payload["point_status"] = str(point.get("status") or "unknown")
    return payload


def _missing_event_facts(facts_gate: dict[str, Any], event_point: dict[str, Any]) -> list[str]:
    missing = [str(item) for item in facts_gate.get("missing_event_facts") or []]
    if not event_point and EVENT_STATUS_FACT not in missing:
        missing.append(EVENT_STATUS_FACT)
    return list(dict.fromkeys(missing))


def _missing_macro_facts(facts_gate: dict[str, Any], macro_point: dict[str, Any]) -> list[str]:
    missing = [str(item) for item in facts_gate.get("missing_macro_facts") or []]
    if not macro_point:
        missing.extend(f"{MACRO_EVENT_FACT}.{field_name}" for field_name in MACRO_REQUIRED_FIELDS)
        return sorted(dict.fromkeys(missing))

    value = mapping(macro_point.get("value"))
    for field_name in MACRO_REQUIRED_FIELDS:
        item = value.get(field_name)
        if item is None or item == "" or item == {} or item == []:
            missing.append(f"{MACRO_EVENT_FACT}.{field_name}")
    return sorted(dict.fromkeys(missing))


def _confidence_cap(
    facts_gate: dict[str, Any],
    missing_event_facts: list[str],
    missing_macro_facts: list[str],
) -> float | None:
    values = [
        _as_float(facts_gate.get("confidence_cap")),
        EVENT_CONFIDENCE_CAP if missing_event_facts else None,
        MACRO_CONFIDENCE_CAP if missing_macro_facts else None,
    ]
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _confidence_cap_reasons(
    facts_gate: dict[str, Any],
    missing_event_facts: list[str],
    missing_macro_facts: list[str],
) -> list[str]:
    reasons = [str(item) for item in facts_gate.get("confidence_cap_reasons") or []]
    if missing_event_facts and "facts_gate:event_status_stale" not in reasons:
        reasons.append("facts_gate:event_status_stale")
    if missing_macro_facts and "facts_gate:macro_surprise_incomplete" not in reasons:
        reasons.append("facts_gate:macro_surprise_incomplete")
    return list(dict.fromkeys(reasons))


def _event_compression(
    missing_event_facts: list[str],
    missing_macro_facts: list[str],
    event_status: dict[str, Any],
    macro_event: dict[str, Any],
) -> str:
    if missing_event_facts:
        return "event_status_missing"
    if missing_macro_facts:
        return "macro_surprise_incomplete"
    if event_status and macro_event:
        return "active_macro_event"
    return "no_macro_event_context"


def _claims(event_point: dict[str, Any], macro_point: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if event_point:
        result.append(
            claim(
                f"event status source={source_type(point_source({EVENT_STATUS_FACT: event_point}, EVENT_STATUS_FACT))}",
                str(event_point.get("evidence_id") or "snapshot.points.active_event_status"),
                "neutral",
            )
        )
    if macro_point:
        macro_event = _macro_event_payload(macro_point)
        result.append(
            claim(
                f"macro event surprise={macro_event.get('surprise') or 'unknown'} source={macro_event.get('source')}",
                str(macro_point.get("evidence_id") or "snapshot.points.macro_event"),
                "neutral",
            )
        )
    return result


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
