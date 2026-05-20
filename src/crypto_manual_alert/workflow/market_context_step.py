from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.market.event_status import EventStatusProvider, enrich_snapshot_with_event_status
from crypto_manual_alert.skills.context_loader import SkillContext, SkillRuntime


class SnapshotProvider(Protocol):
    def fetch_snapshot(self, symbol: str) -> MarketSnapshot:
        ...


@dataclass(frozen=True)
class MarketContextStepResult:
    """Market snapshot and skill context for one legacy decision run.

    This step fetches current market context and loads the strategy skill. It
    does not perform research fallback, run agents, or make a decision.
    """

    snapshot: MarketSnapshot
    skill_context: SkillContext
    market_summary: dict[str, object]
    skill_summary: dict[str, object]


def load_market_context_step(
    *,
    symbol: str,
    market_provider: SnapshotProvider,
    skill_runtime: SkillRuntime,
    event_status_provider: EventStatusProvider | None = None,
) -> MarketContextStepResult:
    snapshot = market_provider.fetch_snapshot(symbol)
    snapshot = enrich_snapshot_with_event_status(snapshot, event_status_provider, symbol)
    skill_context = skill_runtime.load_context()
    return MarketContextStepResult(
        snapshot=snapshot,
        skill_context=skill_context,
        market_summary={
            "symbol": snapshot.symbol,
            "point_names": sorted(snapshot.points),
            "unavailable": list(snapshot.unavailable),
        },
        skill_summary={
            "name": skill_context.name,
            "sha256": skill_context.sha256,
            "required_references": list(skill_context.references),
        },
    )
