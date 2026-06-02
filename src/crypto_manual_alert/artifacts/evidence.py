from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.research_pipeline import ResearchAudit


EXECUTION_FACT_TYPES = {"mark", "index", "order_book"}
AUXILIARY_FACT_TYPES = {"funding", "open_interest", "liquidation"}
EVENT_FACT_TYPES = {"active_event_status"}
MACRO_FACT_TYPES = {"macro_event"}
MACRO_REQUIRED_FIELDS = ("actual", "consensus", "market_reaction", "released_at", "surprise", "event_name")
FALLBACK_SOURCE_TYPES = {"aggregator_api", "web_derived", "search_derived"}
EXCHANGE_SOURCE_HINTS = ("okx", "binance", "bybit", "coinbase", "kraken", "deribit")
AGGREGATOR_SOURCE_HINTS = ("coinglass", "glassnode", "cryptoquant", "laevitas", "hyblock")
OFFICIAL_SOURCE_HINTS = ("federal_reserve", "fomc", "bls", "bea", "treasury", "sec", "cftc")
EVENT_POOL_SOURCE_HINTS = ("event_pool",)
SEARCH_SOURCE_HINTS = ("search", "web", "duckduckgo", "responses")
SEARCH_CONFIDENCE_CAP = 0.58
DERIVATIVES_CONFIDENCE_CAP = 0.58
EVENT_CONFIDENCE_CAP = 0.55
MACRO_CONFIDENCE_CAP = 0.58
FRESHNESS_TTL_SECONDS = {
    "mark": 120,
    "index": 120,
    "order_book": 30,
    "funding": 3600,
    "open_interest": 300,
    "liquidation": 300,
    "candles": 7200,
    "last": 120,
    "active_event_status": 900,
    "macro_event": 900,
}
SOURCE_TIERS = {
    "exchange_native": 1,
    "official": 1,
    "event_pool": 2,
    "aggregator_api": 2,
    "web_derived": 3,
    "search_derived": 4,
    "fixture": 9,
}


@dataclass(frozen=True)
class EvidencePacket:
    """Structured evidence boundary.

    EvidencePacket normalizes market and research outputs before they can be
    consumed by later gates. It does not fetch live data, score trades, or
    decide whether an action is allowed.
    """

    evidence_id: str
    name: str
    symbol: str
    data_type: str
    value: Any
    observed_at: datetime | None
    retrieved_at: datetime
    source_type: str
    source_tier: int
    source_name: str
    source_url: str | None
    freshness_status: str
    can_satisfy_execution_fact: bool
    confidence_cap: float | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    claims: list[str] = field(default_factory=list)
    trace_ref: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "evidence_id": self.evidence_id,
            "name": self.name,
            "symbol": self.symbol,
            "data_type": self.data_type,
            "value": self.value,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "retrieved_at": self.retrieved_at.isoformat(),
            "source_type": self.source_type,
            "source_tier": self.source_tier,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "freshness_status": self.freshness_status,
            "can_satisfy_execution_fact": self.can_satisfy_execution_fact,
            "confidence_cap": self.confidence_cap,
            "claims": list(self.claims),
            "trace_ref": self.trace_ref,
        }
        if self.fallback_used:
            payload["fallback_used"] = True
            payload["fallback_reason"] = self.fallback_reason
        return payload


