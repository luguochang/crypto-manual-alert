from datetime import UTC, datetime

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from crypto_alert_v2.agents.research import CapabilityAwareResearchCollector
from crypto_alert_v2.providers.capability_probe import (
    ModelCapabilities,
    SearchReadiness,
    SearchProvider,
    SearchReadinessError,
    _with_probe_retry,
    establish_search_readiness,
    establish_search_readiness_async,
    select_search_provider,
)
from crypto_alert_v2.providers.errors import ResearchUnavailable, TRANSIENT_MODEL_ERRORS
from crypto_alert_v2.providers.model import as_chat_completions_model
from crypto_alert_v2.providers.retry_policy import SearchRetryPolicy
from crypto_alert_v2.providers.search import BuiltinWebSearchProvider


class RecordingResearchCollector:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def collect(self, query: str, config: object = None) -> object:
        del config
        self.queries.append(query)
        return object()


class RecordingRunnable:
    def __init__(self) -> None:
        self.retry_options: dict[str, object] | None = None

    def with_retry(self, **kwargs: object) -> "RecordingRunnable":
        self.retry_options = kwargs
        return self


class TransportStructuredResult(BaseModel):
    supported: bool


def ready_capabilities(**overrides: object) -> ModelCapabilities:
    values: dict[str, object] = {
        "tool_calling": True,
        "structured_output": True,
        "streaming": True,
        "usage_reporting": True,
        "builtin_web_search_invoked": True,
        "builtin_web_search_citation_count": 1,
    }
    values.update(overrides)
    return ModelCapabilities.model_validate(values)


def test_generic_capabilities_use_chat_completions_not_responses_api() -> None:
    responses_model = ChatOpenAI(
        model="capability-test",
        api_key="test-key",
        base_url="https://example.com/v1",
        use_responses_api=True,
        output_version="responses/v1",
    )

    chat_model = as_chat_completions_model(responses_model)

    assert chat_model is not responses_model
    assert chat_model.use_responses_api is False
    assert chat_model.output_version is None
    assert chat_model.root_client is responses_model.root_client
    assert chat_model.client is responses_model.client
    assert responses_model.use_responses_api is True
    assert responses_model.output_version == "responses/v1"


def test_non_openai_model_is_not_replaced() -> None:
    model = object()

    assert as_chat_completions_model(model) is model


def test_structured_model_routes_to_chat_completions_transport() -> None:
    request_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chatcmpl_transport_contract",
                "object": "chat.completion",
                "created": 1,
                "model": "capability-test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"supported":true}',
                            "refusal": None,
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        responses_model = ChatOpenAI(
            model="capability-test",
            api_key="test-key",
            base_url="https://model.invalid/v1",
            http_client=http_client,
            use_responses_api=True,
            output_version="responses/v1",
            max_retries=0,
        )
        structured = as_chat_completions_model(
            responses_model
        ).with_structured_output(TransportStructuredResult)

        result = structured.invoke("Return supported true.")
    finally:
        http_client.close()

    assert result == TransportStructuredResult(supported=True)
    assert request_paths == ["/v1/chat/completions"]


def test_capability_probe_uses_official_transient_retry_contract() -> None:
    runnable = RecordingRunnable()

    retried = _with_probe_retry(runnable)

    assert retried is runnable
    assert runnable.retry_options == {
        "retry_if_exception_type": TRANSIENT_MODEL_ERRORS,
        "stop_after_attempt": 2,
    }


def test_official_bound_chat_model_receives_per_attempt_search_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Clock:
        def __init__(self) -> None:
            self.now = 100.0

        def monotonic(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    clock = Clock()
    timeouts: list[float] = []
    tool_types: list[str] = []
    generations = [
        AIMessage(content=[{"type": "text", "text": "No provider evidence."}]),
        AIMessage(
            content=[
                {
                    "type": "web_search_call",
                    "id": "search_1",
                    "status": "completed",
                },
                {
                    "type": "text",
                    "text": "Verified provider citation.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://www.reuters.com/markets/",
                            "title": "Markets",
                        }
                    ],
                },
            ]
        ),
    ]

    def fake_generate(self, messages, stop=None, run_manager=None, **kwargs):
        del self, messages, stop, run_manager
        timeouts.append(float(kwargs["timeout"]))
        tool_types.append(kwargs["tools"][0]["type"])
        clock.advance(0.25)
        return ChatResult(
            generations=[ChatGeneration(message=generations.pop(0))]
        )

    monkeypatch.setattr(ChatOpenAI, "_generate", fake_generate)
    model = ChatOpenAI(
        model="capability-test",
        api_key="test-key",
        base_url="https://model.example/v1",
        use_responses_api=True,
        output_version="responses/v1",
        max_retries=0,
    )

    evidence = BuiltinWebSearchProvider(
        model,
        retry_policy=SearchRetryPolicy(
            total_budget_seconds=10.0,
            backoff_seconds=(1.0,),
            monotonic=clock.monotonic,
            sleep=clock.advance,
        ),
    ).search("current Bitcoin news")

    assert evidence
    assert tool_types == ["web_search", "web_search_preview"]
    assert len(timeouts) == 2
    assert 0 < timeouts[1] < timeouts[0] <= 10


