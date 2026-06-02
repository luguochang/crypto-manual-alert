from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.artifacts.evidence import SEARCH_CONFIDENCE_CAP
from crypto_manual_alert.orchestration.contracts import SubTask

from .common import claim, contribution, mapping, research_snippets, research_titles


class SentimentCrowdingLocalWorker:
    def run(self, subtask: SubTask, input_view: dict[str, Any]) -> AgentContribution:
        research = mapping(input_view.get("research"))
        snapshot = mapping(input_view.get("snapshot"))
        facts_gate = mapping(input_view.get("facts_gate"))
        points = mapping(snapshot.get("points"))
        titles = research_titles(research)
        snippets = research_snippets(research)
        sentiment_text = " ".join([*titles, *snippets]).lower()
        drivers = _crowding_drivers(points, sentiment_text)
        crowding = bool(drivers)
        research_refs = _research_refs(research)
        missing_sentiment_facts = _missing_sentiment_facts(points, research)
        summary = "search-derived sentiment"
        if crowding:
            summary = "search-derived sentiment shows crowded positioning"
        elif titles:
            summary = f"search-derived sentiment observed: {titles[0]}"
        claims = [
            claim(f"sentiment source observed: {title}", "research.results", "neutral")
            for title in titles
        ]
        if crowding:
            claims.append(_counter_claim(_crowding_evidence_ids(drivers, research_refs)))
        confidence_cap = _confidence_cap(facts_gate, missing_sentiment_facts, bool(titles))
        required = _required_confirmations(missing_sentiment_facts, crowding)
        constraints = {
            "decision_effect": "none",
            "sentiment_source_quality": _source_quality(points, titles),
            "crowding_state": _crowding_state(drivers, research_refs),
            "priced_in_assessment": _priced_in_assessment(sentiment_text, research_refs, crowding),
            "reflexivity_risk": _reflexivity_risk(drivers, research_refs, crowding),
            "counter_thesis": [_counter_thesis(_crowding_evidence_ids(drivers, research_refs))] if crowding else [],
            "missing_sentiment_facts": missing_sentiment_facts,
            "required_confirmations": required,
        }
        if confidence_cap is not None:
            constraints["confidence_cap"] = confidence_cap
        if missing_sentiment_facts:
            constraints["confidence_cap_reasons"] = ["facts_gate:sentiment_or_positioning_incomplete"]
        elif titles:
            constraints["confidence_cap_reasons"] = ["facts_gate:sentiment_uses_search_context"]
        return contribution(
            subtask,
            status="ok",
            summary=summary,
            claims=claims,
            constraints=constraints,
            conflicts=_conflicts(crowding, missing_sentiment_facts),
            missing_facts=missing_sentiment_facts,
        )


MarketSentimentLocalWorker = SentimentCrowdingLocalWorker


def _point_value(points: dict[str, Any], name: str) -> Any:
    point = points.get(name)
    if isinstance(point, dict):
        return point.get("value")
    return None


