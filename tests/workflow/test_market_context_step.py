from __future__ import annotations

from datetime import datetime, timezone

from crypto_manual_alert.config import load_config
from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.skills.context_loader import SkillRuntime
from crypto_manual_alert.workflow.market_context_step import load_market_context_step


class StubMarketProvider:
    def fetch_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            fetched_at=datetime.now(timezone.utc),
            points={"mark": DataPoint("mark", 3500, None, "fixture")},
            unavailable=["index: missing"],
        )


def test_market_context_step_fetches_snapshot_and_loads_skill_context():
    config = load_config("config/default.yaml")

    result = load_market_context_step(
        symbol="ETH-USDT-SWAP",
        market_provider=StubMarketProvider(),
        skill_runtime=SkillRuntime(config),
    )

    assert result.snapshot.symbol == "ETH-USDT-SWAP"
    assert result.skill_context.name == "crypto-macro-decision"
    assert result.market_summary == {
        "symbol": "ETH-USDT-SWAP",
        "point_names": ["mark"],
        "unavailable": ["index: missing"],
    }
    assert result.skill_summary == {
        "name": "crypto-macro-decision",
        "sha256": result.skill_context.sha256,
        "required_references": ["data-sources.md", "event-pool.md", "exchange-derivatives.md", "templates.md"],
    }
