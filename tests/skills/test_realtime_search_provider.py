from __future__ import annotations

import json

import httpx
import pytest

from crypto_manual_alert.skills.facade import SkillTaskContext
from crypto_manual_alert.skills.realtime_search import RealtimeSearchSkill
from crypto_manual_alert.skills.realtime_search import providers as realtime_providers
from crypto_manual_alert.skills.realtime_search.providers import SearchProviderRequest


class RecordingSearchProvider:
    def __init__(self) -> None:
        self.request: SearchProviderRequest | None = None

    def search(self, request: SearchProviderRequest) -> list[dict[str, str]]:
        self.request = request
        return [
            {
                "title": "provider ETF flow surprise",
                "url": "https://example.test/provider-etf",
                "snippet_ref": "provider.search[0].snippet_redacted",
                "source_type": "exchange_native",
            }
        ]


def test_realtime_search_uses_injected_provider_before_input_view_results():
    provider = RecordingSearchProvider()
    context = SkillTaskContext(
        skill_name="realtime_search",
        task_id="skill:realtime_search",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-search",
        query="ETF flow surprise",
        input_view={
            "search_results": [
                {
                    "title": "input view fallback should not be used",
                    "url": "https://example.test/fallback",
                    "snippet_ref": "fallback[0]",
                }
            ]
        },
        max_depth=2,
        timeout_seconds=12,
    )

    public = RealtimeSearchSkill(provider=provider).run(context).to_public_dict()

    assert provider.request == SearchProviderRequest(
        symbol="ETH-USDT-SWAP",
        query="ETF flow surprise",
        trace_id="trace-search",
        task_id="skill:realtime_search",
        max_results=5,
    )
    assert public["evidence_candidates"] == [
        {
            "title": "provider ETF flow surprise",
            "url": "https://example.test/provider-etf",
            "snippet_ref": "provider.search[0].snippet_redacted",
            "source_type": "search_derived",
        }
    ]


def test_responses_web_search_provider_posts_web_search_tool_and_returns_refs_only():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        payload = json.loads(request.content)
        captured["payload"] = payload
        return httpx.Response(
            200,
            json={
                "usage": {"input_tokens": 11, "output_tokens": 13, "total_tokens": 24},
                "tool_usage": {"web_search": {"num_requests": 1}},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "ETH headline from search. URL: https://example.test/eth",
                            }
                        ],
                    }
                ],
            },
        )

    provider = realtime_providers.ResponsesWebSearchProvider(
        base_url="https://example.test",
        model="gpt-test",
        api_key="search-key",
        timeout_seconds=3,
        max_results=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = provider.search(
        SearchProviderRequest(
            symbol="ETH-USDT-SWAP",
            query="ETF flow surprise",
            trace_id="trace-search",
            task_id="skill:realtime_search",
            max_results=2,
        )
    )

    assert captured["url"] == "https://example.test/v1/responses"
    assert captured["authorization"] == "Bearer search-key"
    assert captured["payload"]["model"] == "gpt-test"
    assert captured["payload"]["tools"] == [{"type": "web_search"}]
    assert "ETH-USDT-SWAP" in captured["payload"]["input"]
    assert "ETF flow surprise" in captured["payload"]["input"]
    assert results == [
        {
            "title": "Responses web search: ETH-USDT-SWAP",
            "url": "responses://web_search",
            "snippet_ref": results[0]["snippet_ref"],
            "source_type": "search_derived",
        }
    ]
    assert results[0]["snippet_ref"].startswith("responses.realtime_search.trace-search.0.snippet_sha256:")
    assert "ETH headline from search" not in json.dumps(results)


def test_responses_web_search_provider_rejects_zero_web_search_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tool_usage": {"web_search": {"num_requests": 0}},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "No search used."}]}],
            },
        )

    provider = realtime_providers.ResponsesWebSearchProvider(
        base_url="https://example.test",
        model="gpt-test",
        api_key="search-key",
        timeout_seconds=3,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RuntimeError, match="web_search"):
        provider.search(
            SearchProviderRequest(
                symbol="ETH-USDT-SWAP",
                query="ETF flow surprise",
                trace_id="trace-search",
                task_id="skill:realtime_search",
            )
        )


def test_responses_web_search_provider_requires_api_key():
    with pytest.raises(ValueError, match="api_key"):
        realtime_providers.ResponsesWebSearchProvider(
            base_url="https://example.test",
            model="gpt-test",
            api_key="",
            timeout_seconds=3,
        )


def test_responses_web_search_provider_repr_does_not_expose_api_key():
    provider = realtime_providers.ResponsesWebSearchProvider(
        base_url="https://example.test",
        model="gpt-test",
        api_key="search-key",
        timeout_seconds=3,
    )

    assert "search-key" not in repr(provider)
