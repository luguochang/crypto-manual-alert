from datetime import UTC, datetime

import httpx
import pytest
from langchain_core.messages import AIMessage
from openai import APITimeoutError

from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    DuckDuckGoSearchProvider,
    ResearchUnavailable,
    SearchEvidenceUnavailable,
    TavilySearchProvider,
    parse_builtin_search_response,
    parse_duckduckgo_response,
    parse_tavily_response,
)
from crypto_alert_v2.providers.retry_policy import SearchRetryPolicy


def test_builtin_search_parser_returns_typed_citation() -> None:
    response = AIMessage(
        content=[
            {"type": "web_search_call", "id": "search_1", "status": "completed"},
            {
                "type": "text",
                "text": "Bitcoin rose after the policy announcement.",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url": "https://www.reuters.com/markets/",
                        "title": "Bitcoin reacts to policy",
                        "start_index": 0,
                        "end_index": 44,
                    }
                ],
            },
        ]
    )
    fetched_at = datetime(2026, 7, 13, tzinfo=UTC)

    evidence = parse_builtin_search_response(
        query="current Bitcoin policy news",
        response=response,
        fetched_at=fetched_at,
    )

    assert len(evidence) == 1
    assert str(evidence[0].final_url) == "https://www.reuters.com/markets/"
    assert evidence[0].title == "Bitcoin reacts to policy"
    assert evidence[0].excerpt == "Bitcoin rose after the policy announcement."
    assert evidence[0].fetched_at == fetched_at
    assert evidence[0].source == "openai_builtin_web_search"
    assert evidence[0].evidence_relation == "supports"
    assert len(evidence[0].content_hash) == 64


def test_builtin_search_parser_accepts_official_content_block_citations() -> None:
    response = AIMessage(
        content=[
            {
                "type": "server_tool_call",
                "id": "search_1",
                "name": "web_search",
                "args": {"query": "current Bitcoin price"},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "search_1",
                "status": "success",
            },
            {
                "type": "text",
                "text": "Bitcoin is trading near the cited market price.",
                "annotations": [
                    {
                        "type": "citation",
                        "url": "https://www.cmegroup.com/markets/cryptocurrencies/bitcoin/bitcoin.html",
                        "title": "Bitcoin market price",
                    }
                ],
            },
        ]
    )

    evidence = parse_builtin_search_response(
        query="current Bitcoin price",
        response=response,
        fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert [str(item.final_url) for item in evidence] == [
        "https://www.cmegroup.com/markets/cryptocurrencies/bitcoin/bitcoin.html"
    ]
    assert evidence[0].title == "Bitcoin market price"


def test_builtin_search_parser_rejects_model_text_url_after_successful_server_search() -> None:
    response = AIMessage(
        content=[
            {
                "type": "server_tool_call",
                "id": "search_1",
                "name": "web_search",
                "args": {"query": "current Bitcoin macro news"},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "search_1",
                "status": "success",
            },
            {
                "type": "text",
                "text": (
                    "Current macro coverage: "
                    "https://example.com/bitcoin-macro."
                ),
                "annotations": [],
            },
        ]
    )

    with pytest.raises(ResearchUnavailable, match="provider URL citation"):
        parse_builtin_search_response(
            query="current Bitcoin macro news",
            response=response,
            fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
        )


def test_builtin_search_parser_rejects_plain_model_url_without_server_search() -> None:
    response = AIMessage(
        content=[
            {
                "type": "text",
                "text": "Unverified model URL: https://example.com/not-searched",
                "annotations": [],
            }
        ]
    )

    with pytest.raises(SearchEvidenceUnavailable, match="citation"):
        parse_builtin_search_response(
            query="current Bitcoin news",
            response=response,
            fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "search_blocks",
    [
        [],
        [
            {
                "type": "server_tool_call",
                "id": "search_incomplete",
                "name": "web_search",
                "args": {"query": "current Bitcoin news"},
            }
        ],
    ],
)
def test_builtin_search_parser_rejects_provider_annotation_without_successful_call(
    search_blocks: list[dict[str, object]],
) -> None:
    response = AIMessage(
        content=[
            *search_blocks,
            {
                "type": "text",
                "text": "A provider-shaped citation without a completed call.",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url": "https://www.reuters.com/markets/",
                        "title": "Unverified citation",
                    }
                ],
            },
        ]
    )

    with pytest.raises(ResearchUnavailable, match="completed.*provider URL citation"):
        parse_builtin_search_response(
            query="current Bitcoin news",
            response=response,
            fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
        )


