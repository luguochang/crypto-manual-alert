from __future__ import annotations

from typing import Any

from crypto_manual_alert.skills.liquidity_order_book import (
    FixtureOrderBookProvider,
    LiquidityOrderBookSkill,
    OkxPublicOrderBookProvider,
)
from crypto_manual_alert.skills.macro_event import MacroEventSkill
from crypto_manual_alert.skills.realtime_search import (
    FixtureSearchProvider,
    RealtimeSearchSkill,
    ResponsesWebSearchProvider,
)
from crypto_manual_alert.skills.root_cause import FixtureRootCauseProvider, RealtimeBackedRootCauseProvider, RootCauseSearchSkill
from crypto_manual_alert.skills.sentiment_crowding import MarketSentimentSkill


DEFAULT_SKILL_NAMES = (
    "realtime_search",
    "root_cause_search",
    "market_sentiment",
    "macro_event",
    "liquidity_order_book",
)


def build_default_skill_registry() -> dict[str, Any]:
    """Build the controlled business-skill registry for worker execution."""

    return {
        "realtime_search": RealtimeSearchSkill(),
        "root_cause_search": RootCauseSearchSkill(),
        "market_sentiment": MarketSentimentSkill(),
        "macro_event": MacroEventSkill(),
        "liquidity_order_book": LiquidityOrderBookSkill(),
    }


def build_fixture_skill_registry() -> dict[str, Any]:
    """Build deterministic skill adapters for local fixture smoke runs."""

    return {
        "realtime_search": RealtimeSearchSkill(provider=FixtureSearchProvider()),
        "root_cause_search": RootCauseSearchSkill(provider=FixtureRootCauseProvider()),
        "market_sentiment": MarketSentimentSkill(),
        "macro_event": MacroEventSkill(),
        "liquidity_order_book": LiquidityOrderBookSkill(provider=FixtureOrderBookProvider()),
    }


def build_skill_registry_from_config(config: object | None = None) -> dict[str, Any]:
    """Build skills with explicit provider modes from config."""

    providers = getattr(config, "skill_providers", None)
    realtime_mode = str(getattr(providers, "realtime_search", "disabled"))
    root_mode = str(getattr(providers, "root_cause", "disabled"))
    liquidity_mode = str(getattr(providers, "liquidity_order_book", "disabled"))
    realtime_provider = None
    if realtime_mode == "fixture":
        realtime_provider = FixtureSearchProvider()
    elif realtime_mode == "responses_web_search":
        realtime_provider = ResponsesWebSearchProvider.from_config(config)
    if root_mode == "realtime_search" and realtime_provider is None:
        raise ValueError("skill_providers.root_cause=realtime_search requires a realtime_search provider")
    root_provider = None
    if root_mode == "fixture":
        root_provider = FixtureRootCauseProvider()
    elif root_mode == "realtime_search":
        root_provider = RealtimeBackedRootCauseProvider(search_provider=realtime_provider)
    liquidity_provider = None
    if liquidity_mode == "fixture":
        liquidity_provider = FixtureOrderBookProvider()
    elif liquidity_mode == "exchange_native":
        market_data = getattr(config, "market_data", None)
        liquidity_provider = OkxPublicOrderBookProvider(
            base_url=str(getattr(market_data, "okx_base_url", "https://www.okx.com")),
            timeout_seconds=int(getattr(market_data, "request_timeout_seconds", 8)),
            order_book_depth=int(getattr(market_data, "order_book_depth", 20)),
            max_age_seconds=int(getattr(market_data, "stale_market_data_seconds", 60)),
        )
    return {
        "realtime_search": RealtimeSearchSkill(provider=realtime_provider),
        "root_cause_search": RootCauseSearchSkill(provider=root_provider),
        "market_sentiment": MarketSentimentSkill(),
        "macro_event": MacroEventSkill(),
        "liquidity_order_book": LiquidityOrderBookSkill(provider=liquidity_provider),
    }
