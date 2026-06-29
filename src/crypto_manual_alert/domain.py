from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


ALLOWED_ACTIONS = {
    "open long",
    "open short",
    "hold long",
    "hold short",
    "close long",
    "close short",
    "flip long to short",
    "flip short to long",
    "trigger long",
    "trigger short",
    "no trade",
}

OPENING_ACTIONS = {"open long", "open short", "trigger long", "trigger short", "flip long to short", "flip short to long"}


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


@dataclass(frozen=True)
class DecisionPlan:
    plan_id: str
    instrument: str
    main_action: str
    horizon: str
    manual_execution_required: bool
    generated_at: datetime
    expires_at: datetime
    reference_price: float | None = None
    entry_trigger: float | None = None
    stop_price: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    probability: float | None = None
    position_size_class: str | None = None
    max_leverage: int | None = None
    risk_pct: float | None = None
    why_not_opposite: str = ""
    invalidation: str = ""
    unavailable_data: list[str] = field(default_factory=list)
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def build_id(payload: dict[str, Any], generated_at: datetime) -> str:
        normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(f"{generated_at.isoformat()}:{normalized}".encode("utf-8")).hexdigest()
        return digest[:16]

    @classmethod
    def from_payload(cls, payload: dict[str, Any], generated_at: datetime | None = None) -> "DecisionPlan":
        now = generated_at or datetime.now(timezone.utc)
        expires_in = 90 if payload.get("expires_in_seconds") is None else int(payload.get("expires_in_seconds"))
        plan_id = str(payload.get("plan_id") or cls.build_id(payload, now))
        return cls(
            plan_id=plan_id,
            instrument=str(payload.get("instrument") or ""),
            main_action=str(payload.get("main_action") or ""),
            horizon=str(payload.get("horizon") or ""),
            manual_execution_required=bool(payload.get("manual_execution_required", True)),
            generated_at=now,
            expires_at=now + timedelta(seconds=expires_in),
            reference_price=_optional_float(payload.get("reference_price")),
            entry_trigger=_optional_float(payload.get("entry_trigger")),
            stop_price=_optional_float(payload.get("stop_price")),
            target_1=_optional_float(payload.get("target_1")),
            target_2=_optional_float(payload.get("target_2")),
            probability=_optional_float(payload.get("probability")),
            position_size_class=payload.get("position_size_class"),
            max_leverage=_optional_int(payload.get("max_leverage")),
            risk_pct=_optional_float(payload.get("risk_pct")),
            why_not_opposite=str(payload.get("why_not_opposite") or ""),
            invalidation=str(payload.get("invalidation") or ""),
            unavailable_data=list(payload.get("unavailable_data") or []),
            notes=str(payload.get("notes") or ""),
            raw=payload,
        )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


@dataclass(frozen=True)
class RiskVerdict:
    allowed: bool
    reasons: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NotificationResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None