@dataclass(frozen=True)
class FactsGateResult:
    """Execution-fact check result.

    This gate only checks whether mark/index/order_book can come from
    executable fact sources; full risk control belongs to later gates.
    """

    passed: bool
    severity: str
    missing_execution_facts: list[str]
    blocked_action_classes: list[str]
    reasons: list[str]
    missing_auxiliary_facts: list[str] = field(default_factory=list)
    missing_event_facts: list[str] = field(default_factory=list)
    missing_macro_facts: list[str] = field(default_factory=list)
    confidence_cap: float | None = None
    confidence_cap_reasons: list[str] = field(default_factory=list)
    conflicting_execution_facts: list[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_source_types: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "missing_execution_facts": list(self.missing_execution_facts),
            "blocked_action_classes": list(self.blocked_action_classes),
            "reasons": list(self.reasons),
            "missing_auxiliary_facts": list(self.missing_auxiliary_facts),
            "missing_event_facts": list(self.missing_event_facts),
            "missing_macro_facts": list(self.missing_macro_facts),
            "confidence_cap": self.confidence_cap,
            "confidence_cap_reasons": list(self.confidence_cap_reasons),
            "conflicting_execution_facts": list(self.conflicting_execution_facts),
            "fallback_used": self.fallback_used,
            "fallback_source_types": list(self.fallback_source_types),
        }


def from_market_snapshot(snapshot: MarketSnapshot) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    for name, point in sorted(snapshot.points.items()):
        source_type = _source_type_from_name(point.source)
        observed_at = _datetime_from_timestamp_ms(point.timestamp_ms)
        data_type = _data_type_from_point_name(point.name or name)
        freshness_status = _freshness_status(
            point.status,
            _freshness_observed_at(point.value, observed_at, data_type),
            snapshot.fetched_at,
            data_type,
        )
        can_satisfy_execution_fact = (
            data_type in EXECUTION_FACT_TYPES
            and source_type == "exchange_native"
            and freshness_status == "fresh"
        )
        fallback_used = _fallback_used(data_type, source_type)
        packets.append(
            EvidencePacket(
                evidence_id=_evidence_id(
                    "market",
                    snapshot.symbol,
                    name,
                    point.source,
                    point.timestamp_ms,
                    point.value,
                ),
                name=name,
                symbol=snapshot.symbol,
                data_type=data_type,
                value=point.value,
                observed_at=observed_at,
                retrieved_at=snapshot.fetched_at,
                source_type=source_type,
                source_tier=_source_tier(source_type),
                source_name=point.source,
                source_url=None,
                freshness_status=freshness_status,
                can_satisfy_execution_fact=can_satisfy_execution_fact,
                confidence_cap=SEARCH_CONFIDENCE_CAP if fallback_used or source_type == "search_derived" else None,
                fallback_used=fallback_used,
                fallback_reason=f"source_fallback:{source_type}" if fallback_used else None,
                claims=[],
                trace_ref=f"market:{name}",
            )
        )
    return packets