def test_builtin_search_parser_rejects_private_url_from_server_search_text() -> None:
    response = AIMessage(
        content=[
            {
                "type": "server_tool_call",
                "id": "search_1",
                "name": "web_search",
                "args": {},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "search_1",
                "status": "success",
            },
            {
                "type": "text",
                "text": "Private URL: https://127.0.0.1/internal",
                "annotations": [],
            },
        ]
    )

    with pytest.raises(SearchEvidenceUnavailable, match="citation"):
        parse_builtin_search_response(
            query="current Bitcoin news",
            response=response,
            fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/source",
        "https://source.example/source",
        "https://source.test/source",
        "https://service.internal/source",
        "https://localhost/source",
        "https://dev.localhost/source",
        "https://source.invalid/source",
    ],
)
def test_builtin_search_rejects_reserved_or_internal_provider_url(url: str) -> None:
    response = AIMessage(
        content=[
            {"type": "web_search_call", "id": "search_1", "status": "completed"},
            {
                "type": "text",
                "text": "Provider annotation with a non-public source.",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url": url,
                        "title": "Non-public source",
                    }
                ],
            },
        ]
    )

    with pytest.raises(ResearchUnavailable, match="provider URL citation"):
        parse_builtin_search_response(
            query="current Bitcoin news",
            response=response,
            fetched_at=datetime.now(UTC),
        )


def test_builtin_search_provider_normalizes_model_timeout_as_retryable() -> None:
    attempts = 0
    bound_tool_types: list[str] = []
    records = []

    def time_out(_: object) -> AIMessage:
        nonlocal attempts
        attempts += 1
        raise APITimeoutError(
            request=httpx.Request("POST", "https://model.example/v1/responses")
        )

    class TimedOutModel:
        def bind_tools(
            self,
            tools: list[dict[str, str]],
            **__: object,
        ) -> object:
            bound_tool_types.append(tools[0]["type"])

            class BoundSearch:
                def invoke(
                    self,
                    input: object,
                    config: object = None,
                    **kwargs: object,
                ) -> AIMessage:
                    del config
                    assert 0 < float(kwargs["timeout"]) <= 30
                    return time_out(input)

            return BoundSearch()

    with pytest.raises(SearchEvidenceUnavailable) as raised:
        BuiltinWebSearchProvider(  # type: ignore[arg-type]
            TimedOutModel(),
            retry_policy=SearchRetryPolicy(
                sleep=lambda _: None,
                record_attempt=records.append,
            ),
        ).search("current Bitcoin news")

    assert raised.value.retryable is True
    assert raised.value.code == "research_unavailable"
    assert raised.value.provider == "builtin_web_search"
    assert raised.value.attempt == 3
    assert "APITimeoutError" in str(raised.value)
    assert attempts == 3
    assert bound_tool_types == ["web_search", "web_search", "web_search"]
    assert [record.attempt for record in records] == [1, 2, 3]
    assert [record.outcome for record in records] == [
        "retryable_failure",
        "retryable_failure",
        "terminal_failure",
    ]


