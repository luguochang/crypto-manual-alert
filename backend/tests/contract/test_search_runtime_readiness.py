import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import importlib
import json
from pathlib import Path
import time
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_tavily import TavilySearch
from pydantic import SecretStr, ValidationError
import pytest

from crypto_alert_v2.config import Settings
from crypto_alert_v2.graph import runtime as runtime_module
from crypto_alert_v2.providers import capability_probe as capability_probe_module
from crypto_alert_v2.providers.capability_probe import (
    ModelCapabilities,
    SearchProvider,
    SearchReadiness,
    SearchReadinessError,
    establish_search_readiness_async,
)


def _readiness() -> SearchReadiness:
    return SearchReadiness(
        status="ready",
        selected_provider=SearchProvider.TAVILY,
        probed_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
        model="capability-test",
        endpoint="https://model.example",
        capabilities=ModelCapabilities(
            tool_calling=True,
            structured_output=True,
            streaming=True,
            usage_reporting=True,
            builtin_web_search_invoked=False,
            builtin_web_search_citation_count=0,
        ),
        tavily_configured=True,
        tavily_connected=True,
    )


def _builtin_readiness() -> SearchReadiness:
    return SearchReadiness(
        status="ready",
        selected_provider=SearchProvider.BUILTIN,
        probed_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
        model="capability-test",
        endpoint="https://model.example",
        capabilities=ModelCapabilities(
            tool_calling=True,
            structured_output=True,
            streaming=True,
            usage_reporting=True,
            builtin_web_search_invoked=True,
            builtin_web_search_citation_count=1,
        ),
        tavily_configured=False,
        tavily_connected=False,
    )


def _ddgs_metasearch_readiness() -> SearchReadiness:
    return SearchReadiness(
        status="ready",
        selected_provider=SearchProvider.DDGS_METASEARCH,
        probed_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
        model="capability-test",
        endpoint="https://model.example",
        capabilities=ModelCapabilities(
            tool_calling=True,
            structured_output=True,
            streaming=True,
            usage_reporting=True,
            builtin_web_search_invoked=False,
            builtin_web_search_citation_count=0,
        ),
        tavily_configured=False,
        tavily_connected=False,
        ddgs_metasearch_connected=True,
    )


def test_runtime_passes_configured_okx_endpoint_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        app_environment="development",
        openai_api_key=SecretStr("test-only-model-key"),
        okx_base_url="https://okx.example.test",
    )
    provider_options: dict[str, object] = {}

    monkeypatch.setattr(runtime_module, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_: object())
    monkeypatch.setattr(
        runtime_module,
        "OkxProvider",
        lambda **kwargs: provider_options.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        runtime_module,
        "create_market_analysis_agent",
        lambda **_: object(),
    )
    monkeypatch.setattr(
        runtime_module,
        "CapabilityAwareResearchCollector",
        lambda *_args, **_kwargs: object(),
    )
    runtime_module.get_default_runtime.cache_clear()
    try:
        runtime_module.get_default_runtime()
    finally:
        runtime_module.get_default_runtime.cache_clear()

    assert provider_options == {
        "base_url": "https://okx.example.test",
        "proxy": None,
    }


