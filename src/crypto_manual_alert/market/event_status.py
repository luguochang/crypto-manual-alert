from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import DataPoint


class EventStatusProvider(Protocol):
    """Provides the active_event_status fact for the facts_gate.

    The facts_gate requires an active_event_status point (source_type in
    {event_pool, official}, fresh) to allow opening/trigger/flip actions. Market
    data providers do not supply this point — it comes from a macro event
    calendar or an operator assertion.
    """

    def active_event_status(self, symbol: str) -> DataPoint | None:
        """Return the active_event_status DataPoint, or None when not configured."""


class DisabledEventStatusProvider:
    """Default: no active_event_status point. Opening actions stay blocked."""

    def active_event_status(self, symbol: str) -> DataPoint | None:
        return None


class NoActiveEventStatusProvider:
    """Operator-asserted "no scheduled macro event affects this symbol's horizon".

    Records an active_event_status point with source="event_pool" (maps to
    source_type=event_pool) and freshness=fresh, so facts_gate can allow opening
    actions. Only enable when the operator has confirmed there is no active macro
    event; the assertion is auditable via the snapshot point and trace.

    This is a manual-alert control, not an automatic calendar. A real macro event
    calendar provider would replace this in a later phase.
    """

    def __init__(
        self,
        *,
        operator_ref: str = "",
        confirmed_at: str = "",
        source_ref: str = "",
        horizon: str = "",
        valid_until: str = "",
        clock: datetime | None = None,
    ):
        self._operator_ref = operator_ref
        self._confirmed_at = confirmed_at
        self._source_ref = source_ref
        self._horizon = horizon
        self._valid_until = valid_until
        self._clock = clock

    def active_event_status(self, symbol: str) -> DataPoint:
        now = self._clock or datetime.now(timezone.utc)
        metadata_complete = all(
            [
                self._operator_ref.strip(),
                self._confirmed_at.strip(),
                self._source_ref.strip(),
                self._horizon.strip(),
                self._valid_until.strip(),
            ]
        )
        return DataPoint(
            name="active_event_status",
            value={
                "status": "no_active_event",
                "symbol": symbol,
                "assertion": "operator_confirmed_no_scheduled_macro_event",
                "provider": "no_active_event",
                "operator_ref": self._operator_ref,
                "confirmed_at": self._confirmed_at,
                "source_ref": self._source_ref,
                "horizon": self._horizon,
                "valid_until": self._valid_until,
                "metadata_complete": metadata_complete,
            },
            timestamp_ms=int(now.timestamp() * 1000),
            source="event_pool",
            status="ok",
        )


def build_event_status_provider(config: Config) -> EventStatusProvider:
    provider = config.macro_event.provider
    if provider == "no_active_event":
        return NoActiveEventStatusProvider(
            operator_ref=config.macro_event.no_active_event_operator_ref,
            confirmed_at=config.macro_event.no_active_event_confirmed_at,
            source_ref=config.macro_event.no_active_event_source_ref,
            horizon=config.macro_event.no_active_event_horizon,
            valid_until=config.macro_event.no_active_event_valid_until,
        )
    if provider == "disabled":
        return DisabledEventStatusProvider()
    raise ValueError(f"Unsupported macro_event.provider: {provider}")


def enrich_snapshot_with_event_status(
    snapshot: Any | None,
    provider: EventStatusProvider | None,
    symbol: str,
) -> Any | None:
    """Return a snapshot with active_event_status added, or the original snapshot.

    Keeps the market snapshot immutable in spirit by copying points when enrichment
    is applied. When the provider is None/disabled or the snapshot is None, returns
    the snapshot unchanged.
    """
    if snapshot is None or provider is None:
        return snapshot
    point = provider.active_event_status(symbol)
    if point is None:
        return snapshot
    if point.name in snapshot.points:
        return snapshot
    enriched_points = {**snapshot.points, point.name: point}
    enriched_unavailable = [u for u in snapshot.unavailable if u != point.name]
    return type(snapshot)(
        symbol=snapshot.symbol,
        fetched_at=snapshot.fetched_at,
        points=enriched_points,
        unavailable=enriched_unavailable,
    )