def test_builtin_search_provider_has_one_retry_owner_and_records_each_attempt() -> None:
    bind_options: dict[str, object] = {}
    invocation_options: list[dict[str, object]] = []
    attempts = 0
    records = []

    def searched(_: object) -> AIMessage:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return AIMessage(
                content=[
                    {
                        "type": "text",
                        "text": "No verified source was returned.",
                        "annotations": [],
                    }
                ]
            )
        return AIMessage(
            content=[
                {
                    "type": "server_tool_call",
                    "id": "search_required",
                    "name": "web_search",
                    "args": {"query": "current Bitcoin news"},
                },
                {
                    "type": "server_tool_result",
                    "tool_call_id": "search_required",
                    "status": "success",
                },
                {
                    "type": "text",
                    "text": "Current Bitcoin news source.",
                    "annotations": [
                        {
                            "type": "citation",
                            "url": "https://www.coindesk.com/price/bitcoin",
                            "title": "Current Bitcoin news",
                        }
                    ],
                },
            ]
        )

    class BoundSearch:
        def invoke(
            self,
            input: object,
            config: object = None,
            **kwargs: object,
        ) -> AIMessage:
            del config
            invocation_options.append({"input": input, **kwargs})
            return searched(input)

    class RecordingModel:
        def bind_tools(
            self, _: object, **kwargs: object
        ) -> BoundSearch:
            bind_options.update(kwargs)
            return BoundSearch()

    evidence = BuiltinWebSearchProvider(  # type: ignore[arg-type]
        RecordingModel(),
        retry_policy=SearchRetryPolicy(
            sleep=lambda _: None,
            record_attempt=records.append,
        ),
    ).search(
        "current Bitcoin news",
        config={"metadata": {"correlation_id": "corr-search-1"}},
    )

    assert evidence
    assert attempts == 2
    assert bind_options == {}
    assert len(invocation_options) == 2
    assert all(0 < float(item["timeout"]) <= 30 for item in invocation_options)
    assert [record.attempt for record in records] == [1, 2]
    assert [record.outcome for record in records] == [
        "retryable_failure",
        "succeeded",
    ]
    assert [record.correlation_id for record in records] == [
        "corr-search-1",
        "corr-search-1",
    ]


@pytest.mark.parametrize(
    ("first_response", "first_error_type"),
    [
        (
            AIMessage(
                content=[
                    {
                        "type": "text",
                        "text": "No completed server search was returned.",
                        "annotations": [],
                    }
                ]
            ),
            "UnverifiedServerToolCall",
        ),
        (
            AIMessage(
                content=[
                    {
                        "type": "web_search_call",
                        "id": "search_without_citation",
                        "status": "completed",
                    },
                    {
                        "type": "text",
                        "text": "The search completed without a provider citation.",
                        "annotations": [],
                    },
                ]
            ),
            "MissingProviderCitation",
        ),
    ],
    ids=["unverified-server-tool-call", "missing-provider-citation"],
)
def test_builtin_search_uses_preview_on_the_same_retry_budget_after_unverified_evidence(
    first_response: AIMessage,
    first_error_type: str,
) -> None:
    class Clock:
        def __init__(self) -> None:
            self.now = 100.0

        def monotonic(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    clock = Clock()
    responses = [
        first_response,
        AIMessage(
            content=[
                {
                    "type": "web_search_call",
                    "id": "preview_search",
                    "status": "completed",
                },
                {
                    "type": "text",
                    "text": "Verified evidence returned by the compatibility search.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://www.reuters.com/markets/currencies/",
                            "title": "Currencies",
                        }
                    ],
                },
            ]
        ),
    ]
    bound_tool_types: list[str] = []
    invocation_timeouts: list[float] = []
    records = []

    class BoundSearch:
        def invoke(
            self,
            input: object,
            config: object = None,
            **kwargs: object,
        ) -> AIMessage:
            del input, config
            invocation_timeouts.append(float(kwargs["timeout"]))
            clock.advance(0.25)
            return responses.pop(0)

    class RecordingModel:
        def bind_tools(
            self,
            tools: list[dict[str, str]],
            **kwargs: object,
        ) -> BoundSearch:
            assert kwargs == {}
            bound_tool_types.append(tools[0]["type"])
            return BoundSearch()

    evidence = BuiltinWebSearchProvider(  # type: ignore[arg-type]
        RecordingModel(),
        retry_policy=SearchRetryPolicy(
            max_attempts=2,
            total_budget_seconds=10.0,
            backoff_seconds=(1.0,),
            monotonic=clock.monotonic,
            sleep=clock.advance,
            record_attempt=records.append,
        ),
    ).search(
        "current Bitcoin currency news",
        config={"metadata": {"correlation_id": "corr-preview-1"}},
    )

    assert bound_tool_types == ["web_search", "web_search_preview"]
    assert len(invocation_timeouts) == 2
    assert 0 < invocation_timeouts[1] < invocation_timeouts[0] <= 10.0
    assert [record.remaining_budget_seconds for record in records] == pytest.approx(
        invocation_timeouts
    )
    assert [record.attempt for record in records] == [1, 2]
    assert [record.outcome for record in records] == [
        "retryable_failure",
        "succeeded",
    ]
    assert records[0].error_type == first_error_type
    assert {record.correlation_id for record in records} == {"corr-preview-1"}
    assert responses == []
    assert [str(item.final_url) for item in evidence] == [
        "https://www.reuters.com/markets/currencies/"
    ]
    assert evidence[0].title == "Currencies"
    assert evidence[0].excerpt == (
        "Verified evidence returned by the compatibility search."
    )
    assert evidence[0].source == "openai_builtin_web_search"


