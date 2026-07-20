from datetime import UTC, datetime

import httpx
import pytest
from langchain_core.messages import AIMessage
from openai import APITimeoutError

from crypto_alert_v2.providers.search import (
    BuiltinWebSearchProvider,
    DdgsMetasearchProvider,
    ResearchUnavailable,
    SearchEvidenceUnavailable,
    TavilySearchProvider,
    parse_builtin_search_response,
    parse_ddgs_metasearch_response,
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
    assert evidence[0].excerpt == "Bitcoin is trading near the cited market price."


def test_completed_open_page_can_be_enabled_for_strict_gateway_compatibility() -> None:
    url = "https://finance.yahoo.com/quote/BTC-USD/"
    response = AIMessage(
        content=[
            {
                "type": "server_tool_call",
                "id": "search_1",
                "name": "web_search",
                "args": {"type": "search", "query": "current BTC price"},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "search_1",
                "status": "success",
            },
            {
                "type": "server_tool_call",
                "id": "open_1",
                "name": "web_search",
                "args": {"type": "open_page", "url": url},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "open_1",
                "status": "success",
            },
            {
                "type": "text",
                "text": f"Bitcoin is $64,169.21 USD ({url}).",
                "annotations": [],
            },
        ]
    )

    evidence = parse_builtin_search_response(
        query="current BTC price",
        response=response,
        fetched_at=datetime(2026, 7, 17, tzinfo=UTC),
        allow_completed_open_page_evidence=True,
    )

    assert len(evidence) == 1
    assert str(evidence[0].final_url) == url
    assert evidence[0].excerpt == f"Bitcoin is $64,169.21 USD ({url})."
    assert evidence[0].parser_version == "openai-responses-open-page-v1"


def test_completed_open_page_is_merged_with_a_bare_search_annotation() -> None:
    opened_url = "https://finance.yahoo.com/quote/BTC-USD/"
    search_url = "https://coinmarketcap.com/currencies/bitcoin/"
    response = AIMessage(
        content=[
            {
                "type": "server_tool_call",
                "id": "search_1",
                "name": "web_search",
                "args": {"type": "search", "query": "current BTC price"},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "search_1",
                "status": "success",
            },
            {
                "type": "text",
                "text": "CoinMarketCap",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url": search_url,
                        "title": "Bitcoin price",
                        "start_index": 0,
                        "end_index": 13,
                    }
                ],
            },
            {
                "type": "server_tool_call",
                "id": "open_1",
                "name": "web_search",
                "args": {"type": "open_page", "url": opened_url},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "open_1",
                "status": "success",
            },
            {
                "type": "text",
                "text": f"Bitcoin is $64,169.21 USD ({opened_url}).",
                "annotations": [],
            },
        ]
    )

    evidence = parse_builtin_search_response(
        query="current BTC price",
        response=response,
        fetched_at=datetime(2026, 7, 17, tzinfo=UTC),
        allow_completed_open_page_evidence=True,
    )

    assert [str(item.final_url) for item in evidence] == [search_url, opened_url]
    assert evidence[1].excerpt.startswith("Bitcoin is $64,169.21 USD")


def test_completed_open_page_is_rejected_by_default_research_contract() -> None:
    url = "https://finance.yahoo.com/quote/BTC-USD/"
    response = AIMessage(
        content=[
            {
                "type": "server_tool_call",
                "id": "open_1",
                "name": "web_search",
                "args": {"type": "open_page", "url": url},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "open_1",
                "status": "success",
            },
            {
                "type": "text",
                "text": f"Bitcoin is $64,169.21 USD ({url}).",
                "annotations": [],
            },
        ]
    )

    with pytest.raises(ResearchUnavailable) as caught:
        parse_builtin_search_response(
            query="current BTC price",
            response=response,
            fetched_at=datetime(2026, 7, 17, tzinfo=UTC),
        )

    assert caught.value.error_type == "MissingProviderCitation"


