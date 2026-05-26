from __future__ import annotations

from crypto_manual_alert.config import Config
from crypto_manual_alert.research_pipeline.core import (
    FallbackResearchPlanner,
    OpenAICompatibleResearchPlanner,
    StaticResearchPlanner,
)
from crypto_manual_alert.research_pipeline.leader_synthesizers import (
    FallbackLeaderResearchSynthesizer,
    OpenAICompatibleLeaderResearchSynthesizer,
    StaticLeaderResearchSynthesizer,
)
from crypto_manual_alert.research_pipeline.protocols import LeaderResearchSynthesizer, ResearchPlanner, SearchAdapter
from crypto_manual_alert.research_pipeline.search_adapters import (
    DisabledSearchAdapter,
    DuckDuckGoHtmlSearchAdapter,
    FixtureSearchAdapter,
    ResponsesWebSearchAdapter,
)


def build_research_planner(config: Config) -> ResearchPlanner:
    static = StaticResearchPlanner(max_queries=config.research.max_queries)
    if config.research.planner == "llm":
        return FallbackResearchPlanner(OpenAICompatibleResearchPlanner(config), static)
    return static


def build_leader_synthesizer(config: Config) -> LeaderResearchSynthesizer:
    static = StaticLeaderResearchSynthesizer()
    if config.research.leader_mode == "llm":
        return FallbackLeaderResearchSynthesizer(OpenAICompatibleLeaderResearchSynthesizer(config), static)
    return static


def build_search_adapter(config: Config) -> SearchAdapter:
    if config.research.search_provider == "disabled":
        return DisabledSearchAdapter()
    if config.research.search_provider == "fixture":
        return FixtureSearchAdapter({})
    if config.research.search_provider == "duckduckgo_html":
        return DuckDuckGoHtmlSearchAdapter(config)
    if config.research.search_provider == "responses_web_search":
        return ResponsesWebSearchAdapter(config)
    raise ValueError(f"Unsupported research.search_provider: {config.research.search_provider}")