def test_builtin_search_switches_to_preview_only_after_evidence_failure() -> None:
    responses: list[AIMessage | Exception] = [
        TimeoutError("transient model timeout"),
        AIMessage(
            content=[
                {
                    "type": "text",
                    "text": "No completed server search was returned.",
                    "annotations": [],
                }
            ]
        ),
        AIMessage(
            content=[
                {
                    "type": "web_search_call",
                    "id": "preview_search",
                    "status": "completed",
                },
                {
                    "type": "text",
                    "text": "Verified evidence after compatibility selection.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://www.reuters.com/technology/",
                            "title": "Technology",
                        }
                    ],
                },
            ]
        ),
    ]
    bound_tool_types: list[str] = []
    records = []

    class BoundSearch:
        def invoke(
            self,
            input: object,
            config: object = None,
            **kwargs: object,
        ) -> AIMessage:
            del input, config
            assert 0 < float(kwargs["timeout"]) <= 30
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

    class RecordingModel:
        def bind_tools(
            self,
            tools: list[dict[str, str]],
            **kwargs: object,
        ) -> BoundSearch:
            assert kwargs == {}
            bound_tool_types.append(tools[0]["type"])
            return BoundSearch()

    evidence = BuiltinWebSearchProvider(  # type: ignore[arg-type]
        RecordingModel(),
        retry_policy=SearchRetryPolicy(
            backoff_seconds=(0.0,),
            sleep=lambda _: None,
            record_attempt=records.append,
        ),
    ).search("current Bitcoin technology news")

    assert bound_tool_types == [
        "web_search",
        "web_search",
        "web_search_preview",
    ]
    assert [record.error_type for record in records] == [
        "TimeoutError",
        "UnverifiedServerToolCall",
        None,
    ]
    assert [record.outcome for record in records] == [
        "retryable_failure",
        "retryable_failure",
        "succeeded",
    ]
    assert responses == []
    assert [str(item.final_url) for item in evidence] == [
        "https://www.reuters.com/technology/"
    ]


def test_builtin_search_without_url_citation_is_provider_failure() -> None:
    response = AIMessage(
        content=[
            {"type": "web_search_call", "id": "search_1", "status": "completed"},
            {"type": "text", "text": "A claim without a source.", "annotations": []},
        ]
    )

    with pytest.raises(SearchEvidenceUnavailable, match="citation"):
        parse_builtin_search_response(
            query="current Bitcoin news",
            response=response,
            fetched_at=datetime.now(UTC),
        )


