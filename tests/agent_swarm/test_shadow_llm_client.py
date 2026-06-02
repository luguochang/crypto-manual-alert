from __future__ import annotations

import json

import httpx
import pytest

from crypto_manual_alert.config import load_config
from crypto_manual_alert.agent_swarm.shadow_llm_client import (
    FixtureLlmShadowClient,
    OpenAICompatibleLlmShadowClient,
    build_openai_compatible_shadow_client_factory,
)


def test_fixture_shadow_client_returns_agent_specific_response():
    client = FixtureLlmShadowClient(
        {
            "RootCauseAgent": {"summary": "root fixture"},
            "MarketSentimentAgent": {"summary": "sentiment fixture"},
        }
    )

    assert client.complete({"agent_name": "RootCauseAgent"}) == '{"summary":"root fixture"}'
    assert client.complete({"agent_name": "RootCauseAgent"}, timeout_seconds=1) == '{"summary":"root fixture"}'
    assert client.complete({"agent_name": "UnknownAgent"}) == '{"summary":"fixture shadow audit"}'


def test_openai_compatible_shadow_client_posts_audit_only_chat_completion():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert request.url == "https://example.test/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        assert payload["model"] == "gpt-test"
        assert payload["messages"][0]["role"] == "system"
        assert "shadow worker" in payload["messages"][0]["content"]
        assert "decision_effect=none" in payload["messages"][0]["content"]
        assert payload["messages"][1]["role"] == "user"
        assert json.loads(payload["messages"][1]["content"])["agent_name"] == "RootCauseAgent"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"summary":"ok"}'}}]})

    client = OpenAICompatibleLlmShadowClient(
        base_url="https://example.test",
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=30,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.complete({"agent_name": "RootCauseAgent", "input_view": {"symbol": "ETH-USDT-SWAP"}}) == (
        '{"summary":"ok"}'
    )
    assert requests


def test_openai_compatible_shadow_client_uses_per_request_timeout_override():
    calls: list[dict[str, object]] = []

    class RecordingClient:
        def post(self, url, *, headers, json, timeout=None):  # noqa: ANN001 - test fake mirrors httpx subset.
            calls.append({"url": url, "timeout": timeout})
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"choices": [{"message": {"content": '{"summary":"ok"}'}}]},
            )

    client = OpenAICompatibleLlmShadowClient(
        base_url="https://example.test",
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=30,
        http_client=RecordingClient(),
    )

    assert client.complete({"agent_name": "RootCauseAgent"}, timeout_seconds=2.5) == '{"summary":"ok"}'

    assert calls == [{"url": "https://example.test/v1/chat/completions", "timeout": 2.5}]


def test_openai_shadow_client_factory_requires_explicit_credentials(monkeypatch):
    config = load_config("config/default.yaml")

    with pytest.raises(ValueError, match="openai_base_url"):
        build_openai_compatible_shadow_client_factory(config)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = config.decision.__class__(
        **{
            **config.decision.__dict__,
            "openai_base_url": "https://example.test",
            "openai_model": "gpt-test",
        }
    )
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
        shadow=config.shadow,
    )

    factory = build_openai_compatible_shadow_client_factory(config)
    client = factory("RootCauseAgent")

    assert isinstance(client, OpenAICompatibleLlmShadowClient)
    assert client.agent_name == "RootCauseAgent"
