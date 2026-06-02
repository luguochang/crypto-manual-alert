from __future__ import annotations

import hashlib
import json
from typing import Any

from crypto_manual_alert.artifacts.contributions import AgentContribution
from crypto_manual_alert.orchestration.contracts import SubTask


def contribution(
    subtask: SubTask,
    *,
    status: str,
    summary: str,
    claims: list[dict[str, Any]],
    constraints: dict[str, Any],
    conflicts: list[str],
    missing_facts: list[str],
) -> AgentContribution:
    payload = {
        "agent_name": subtask.agent_name,
        "task_id": subtask.task_id,
        "status": status,
        "summary": summary,
        "claims": claims,
        "constraints": constraints,
        "conflicts": conflicts,
        "missing_facts": missing_facts,
    }
    return AgentContribution(
        contribution_id=f"shadow_swarm:{subtask.task_id}",
        agent_name=subtask.agent_name,
        status=status,
        required=subtask.required,
        summary=summary,
        claims=claims,
        constraints=constraints,
        conflicts=conflicts,
        missing_facts=missing_facts,
        input_ref=subtask.input_ref,
        output_hash=hash_payload(payload),
        failure_policy_applied="none",
        trace_ref=subtask.trace_ref,
        migration_stage="shadow_swarm",
    )


def claim(
    text: str,
    evidence_ref: str,
    side: str,
    *,
    confidence: str = "low",
    strength: float | None = None,
) -> dict[str, Any]:
    payload = {
        "claim": text,
        "claim_type": "audit_observation",
        "side": side,
        "evidence_ids": [evidence_ref],
        "confidence": confidence,
        "freshness": "mixed",
    }
    if strength is not None:
        payload["strength"] = strength
    return payload


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def research_titles(research: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for results in mapping(research.get("results")).values():
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and item.get("title"):
                    titles.append(str(item["title"]))
    return titles


def research_snippets(research: dict[str, Any]) -> list[str]:
    snippets: list[str] = []
    for results in mapping(research.get("results")).values():
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and item.get("snippet"):
                    snippets.append(str(item["snippet"]))
    return snippets


def missing_execution_facts(input_view: dict[str, Any]) -> list[str]:
    facts_gate = mapping(input_view.get("facts_gate"))
    missing = [str(item) for item in facts_gate.get("missing_execution_facts") or []]
    snapshot = mapping(input_view.get("snapshot"))
    points = mapping(snapshot.get("points"))
    for name in ("mark", "index", "order_book"):
        if name not in points:
            missing.append(name)
    return list(dict.fromkeys(missing))


def point_source(points: dict[str, Any], name: str) -> str:
    point = points.get(name)
    if isinstance(point, dict):
        return str(point.get("source") or "unknown")
    return "missing"


def source_type(source: str) -> str:
    normalized = source.strip().lower().replace("-", "_")
    if normalized in {"", "missing"}:
        return "missing"
    if any(hint in normalized for hint in ("okx", "binance", "bybit", "coinbase", "kraken", "deribit")):
        return "exchange_native"
    if any(hint in normalized for hint in ("federal_reserve", "fomc", "bls", "bea", "treasury", "sec", "cftc", "official")):
        return "official"
    if "event_pool" in normalized:
        return "event_pool"
    if any(hint in normalized for hint in ("coinglass", "glassnode", "cryptoquant", "laevitas", "hyblock")):
        return "aggregator_api"
    if "search" in normalized or "web" in normalized:
        return "search_derived"
    return "unknown"


def data_freshness(points: dict[str, Any]) -> dict[str, str]:
    freshness: dict[str, str] = {}
    for name, point in points.items():
        if isinstance(point, dict):
            freshness[str(name)] = str(point.get("status") or "unknown")
    return freshness


def required_confirmations(missing_facts: list[str]) -> list[str]:
    return [f"confirm {name}" for name in missing_facts]


def execution_hard_block(facts_gate: dict[str, Any], missing_facts: list[str]) -> bool:
    return bool(
        missing_facts
        or facts_gate.get("blocked_action_classes")
        or facts_gate.get("severity") == "hard_fail"
    )


def hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
