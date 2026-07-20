from typing import Annotated, Any, Protocol, runtime_checkable

import httpx
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, SkipValidation, WithJsonSchema

from crypto_alert_v2.agents.market_analysis import create_market_analysis_agent
from crypto_alert_v2.agents.deep_research import (
    DeepResearchExecutionResult,
    DeepResearchExecutor,
)
from crypto_alert_v2.agents.research import CapabilityAwareResearchCollector
from crypto_alert_v2.config import Settings, get_settings, requires_search_readiness
from crypto_alert_v2.domain.models import MarketSnapshot as DomainMarketSnapshot
from crypto_alert_v2.domain.deep_research import ResearchHarnessMode
from crypto_alert_v2.graph.request import DeepResearchRequest
from crypto_alert_v2.providers.okx import OkxProvider
from crypto_alert_v2.providers.capability_probe import (
    SearchProvider,
    SearchReadiness,
    establish_search_readiness,
    establish_search_readiness_async,
)
from crypto_alert_v2.providers.search import ResearchResult
from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    DdgsMetasearchProvider,
    TavilySearchProvider,
)
from crypto_alert_v2.providers.models import MarketSnapshot as ProviderMarketSnapshot
from crypto_alert_v2.providers.web_market import (
    WebMarketResult,
    WebSearchMarketCollector,
    require_usd_price_evidence,
)
from crypto_alert_v2.testing.failure_injection import (
    FailureInjectionModelMiddleware,
    InjectingMarketProvider,
    InjectingOkxTransport,
    InjectingResearchCollector,
    InjectingWebMarketCollector,
    failure_injection_from_settings,
)


@runtime_checkable
class MarketProvider(Protocol):
    def fetch_snapshot(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        correlation_id: str,
    ) -> DomainMarketSnapshot | ProviderMarketSnapshot: ...


@runtime_checkable
class ResearchCollector(Protocol):
    def collect(
        self, query: str, config: RunnableConfig | None = None
    ) -> ResearchResult: ...


@runtime_checkable
class MarketFallbackCollector(Protocol):
    def collect(
        self,
        symbol: str,
        *,
        horizon: str | None = None,
        config: RunnableConfig | None = None,
    ) -> WebMarketResult: ...


@runtime_checkable
class AnalysisAgent(Protocol):
    def invoke(
        self, payload: dict[str, Any], config: RunnableConfig | None = None
    ) -> dict[str, Any]: ...


@runtime_checkable
class DeepResearchRunner(Protocol):
    async def execute(
        self,
        request: DeepResearchRequest,
        config: RunnableConfig | None = None,
    ) -> DeepResearchExecutionResult: ...


_RUNTIME_DEPENDENCY_JSON_SCHEMA = {
    "anyOf": [{"type": "object"}, {"type": "null"}],
}


class AnalysisRuntime(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="ignore",
        frozen=True,
    )

    market_provider: Annotated[
        SkipValidation[MarketProvider | None],
        WithJsonSchema(_RUNTIME_DEPENDENCY_JSON_SCHEMA),
    ] = None
    market_fallback_collector: Annotated[
        SkipValidation[MarketFallbackCollector | None],
        WithJsonSchema(_RUNTIME_DEPENDENCY_JSON_SCHEMA),
    ] = None
    research_collector: Annotated[
        SkipValidation[ResearchCollector | None],
        WithJsonSchema(_RUNTIME_DEPENDENCY_JSON_SCHEMA),
    ] = None
    analysis_agent: Annotated[
        SkipValidation[AnalysisAgent | None],
        WithJsonSchema(_RUNTIME_DEPENDENCY_JSON_SCHEMA),
    ] = None
    deep_research_executor: Annotated[
        SkipValidation[DeepResearchRunner | None],
        WithJsonSchema(_RUNTIME_DEPENDENCY_JSON_SCHEMA),
    ] = None
    deep_research_harness_mode: ResearchHarnessMode | None = None
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
    failure_injection = failure_injection_from_settings(settings)
    if failure_injection is None:
        market_provider: MarketProvider = OkxProvider(
            base_url=settings.okx_base_url,
            proxy=settings.market_data_http_proxy,
        )
    else:
        okx_transport = InjectingOkxTransport(
            httpx.HTTPTransport(
                retries=0,
                proxy=settings.market_data_http_proxy,
            ),
            failure_injection,
        )
        market_provider = OkxProvider(
            base_url=settings.okx_base_url,
            transport=okx_transport,
        )
    research_collector: ResearchCollector = CapabilityAwareResearchCollector(
        model,
        provider=selected_provider,
        tavily_api_key=tavily_api_key,
        search_http_proxy=settings.search_http_proxy,
    )
    if selected_provider is SearchProvider.BUILTIN:
        deep_research_search = BuiltinWebSearchProvider(model)
        market_fallback_collector: MarketFallbackCollector | None = (
            WebSearchMarketCollector(model)
        )
    elif selected_provider is SearchProvider.DDGS_METASEARCH:
        deep_research_search = DdgsMetasearchProvider(
            proxy=settings.search_http_proxy,
        )
        market_fallback_collector = WebSearchMarketCollector(
            model,
            search=DdgsMetasearchProvider(
                proxy=settings.search_http_proxy,
                evidence_validator=require_usd_price_evidence,
                result_kind="text",
            ),
        )
    else:
        deep_research_search = TavilySearchProvider(api_key=tavily_api_key)
        market_fallback_collector = WebSearchMarketCollector(
            model,
            search=TavilySearchProvider(
                api_key=tavily_api_key,
                evidence_validator=require_usd_price_evidence,
            ),
        )
    analysis_agent: AnalysisAgent = create_market_analysis_agent(
        model=model,
        additional_middleware=(
            (FailureInjectionModelMiddleware(failure_injection),)
            if failure_injection is not None
            else ()
        ),
    )
    if failure_injection is not None:
        market_provider = InjectingMarketProvider(market_provider, failure_injection)
        research_collector = InjectingResearchCollector(
            research_collector, failure_injection
        )
        if market_fallback_collector is not None:
            market_fallback_collector = InjectingWebMarketCollector(
                market_fallback_collector,
                failure_injection,
            )
    return AnalysisRuntime(
        market_provider=market_provider,
        market_fallback_collector=market_fallback_collector,
        research_collector=research_collector,
        analysis_agent=analysis_agent,
        deep_research_executor=DeepResearchExecutor(
            model=model,
            search=deep_research_search,
            harness_mode=settings.deep_research_harness_mode,
        ),
        deep_research_harness_mode=settings.deep_research_harness_mode,
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
            requested_provider=SearchProvider(settings.search_provider),
            search_http_proxy=settings.search_http_proxy,
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
            requested_provider=SearchProvider(settings.search_provider),
            search_http_proxy=settings.search_http_proxy,
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
