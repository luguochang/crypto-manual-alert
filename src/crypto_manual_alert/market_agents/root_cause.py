from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.artifacts.evidence import SEARCH_CONFIDENCE_CAP
from crypto_manual_alert.orchestration.contracts import SubTask

from .common import claim, contribution, mapping, research_titles


class RootCauseLocalWorker:
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        research = mapping(input_view.get("research"))
        snapshot = mapping(input_view.get("snapshot"))
        facts_gate = mapping(input_view.get("facts_gate"))
        points = mapping(snapshot.get("points"))
        titles = research_titles(research)
        summary = f"{input_view.get('symbol')} pre-decision root-cause audit"
        evidence_refs = _evidence_refs(points, research)
        missing_causal_facts = _missing_causal_facts(points, research, facts_gate)
        direct_causes = _direct_causes(points)
        second_order_causes = _second_order_causes(points, research, direct_causes)
        graph = _root_cause_graph(direct_causes, second_order_causes)
        required = _required_confirmations(missing_causal_facts, direct_causes, second_order_causes)
        claims = [
            claim("pre-decision catalyst review has no final action", "shadow.input_scope", "neutral"),
        ]
        if titles:
            claims.append(claim(f"research catalyst observed: {titles[0]}", "research.results", "neutral"))
        if direct_causes:
            direct = direct_causes[0]
            claims.append(
                claim(
                    f"{direct['description']} is a likely direct catalyst",
                    str(direct["evidence_ids"][0]),
                    "bullish" if _positive_direct_cause(direct) else "neutral",
                    confidence="medium",
                    strength=0.6,
                )
            )
        confidence_cap = _confidence_cap(facts_gate, missing_causal_facts, bool(titles))
        confidence_cap_reasons = _confidence_cap_reasons(facts_gate, missing_causal_facts, bool(titles))
        constraints = {
            "decision_effect": "none",
            "root_cause_graph": graph,
            "direct_causes": direct_causes,
            "second_order_causes": second_order_causes,
            "evidence_refs": evidence_refs,
            "missing_causal_facts": missing_causal_facts,
            "required_confirmations": required,
        }
        if confidence_cap is not None:
            constraints["confidence_cap"] = confidence_cap
        if confidence_cap_reasons:
            constraints["confidence_cap_reasons"] = confidence_cap_reasons
        return contribution(
            subtask,
            status="ok",
            summary=summary,
            claims=claims,
            constraints=constraints,
            conflicts=_conflicts(missing_causal_facts, bool(titles)),
            missing_facts=missing_causal_facts,
        )


def _point_value(points: dict[str, Any], name: str) -> Any:
    point = points.get(name)
    if isinstance(point, dict):
        return point.get("value")
    return None


def _evidence_refs(points: dict[str, Any], research: dict[str, Any]) -> list[str]:
    refs = [
        f"snapshot.{name}"
        for name in ("active_event_status", "macro_event", "funding_rate", "open_interest")
        if name in points
    ]
    refs.extend(_research_refs(research))
    return refs


