from datetime import UTC, datetime

import httpx
import pytest
from langchain_core.messages import AIMessage
from openai import APITimeoutError

from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    ResearchUnavailable,
    SearchEvidenceUnavailable,
    TavilySearchProvider,
    parse_builtin_search_response,
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
    records = []

    def time_out(_: object) -> AIMessage:
        nonlocal attempts
        attempts += 1
        raise APITimeoutError(
            request=httpx.Request("POST", "https://model.example/v1/responses")
        )

    class TimedOutModel:
        def bind_tools(self, _: object, **__: object) -> object:
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
