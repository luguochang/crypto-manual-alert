from __future__ import annotations

import json

from crypto_manual_alert.research_pipeline import SearchResult
from crypto_manual_alert.agent_swarm.tool_executor import FixtureShadowToolExecutor


def test_fixture_shadow_tool_executor_returns_search_refs_without_raw_snippets():
    executor = FixtureShadowToolExecutor(
        {
            "ETH ETF flow today": [
                SearchResult(
                    title="ETH ETF flow",
                    url="https://example.test/eth-etf",
                    snippet="RAW SEARCH SNIPPET MUST NOT ENTER CONTRIBUTION",
                    source="fixture-search",
                )
            ]
        }
    )

    result = executor.execute(
        agent_name="RootCauseAgent",
        tool_name="web_search",
        arguments={"query": "ETH ETF flow today"},
    )

    assert result["tool_name"] == "web_search"
    assert result["status"] == "ok"
    assert result["result_count"] == 1
    assert result["source_type"] == "fixture"
    assert result["result_ref"].startswith("shadow_tool:web_search:")
    assert result["result_refs"] == [
        {
            "title": "ETH ETF flow",
            "url": "https://example.test/eth-etf",
            "source": "fixture-search",
            "snippet_ref": "shadow_tool.web_search.RootCauseAgent[0].snippet_redacted",
        }
    ]
    rendered = json.dumps(result, ensure_ascii=False)
    assert "RAW SEARCH SNIPPET" not in rendered


def test_fixture_shadow_tool_executor_returns_auditable_error_for_missing_query():
    executor = FixtureShadowToolExecutor({})

    result = executor.execute(agent_name="RootCauseAgent", tool_name="web_search", arguments={})

    assert result == {
        "tool_name": "web_search",
        "status": "failed",
        "source_type": "fixture",
        "error_type": "ToolArgumentError",
        "error_message": "web_search requires a non-empty query",
    }


def test_fixture_shadow_tool_executor_returns_auditable_error_for_unsupported_tool():
    executor = FixtureShadowToolExecutor({})

    result = executor.execute(agent_name="RootCauseAgent", tool_name="place_order", arguments={})

    assert result == {
        "tool_name": "place_order",
        "status": "failed",
        "source_type": "fixture",
        "error_type": "ToolNotSupported",
        "error_message": "unsupported shadow tool: place_order",
    }