def check_execution_facts(packets: list[EvidencePacket]) -> FactsGateResult:
    """检查 opening/trigger/flip 前必须具备的核心执行事实。"""

    eligible_execution = {
        packet.data_type
        for packet in packets
        if packet.data_type in EXECUTION_FACT_TYPES and packet.can_satisfy_execution_fact
    }
    eligible_auxiliary = {
        packet.data_type
        for packet in packets
        if packet.data_type in AUXILIARY_FACT_TYPES and _can_satisfy_auxiliary_fact(packet)
    }
    eligible_event = {
        packet.data_type
        for packet in packets
        if packet.data_type in EVENT_FACT_TYPES and _can_satisfy_event_fact(packet)
    }
    conflicting = _conflicting_execution_facts(packets)
    eligible_without_conflicts = eligible_execution - set(conflicting)
    missing = sorted(EXECUTION_FACT_TYPES - eligible_without_conflicts)
    missing_auxiliary = sorted(AUXILIARY_FACT_TYPES - eligible_auxiliary)
    missing_event = sorted(EVENT_FACT_TYPES - eligible_event)
    missing_macro = _missing_macro_facts(packets)
    reasons = [_reason_for_missing_fact(name, packets, conflicting) for name in missing]
    reasons.extend(_reason_for_missing_fact(name, packets, conflicting) for name in missing_event)
    reasons.extend(f"{name}: missing" for name in missing_macro)
    fallback_source_types = sorted(
        {
            packet.source_type
            for packet in packets
            if packet.fallback_used and packet.data_type in EXECUTION_FACT_TYPES | AUXILIARY_FACT_TYPES
        }
    )
    confidence_cap_reasons: list[str] = []
    if missing_auxiliary:
        confidence_cap_reasons.append("facts_gate:derivatives_facts_missing")
    if missing_event:
        confidence_cap_reasons.append("facts_gate:event_status_stale")
    if missing_macro:
        confidence_cap_reasons.append("facts_gate:macro_surprise_incomplete")
    if fallback_source_types:
        confidence_cap_reasons.append("facts_gate:fallback_source_used")
    confidence_cap = _min_optional(
        [
            DERIVATIVES_CONFIDENCE_CAP if missing_auxiliary or fallback_source_types else None,
            EVENT_CONFIDENCE_CAP if missing_event else None,
            MACRO_CONFIDENCE_CAP if missing_macro else None,
        ]
    )
    severity = "hard_fail" if missing or missing_event else "soft_downgrade" if confidence_cap_reasons else "ok"
    return FactsGateResult(
        passed=not missing and not missing_event,
        severity=severity,
        missing_execution_facts=missing,
        blocked_action_classes=[] if not missing and not missing_event else ["opening", "trigger", "flip"],
        reasons=reasons,
        missing_auxiliary_facts=missing_auxiliary,
        missing_event_facts=missing_event,
        missing_macro_facts=missing_macro,
        confidence_cap=confidence_cap,
        confidence_cap_reasons=confidence_cap_reasons,
        conflicting_execution_facts=conflicting,
        fallback_used=bool(fallback_source_types),
        fallback_source_types=fallback_source_types,
    )


def from_research_audit(symbol: str, audit: ResearchAudit) -> list[EvidencePacket]:
    packets: list[EvidencePacket] = []
    retrieved_at = datetime.now(timezone.utc)
    for query_name, results in sorted(audit.results.items()):
        for index, result in enumerate(results):
            packets.append(
                EvidencePacket(
                    evidence_id=_evidence_id(
                        "research",
                        symbol,
                        query_name,
                        result.source,
                        result.url,
                        result.title,
                        result.snippet,
                    ),
                    name=query_name,
                    symbol=symbol,
                    data_type="news",
                    value=result.to_public_dict(),
                    observed_at=None,
                    retrieved_at=retrieved_at,
                    source_type="search_derived",
                    source_tier=_source_tier("search_derived"),
                    source_name=result.source,
                    source_url=result.url,
                    freshness_status="unknown",
                    can_satisfy_execution_fact=False,
                    confidence_cap=SEARCH_CONFIDENCE_CAP,
                    claims=[claim for claim in (result.title, result.snippet) if claim],
                    trace_ref=f"research:{query_name}:{index}",
                )
            )
    return packets


def _reason_for_missing_fact(
    name: str,
    packets: list[EvidencePacket],
    conflicting: list[str] | None = None,
) -> str:
    if name in set(conflicting or []):
        return f"{name}: conflicting exchange_native values"
    candidates = [packet for packet in packets if packet.data_type == name]
    if not candidates:
        return f"{name}: missing"
    freshness = sorted({packet.freshness_status for packet in candidates})
    if freshness and all(status != "fresh" for status in freshness):
        return f"{name}: {','.join(freshness)}"
    source_types = sorted({packet.source_type for packet in candidates})
    return f"{name}: present but not execution fact source; source_types={','.join(source_types)}"


def _conflicting_execution_facts(packets: list[EvidencePacket]) -> list[str]:
    conflicts: list[str] = []
    for data_type in sorted(EXECUTION_FACT_TYPES):
        candidates = [
            packet
            for packet in packets
            if packet.data_type == data_type and packet.can_satisfy_execution_fact
        ]
        values = {_normalized_value(packet.value) for packet in candidates}
        if len(values) > 1:
            conflicts.append(data_type)
    return conflicts