def test_openai_transport_receives_search_budget_as_actual_request_timeout() -> None:
    request_timeouts: list[dict[str, float]] = []
    request_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_timeouts.append(request.extensions["timeout"])
        request_paths.append(request.url.path)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "resp_timeout_contract",
                "created_at": 1.0,
                "model": "capability-test",
                "object": "response",
                "output": [
                    {
                        "id": "search_1",
                        "action": {"type": "search", "query": "bitcoin"},
                        "status": "completed",
                        "type": "web_search_call",
                    },
                    {
                        "id": "message_1",
                        "content": [
                            {
                                "annotations": [
                                    {
                                        "end_index": 8,
                                        "start_index": 0,
                                        "title": "Markets",
                                        "type": "url_citation",
                                        "url": "https://www.reuters.com/markets/",
                                    }
                                ],
                                "text": "Markets.",
                                "type": "output_text",
                            }
                        ],
                        "role": "assistant",
                        "status": "completed",
                        "type": "message",
                    },
                ],
                "parallel_tool_calls": True,
                "status": "completed",
                "tool_choice": "auto",
                "tools": [],
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        model = ChatOpenAI(
            model="capability-test",
            api_key="test-key",
            base_url="https://model.invalid/v1",
            http_client=http_client,
            use_responses_api=True,
            output_version="responses/v1",
            max_retries=0,
            timeout=90,
        )

        evidence = BuiltinWebSearchProvider(
            model,
            retry_policy=SearchRetryPolicy(max_attempts=1),
        ).search("current Bitcoin news")
    finally:
        http_client.close()

    assert evidence
    assert request_paths == ["/v1/responses"]
    assert len(request_timeouts) == 1
    assert request_timeouts[0]
    assert all(
        0 < timeout <= 30 for timeout in request_timeouts[0].values()
    )


@pytest.mark.parametrize(
    "missing_capability",
    ["tool_calling", "structured_output", "streaming", "usage_reporting"],
)
def test_required_model_capability_cannot_fall_back_to_tavily(
    missing_capability: str,
) -> None:
    capabilities = ready_capabilities(**{missing_capability: False})

    with pytest.raises(SearchReadinessError, match=missing_capability):
        select_search_provider(
            capabilities,
            tavily_configured=True,
            tavily_connected=True,
        )


def test_builtin_web_search_requires_a_real_citation() -> None:
    capabilities = ready_capabilities(builtin_web_search_citation_count=0)

    with pytest.raises(SearchReadinessError, match="citation"):
        select_search_provider(
            capabilities,
            tavily_configured=False,
            tavily_connected=False,
        )


def test_tavily_is_selected_only_for_builtin_search_failure() -> None:
    capabilities = ready_capabilities(
        builtin_web_search_invoked=True,
        builtin_web_search_citation_count=0,
    )

    selected = select_search_provider(
        capabilities,
        tavily_configured=True,
        tavily_connected=True,
    )

    assert selected is SearchProvider.TAVILY


def test_builtin_search_is_preferred_when_verified() -> None:
    selected = select_search_provider(
        ready_capabilities(),
        tavily_configured=True,
        tavily_connected=True,
    )

    assert selected is SearchProvider.BUILTIN


def test_runtime_uses_explicit_builtin_provider_without_reprobing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import crypto_alert_v2.agents.research as research_module

    selected = RecordingResearchCollector()
    monkeypatch.setattr(
        research_module,
        "BuiltinResearchCollector",
        lambda _: selected,
    )
    collector = CapabilityAwareResearchCollector(
        object(),  # type: ignore[arg-type]
        tavily_api_key=None,
        provider=SearchProvider.BUILTIN,
    )

    result = collector.collect("bounded research")

    assert result is not None
    assert selected.queries == ["bounded research"]


def test_explicit_tavily_provider_requires_its_key() -> None:
    collector = CapabilityAwareResearchCollector(
        object(),  # type: ignore[arg-type]
        tavily_api_key=None,
        provider=SearchProvider.TAVILY,
    )

    with pytest.raises(SearchReadinessError, match="Tavily"):
        collector.collect("bounded research")


def test_explicit_duckduckgo_provider_uses_the_official_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import crypto_alert_v2.agents.research as research_module

    selected = RecordingResearchCollector()
    monkeypatch.setattr(
        research_module,
        "DuckDuckGoResearchCollector",
        lambda _, **__: selected,
    )
    collector = CapabilityAwareResearchCollector(
        object(),  # type: ignore[arg-type]
        tavily_api_key=None,
        provider=SearchProvider.DUCKDUCKGO,
    )

    result = collector.collect("bounded research")

    assert result is not None
    assert selected.queries == ["bounded research"]