@pytest.mark.parametrize(
    ("provider", "readiness", "tavily_key", "factory_name", "factory_options"),
    [
        (
            "ddgs_metasearch",
            _ddgs_metasearch_readiness(),
            None,
            "DdgsMetasearchProvider",
            {
                "proxy": "http://proxy.example:8080",
                "result_kind": "text",
            },
        ),
        (
            "tavily",
            _readiness(),
            "test-tavily-key",
            "TavilySearchProvider",
            {"api_key": "test-tavily-key"},
        ),
    ],
)
def test_runtime_assembles_market_fallback_for_external_search_providers(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    readiness: SearchReadiness,
    tavily_key: str | None,
    factory_name: str,
    factory_options: dict[str, str],
) -> None:
    selected_search = object()
    fallback = object()
    search_options: dict[str, object] = {}
    fallback_options: dict[str, object] = {}

    monkeypatch.setattr(
        runtime_module, "failure_injection_from_settings", lambda _: None
    )
    monkeypatch.setattr(runtime_module, "OkxProvider", lambda **_: object())
    monkeypatch.setattr(
        runtime_module,
        "CapabilityAwareResearchCollector",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        runtime_module,
        "create_market_analysis_agent",
        lambda **_: object(),
    )
    monkeypatch.setattr(
        runtime_module,
        factory_name,
        lambda **kwargs: search_options.update(kwargs) or selected_search,
    )
    monkeypatch.setattr(
        runtime_module,
        "WebSearchMarketCollector",
        lambda *_args, **kwargs: fallback_options.update(kwargs) or fallback,
    )

    assembled = runtime_module._assemble_runtime(
        settings=Settings(
            _env_file=None,
            app_environment="local",
            search_provider=provider,
            tavily_api_key=(SecretStr(tavily_key) if tavily_key is not None else None),
            search_http_proxy="http://proxy.example:8080",
        ),
        model=object(),
        tavily_api_key=tavily_key,
        search_readiness=readiness,
    )

    assert assembled.market_fallback_collector is fallback
    assert fallback_options["search"] is selected_search
    assert search_options == {
        **factory_options,
        "evidence_validator": runtime_module.require_usd_price_evidence,
    }


@pytest.mark.asyncio
async def test_async_readiness_does_not_block_the_event_loop() -> None:
    capabilities = ModelCapabilities(
        tool_calling=True,
        structured_output=True,
        streaming=True,
        usage_reporting=True,
        builtin_web_search_invoked=True,
        builtin_web_search_citation_count=1,
    )
    heartbeat_elapsed = 0.0
    started = asyncio.get_running_loop().time()

    def blocking_probe(_: object) -> ModelCapabilities:
        time.sleep(0.06)
        return capabilities

    async def heartbeat() -> None:
        nonlocal heartbeat_elapsed
        await asyncio.sleep(0.01)
        heartbeat_elapsed = asyncio.get_running_loop().time() - started

    await asyncio.gather(
        establish_search_readiness_async(
            model=object(),  # type: ignore[arg-type]
            model_name="capability-test",
            base_url=None,
            tavily_api_key=None,
            capability_probe=blocking_probe,  # type: ignore[arg-type]
        ),
        heartbeat(),
    )

    assert heartbeat_elapsed < 0.04


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("development", "development"),
        ("local", "local"),
        ("test", "test"),
        ("staging", "staging"),
        ("production", "production"),
        ("  PRODUCTION  ", "production"),
    ],
)
def test_app_environment_accepts_only_normalized_supported_values(
    configured: str,
    expected: str,
) -> None:
    settings = Settings(_env_file=None, app_environment=configured)

    assert settings.app_environment == expected


@pytest.mark.parametrize("configured", ["prod", "unknown", ""])
def test_app_environment_rejects_values_that_could_bypass_readiness(
    configured: str,
) -> None:
    with pytest.raises(ValidationError, match="app_environment"):
        Settings(_env_file=None, app_environment=configured)


def test_app_environment_is_required_when_no_env_file_is_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_ENVIRONMENT", raising=False)

    with pytest.raises(ValidationError, match="app_environment"):
        Settings(_env_file=None)


@pytest.mark.parametrize("environment", ["development", "local", "test"])
def test_non_strict_environment_accepts_ddgs_metasearch(environment: str) -> None:
    settings = Settings(
        _env_file=None,
        app_environment=environment,
        search_provider="ddgs_metasearch",
    )

    assert settings.search_provider == "ddgs_metasearch"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_strict_environment_rejects_ddgs_metasearch(environment: str) -> None:
    with pytest.raises(ValidationError, match="ddgs_metasearch"):
        Settings(
            _env_file=None,
            app_environment=environment,
            search_provider="ddgs_metasearch",
        )


def test_search_provider_rejects_legacy_name() -> None:
    with pytest.raises(ValidationError, match="search_provider"):
        Settings(
            _env_file=None,
            app_environment="local",
            search_provider="duckduckgo",  # type: ignore[arg-type]
        )