def _fallback_used(data_type: str, source_type: str) -> bool:
    return data_type in EXECUTION_FACT_TYPES | AUXILIARY_FACT_TYPES and source_type in FALLBACK_SOURCE_TYPES


def _can_satisfy_auxiliary_fact(packet: EvidencePacket) -> bool:
    return packet.freshness_status == "fresh" and (
        packet.source_type == "exchange_native" or packet.fallback_used
    )


def _can_satisfy_event_fact(packet: EvidencePacket) -> bool:
    return packet.freshness_status == "fresh" and packet.source_type in {"event_pool", "official"}


def _missing_macro_facts(packets: list[EvidencePacket]) -> list[str]:
    missing: list[str] = []
    for packet in packets:
        if packet.data_type not in MACRO_FACT_TYPES:
            continue
        if packet.freshness_status != "fresh":
            missing.append("macro_event.freshness")
            continue
        if not isinstance(packet.value, dict):
            missing.extend(f"macro_event.{field_name}" for field_name in MACRO_REQUIRED_FIELDS)
            continue
        for field_name in MACRO_REQUIRED_FIELDS:
            value = packet.value.get(field_name)
            if value is None or value == "" or value == {} or value == []:
                missing.append(f"macro_event.{field_name}")
    return sorted(dict.fromkeys(missing))


def _normalized_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _source_type_from_name(source: str) -> str:
    normalized = source.strip().lower().replace("-", "_")
    if normalized == "fixture":
        return "fixture"
    if any(hint in normalized for hint in EVENT_POOL_SOURCE_HINTS):
        return "event_pool"
    if any(hint in normalized for hint in SEARCH_SOURCE_HINTS):
        return "search_derived"
    if any(hint in normalized for hint in EXCHANGE_SOURCE_HINTS):
        return "exchange_native"
    if any(hint in normalized for hint in AGGREGATOR_SOURCE_HINTS):
        return "aggregator_api"
    if any(hint in normalized for hint in OFFICIAL_SOURCE_HINTS):
        return "official"
    if "web" in normalized or "html" in normalized:
        return "web_derived"
    return "search_derived"


def _source_tier(source_type: str) -> int:
    return SOURCE_TIERS.get(source_type, 4)


def _data_type_from_point_name(name: str) -> str:
    normalized = name.strip().lower()
    if normalized == "funding_rate":
        return "funding"
    if normalized in {"mark", "index", "last", "order_book", "candles", "open_interest", "liquidation"}:
        return normalized
    if normalized in {"liquidation_heatmap", "liquidations"}:
        return "liquidation"
    if normalized in {"bid", "ask"}:
        return "last"
    if normalized in {"active_event_status", "event_status"}:
        return "active_event_status"
    if normalized.startswith("web_"):
        return "news"
    return normalized


def _min_optional(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return min(present)


def _datetime_from_timestamp_ms(timestamp_ms: int | None) -> datetime | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def _freshness_observed_at(
    value: Any,
    observed_at: datetime | None,
    data_type: str,
) -> datetime | None:
    if data_type != "active_event_status":
        return observed_at
    if isinstance(value, dict):
        refreshed_at = value.get("refreshed_at")
        if isinstance(refreshed_at, str) and refreshed_at.strip():
            try:
                parsed = datetime.fromisoformat(refreshed_at.replace("Z", "+00:00"))
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return observed_at


def _freshness_status(
    status: str,
    observed_at: datetime | None,
    retrieved_at: datetime,
    data_type: str,
) -> str:
    if observed_at is None:
        return "unknown"
    normalized = status.lower()
    if normalized in {"conflicting", "conflict"}:
        return "conflicting"
    if normalized != "ok":
        return "stale"
    ttl = FRESHNESS_TTL_SECONDS.get(data_type)
    if ttl is not None and (retrieved_at - observed_at).total_seconds() > ttl:
        return "stale"
    return "fresh"


def _evidence_id(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
