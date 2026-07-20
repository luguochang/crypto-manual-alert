from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

import httpx
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_openai import ChatOpenAI
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from crypto_alert_v2.api.app import UnavailableProductService, create_app
from crypto_alert_v2.agents.market_analysis import create_market_analysis_agent
from crypto_alert_v2.config import Settings
from crypto_alert_v2.domain.models import MarketAnalysis, MarketSnapshot
from crypto_alert_v2.graph import runtime as graph_runtime
from crypto_alert_v2.notifications.adapters import (
    BarkNotificationAdapter,
    DeliveryRequest,
)
from crypto_alert_v2.testing.failure_injection import (
    FailureInjectionController,
    FailureInjectionConflict,
    FailureInjectionModelMiddleware,
    FailureInjectionScenario,
    InjectingMarketProvider,
    InjectingOkxTransport,
    InjectingResearchCollector,
    InjectingWebMarketCollector,
    failure_injection_from_settings,
    install_database_failure_injection,
)
from crypto_alert_v2.providers.errors import ProviderUnavailable, ResearchUnavailable
from crypto_alert_v2.providers.okx import OkxProvider
from crypto_alert_v2.providers.retry_policy import RetryPolicy
from crypto_alert_v2.providers.search import ResearchResult


def test_failure_injection_requires_a_non_production_local_profile() -> None:
    with pytest.raises(ValidationError, match="non-production local"):
        Settings(
            app_environment="production",
            failure_injection_enabled=True,
            failure_injection_profile="task12",
            failure_injection_scenario_file="/tmp/scenario.json",
            failure_injection_control_token=SecretStr("control-token"),
        )


def test_e2e_profiles_contain_only_non_sensitive_controls() -> None:
    repository = Path(__file__).resolve().parents[3]
    real_profile = repository / "tools/v2/profiles/real-provider.env"
    failure_profile = repository / "tools/v2/profiles/failure-injection.env"
    assert real_profile.is_file()
    assert failure_profile.is_file()
    for profile in (real_profile, failure_profile):
        text = profile.read_text(encoding="utf-8")
        assert "API_KEY" not in text
        assert "TOKEN" not in text
        assert "PASSWORD" not in text
        assert "SECRET" not in text

    settings = Settings(
        app_environment="development",
        failure_injection_enabled=True,
        failure_injection_profile="task12",
        failure_injection_scenario_file="/tmp/scenario.json",
        failure_injection_control_token=SecretStr("control-token"),
    )
    assert failure_injection_from_settings(settings) is not None


def test_failure_injection_requires_an_absolute_shared_scenario_file() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        Settings(
            app_environment="test",
            failure_injection_enabled=True,
            failure_injection_profile="task12",
            failure_injection_scenario_file="scenario.json",
            failure_injection_control_token=SecretStr("control-token"),
        )

    settings = Settings(
        app_environment="test",
        failure_injection_enabled=True,
        failure_injection_profile="task12",
        failure_injection_scenario_file="/tmp/crypto-alert-scenario.json",
        failure_injection_control_token=SecretStr("control-token"),
    )
    controller = failure_injection_from_settings(settings)
    assert controller is not None
    assert controller.snapshot().scenario is FailureInjectionScenario.NONE


def test_controller_publishes_atomic_cross_process_scenario_state() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "scenario.json"
        first = FailureInjectionController(path)
        initial = first.snapshot()
        active = first.set(
            FailureInjectionScenario.SEARCH_UNAVAILABLE,
            expected_generation=initial.generation,
        )
        second = FailureInjectionController(path)
        assert second.snapshot().scenario is FailureInjectionScenario.SEARCH_UNAVAILABLE
        with pytest.raises(FailureInjectionConflict, match="stale"):
            second.set(
                FailureInjectionScenario.OKX_TIMEOUT,
                expected_generation=initial.generation,
            )

        second.reset(expected_generation=active.generation)
        assert first.snapshot().scenario is FailureInjectionScenario.NONE


@pytest.mark.asyncio
async def test_database_rollback_listener_is_narrow_and_removable() -> None:
    engine = create_async_engine("postgresql+asyncpg://")
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        no_op_remove = install_database_failure_injection(engine, None)
        no_op_remove()
        no_op_remove()
        remove = install_database_failure_injection(engine, controller)
        dispatch = engine.sync_engine.dispatch.before_cursor_execute

        dispatch(
            None,
            None,
            "INSERT INTO app.notification_outbox (id) VALUES ($1)",
            (uuid4(),),
            None,
            False,
        )
        controller.set(FailureInjectionScenario.DATABASE_ROLLBACK)
        dispatch(
            None,
            None,
            "INSERT INTO app.notification_attempts (id) VALUES ($1)",
            (uuid4(),),
            None,
            False,
        )
        with pytest.raises(OperationalError, match="injected_database_rollback"):
            dispatch(
                None,
                None,
                'INSERT INTO "app"."notification_outbox" (id) VALUES ($1)',
                (uuid4(),),
                None,
                False,
            )

        remove()
        remove()
        dispatch(
            None,
            None,
            "INSERT INTO app.notification_outbox (id) VALUES ($1)",
            (uuid4(),),
            None,
            False,
        )

    await engine.dispose()