def test_blank_optional_provider_configuration_is_normalized_to_missing() -> None:
    settings = Settings(
        _env_file=None,
        app_environment="local",
        openai_api_key="  ",
        openai_base_url="  ",
        tavily_api_key=SecretStr(""),
        market_data_http_proxy="",
        search_http_proxy="\t",
        worker_readiness_url=" ",
        agent_readiness_url=" ",
        langfuse_host=" ",
    )

    assert settings.openai_api_key is None
    assert settings.openai_base_url is None
    assert settings.tavily_api_key is None
    assert settings.market_data_http_proxy is None
    assert settings.search_http_proxy is None
    assert settings.worker_readiness_url is None
    assert settings.agent_readiness_url is None
    assert settings.langfuse_host is None


def test_tavily_selection_rejects_a_blank_credential() -> None:
    with pytest.raises(ValidationError, match="TAVILY_API_KEY"):
        Settings(
            _env_file=None,
            app_environment="local",
            search_provider="tavily",
            tavily_api_key=" ",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["development", "local", "test"])
async def test_non_strict_environment_lifespan_does_not_probe_search(
    environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")

    async def unexpected_runtime() -> runtime_module.AnalysisRuntime:
        raise AssertionError("non-strict environments must not probe search readiness")

    monkeypatch.setattr(
        http_app_module,
        "get_settings",
        lambda: Settings(_env_file=None, app_environment=environment),
    )
    monkeypatch.setattr(
        http_app_module,
        "get_default_runtime_async",
        unexpected_runtime,
        raising=False,
    )
    application = FastAPI()

    async with http_app_module.lifespan(application):
        assert application.state.search_readiness is None


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["staging", "production"])
async def test_strict_environment_lifespan_awaits_search_readiness(
    environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")
    readiness = _readiness()
    calls = 0

    async def runtime_provider() -> runtime_module.AnalysisRuntime:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return runtime_module.AnalysisRuntime(search_readiness=readiness)

    monkeypatch.setattr(
        http_app_module,
        "get_settings",
        lambda: Settings(_env_file=None, app_environment=environment),
    )
    monkeypatch.setattr(
        http_app_module,
        "get_default_runtime_async",
        runtime_provider,
        raising=False,
    )
    application = FastAPI()

    async with http_app_module.lifespan(application):
        assert application.state.search_readiness is readiness

    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["staging", "production"])