def _research_refs(research: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for query_name, results in mapping(research.get("results")).items():
        if not isinstance(results, list):
            continue
        for index, item in enumerate(results):
            if isinstance(item, dict) and (item.get("title") or item.get("snippet")):
                refs.append(f"research.{query_name}[{index}]")
    return refs


def _missing_causal_facts(
    points: dict[str, Any],
    research: dict[str, Any],
    facts_gate: dict[str, Any],
) -> list[str]:
    missing = [str(item) for item in facts_gate.get("missing_event_facts") or []]
    missing.extend(str(item) for item in facts_gate.get("missing_macro_facts") or [])
    if "active_event_status" not in points:
        missing.append("active_event_status")
    if "macro_event" not in points:
        missing.append("macro_event")
    if not research_titles(research):
        missing.append("research.results")
    return _canonical_missing_order(list(dict.fromkeys(missing)))


def _canonical_missing_order(missing: list[str]) -> list[str]:
    preferred = ("active_event_status", "macro_event", "research.results")
    ordered = [item for item in preferred if item in missing]
    ordered.extend(item for item in missing if item not in preferred)
    return ordered


def _direct_causes(points: dict[str, Any]) -> list[dict[str, Any]]:
    macro_event = _point_value(points, "macro_event")
    if not isinstance(macro_event, dict):
        return []
    event_name = str(macro_event.get("event_name") or "macro event")
    actual = macro_event.get("actual")
    description = f"{event_name}: actual {actual}" if actual not in (None, "") else event_name
    return [
        {
            "cause_id": "macro_event_surprise",
            "factor_type": "macro_event",
            "description": description,
            "evidence_ids": ["snapshot.macro_event"],
            "confidence": "medium",
        }
    ]


def _second_order_causes(
    points: dict[str, Any],
    research: dict[str, Any],
    direct_causes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not direct_causes:
        return []
    causes: list[dict[str, Any]] = []
    if "funding_rate" in points and "open_interest" in points:
        causes.append(
            {
                "cause_id": "derivatives_crowding_amplifier",
                "factor_type": "derivatives",
                "description": "positive funding and rising open interest can amplify the observed catalyst",
                "depends_on": ["macro_event_surprise"],
                "evidence_ids": ["snapshot.funding_rate", "snapshot.open_interest"],
                "confidence": "medium",
            }
        )
    refs = _research_refs(research)
    titles = research_titles(research)
    if refs and titles:
        causes.append(
            {
                "cause_id": "search_context_confirmation",
                "factor_type": "research",
                "description": f"search-derived context reports {titles[0]}",
                "depends_on": ["macro_event_surprise"],
                "evidence_ids": [refs[0]],
                "confidence": "low",
            }
        )
    return causes


def _root_cause_graph(
    direct_causes: list[dict[str, Any]],
    second_order_causes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = []
    for item in direct_causes:
        graph.append(
            {
                "node_id": item["cause_id"],
                "factor_type": item["factor_type"],
                "evidence_ids": list(item["evidence_ids"]),
                "depends_on": [],
            }
        )
    for item in second_order_causes:
        graph.append(
            {
                "node_id": item["cause_id"],
                "factor_type": item["factor_type"],
                "evidence_ids": list(item["evidence_ids"]),
                "depends_on": list(item.get("depends_on") or []),
            }
        )
    return graph


def _required_confirmations(
    missing_causal_facts: list[str],
    direct_causes: list[dict[str, Any]],
    second_order_causes: list[dict[str, Any]],
) -> list[str]:
    if missing_causal_facts:
        return [f"confirm {name}" for name in missing_causal_facts]
    required: list[str] = []
    if direct_causes:
        required.append("confirm macro_event_surprise with official/event-pool source")
    if any(item.get("factor_type") == "derivatives" for item in second_order_causes):
        required.append("confirm derivatives_crowding_amplifier with exchange or aggregator data")
    return required


def _confidence_cap(
    facts_gate: dict[str, Any],
    missing_causal_facts: list[str],
    has_search_context: bool,
) -> float | None:
    candidates = [_as_float(facts_gate.get("confidence_cap"))]
    if missing_causal_facts or has_search_context:
        candidates.append(SEARCH_CONFIDENCE_CAP)
    present = [item for item in candidates if item is not None]
    return min(present) if present else None


def _confidence_cap_reasons(
    facts_gate: dict[str, Any],
    missing_causal_facts: list[str],
    has_search_context: bool,
) -> list[str]:
    reasons = [str(item) for item in facts_gate.get("confidence_cap_reasons") or []]
    if has_search_context and "facts_gate:root_cause_uses_search_context" not in reasons:
        reasons.append("facts_gate:root_cause_uses_search_context")
    if missing_causal_facts and "facts_gate:root_cause_missing_causal_facts" not in reasons:
        reasons.append("facts_gate:root_cause_missing_causal_facts")
    return reasons


def _conflicts(missing_causal_facts: list[str], has_search_context: bool) -> list[str]:
    conflicts = [f"missing_causal_fact:{item}" for item in missing_causal_facts]
    if has_search_context:
        conflicts.append("root_cause_search_context_requires_confirmation")
    return conflicts


def _positive_direct_cause(cause_payload: dict[str, Any]) -> bool:
    return "above" in str(cause_payload.get("description", "")).lower() or "positive" in str(
        cause_payload.get("description", "")
    ).lower()


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
