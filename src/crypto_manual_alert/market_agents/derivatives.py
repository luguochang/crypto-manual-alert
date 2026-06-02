from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.artifacts.evidence import SEARCH_CONFIDENCE_CAP
from crypto_manual_alert.orchestration.contracts import SubTask

from .common import claim, contribution, mapping, point_source, required_confirmations, source_type


CORE_DERIVATIVE_FACTS = ("funding_rate", "open_interest", "liquidation_map", "basis")
OPTIONAL_DERIVATIVE_FACTS = ("long_short_ratio", "taker_flow")
DERIVATIVE_FACTS = (*CORE_DERIVATIVE_FACTS, *OPTIONAL_DERIVATIVE_FACTS)
DEFAULT_BLOCKED_ACTION_CLASSES = ("opening", "trigger", "flip")


class DerivativesAgent:
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        snapshot = mapping(input_view.get("snapshot"))
        facts_gate = mapping(input_view.get("facts_gate"))
        points = mapping(snapshot.get("points"))
        missing_facts = [name for name in CORE_DERIVATIVE_FACTS if name not in points]
        derivatives = {
            name: _derivative_point(points, name)
            for name in DERIVATIVE_FACTS
            if name in points
        }
        claims = [
            claim(
                f"derivatives {name} status={derivatives[name]['status']} source={derivatives[name]['source']}",
                f"snapshot.points.{name}",
                "neutral",
            )
            for name in derivatives
        ]
        constraints: dict[str, Any] = {
            "decision_effect": "none",
            "derivatives": derivatives,
            "crowding_state": _crowding_state(derivatives),
            "missing_derivative_facts": list(missing_facts),
            "blocked_action_classes": list(facts_gate.get("blocked_action_classes") or []),
            "required_confirmations": required_confirmations(missing_facts),
        }
        conflicts = [f"missing_derivative_fact:{name}" for name in missing_facts]
        if missing_facts:
            constraints["confidence_cap"] = SEARCH_CONFIDENCE_CAP
            if not constraints["blocked_action_classes"]:
                constraints["blocked_action_classes"] = list(DEFAULT_BLOCKED_ACTION_CLASSES)
        return contribution(
            subtask,
            status="ok",
            summary=f"derivatives audit missing={','.join(missing_facts) or 'none'}",
            claims=claims,
            constraints=constraints,
            conflicts=conflicts,
            missing_facts=missing_facts,
        )


def _derivative_point(points: dict[str, Any], name: str) -> dict[str, Any]:
    point = mapping(points.get(name))
    result: dict[str, Any] = {
        "value": point.get("value"),
        "source": source_type(point_source(points, name)),
        "status": str(point.get("status") or "unknown"),
    }
    if "delta" in point:
        result["delta"] = point["delta"]
    return result


def _crowding_state(derivatives: dict[str, dict[str, Any]]) -> str:
    funding = _as_float(derivatives.get("funding_rate", {}).get("value"))
    oi_delta = _as_float(derivatives.get("open_interest", {}).get("delta"))
    long_short = _as_float(derivatives.get("long_short_ratio", {}).get("value"))
    if (funding is not None and funding >= 0.0005) and (
        (oi_delta is not None and oi_delta >= 0.05) or (long_short is not None and long_short >= 1.5)
    ):
        return "crowded_longs"
    if (funding is not None and funding <= -0.0005) and (
        (oi_delta is not None and oi_delta >= 0.05) or (long_short is not None and long_short <= 0.7)
    ):
        return "crowded_shorts"
    return "not_enough_derivatives_context" if len(derivatives) < len(CORE_DERIVATIVE_FACTS) else "balanced_or_unclear"


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