async def test_active_loop_lifespan_uses_configured_async_tavily_provider(
    environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")
    settings = Settings(
        _env_file=None,
        app_environment=environment,
        openai_api_key=SecretStr("test-only-model-key"),
        tavily_api_key=SecretStr("test-only-tavily-key"),
        search_provider="tavily",
    )
    capabilities = ModelCapabilities(
        tool_calling=True,
        structured_output=True,
        streaming=True,
        usage_reporting=True,
        builtin_web_search_invoked=False,
        builtin_web_search_citation_count=0,
    )
    tavily_calls: list[dict[str, str]] = []
    collector_options: dict[str, object] = {}

    async def tavily_ainvoke(
        self: TavilySearch,
        input: dict[str, str],
        config: object = None,
        **kwargs: object,
    ) -> object:
        del self, config, kwargs
        asyncio.get_running_loop()
        tavily_calls.append(input)
        return {
            "results": [
                {
                    "url": "https://www.reuters.com/markets/currencies/",
                    "title": "Currencies",
                    "content": "Current public Bitcoin market evidence.",
                }
            ]
        }

    def collector(model: object, **kwargs: object) -> object:
        del model
        collector_options.update(kwargs)
        return object()

    async_runtime_provider = getattr(
        runtime_module,
        "get_default_runtime_async",
        None,
    )
    assert callable(async_runtime_provider), (
        "production lifespan requires an async runtime readiness entrypoint"
    )

    monkeypatch.setattr(runtime_module, "get_settings", lambda: settings)
    monkeypatch.setattr(http_app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_: object())
    monkeypatch.setattr(runtime_module, "OkxProvider", lambda **_: object())
    monkeypatch.setattr(
        runtime_module,
        "create_market_analysis_agent",
        lambda **_: object(),
    )
    monkeypatch.setattr(
        runtime_module,
        "CapabilityAwareResearchCollector",
        collector,
    )
    monkeypatch.setattr(
        capability_probe_module,
        "probe_openai_capabilities",
        lambda _: capabilities,
    )
    monkeypatch.setattr(TavilySearch, "ainvoke", tavily_ainvoke)
    monkeypatch.setattr(
        http_app_module,
        "get_default_runtime_async",
        async_runtime_provider,
        raising=False,
    )
    runtime_module.get_default_runtime.cache_clear()
    application = FastAPI()
    try:
        async with http_app_module.lifespan(application):
            readiness = application.state.search_readiness
            cached_runtime = runtime_module.get_default_runtime()
    finally:
        runtime_module.get_default_runtime.cache_clear()

    assert isinstance(readiness, SearchReadiness)
    assert readiness.selected_provider is SearchProvider.TAVILY
    assert cached_runtime.search_readiness is readiness
    assert collector_options["provider"] is SearchProvider.TAVILY
    assert tavily_calls == [
        {"query": "Find one current public Bitcoin market news source."}
    ]


def test_production_runtime_probes_once_and_caches_immutable_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        app_environment="production",
        openai_api_key=SecretStr("test-only-model-key"),
        tavily_api_key=SecretStr("test-only-tavily-key"),
    )
    readiness = _builtin_readiness()
    probe_calls = 0
    collector_options = {}

    monkeypatch.setattr(runtime_module, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_: object())
    monkeypatch.setattr(runtime_module, "OkxProvider", lambda **_: object())
    monkeypatch.setattr(
        runtime_module,
        "create_market_analysis_agent",
        lambda **_: object(),
    )

    def probe(**kwargs):
        nonlocal probe_calls
        probe_calls += 1
        assert kwargs["tavily_api_key"] == "test-only-tavily-key"
        assert kwargs["requested_provider"] is SearchProvider.BUILTIN
        return readiness

    def collector(model, **kwargs):
        del model
        collector_options.update(kwargs)
        return object()

    monkeypatch.setattr(runtime_module, "establish_search_readiness", probe)
    monkeypatch.setattr(runtime_module, "CapabilityAwareResearchCollector", collector)
    runtime_module.get_default_runtime.cache_clear()
    try:
        first = runtime_module.get_default_runtime()
        second = runtime_module.get_default_runtime()
    finally:
        runtime_module.get_default_runtime.cache_clear()

    assert first is second
    assert first.search_readiness is readiness
    assert probe_calls == 1
    assert collector_options["provider"] is SearchProvider.BUILTIN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_provider", "readiness", "tavily_key"),
    [
        ("builtin_web_search", _builtin_readiness(), None),
        ("tavily", _readiness(), "test-only-tavily-key"),
    ],
)
async def test_strict_runtime_requests_configured_search_provider(
    monkeypatch: pytest.MonkeyPatch,
    configured_provider: str,
    readiness: SearchReadiness,
    tavily_key: str | None,
) -> None:
    settings = Settings(
        _env_file=None,
        app_environment="production",
        openai_api_key=SecretStr("test-only-model-key"),
        search_provider=configured_provider,
        tavily_api_key=SecretStr(tavily_key) if tavily_key is not None else None,
        search_http_proxy="http://127.0.0.1:7890",
    )
    probe_options: dict[str, object] = {}
    collector_options: dict[str, object] = {}

    async def probe(**kwargs: object) -> SearchReadiness:
        probe_options.update(kwargs)
        return readiness

    def collector(model: object, **kwargs: object) -> object:
        del model
        collector_options.update(kwargs)
        return object()

    monkeypatch.setattr(runtime_module, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_: object())
    monkeypatch.setattr(runtime_module, "OkxProvider", lambda **_: object())
    monkeypatch.setattr(
        runtime_module,
        "create_market_analysis_agent",
        lambda **_: object(),
    )
    monkeypatch.setattr(runtime_module, "establish_search_readiness_async", probe)
    monkeypatch.setattr(runtime_module, "CapabilityAwareResearchCollector", collector)
    runtime_module.get_default_runtime.cache_clear()
    try:
        runtime = await runtime_module.get_default_runtime_async()
    finally:
        runtime_module.get_default_runtime.cache_clear()

    assert runtime.search_readiness is readiness
    assert probe_options["requested_provider"] is SearchProvider(configured_provider)
    assert collector_options["provider"] is SearchProvider(configured_provider)


