import asyncio
from datetime import UTC, datetime
import importlib
import json
from pathlib import Path
import time

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
async def test_active_loop_lifespan_uses_official_async_tavily_fallback(
    environment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_app_module = importlib.import_module("crypto_alert_v2.http.app")
    settings = Settings(
        _env_file=None,
        app_environment=environment,
        openai_api_key=SecretStr("test-only-model-key"),
        tavily_api_key=SecretStr("test-only-tavily-key"),
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
    readiness = _readiness()
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
    assert collector_options["provider"] is SearchProvider.TAVILY


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
            SearchReadinessError(
                "built-in web search failed; Tavily is not configured"
            )
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


def test_langgraph_config_mounts_authenticated_custom_http_app() -> None:
    config = json.loads(
        (
            Path(__file__).resolve().parents[2] / "langgraph.json"
        ).read_text()
    )

    assert config["http"] == {
        "app": "./src/crypto_alert_v2/http/app.py:app",
        "enable_custom_route_auth": True,
    }
