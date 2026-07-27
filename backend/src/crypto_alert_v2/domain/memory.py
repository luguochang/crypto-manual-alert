from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


MemoryPurpose = Literal[
    "session_clarification",
    "profile",
    "strategy_config",
    "process_lesson",
    "event",
    "badcase",
]
MemoryScope = Literal["session", "workspace"]

_HISTORICAL_FACT_KEYS = frozenset(
    {
        "action",
        "close",
        "entry_price",
        "fact",
        "market_price",
        "mfe",
        "mae",
        "pnl",
        "prediction",
        "profit",
        "recommendation",
        "return",
    }
)


class MemoryRecord(BaseModel):
    """Typed memory content; it is not a market-fact or checkpoint store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: UUID
    scope: MemoryScope
    purpose: MemoryPurpose
    key: str = Field(min_length=1, max_length=128)
    content: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    expires_at: datetime | None = None
    refreshed_at: datetime | None = None
    source_artifact_id: UUID | None = None

    @model_validator(mode="after")
    def require_aware_times(self) -> Self:
        for name in ("expires_at", "refreshed_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.purpose == "event" and self.refreshed_at is None:
            raise ValueError("event memory requires a refreshed_at timestamp")
        return self


class MemoryInjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: UUID
    purpose: MemoryPurpose
    key: str
    content: dict[str, Any]


def _contains_historical_fact(value: Any) -> bool:
    if isinstance(value, dict):
        if any(str(key).casefold() in _HISTORICAL_FACT_KEYS for key in value):
            return True
        return any(_contains_historical_fact(nested) for nested in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_historical_fact(item) for item in value)
    return False


def safe_memory_injection(
    records: list[MemoryRecord] | tuple[MemoryRecord, ...],
    *,
    now: datetime,
) -> tuple[MemoryInjection, ...]:
    """Return only enabled, live, non-historical context for a new request."""

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    result: list[MemoryInjection] = []
    for record in records:
        if not record.enabled or (record.expires_at is not None and record.expires_at <= now):
            continue
        if _contains_historical_fact(record.content):
            continue
        if record.purpose == "event" and record.refreshed_at is None:
            continue
        result.append(
            MemoryInjection(
                memory_id=record.memory_id,
                purpose=record.purpose,
                key=record.key,
                content=dict(record.content),
            )
        )
    return tuple(result)


def memory_expired(record: MemoryRecord, *, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return record.expires_at is not None and record.expires_at <= now


__all__ = [
    "MemoryInjection",
    "MemoryPurpose",
    "MemoryRecord",
    "MemoryScope",
    "memory_expired",
    "safe_memory_injection",
]