def test_production_runtime_cannot_start_when_search_readiness_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        app_environment="production",
        openai_api_key=SecretStr("test-only-model-key"),
    )
    monkeypatch.setattr(runtime_module, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime_module, "ChatOpenAI", lambda **_: object())
    monkeypatch.setattr(
        runtime_module,
        "establish_search_readiness",
        lambda **_: (_ for _ in ()).throw(
            SearchReadinessError("built-in web search failed; Tavily is not configured")
        ),
    )
    runtime_module.get_default_runtime.cache_clear()
    try:
        with pytest.raises(SearchReadinessError, match="Tavily is not configured"):
            runtime_module.get_default_runtime()
    finally:
        runtime_module.get_default_runtime.cache_clear()


def test_agent_server_http_app_runs_production_readiness_at_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")

    readiness = _readiness()
    runtime = runtime_module.AnalysisRuntime(search_readiness=readiness)
    startup_calls = 0

    async def runtime_provider():
        nonlocal startup_calls
        startup_calls += 1
        return runtime

    monkeypatch.setattr(
        http_app_module,
        "get_settings",
        lambda: Settings(_env_file=None, app_environment="production"),
    )
    monkeypatch.setattr(
        http_app_module,
        "get_default_runtime_async",
        runtime_provider,
    )

    with TestClient(http_app_module.app) as client:
        response = client.get("/app/system/readiness")

    assert response.status_code == 200
    assert response.json() == json.loads(readiness.model_dump_json())
    assert startup_calls == 1


def test_production_http_lifespan_cannot_bypass_missing_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")
    monkeypatch.setattr(
        http_app_module,
        "get_settings",
        lambda: Settings(_env_file=None, app_environment="production"),
    )

    async def runtime_without_readiness() -> runtime_module.AnalysisRuntime:
        return runtime_module.AnalysisRuntime()

    monkeypatch.setattr(
        http_app_module,
        "get_default_runtime_async",
        runtime_without_readiness,
    )

    with pytest.raises(SearchReadinessError, match="requires search readiness"):
        with TestClient(http_app_module.app):
            pass


def test_custom_app_exposes_product_health_without_shadowing_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")
    product_app_module = importlib.import_module("crypto_alert_v2.api.app")
    product_app = product_app_module.create_app(
        service=product_app_module.UnavailableProductService(),
        mode="test",
    )
    monkeypatch.setattr(
        http_app_module,
        "get_settings",
        lambda: Settings(_env_file=None, app_environment="test"),
    )
    application = http_app_module.create_app(product_app=product_app)

    with TestClient(application) as client:
        health_response = client.get("/app/api/v2/health")
        readiness_response = client.get("/app/system/readiness")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok", "version": "2.0.0"}
    assert readiness_response.status_code == 503
    assert readiness_response.json() == {
        "detail": "Search readiness is not available in this environment."
    }


def test_custom_app_enters_and_exits_product_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")
    lifecycle_events: list[str] = []

    @asynccontextmanager
    async def product_lifespan(_: FastAPI) -> AsyncIterator[None]:
        lifecycle_events.append("startup")
        yield
        lifecycle_events.append("shutdown")

    product_app = FastAPI(lifespan=product_lifespan)
    monkeypatch.setattr(
        http_app_module,
        "get_settings",
        lambda: Settings(_env_file=None, app_environment="test"),
    )
    application = http_app_module.create_app(product_app=product_app)

    with TestClient(application):
        assert lifecycle_events == ["startup"]

    assert lifecycle_events == ["startup", "shutdown"]


def test_langgraph_config_mounts_authenticated_custom_http_app() -> None:
    config = json.loads(
        (Path(__file__).resolve().parents[2] / "langgraph.json").read_text()
    )

    assert config["http"] == {
        "app": "./src/crypto_alert_v2/http/app.py:app",
        "enable_custom_route_auth": True,
    }
