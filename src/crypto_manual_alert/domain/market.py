from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DataPoint:
    name: str
    value: float | str | dict[str, Any] | list[Any] | None
    timestamp_ms: int | None
    source: str
    status: str = "ok"

    def age_seconds(self, now: datetime | None = None) -> float | None:
        if self.timestamp_ms is None:
            return None
        current = now or datetime.now(timezone.utc)
        return current.timestamp() - (self.timestamp_ms / 1000)


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    fetched_at: datetime
    points: dict[str, DataPoint]
    unavailable: list[str] = field(default_factory=list)

    def stale_points(self, max_age_seconds: int) -> list[str]:
        stale = []
        for name, point in self.points.items():
            age = point.age_seconds(self.fetched_at)
            if age is None or age > max_age_seconds:
                stale.append(name)
        return stale

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "fetched_at": self.fetched_at.isoformat(),
            "points": {name: point.__dict__ for name, point in self.points.items()},
            "unavailable": self.unavailable,
        }
