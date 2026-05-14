from __future__ import annotations

from typing import Any


def project_evidence_sources(evidence_packets: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in _list(evidence_packets):
        packet = _mapping(item)
        evidence_ref = packet.get("evidence_id") or packet.get("id")
        if evidence_ref is None:
            continue
        sources.append(
            {
                "evidence_ref": str(evidence_ref),
                "claim_ref": _claim_ref(packet),
                "source_url": packet.get("source_url"),
                "source_type": packet.get("source_type"),
                "source_tier": packet.get("source_tier"),
                "observed_at": packet.get("observed_at"),
                "retrieved_at": packet.get("retrieved_at"),
                "freshness_status": packet.get("freshness_status"),
                "can_satisfy_execution_fact": packet.get("can_satisfy_execution_fact"),
            }
        )
    return sources


def project_source_freshness(
    evidence_sources: list[dict[str, Any]],
    *,
    facts_gate: dict[str, Any],
    tool_calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, Any, str], dict[str, Any]] = {}
    for item in [*evidence_sources, *(tool_calls or [])]:
        source_type = item.get("source_type")
        freshness_status = item.get("freshness_status")
        if source_type is None or freshness_status is None:
            continue
        key = (str(source_type), item.get("source_tier"), str(freshness_status))
        group = groups.setdefault(
            key,
            {
                "source_type": key[0],
                "source_tier": key[1],
                "freshness_status": key[2],
                "count": 0,
                "can_satisfy_execution_fact_count": 0,
            },
        )
        group["count"] += 1
        if item.get("can_satisfy_execution_fact") is True:
            group["can_satisfy_execution_fact_count"] += 1

    rows = sorted(
        groups.values(),
        key=lambda value: (
            str(value.get("source_type")),
            str(value.get("source_tier")),
            str(value.get("freshness_status")),
        ),
    )
    missing_execution_facts = [str(item) for item in _list(facts_gate.get("missing_execution_facts"))]
    if missing_execution_facts:
        rows.append(
            {
                "source_type": "execution_fact",
                "source_tier": "missing",
                "freshness_status": "missing",
                "count": len(missing_execution_facts),
                "can_satisfy_execution_fact_count": 0,
                "missing_execution_facts": missing_execution_facts,
            }
        )
    return rows


def _claim_ref(packet: dict[str, Any]) -> str | None:
    trace_ref = packet.get("trace_ref")
    if isinstance(trace_ref, str) and trace_ref:
        return trace_ref
    name = packet.get("name") or packet.get("data_type")
    if name is None:
        return None
    source_type = str(packet.get("source_type") or "")
    prefix = "research" if source_type in {"search_derived", "web_derived"} else "market"
    return f"{prefix}:{name}"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