def test_open_page_compatibility_rejects_uncompleted_or_unlinked_pages() -> None:
    url = "https://finance.yahoo.com/quote/BTC-USD/"
    response = AIMessage(
        content=[
            {
                "type": "server_tool_call",
                "id": "open_1",
                "name": "web_search",
                "args": {"type": "open_page", "url": url},
            },
            {
                "type": "server_tool_result",
                "tool_call_id": "open_1",
                "status": "failed",
            },
            {
                "type": "text",
                "text": "Bitcoin is $64,169.21 USD without its opened source URL.",
                "annotations": [],
            },
        ]
    )

    with pytest.raises(ResearchUnavailable):
        parse_builtin_search_response(
            query="current BTC price",
            response=response,
            fetched_at=datetime(2026, 7, 17, tzinfo=UTC),
            allow_completed_open_page_evidence=True,
        )


def test_builtin_search_parser_keeps_citation_excerpts_source_specific() -> None:
    first_claim = "Bitcoin rose after softer inflation data."
    second_claim = "ETF outflows later reduced near-term momentum."
    text = f"- {first_claim}\n- {second_claim}"
    response = AIMessage(
        content=[
            {"type": "web_search_call", "id": "search_1", "status": "completed"},
            {
                "type": "text",
                "text": text,
                "annotations": [
                    {
                        "type": "url_citation",
                        "url": "https://www.reuters.com/markets/inflation/",
                        "title": "Inflation supports Bitcoin",
                        "start_index": text.index(first_claim),
                        "end_index": text.index(first_claim) + len(first_claim),
                    },
                    {
                        "type": "url_citation",
                        "url": "https://www.coindesk.com/markets/etf-outflows/",
                        "title": "ETF outflows weigh on momentum",
                        "start_index": text.index(second_claim),
                        "end_index": text.index(second_claim) + len(second_claim),
                    },
                ],
            },
        ]
    )

    evidence = parse_builtin_search_response(
        query="current Bitcoin macro news",
        response=response,
        fetched_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert [item.excerpt for item in evidence] == [first_claim, second_claim]
    assert evidence[0].content_hash != evidence[1].content_hash


def test_builtin_search_parser_uses_title_without_provider_offsets() -> None:
    response = AIMessage(
        content=[
            {"type": "web_search_call", "id": "search_1", "status": "completed"},
            {
                "type": "text",
                "text": "One aggregate answer covering two unrelated sources.",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url": "https://www.reuters.com/markets/rates/",
                        "title": "Rates pressure risk assets",
                    },
                    {
                        "type": "url_citation",
                        "url": "https://www.coindesk.com/markets/liquidity/",
                        "title": "Liquidity conditions improve",
                    },
                ],
            },
        ]
    )

    evidence = parse_builtin_search_response(
        query="current Bitcoin macro news",
        response=response,
        fetched_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert [item.excerpt for item in evidence] == [
        "Rates pressure risk assets",
        "Liquidity conditions improve",
    ]


def test_builtin_search_parser_rejects_model_text_url_after_successful_server_search() -> (
    None
):
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
                "text": ("Current macro coverage: https://example.com/bitcoin-macro."),
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


def test_builtin_search_honors_retry_after_from_provider_error_body() -> None:
    attempts = 0
    records = []

    class OriginBadGateway(Exception):
        body = {"retryable": True, "retry_after": 60}

    class FailingModel:
        def bind_tools(
            self,
            tools: list[dict[str, str]],
            **__: object,
        ) -> object:
            assert tools[0]["type"] == "web_search"

            class BoundSearch:
                def invoke(
                    self,
                    input: object,
                    config: object = None,
                    **kwargs: object,
                ) -> AIMessage:
                    nonlocal attempts
                    del input, config, kwargs
                    attempts += 1
                    raise OriginBadGateway("Error 502: origin bad gateway")

            return BoundSearch()

    with pytest.raises(SearchEvidenceUnavailable) as raised:
        BuiltinWebSearchProvider(  # type: ignore[arg-type]
            FailingModel(),
            retry_policy=SearchRetryPolicy(
                sleep=lambda _: None,
                record_attempt=records.append,
            ),
        ).search("current Bitcoin news")

    assert raised.value.retryable is True
    assert raised.value.retry_after_seconds == 60
    assert attempts == 1
    assert [record.outcome for record in records] == ["terminal_failure"]


def test_builtin_search_provider_has_one_retry_owner_and_records_each_attempt() -> None:
    bind_options: list[dict[str, object]] = []
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
        def bind_tools(self, _: object, **kwargs: object) -> BoundSearch:
            bind_options.append(dict(kwargs))
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
    assert bind_options == [
        {"tool_choice": "web_search", "parallel_tool_calls": False},
        {"tool_choice": "web_search_preview", "parallel_tool_calls": False},
    ]
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


def test_builtin_search_compacts_long_cjk_queries_for_provider_transport() -> None:
    prompts: list[str] = []

    class BoundSearch:
        def invoke(
            self,
            input: object,
            config: object = None,
            **kwargs: object,
        ) -> AIMessage:
            del config, kwargs
            prompts.append(str(input))
            return AIMessage(
                content=[
                    {
                        "type": "web_search_call",
                        "id": "search_compact",
                        "status": "completed",
                    },
                    {
                        "type": "text",
                        "text": "Current Bitcoin market evidence.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://www.reuters.com/markets/currencies/",
                                "title": "Bitcoin market evidence",
                            }
                        ],
                    },
                ]
            )

    class RecordingModel:
        def bind_tools(self, _: object, **kwargs: object) -> BoundSearch:
            assert kwargs == {
                "tool_choice": "web_search",
                "parallel_tool_calls": False,
            }
            return BoundSearch()

    original_query = (
        "结合当前宏观事件、真实市场结构与可验证来源，判断 BTC 在未来 4 小时的方向、"
        "主要风险和失效条件\nAsset: BTC\nMarket: cryptocurrency\nAnalysis horizon: 4h"
    )

    evidence = BuiltinWebSearchProvider(  # type: ignore[arg-type]
        RecordingModel(),
        retry_policy=SearchRetryPolicy(max_attempts=1),
    ).search(original_query)

    assert len(prompts) == 1
    assert original_query not in prompts[0]
    assert "BTC" in prompts[0]
    assert "macro" in prompts[0]
    assert evidence[0].query == original_query


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
            assert kwargs == {
                "tool_choice": tools[0]["type"],
                "parallel_tool_calls": False,
            }
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
    assert invocation_timeouts == pytest.approx([4.5, 8.75])
    assert [record.remaining_budget_seconds for record in records] == pytest.approx(
        [10.0, 8.75]
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
            assert kwargs == {
                "tool_choice": tools[0]["type"],
                "parallel_tool_calls": False,
            }
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
            },
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