def test_builtin_malformed_provider_annotation_is_typed_research_unavailable() -> None:
    response = AIMessage(
        content=[
            {"type": "web_search_call", "id": "search_1", "status": "completed"},
            {
                "type": "text",
                "text": "Malformed provider citation.",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url": "https://[invalid-host",
                        "title": "Malformed",
                    }
                ],
            },
        ]
    )

    with pytest.raises(ResearchUnavailable) as raised:
        parse_builtin_search_response(
            query="current Bitcoin news",
            response=response,
            fetched_at=datetime.now(UTC),
        )

    assert raised.value.code == "research_unavailable"
    assert raised.value.provider == "builtin_web_search"


def test_search_parser_deduplicates_repeated_urls() -> None:
    annotation = {
        "type": "url_citation",
        "url": "https://www.reuters.com/markets/",
        "title": "One",
        "start_index": 0,
        "end_index": 4,
    }
    response = AIMessage(
        content=[
            {"type": "web_search_call", "id": "search_1", "status": "completed"},
            {
                "type": "text",
                "text": "Same citation twice.",
                "annotations": [annotation, annotation],
            }
        ]
    )

    evidence = parse_builtin_search_response(
        query="deduplicate",
        response=response,
        fetched_at=datetime.now(UTC),
    )

    assert [str(item.final_url) for item in evidence] == [
        "https://www.reuters.com/markets/"
    ]


