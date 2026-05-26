"""Research fallback planning, search, and synthesis package."""

from typing import Any

__all__ = [
    "CORE_MARKET_POINTS",
    "LEADER_REVIEW_KEYS",
    "SEARCH_CONFIDENCE_CAP",
    "USER_FACING_LANGUAGE_RULE",
    "DisabledSearchAdapter",
    "DuckDuckGoHtmlSearchAdapter",
    "FallbackLeaderResearchSynthesizer",
    "FallbackResearchPlanner",
    "FixtureSearchAdapter",
    "LeaderResearchSynthesizer",
    "OpenAICompatibleLeaderResearchSynthesizer",
    "OpenAICompatibleResearchPlanner",
    "ResearchAudit",
    "ResearchPlan",
    "ResearchPlanner",
    "ResearchQuery",
    "ResponsesWebSearchAdapter",
    "SearchAdapter",
    "SearchResult",
    "StaticLeaderResearchSynthesizer",
    "StaticResearchPlanner",
    "build_leader_synthesizer",
    "build_research_planner",
    "build_search_adapter",
    "candle_max_age_seconds",
    "execute_research",
    "needs_research_fallback",
    "synthesize_search_evidence",
]

_EXPORT_MODULES = {
    "CORE_MARKET_POINTS": "crypto_manual_alert.research_pipeline.evidence",
    "LEADER_REVIEW_KEYS": "crypto_manual_alert.research_pipeline.prompts",
    "SEARCH_CONFIDENCE_CAP": "crypto_manual_alert.research_pipeline.evidence",
    "USER_FACING_LANGUAGE_RULE": "crypto_manual_alert.research_pipeline.prompts",
    "DisabledSearchAdapter": "crypto_manual_alert.research_pipeline.search_adapters",
    "DuckDuckGoHtmlSearchAdapter": "crypto_manual_alert.research_pipeline.search_adapters",
    "FallbackLeaderResearchSynthesizer": "crypto_manual_alert.research_pipeline.leader_synthesizers",
    "FallbackResearchPlanner": "crypto_manual_alert.research_pipeline.core",
    "FixtureSearchAdapter": "crypto_manual_alert.research_pipeline.search_adapters",
    "LeaderResearchSynthesizer": "crypto_manual_alert.research_pipeline.protocols",
    "OpenAICompatibleLeaderResearchSynthesizer": "crypto_manual_alert.research_pipeline.leader_synthesizers",
    "OpenAICompatibleResearchPlanner": "crypto_manual_alert.research_pipeline.core",
    "ResearchAudit": "crypto_manual_alert.research_pipeline.models",
    "ResearchPlan": "crypto_manual_alert.research_pipeline.models",
    "ResearchPlanner": "crypto_manual_alert.research_pipeline.protocols",
    "ResearchQuery": "crypto_manual_alert.research_pipeline.models",
    "ResponsesWebSearchAdapter": "crypto_manual_alert.research_pipeline.search_adapters",
    "SearchAdapter": "crypto_manual_alert.research_pipeline.protocols",
    "SearchResult": "crypto_manual_alert.research_pipeline.models",
    "StaticLeaderResearchSynthesizer": "crypto_manual_alert.research_pipeline.leader_synthesizers",
    "StaticResearchPlanner": "crypto_manual_alert.research_pipeline.core",
    "build_leader_synthesizer": "crypto_manual_alert.research_pipeline.factory",
    "build_research_planner": "crypto_manual_alert.research_pipeline.factory",
    "build_search_adapter": "crypto_manual_alert.research_pipeline.factory",
    "candle_max_age_seconds": "crypto_manual_alert.research_pipeline.evidence",
    "execute_research": "crypto_manual_alert.research_pipeline.executor",
    "needs_research_fallback": "crypto_manual_alert.research_pipeline.evidence",
    "synthesize_search_evidence": "crypto_manual_alert.research_pipeline.evidence",
}

_SUBMODULES = {
    "core",
    "evidence",
    "executor",
    "factory",
    "leader_synthesizers",
    "models",
    "prompts",
    "protocols",
    "redaction",
    "search_adapters",
}


def __getattr__(name: str) -> Any:
    import importlib

    if name in _SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