def test_failure_injection_wrappers_preserve_typed_provider_boundaries() -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")

        market = InjectingMarketProvider(object(), controller)
        controller.set(FailureInjectionScenario.OKX_UNAVAILABLE)
        with pytest.raises(ProviderUnavailable, match="injected_okx_unavailable"):
            market.fetch_snapshot("BTC-USDT-SWAP", correlation_id="corr-market")

        research = InjectingResearchCollector(object(), controller)
        controller.set(FailureInjectionScenario.SEARCH_UNAVAILABLE)
        with pytest.raises(ResearchUnavailable, match="injected_search_unavailable"):
            research.collect("BTC macro", config=None)


def test_downstream_failures_use_typed_controlled_dependencies_without_egress() -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        market = InjectingMarketProvider(object(), controller)
        research = InjectingResearchCollector(object(), controller)

        controller.set(FailureInjectionScenario.SEARCH_UNAVAILABLE)
        search_market = market.fetch_snapshot(
            "BTC-USDT-SWAP",
            horizon="4h",
            correlation_id="corr-search-controlled",
        )
        assert isinstance(search_market, MarketSnapshot)
        assert search_market.symbol == "BTC-USDT-SWAP"

        controller.set(FailureInjectionScenario.MODEL_INVALID_OUTPUT)
        model_market = market.fetch_snapshot(
            "BTC-USDT-SWAP",
            horizon="4h",
            correlation_id="corr-model-controlled",
        )
        model_research = research.collect("BTC macro", config=None)
        assert isinstance(model_market, MarketSnapshot)
        assert model_market.source_level == "controlled_dependency"
        assert isinstance(model_research, ResearchResult)
        assert len(model_research.evidence) == 1
        assert model_research.evidence[0].source == "controlled_dependency_test"
        assert model_research.evidence[0].parser_version == "controlled-dependency-v1"
        assert model_research.bundle.evidence_gaps == [
            "controlled_dependency:model_invalid_output"
        ]


def test_controlled_web_market_fallback_success_never_calls_external_delegate() -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(FailureInjectionScenario.OKX_WEB_FALLBACK_SUCCESS)
        fallback = InjectingWebMarketCollector(object(), controller)

        result = fallback.collect(
            "BTC-USDT-SWAP",
            horizon="4h",
            config={"metadata": {"correlation_id": "corr-fallback-success"}},
        )

    assert result.snapshot.symbol == "BTC-USDT-SWAP"
    assert result.snapshot.source_level == "web_search_verified"
    assert result.snapshot.ticker is not None
    assert result.snapshot.ticker.last == 65000
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "controlled_dependency_test"
    assert result.evidence[0].parser_version == "controlled-web-market-v1"
    assert result.evidence[0].evidence_relation == "market_snapshot"
    assert result.model_audit.prompt_version == "controlled-web-market-v1"


def test_controlled_web_market_fallback_success_finishes_with_official_tool_strategy() -> (
    None
):
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(FailureInjectionScenario.OKX_WEB_FALLBACK_SUCCESS)
        research = InjectingResearchCollector(object(), controller).collect(
            "BTC macro",
            config=None,
        )
        model = ChatOpenAI(
            model="failure-injection-test",
            api_key="test-key",
            base_url="http://127.0.0.1:9/v1",
            max_retries=0,
        )
        agent = create_market_analysis_agent(
            model=model,
            additional_middleware=(FailureInjectionModelMiddleware(controller),),
        )
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "request": {
                                    "symbol": "BTC-USDT-SWAP",
                                    "horizon": "4h",
                                }
                            }
                        ),
                    }
                ]
            }
        )

    assert research.evidence[0].source == "controlled_dependency_test"
    analysis = result["structured_response"]
    assert isinstance(analysis, MarketAnalysis)
    assert analysis.instrument == "BTC-USDT-SWAP"
    assert analysis.main_action == "no_trade"


