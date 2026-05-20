from __future__ import annotations

from datetime import datetime, timezone

from crypto_manual_alert.config import load_config
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.research_pipeline import (
    FixtureSearchAdapter,
    StaticLeaderResearchSynthesizer,
    StaticResearchPlanner,
)
from crypto_manual_alert.workflow.research_orchestration import run_research_orchestration


def _config_with_research(enabled: bool):
    config = load_config("config/default.yaml")
    research = config.research.__class__(
        **{
            **config.research.__dict__,
            "enabled": enabled,
            "search_provider": "fixture",
            "max_queries": 1,
            "max_workers": 1,
        }
    )
    return config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=config.decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=research,
        security=config.security,
    )


def test_research_orchestration_skips_when_disabled():
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={},
        unavailable=["mark: timeout"],
    )

    result = run_research_orchestration(
        config=_config_with_research(False),
        recorder=None,
        trace_id="trace-1",
        snapshot=snapshot,
        skill_context={"name": "crypto-macro-decision"},
        research_planner=StaticResearchPlanner(max_queries=1),
        search_adapter=FixtureSearchAdapter({}),
        leader_synthesizer=StaticLeaderResearchSynthesizer(),
    )

    assert result.snapshot is snapshot
    assert result.research_audit is None
    assert result.used_fallback is False
    assert result.public_summary == {"used_fallback": False, "reason": "research_disabled"}


def test_research_orchestration_runs_fallback_and_returns_enriched_snapshot():
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={},
        unavailable=["mark: timeout"],
    )

    result = run_research_orchestration(
        config=_config_with_research(True),
        recorder=None,
        trace_id="trace-1",
        snapshot=snapshot,
        skill_context={"name": "crypto-macro-decision"},
        research_planner=StaticResearchPlanner(max_queries=1),
        search_adapter=FixtureSearchAdapter(
            {
                "eth_price_context": [
                    {
                        "title": "ETH context",
                        "url": "https://example.test/eth",
                        "snippet": "ETH fallback context.",
                    }
                ]
            }
        ),
        leader_synthesizer=StaticLeaderResearchSynthesizer(),
    )

    assert result.used_fallback is True
    assert result.research_audit is not None
    assert "web_eth_price_context" in result.snapshot.points
    assert "leader_finalizer" in result.research_audit.leader_summary
    assert result.public_summary == {
        "used_fallback": True,
        "result_names": ["eth_price_context"],
        "unavailable": [],
    }
