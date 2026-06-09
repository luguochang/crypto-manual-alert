from __future__ import annotations

from crypto_manual_alert.skills.registry import (
    DEFAULT_SKILL_NAMES,
    build_default_skill_registry,
    build_skill_registry_from_config,
)
from crypto_manual_alert.skills.facade import SkillTaskContext


def test_default_skill_registry_contains_only_business_skill_names():
    registry = build_default_skill_registry()

    assert tuple(registry) == DEFAULT_SKILL_NAMES
    assert set(DEFAULT_SKILL_NAMES) == {
        "realtime_search",
        "root_cause_search",
        "market_sentiment",
        "macro_event",
        "liquidity_order_book",
    }
    assert "web_search" not in registry


def test_default_skill_registry_builds_distinct_skill_instances():
    first = build_default_skill_registry()
    second = build_default_skill_registry()

    assert first.keys() == second.keys()
    assert all(first[name] is not second[name] for name in DEFAULT_SKILL_NAMES)


def test_skill_registry_from_config_wires_fixture_providers():
    class SkillProviders:
        realtime_search = "fixture"
        root_cause = "fixture"
        liquidity_order_book = "fixture"

    class Config:
        skill_providers = SkillProviders()

    registry = build_skill_registry_from_config(Config())

    realtime = registry["realtime_search"].run(
        SkillTaskContext(
            skill_name="realtime_search",
            task_id="skill:realtime_search",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-skill-provider",
            query="ETF flow surprise",
            input_view={},
        )
    ).to_public_dict()
    root = registry["root_cause_search"].run(
        SkillTaskContext(
            skill_name="root_cause_search",
            task_id="skill:root_cause",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-skill-provider",
            query="why did ETH move",
            input_view={},
            max_depth=2,
        )
    ).to_public_dict()
    liquidity = registry["liquidity_order_book"].run(
        SkillTaskContext(
            skill_name="liquidity_order_book",
            task_id="skill:liquidity_order_book",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-skill-provider",
            query="execution check",
            input_view={},
        )
    ).to_public_dict()

    assert realtime["evidence_candidates"][0]["snippet_ref"] == "fixture.realtime_search[0].snippet_redacted"
    assert root["evidence_candidates"]
    assert set(liquidity["fact_refs"]) == {"mark", "index", "order_book"}


def test_skill_registry_from_config_can_back_root_cause_with_realtime_search_provider():
    class SkillProviders:
        realtime_search = "fixture"
        root_cause = "realtime_search"
        liquidity_order_book = "disabled"

    class Config:
        skill_providers = SkillProviders()

    registry = build_skill_registry_from_config(Config())

    root = registry["root_cause_search"].run(
        SkillTaskContext(
            skill_name="root_cause_search",
            task_id="skill:root_cause",
            symbol="ETH-USDT-SWAP",
            trace_id="trace-root-realtime",
            query="why did ETH move",
            input_view={},
            max_depth=1,
        )
    ).to_public_dict()

    assert root["evidence_candidates"] == [
        {
            "title": "depth 1 flow: fixture search: why did ETH move",
            "url": "fixture://realtime_search/ETH-USDT-SWAP",
            "snippet_ref": "fixture.realtime_search[0].snippet_redacted",
            "source_type": "search_derived",
        }
    ]


def test_skill_registry_from_config_wires_explicit_responses_web_search_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "skill-search-key")

    class RealtimeProviders:
        realtime_search = "responses_web_search"
        root_cause = "disabled"
        liquidity_order_book = "disabled"

    class Decision:
        openai_base_url = "https://example.test"
        openai_model = "gpt-test"
        openai_api_key_env = "OPENAI_API_KEY"

    class Research:
        request_timeout_seconds = 3
        max_results_per_query = 2

    class RealtimeConfig:
        skill_providers = RealtimeProviders()
        decision = Decision()
        research = Research()

    registry = build_skill_registry_from_config(RealtimeConfig())

    provider = registry["realtime_search"].provider
    assert provider.__class__.__name__ == "ResponsesWebSearchProvider"
    assert provider.base_url == "https://example.test"
    assert provider.model == "gpt-test"
    assert provider.timeout_seconds == 3
    assert provider.max_results == 2


def test_skill_registry_from_config_wires_explicit_exchange_native_liquidity_provider():
    class SkillProviders:
        realtime_search = "disabled"
        root_cause = "disabled"
        liquidity_order_book = "exchange_native"

    class MarketData:
        okx_base_url = "https://www.okx.com"
        request_timeout_seconds = 8
        order_book_depth = 20

    class Config:
        skill_providers = SkillProviders()
        market_data = MarketData()

    registry = build_skill_registry_from_config(Config())

    assert registry["liquidity_order_book"].provider.__class__.__name__ == "OkxPublicOrderBookProvider"
