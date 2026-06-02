from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.contracts import SubTask

from .common import (
    claim,
    contribution,
    data_freshness,
    mapping,
    missing_execution_facts,
    point_source,
    source_type,
)


EXECUTION_FACT_NAMES = {"mark", "index", "order_book"}


class DataQualityLocalWorker:
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        snapshot = mapping(input_view.get("snapshot"))
        facts_gate = mapping(input_view.get("facts_gate"))
        points = mapping(snapshot.get("points"))
        missing_facts = missing_execution_facts(input_view)
        claims = [
            claim(f"{name} source={point_source(points, name)}", f"snapshot.points.{name}", "neutral")
            for name in ("mark", "index", "order_book")
        ]
        unavailable = [str(item) for item in snapshot.get("unavailable") or []]
        missing_facts.extend(_execution_fact_from_unavailable(item) for item in unavailable)
        missing_facts = list(dict.fromkeys(item for item in missing_facts if item))
        source_quality = _source_quality(points)
        execution_coverage = {
            name: name in points
            for name in ("mark", "index", "order_book")
        }
        staleness_details = _staleness_details(source_quality)
        conflict_details = _conflicting_fact_details(facts_gate)
        constraints = {
            "decision_effect": "none",
            "execution_fact_coverage": execution_coverage,
            "source_quality": source_quality,
            "staleness_details": staleness_details,
            "conflicting_fact_details": conflict_details,
            "missing_execution_facts": missing_facts,
            "blocked_action_classes": list(facts_gate.get("blocked_action_classes") or []),
            "required_confirmations": _required_confirmations(missing_facts),
            "data_freshness": data_freshness(points),
        }
        conflicts = [f"missing_execution_fact:{name}" for name in missing_facts]
        conflicts.extend(f"conflicting_execution_fact:{item['fact_name']}" for item in conflict_details)
        return contribution(
            subtask,
            status="ok",
            summary=f"data quality audit missing={','.join(missing_facts) or 'none'}",
            claims=claims,
            constraints=constraints,
            conflicts=conflicts,
            missing_facts=missing_facts,
        )


def _source_quality(points: dict[str, Any]) -> dict[str, dict[str, Any]]:
    quality: dict[str, dict[str, Any]] = {}
    for name in ("mark", "index", "order_book"):
        point = points.get(name)
        if isinstance(point, dict):
            source = str(point.get("source") or "unknown")
            status = str(point.get("status") or "unknown")
        else:
            source = "missing"
            status = "missing"
        source_kind = source_type(source)
        quality[name] = {
            "source": source,
            "source_type": source_kind,
            "status": status,
            "can_satisfy_execution_fact": source_kind == "exchange_native" and status == "ok",
        }
    return quality


def _execution_fact_from_unavailable(item: str) -> str:
    fact_name = item.split(":", 1)[0].strip()
    return fact_name if fact_name in EXECUTION_FACT_NAMES else ""


def _staleness_details(source_quality: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for name in ("mark", "index", "order_book"):
        quality = source_quality[name]
        if quality["status"] == "missing":
            details.append(
                {
                    "fact_name": name,
                    "status": "missing",
                    "source_type": "missing",
                    "reason": "missing",
                }
            )
            continue
        if not quality["can_satisfy_execution_fact"]:
            reason = (
                "not_exchange_native_execution_fact"
                if quality["source_type"] != "exchange_native"
                else "not_fresh_execution_fact"
            )
            details.append(
                {
                    "fact_name": name,
                    "status": str(quality["status"]),
                    "source_type": str(quality["source_type"]),
                    "reason": reason,
                }
            )
    return details


def _conflicting_fact_details(facts_gate: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"fact_name": str(name), "reason": "facts_gate_conflict"}
        for name in facts_gate.get("conflicting_execution_facts") or []
    ]


def _required_confirmations(missing_facts: list[str]) -> list[str]:
    return [
        f"confirm {name} from exchange-native source"
        for name in missing_facts
    ]