def _research_refs(research: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for query_name, results in mapping(research.get("results")).items():
        if not isinstance(results, list):
            continue
        for index, item in enumerate(results):
            if isinstance(item, dict) and (item.get("title") or item.get("snippet")):
                refs.append(f"research.{query_name}[{index}]")
    return refs


def _crowding_drivers(points: dict[str, Any], sentiment_text: str) -> list[str]:
    drivers: list[str] = []
    funding = _as_float(_point_value(points, "funding_rate"))
    if funding is not None and funding > 0:
        drivers.append("positive_funding")
    open_interest = _point_value(points, "open_interest")
    if _open_interest_is_expanding(open_interest):
        drivers.append("open_interest_expansion")
    if any(term in sentiment_text for term in ("crowded", "crowding", "funding", "longs", "shorts")):
        drivers.append("search_crowding_language")
    return drivers


def _open_interest_is_expanding(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(item).lower() in {"up", "rising", "increase", "increasing", "expanded"} for item in value.values())
    return "up" in str(value).lower() or "rising" in str(value).lower()


def _crowding_state(drivers: list[str], research_refs: list[str]) -> dict[str, Any]:
    if not drivers:
        return {"state": "unknown", "drivers": [], "evidence_ids": [], "confidence": "low"}
    return {
        "state": "crowded_long" if "positive_funding" in drivers else "crowded",
        "drivers": drivers,
        "evidence_ids": _crowding_evidence_ids(drivers, research_refs),
        "confidence": "medium",
    }


def _priced_in_assessment(sentiment_text: str, research_refs: list[str], crowding: bool) -> dict[str, Any]:
    if not research_refs:
        return {"status": "unknown", "reason": "insufficient sentiment and positioning evidence", "evidence_ids": []}
    if crowding and any(term in sentiment_text for term in ("expected", "already", "consensus")):
        return {
            "status": "partly_priced_in",
            "reason": "search context already frames ETF flow as consensus-positive while derivatives are crowded",
            "evidence_ids": research_refs[:2],
        }
    return {
        "status": "unresolved",
        "reason": "search context is present but pricing saturation is not confirmed",
        "evidence_ids": research_refs[:2],
    }


def _reflexivity_risk(drivers: list[str], research_refs: list[str], crowding: bool) -> dict[str, Any]:
    if not crowding:
        return {"level": "unknown", "mechanism": "insufficient evidence", "evidence_ids": []}
    return {
        "level": "elevated",
        "mechanism": "one-sided positioning can make an objectively positive catalyst fade in the short term",
        "evidence_ids": _crowding_evidence_ids(drivers, research_refs),
    }


def _counter_thesis(evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "claim": "crowded long positioning can fade an objectively positive catalyst in the short term",
        "side": "bearish",
        "evidence_ids": evidence_ids,
        "strength": 0.66,
    }


def _counter_claim(evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "claim": "crowded long positioning can fade an objectively positive catalyst in the short term",
        "claim_type": "audit_observation",
        "side": "bearish",
        "evidence_ids": evidence_ids,
        "confidence": "medium",
        "freshness": "mixed",
        "strength": 0.66,
    }


def _crowding_evidence_ids(drivers: list[str], research_refs: list[str]) -> list[str]:
    evidence_ids: list[str] = []
    if "positive_funding" in drivers:
        evidence_ids.append("snapshot.funding_rate")
    if "open_interest_expansion" in drivers:
        evidence_ids.append("snapshot.open_interest")
    if research_refs:
        evidence_ids.append(research_refs[-1])
    return evidence_ids


def _missing_sentiment_facts(points: dict[str, Any], research: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for name in ("funding_rate", "open_interest"):
        if name not in points:
            missing.append(name)
    if not research_titles(research):
        missing.append("research.results")
    return missing


def _required_confirmations(missing_sentiment_facts: list[str], crowding: bool) -> list[str]:
    if missing_sentiment_facts:
        return [f"confirm {name}" for name in missing_sentiment_facts]
    if crowding:
        return [
            "confirm crowding with exchange-native funding and open interest",
            "confirm whether ETF flow surprise is already priced in",
        ]
    return ["confirm sentiment context with fresh evidence"]


def _confidence_cap(
    facts_gate: dict[str, Any],
    missing_sentiment_facts: list[str],
    has_search_context: bool,
) -> float | None:
    candidates = [_as_float(facts_gate.get("confidence_cap"))]
    if missing_sentiment_facts or has_search_context:
        candidates.append(SEARCH_CONFIDENCE_CAP)
    present = [item for item in candidates if item is not None]
    return min(present) if present else None


def _source_quality(points: dict[str, Any], titles: list[str]) -> str:
    has_structured = "funding_rate" in points or "open_interest" in points
    if has_structured and titles:
        return "mixed_structured_and_search"
    if titles:
        return "search_derived"
    return "missing"


def _conflicts(crowding: bool, missing_sentiment_facts: list[str]) -> list[Any]:
    conflicts: list[Any] = [f"missing_sentiment_fact:{item}" for item in missing_sentiment_facts]
    if crowding:
        conflicts.append(
            {
                "conflict_id": "objective_catalyst_vs_crowded_positioning",
                "summary": "objective catalyst conflicts with crowded positioning",
                "sides": ["bullish", "bearish"],
            }
        )
    if not conflicts:
        conflicts.append("sentiment_crowding_audit_clean")
    return conflicts


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