def test_ddgs_metasearch_parser_returns_normalized_provider_evidence() -> None:
    evidence = parse_ddgs_metasearch_response(
        query="bitcoin macro",
        response=[
            {
                "href": "https://www.reuters.com/markets/currencies/",
                "title": "Bitcoin and macro markets",
                "snippet": "Bitcoin moved as global rates and the dollar changed.",
                "date": "2026-07-14T09:30:00+00:00",
                "source": "Reuters",
            }
        ],
        fetched_at=datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
    )

    assert len(evidence) == 1
    assert str(evidence[0].final_url) == ("https://www.reuters.com/markets/currencies/")
    assert evidence[0].source == "ddgs_metasearch"
    assert evidence[0].parser_version == "ddgs-metasearch-v1"
    assert evidence[0].author == "Reuters"
    assert evidence[0].published_at == datetime(2026, 7, 14, 9, 30, tzinfo=UTC)


def test_ddgs_metasearch_provider_invokes_the_official_tool_with_typed_input() -> None:
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
    evidence = DdgsMetasearchProvider(
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
    assert [item.source for item in evidence] == ["ddgs_metasearch"]


def test_ddgs_metasearch_provider_compacts_long_cjk_queries_for_transport() -> None:
    class RecordingTool:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def invoke(self, input: object, config: object = None) -> object:
            del config
            self.calls.append(input)
            return [
                {
                    "link": "https://www.reuters.com/markets/currencies/",
                    "title": "Bitcoin market evidence",
                    "snippet": "Current market evidence.",
                }
            ]

    tool = RecordingTool()
    original_query = (
        "结合当前宏观事件、真实市场结构与可验证来源，判断 BTC 在未来 4 小时的方向、"
        "主要风险和失效条件\nAsset: BTC\nMarket: cryptocurrency\nAnalysis horizon: 4h"
    )

    evidence = DdgsMetasearchProvider(
        tool=tool,  # type: ignore[arg-type]
        retry_policy=SearchRetryPolicy(max_attempts=1),
    ).search(original_query)

    assert len(tool.calls) == 1
    provider_query = tool.calls[0]["query"]  # type: ignore[index]
    assert len(provider_query) < len(original_query)
    assert "BTC" in provider_query
    assert "macro" in provider_query
    assert evidence[0].query == original_query


@pytest.mark.parametrize("result_kind", ["news", "text"])
def test_ddgs_metasearch_explicitly_uses_the_auto_backend(
    monkeypatch: pytest.MonkeyPatch,
    result_kind: str,
) -> None:
    client_options: list[dict[str, object]] = []
    search_calls: list[tuple[str, str, dict[str, object]]] = []

    class RecordingDdgs:
        def __init__(self, **kwargs: object) -> None:
            client_options.append(kwargs)

        def news(self, query: str, **kwargs: object) -> list[dict[str, object]]:
            search_calls.append(("news", query, kwargs))
            return provider_results()

        def text(self, query: str, **kwargs: object) -> list[dict[str, object]]:
            search_calls.append(("text", query, kwargs))
            return provider_results()

    def provider_results() -> list[dict[str, object]]:
        return [
            {
                "url": "https://www.reuters.com/markets/currencies/",
                "title": "Bitcoin market evidence",
                "body": "Current public market evidence.",
            }
        ]

    monkeypatch.setattr("ddgs.DDGS", RecordingDdgs)

    evidence = DdgsMetasearchProvider(
        result_kind=result_kind,  # type: ignore[arg-type]
        retry_policy=SearchRetryPolicy(max_attempts=1),
    ).search("current bitcoin market")

    assert len(client_options) == 1
    assert client_options[0]["proxy"] is None
    assert 0 < int(client_options[0]["timeout"]) <= 30
    assert search_calls == [
        (
            result_kind,
            "current bitcoin market",
            {"max_results": 8, "backend": "auto"},
        )
    ]
    assert [item.source for item in evidence] == ["ddgs_metasearch"]


def test_ddgs_metasearch_errors_preserve_honest_provider_provenance() -> None:
    with pytest.raises(ResearchUnavailable) as raised:
        parse_ddgs_metasearch_response(
            query="bitcoin macro",
            response={"not": "a DDGS result list"},
            fetched_at=datetime.now(UTC),
        )

    assert raised.value.provider == "ddgs_metasearch"
    assert "DDGS metasearch" in str(raised.value)


def test_ddgs_metasearch_tool_failures_preserve_honest_provider_provenance() -> None:
    class FailingTool:
        def invoke(self, input: object, config: object = None) -> object:
            del input, config
            raise TimeoutError("metasearch timed out")

    with pytest.raises(ResearchUnavailable) as raised:
        DdgsMetasearchProvider(
            tool=FailingTool(),  # type: ignore[arg-type]
            retry_policy=SearchRetryPolicy(max_attempts=1),
        ).search("current bitcoin market")

    assert raised.value.provider == "ddgs_metasearch"
    assert raised.value.error_type == "TimeoutError"
    assert "DDGS metasearch" in str(raised.value)


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
    assert {record.correlation_id for record in records} == {"corr-tavily-async"}


@pytest.mark.asyncio
async def test_async_tavily_retries_aiohttp_connector_failures() -> None:
    class ClientConnectorError(Exception):
        pass

    class AsyncConnectorTool:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, input: object, config: object = None) -> object:
            del input, config
            self.calls += 1
            if self.calls < 3:
                raise ClientConnectorError("transient Tavily connection failure")
            return {
                "results": [
                    {
                        "url": "https://www.imf.org/en/Topics/fintech",
                        "title": "Fintech",
                        "content": "Public provider evidence.",
                    }
                ]
            }

    tool = AsyncConnectorTool()
    records = []
    evidence = await TavilySearchProvider(
        tool=tool,  # type: ignore[arg-type]
        retry_policy=SearchRetryPolicy(
            backoff_seconds=(0.0,),
            record_attempt=records.append,
        ),
    ).asearch(
        "bitcoin macro",
        config={"metadata": {"correlation_id": "corr-tavily-connector"}},
    )

    assert tool.calls == 3
    assert [str(item.final_url) for item in evidence] == [
        "https://www.imf.org/en/Topics/fintech"
    ]
    assert [record.error_type for record in records] == [
        "ClientConnectorError",
        "ClientConnectorError",
        None,
    ]
    assert [record.outcome for record in records] == [
        "retryable_failure",
        "retryable_failure",
        "succeeded",
    ]
    assert {record.correlation_id for record in records} == {"corr-tavily-connector"}
