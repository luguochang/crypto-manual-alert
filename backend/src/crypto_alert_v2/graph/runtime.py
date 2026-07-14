from dataclasses import dataclass
from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig

from crypto_alert_v2.agents.market_analysis import create_market_analysis_agent
from crypto_alert_v2.agents.research import CapabilityAwareResearchCollector
from crypto_alert_v2.config import Settings, get_settings, requires_search_readiness
from crypto_alert_v2.providers.okx import OkxProvider
from crypto_alert_v2.providers.capability_probe import (
    SearchProvider,
    SearchReadiness,
    establish_search_readiness,
    establish_search_readiness_async,
)
from crypto_alert_v2.providers.search import ResearchResult


class MarketProvider(Protocol):
    def fetch_snapshot(self, symbol: str, *, correlation_id: str) -> Any: ...


class ResearchCollector(Protocol):
    def collect(
        self, query: str, config: RunnableConfig | None = None
    ) -> ResearchResult: ...


class AnalysisAgent(Protocol):
    def invoke(
        self, payload: dict[str, Any], config: RunnableConfig | None = None
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class AnalysisRuntime:
    market_provider: MarketProvider | None = None
    research_collector: ResearchCollector | None = None
    analysis_agent: AnalysisAgent | None = None
    search_readiness: SearchReadiness | None = None


_default_runtime: AnalysisRuntime | None = None


def _model_and_tavily_key(settings: Settings) -> tuple[ChatOpenAI, str | None]:
    if settings.openai_api_key is None:
        raise RuntimeError("OPENAI_API_KEY is required for analysis readiness")
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=90,
        max_retries=0,
        output_version="responses/v1",
    )
    tavily_api_key = (
        settings.tavily_api_key.get_secret_value()
        if settings.tavily_api_key is not None
        else None
    )
    return model, tavily_api_key


def _assemble_runtime(
    *,
    settings: Settings,
    model: ChatOpenAI,
    tavily_api_key: str | None,
    search_readiness: SearchReadiness | None,
) -> AnalysisRuntime:
    selected_provider = (
        search_readiness.selected_provider
        if search_readiness is not None
        else SearchProvider(settings.search_provider)
    )
    return AnalysisRuntime(
        market_provider=OkxProvider(proxy=settings.market_data_http_proxy),
        research_collector=CapabilityAwareResearchCollector(
            model,
            provider=selected_provider,
            tavily_api_key=tavily_api_key,
        ),
        analysis_agent=create_market_analysis_agent(model=model),
        search_readiness=search_readiness,
    )


def _cache_runtime(runtime: AnalysisRuntime) -> AnalysisRuntime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = runtime
    return _default_runtime


def get_default_runtime() -> AnalysisRuntime:
    if _default_runtime is not None:
        return _default_runtime
    settings = get_settings()
    model, tavily_api_key = _model_and_tavily_key(settings)
    search_readiness = None
    if requires_search_readiness(settings.app_environment):
        search_readiness = establish_search_readiness(
            model=model,
            model_name=settings.model_name,
            base_url=settings.openai_base_url,
            tavily_api_key=tavily_api_key,
        )
    return _cache_runtime(
        _assemble_runtime(
            settings=settings,
            model=model,
            tavily_api_key=tavily_api_key,
            search_readiness=search_readiness,
        )
    )


async def get_default_runtime_async() -> AnalysisRuntime:
    if _default_runtime is not None:
        return _default_runtime
    settings = get_settings()
    model, tavily_api_key = _model_and_tavily_key(settings)
    search_readiness = None
    if requires_search_readiness(settings.app_environment):
        search_readiness = await establish_search_readiness_async(
            model=model,
            model_name=settings.model_name,
            base_url=settings.openai_base_url,
            tavily_api_key=tavily_api_key,
        )
    return _cache_runtime(
        _assemble_runtime(
            settings=settings,
            model=model,
            tavily_api_key=tavily_api_key,
            search_readiness=search_readiness,
        )
    )


def _clear_default_runtime_cache() -> None:
    global _default_runtime
    _default_runtime = None


setattr(get_default_runtime, "cache_clear", _clear_default_runtime_cache)


__all__ = [
    "AnalysisRuntime",
    "ResearchResult",
    "SearchReadiness",
    "get_default_runtime",
    "get_default_runtime_async",
]