def test_tavily_parser_returns_normalized_web_evidence() -> None:
    evidence = parse_tavily_response(
        query="bitcoin macro",
        response={
            "results": [
                {
                    "url": "https://www.imf.org/en/Topics/fintech",
                    "title": "Bitcoin macro update",
                    "content": "Rates and the dollar moved before the event.",
                }
            ]
        },
        fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert len(evidence) == 1
    assert str(evidence[0].final_url) == "https://www.imf.org/en/Topics/fintech"
    assert evidence[0].source == "tavily"
    assert evidence[0].excerpt == "Rates and the dollar moved before the event."


def test_duckduckgo_parser_returns_normalized_provider_evidence() -> None:
    evidence = parse_duckduckgo_response(
        query="bitcoin macro",
        response=[
            {
                "link": "https://www.reuters.com/markets/currencies/",
                "title": "Bitcoin and macro markets",
                "snippet": "Bitcoin moved as global rates and the dollar changed.",
                "date": "2026-07-14T09:30:00+00:00",
                "source": "Reuters",
            }
        ],
        fetched_at=datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
    )

    assert len(evidence) == 1
    assert str(evidence[0].final_url) == (
        "https://www.reuters.com/markets/currencies/"
    )
    assert evidence[0].source == "duckduckgo"
    assert evidence[0].author == "Reuters"
    assert evidence[0].published_at == datetime(
        2026, 7, 14, 9, 30, tzinfo=UTC
    )


def test_duckduckgo_provider_invokes_the_official_tool_with_typed_input() -> None:
    class RecordingTool:
        def __init__(self) -> None:
            self.calls: list[tuple[object, object]] = []

        def invoke(self, input: object, config: object = None) -> object:
            self.calls.append((input, config))
            return [
                {
                    "link": "https://www.cmegroup.com/markets/cryptocurrencies.html",
                    "title": "Cryptocurrency markets",
                    "snippet": "Public market evidence.",
                }
            ]

    tool = RecordingTool()
    evidence = DuckDuckGoSearchProvider(
        tool=tool,  # type: ignore[arg-type]
        retry_policy=SearchRetryPolicy(max_attempts=1),
    ).search(
        "current bitcoin market",
        config={"metadata": {"correlation_id": "corr-ddg-1"}},
    )

    assert tool.calls == [
        (
            {"query": "current bitcoin market"},
            {"metadata": {"correlation_id": "corr-ddg-1"}},
        )
    ]
    assert [item.source for item in evidence] == ["duckduckgo"]


def test_tavily_error_is_not_a_successful_empty_result() -> None:
    with pytest.raises(ResearchUnavailable, match="Tavily") as raised:
        parse_tavily_response(
            query="bitcoin macro",
            response={"error": RuntimeError("provider down")},
            fetched_at=datetime.now(UTC),
        )

    assert raised.value.code == "research_unavailable"
    assert raised.value.provider == "tavily"


def test_tavily_malformed_url_is_typed_research_unavailable() -> None:
    with pytest.raises(ResearchUnavailable) as raised:
        parse_tavily_response(
            query="bitcoin macro",
            response={
                "results": [
                    {
                        "url": "https://[invalid-host",
                        "title": "Malformed",
                        "content": "Provider returned malformed evidence.",
                    }
                ]
            },
            fetched_at=datetime.now(UTC),
        )

    assert raised.value.code == "research_unavailable"
    assert raised.value.provider == "tavily"


def test_tavily_invocation_exception_is_typed_research_unavailable() -> None:
    class FailingTool:
        def invoke(self, input: object, config: object = None) -> object:
            del input, config
            raise RuntimeError("provider internals must not escape")

    with pytest.raises(ResearchUnavailable) as raised:
        TavilySearchProvider(
            tool=FailingTool(),  # type: ignore[arg-type]
            retry_policy=SearchRetryPolicy(sleep=lambda _: None),
        ).search("bitcoin macro")

    assert raised.value.code == "research_unavailable"
    assert raised.value.provider == "tavily"
    assert raised.value.error_type == "RuntimeError"
    assert "provider internals" not in str(raised.value)


def test_tavily_empty_and_invalid_evidence_retry_under_one_owner() -> None:
    class SequenceTool:
        def __init__(self) -> None:
            self.responses = [
                {"results": []},
                {
                    "results": [
                        {
                            "url": "https://example.com/not-real-evidence",
                            "title": "Reserved source",
                            "content": "This must not be accepted as evidence.",
                        }
                    ]
                },
                {
                    "results": [
                        {
                            "url": "https://www.imf.org/en/Topics/fintech",
                            "title": "Fintech",
                            "content": "Public provider evidence.",
                        }
                    ]
                },
            ]

        def invoke(self, input: object, config: object = None) -> object:
            del input, config
            return self.responses.pop(0)

    records = []
    evidence = TavilySearchProvider(
        tool=SequenceTool(),  # type: ignore[arg-type]
        retry_policy=SearchRetryPolicy(
            sleep=lambda _: None,
            record_attempt=records.append,
        ),
    ).search(
        "bitcoin macro",
        config={"metadata": {"correlation_id": "corr-tavily-1"}},
    )

    assert [str(item.final_url) for item in evidence] == [
        "https://www.imf.org/en/Topics/fintech"
    ]
    assert [record.attempt for record in records] == [1, 2, 3]
    assert [record.outcome for record in records] == [
        "retryable_failure",
        "retryable_failure",
        "succeeded",
    ]
    assert {record.correlation_id for record in records} == {"corr-tavily-1"}


@pytest.mark.asyncio
async def test_async_tavily_retries_under_the_same_search_owner() -> None:
    class AsyncSequenceTool:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, input: object, config: object = None) -> object:
            del input, config
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("transient Tavily timeout")
            return {
                "results": [
                    {
                        "url": "https://www.imf.org/en/Topics/fintech",
                        "title": "Fintech",
                        "content": "Public provider evidence.",
                    }
                ]
            }

    tool = AsyncSequenceTool()
    records = []
    provider = TavilySearchProvider(
        tool=tool,  # type: ignore[arg-type]
        retry_policy=SearchRetryPolicy(
            backoff_seconds=(0.0,),
            record_attempt=records.append,
        ),
    )

    evidence = await provider.asearch(
        "bitcoin macro",
        config={"metadata": {"correlation_id": "corr-tavily-async"}},
    )

    assert tool.calls == 3
    assert [str(item.final_url) for item in evidence] == [
        "https://www.imf.org/en/Topics/fintech"
    ]
    assert [record.outcome for record in records] == [
        "retryable_failure",
        "retryable_failure",
        "succeeded",
    ]
    assert {record.correlation_id for record in records} == {
        "corr-tavily-async"
    }
