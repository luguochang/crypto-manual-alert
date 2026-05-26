from __future__ import annotations

from datetime import datetime, timezone

from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.research_pipeline.models import ResearchAudit


CORE_MARKET_POINTS = ("last", "mark", "index", "funding_rate", "open_interest", "order_book", "candles")
SEARCH_CONFIDENCE_CAP = "confidence_cap:0.58:检索派生的衍生品数据不能替代交易所原生执行事实"


def needs_research_fallback(
    snapshot: MarketSnapshot,
    max_age_seconds: int | None = None,
    candle_max_age_seconds: int | None = None,
) -> bool:
    if missing_core_points(snapshot):
        return True
    if max_age_seconds is not None and stale_core_points(snapshot, max_age_seconds, candle_max_age_seconds):
        return True
    unavailable_text = " ".join(snapshot.unavailable).lower()
    return any(token in unavailable_text for token in ("connecttimeout", "timeout", "unavailable"))


def synthesize_search_evidence(snapshot: MarketSnapshot, audit: ResearchAudit) -> MarketSnapshot:
    points = dict(snapshot.points)
    unavailable = list(snapshot.unavailable)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for name, results in audit.results.items():
        if not results:
            continue
        point_name = f"web_{name}"
        points[point_name] = DataPoint(
            name=point_name,
            value=[result.to_public_dict() for result in results],
            timestamp_ms=now_ms,
            source="search-derived",
        )

    if any(point not in points for point in ("mark", "index", "order_book")) and SEARCH_CONFIDENCE_CAP not in unavailable:
        unavailable.append(SEARCH_CONFIDENCE_CAP)
    unavailable.extend(audit.unavailable)
    return MarketSnapshot(symbol=snapshot.symbol, fetched_at=snapshot.fetched_at, points=points, unavailable=unavailable)


def candle_max_age_seconds(candle_bar: str, stale_seconds: int) -> int:
    return _bar_to_seconds(candle_bar) + stale_seconds


def missing_core_points(snapshot: MarketSnapshot) -> list[str]:
    return [point for point in CORE_MARKET_POINTS if point not in snapshot.points]


def stale_core_points(
    snapshot: MarketSnapshot,
    max_age_seconds: int,
    candle_max_age_seconds: int | None = None,
) -> list[str]:
    stale: list[str] = []
    for name in CORE_MARKET_POINTS:
        point = snapshot.points.get(name)
        if point is None:
            continue
        threshold = candle_max_age_seconds if name == "candles" and candle_max_age_seconds else max_age_seconds
        age = point.age_seconds(snapshot.fetched_at)
        if age is None or age > threshold:
            stale.append(name)
    return stale


def _bar_to_seconds(candle_bar: str) -> int:
    normalized = candle_bar.strip().upper()
    if normalized.endswith("H"):
        return int(normalized[:-1] or "1") * 3600
    if normalized.endswith("M"):
        return int(normalized[:-1] or "1") * 60
    if normalized.endswith("D"):
        return int(normalized[:-1] or "1") * 86400
    return 3600