def test_controlled_web_market_fallback_failure_preserves_provider_boundary() -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(FailureInjectionScenario.OKX_WEB_FALLBACK_UNAVAILABLE)
        fallback = InjectingWebMarketCollector(object(), controller)

        with pytest.raises(
            ResearchUnavailable,
            match="injected_web_market_fallback_unavailable",
        ) as raised:
            fallback.collect(
                "BTC-USDT-SWAP",
                horizon="4h",
                config={"metadata": {"correlation_id": "corr-fallback-failure"}},
            )

    assert raised.value.provider == "builtin_web_search"
    assert raised.value.error_type == "InjectedWebMarketFallbackUnavailable"
    assert raised.value.retryable is False
    assert raised.value.attempt == 1


def test_failure_profile_wraps_the_canonical_web_market_collector(
    monkeypatch: Any,
) -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        market_delegate = object()
        research_delegate = object()
        fallback_delegate = object()
        analysis_delegate = object()
        monkeypatch.setattr(
            graph_runtime,
            "failure_injection_from_settings",
            lambda settings: controller,
        )
        monkeypatch.setattr(
            graph_runtime,
            "OkxProvider",
            lambda **kwargs: market_delegate,
        )
        monkeypatch.setattr(
            graph_runtime,
            "CapabilityAwareResearchCollector",
            lambda *args, **kwargs: research_delegate,
        )
        monkeypatch.setattr(
            graph_runtime,
            "WebSearchMarketCollector",
            lambda *args, **kwargs: fallback_delegate,
        )
        monkeypatch.setattr(
            graph_runtime,
            "create_market_analysis_agent",
            lambda **kwargs: analysis_delegate,
        )

        assembled = graph_runtime._assemble_runtime(
            settings=Settings(
                app_environment="local",
                search_provider="builtin_web_search",
            ),
            model=object(),
            tavily_api_key=None,
            search_readiness=None,
        )

    assert isinstance(assembled.market_provider, InjectingMarketProvider)
    assert isinstance(assembled.research_collector, InjectingResearchCollector)
    assert isinstance(assembled.market_fallback_collector, InjectingWebMarketCollector)
    assert assembled.analysis_agent is analysis_delegate


def test_model_invalid_output_exhausts_the_official_bounded_repair_loop() -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(FailureInjectionScenario.MODEL_INVALID_OUTPUT)
        model = ChatOpenAI(
            model="failure-injection-test",
            api_key="test-key",
            base_url="http://127.0.0.1:9/v1",
            max_retries=0,
        )
        agent = create_market_analysis_agent(
            model=model,
            additional_middleware=(FailureInjectionModelMiddleware(controller),),
        )

        with pytest.raises(ModelCallLimitExceededError) as raised:
            agent.invoke({"messages": [{"role": "user", "content": "controlled"}]})

    assert type(raised.value) is ModelCallLimitExceededError
    assert raised.value.run_count == 3
    assert raised.value.run_limit == 3


@pytest.mark.parametrize(
    "scenario",
    [
        FailureInjectionScenario.NOTIFICATION_FAILURE,
        FailureInjectionScenario.DATABASE_ROLLBACK,
    ],
)
def test_terminal_failure_uses_official_agent_for_controlled_success(
    scenario: FailureInjectionScenario,
) -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(scenario)
        market = InjectingMarketProvider(object(), controller).fetch_snapshot(
            "BTC-USDT-SWAP",
            horizon="4h",
            correlation_id="corr-notification-controlled",
        )
        research = InjectingResearchCollector(object(), controller).collect(
            "BTC macro",
            config=None,
        )
        model = ChatOpenAI(
            model="failure-injection-test",
            api_key="test-key",
            base_url="http://127.0.0.1:9/v1",
            max_retries=0,
        )
        agent = create_market_analysis_agent(
            model=model,
            additional_middleware=(FailureInjectionModelMiddleware(controller),),
        )
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "request": {
                                    "symbol": "BTC-USDT-SWAP",
                                    "horizon": "4h",
                                }
                            }
                        ),
                    }
                ]
            }
        )

    assert isinstance(market, MarketSnapshot)
    assert market.source_level == "controlled_dependency"
    assert research.evidence[0].source == "controlled_dependency_test"
    assert research.bundle.evidence_gaps == [f"controlled_dependency:{scenario.value}"]
    analysis = result["structured_response"]
    assert isinstance(analysis, MarketAnalysis)
    assert analysis.instrument == "BTC-USDT-SWAP"
    assert analysis.horizon == "4h"
    assert analysis.main_action == "no_trade"