def test_readiness_prefers_verified_builtin_without_probing_tavily() -> None:
    tavily_probe_calls = 0

    def unexpected_tavily_probe(_: str) -> bool:
        nonlocal tavily_probe_calls
        tavily_probe_calls += 1
        return True

    readiness = establish_search_readiness(
        model=object(),  # type: ignore[arg-type]
        model_name="capability-test",
        base_url="https://user:password@model.example/v1?token=secret",
        tavily_api_key="must-not-be-exposed",
        capability_probe=lambda _: ready_capabilities(),
        tavily_probe=unexpected_tavily_probe,
        now=lambda: datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
    )

    assert readiness.selected_provider is SearchProvider.BUILTIN
    assert readiness.status == "ready"
    assert readiness.endpoint == "https://model.example"
    assert readiness.model == "capability-test"
    assert readiness.tavily_configured is True
    assert readiness.tavily_connected is False
    assert tavily_probe_calls == 0
    public = readiness.model_dump(mode="json")
    assert "password" not in str(public)
    assert "secret" not in str(public)
    with pytest.raises(ValidationError):
        SearchReadiness.model_validate({**public, "selected_provider": "fixture"})
    with pytest.raises(ValidationError):
        readiness.selected_provider = SearchProvider.TAVILY  # type: ignore[misc]


@pytest.mark.asyncio
async def test_explicit_duckduckgo_readiness_is_probed_and_frozen() -> None:
    probe_proxies: list[str | None] = []

    async def duckduckgo_probe(proxy: str | None) -> bool:
        probe_proxies.append(proxy)
        return True

    readiness = await establish_search_readiness_async(
        model=object(),  # type: ignore[arg-type]
        model_name="capability-test",
        base_url="https://model.example/v1",
        tavily_api_key=None,
        capability_probe=lambda _: ready_capabilities(
            builtin_web_search_invoked=False,
            builtin_web_search_citation_count=0,
        ),
        requested_provider=SearchProvider.DUCKDUCKGO,
        duckduckgo_probe=duckduckgo_probe,
        search_http_proxy="http://127.0.0.1:7890",
        now=lambda: datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
    )

    assert readiness.selected_provider is SearchProvider.DUCKDUCKGO
    assert readiness.duckduckgo_connected is True
    assert readiness.tavily_connected is False
    assert probe_proxies == ["http://127.0.0.1:7890"]


def test_duckduckgo_readiness_requires_a_successful_provider_probe() -> None:
    with pytest.raises(ValidationError, match="DuckDuckGo"):
        SearchReadiness(
            status="ready",
            selected_provider=SearchProvider.DUCKDUCKGO,
            probed_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
            model="capability-test",
            endpoint="https://model.example",
            capabilities=ready_capabilities(),
            tavily_configured=False,
            tavily_connected=False,
        )


def test_failed_builtin_without_tavily_fails_readiness() -> None:
    capabilities = ready_capabilities(
        builtin_web_search_invoked=False,
        builtin_web_search_citation_count=0,
    )

    with pytest.raises(SearchReadinessError, match="Tavily is not configured"):
        establish_search_readiness(
            model=object(),  # type: ignore[arg-type]
            model_name="capability-test",
            base_url=None,
            tavily_api_key=None,
            capability_probe=lambda _: capabilities,
            tavily_probe=lambda _: True,
        )


def test_readiness_drops_malformed_endpoint_metadata_without_leaking() -> None:
    readiness = establish_search_readiness(
        model=object(),  # type: ignore[arg-type]
        model_name="capability-test",
        base_url=(
            "https://user:password@model.example:secret-port/v1?token=secret"
        ),
        tavily_api_key=None,
        capability_probe=lambda _: ready_capabilities(),
        tavily_probe=lambda _: True,
    )

    assert readiness.endpoint is None
    serialized = readiness.model_dump_json()
    assert "password" not in serialized
    assert "secret" not in serialized


def test_failed_builtin_with_unreachable_tavily_fails_readiness() -> None:
    capabilities = ready_capabilities(
        builtin_web_search_invoked=False,
        builtin_web_search_citation_count=0,
    )

    def unavailable(_: str) -> bool:
        raise ResearchUnavailable(
            "connectivity failed",
            provider="tavily",
            retryable=True,
            error_type="TimeoutError",
        )

    with pytest.raises(SearchReadinessError, match="connectivity failed"):
        establish_search_readiness(
            model=object(),  # type: ignore[arg-type]
            model_name="capability-test",
            base_url=None,
            tavily_api_key="configured-but-unreachable",
            capability_probe=lambda _: capabilities,
            tavily_probe=unavailable,
        )