@pytest.mark.parametrize(
    "scenario",
    [
        FailureInjectionScenario.OKX_HTTP_500,
        FailureInjectionScenario.OKX_TIMEOUT,
        FailureInjectionScenario.OKX_WEB_FALLBACK_SUCCESS,
        FailureInjectionScenario.OKX_WEB_FALLBACK_RESEARCH_UNAVAILABLE,
        FailureInjectionScenario.OKX_WEB_FALLBACK_UNAVAILABLE,
    ],
)
def test_okx_transport_failures_run_through_the_provider_retry_budget(
    scenario: FailureInjectionScenario,
) -> None:
    delegated_requests: list[httpx.Request] = []
    retry_delays: list[float] = []

    def unexpected_delegate(request: httpx.Request) -> httpx.Response:
        delegated_requests.append(request)
        return httpx.Response(200, request=request, json={"code": "0", "data": []})

    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(scenario)
        transport = InjectingOkxTransport(
            httpx.MockTransport(unexpected_delegate),
            controller,
        )
        with OkxProvider(
            transport=transport,
            retry_policy=RetryPolicy(
                backoff_seconds=(0.0, 0.0),
                sleep=retry_delays.append,
            ),
        ) as provider:
            with pytest.raises(ProviderUnavailable) as raised:
                provider.fetch_snapshot(
                    "BTC-USDT-SWAP",
                    correlation_id="corr-transport-injection",
                )

    assert delegated_requests == []
    assert retry_delays == [0.0, 0.0]
    assert raised.value.provider == "okx"
    assert raised.value.endpoint == "ticker"
    assert raised.value.retryable is True
    assert raised.value.correlation_id == "corr-transport-injection"


def test_okx_transport_delegates_when_no_failure_scenario_is_active() -> None:
    requests: list[httpx.Request] = []

    def delegate(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204, request=request)

    with TemporaryDirectory() as directory:
        transport = InjectingOkxTransport(
            httpx.MockTransport(delegate),
            FailureInjectionController(Path(directory) / "scenario.json"),
        )
        request = httpx.Request("GET", "https://www.okx.com/api/v5/market/ticker")
        response = transport.handle_request(request)
        transport.close()

    assert response.status_code == 204
    assert requests == [request]


def test_failure_injection_routes_are_not_registered_without_explicit_controller() -> (
    None
):
    settings = Settings(app_environment="local")
    app = create_app(
        service=UnavailableProductService(),
        mode="local",
        settings=settings,
    )
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/v2/testing/failure-scenario" not in paths


def test_failure_injection_routes_are_registered_only_with_controller() -> None:
    with TemporaryDirectory() as directory:
        app = create_app(
            service=UnavailableProductService(),
            mode="test",
            settings=Settings(app_environment="test"),
            failure_injection=FailureInjectionController(
                Path(directory) / "scenario.json"
            ),
            failure_injection_control_token="control-token",
        )
        paths = {route.path for route in app.routes if hasattr(route, "path")}
        assert "/api/v2/testing/failure-scenario" in paths


def test_failure_injection_routes_require_local_or_test_mode() -> None:
    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        with pytest.raises(ValueError, match="non-production local"):
            create_app(
                service=UnavailableProductService(),
                mode="production",
                token_verifier=object(),
                identity_token_verifier=object(),
                membership_authority=object(),
                settings=Settings(app_environment="production"),
                failure_injection=controller,
            )


@pytest.mark.asyncio
async def test_notification_failure_is_injected_before_provider_egress() -> None:
    def unexpected_egress(_: httpx.Request) -> httpx.Response:
        raise AssertionError(
            "notification failure injection must prevent provider egress"
        )

    with TemporaryDirectory() as directory:
        controller = FailureInjectionController(Path(directory) / "scenario.json")
        controller.set(FailureInjectionScenario.NOTIFICATION_FAILURE)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(unexpected_egress)
        ) as client:
            adapter = BarkNotificationAdapter(
                device_key=SecretStr("device-key"),
                client=client,
                failure_injection=controller,
            )
            result = await adapter.send(
                DeliveryRequest(
                    notification_id=uuid4(),
                    task_id=uuid4(),
                    run_id=uuid4(),
                    artifact_id=uuid4(),
                    decision_id=uuid4(),
                    channel="bark",
                    notification_type="analysis_completed",
                    decision_version=1,
                    payload={"title": "Test", "body": "Injected"},
                    payload_hash="a" * 64,
                )
            )
    assert result.outcome == "retryable"
    assert result.reason == "injected_notification_failure"


class _MarketDelegate:
    def fetch_snapshot(self, symbol: str, **kwargs: Any) -> object:
        del symbol, kwargs
        return object()


class _ResearchDelegate:
    def collect(self, query: str, config: object | None = None) -> object:
        del query, config
        return object()


class _AgentDelegate:
    def invoke(self, payload: dict[str, Any], config: object | None = None) -> object:
        del payload, config
        return object()
