from datetime import datetime, timezone
import time

import httpx

from jiami_crypto_alert.config import load_config
from jiami_crypto_alert.domain import DataPoint, MarketSnapshot
from jiami_crypto_alert.research import (
    FixtureSearchAdapter,
    OpenAICompatibleLeaderResearchSynthesizer,
    OpenAICompatibleResearchPlanner,
    ResearchQuery,
    ResponsesWebSearchAdapter,
    SearchResult,
    StaticLeaderResearchSynthesizer,
    StaticResearchPlanner,
    execute_research,
    needs_research_fallback,
    synthesize_search_evidence,
)


def timeout_snapshot():
    return MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={},
        unavailable=[
            "ticker: ConnectTimeout",
            "mark: ConnectTimeout",
            "funding_rate: ConnectTimeout",
            "open_interest: ConnectTimeout",
            "order_book: ConnectTimeout",
            "candles: ConnectTimeout",
        ],
    )


def test_needs_research_fallback_when_core_market_data_missing():
    assert needs_research_fallback(timeout_snapshot()) is True


def test_needs_research_fallback_when_core_market_data_stale():
    old_ms = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime.now(timezone.utc),
        points={
            "last": DataPoint("last", 3500.0, old_ms, "okx"),
            "mark": DataPoint("mark", 3500.0, old_ms, "okx"),
            "index": DataPoint("index", 3500.0, old_ms, "okx"),
            "order_book": DataPoint("order_book", {"asks": [], "bids": []}, old_ms, "okx"),
        },
        unavailable=[],
    )

    assert needs_research_fallback(snapshot, max_age_seconds=120) is True


def test_static_research_planner_generates_crypto_queries():
    plan = StaticResearchPlanner().plan(timeout_snapshot())

    names = {query.name for query in plan.queries}

    assert "eth_price_context" in names
    assert "eth_derivatives_context" in names
    assert "macro_context" in names


def test_llm_research_planner_uses_skill_context_and_parses_queries(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        payload = __import__("json").loads(request.content)
        captured["payload"] = payload
        system_prompt = payload["messages"][0]["content"]
        assert "简体中文" in system_prompt
        assert "reason" in system_prompt
        assert "purpose" in system_prompt
        user_content = payload["messages"][1]["content"]
        assert "crypto-macro-decision" in user_content
        assert "ETH-USDT-SWAP" in user_content
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": __import__("json").dumps(
                                {
                                    "reason": "leader planned current ETH research tasks",
                                    "queries": [
                                        {
                                            "name": "eth_liquidation_heatmap",
                                            "query": "ETH liquidation heatmap latest",
                                            "purpose": "check forced positioning risk",
                                            "required": True,
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = _openai_config()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    planner = OpenAICompatibleResearchPlanner(config, client=client)

    plan = planner.plan(timeout_snapshot(), skill_context={"name": "crypto-macro-decision"})

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "gpt-test"
    assert plan.planner == "llm"
    assert plan.queries[0].name == "eth_liquidation_heatmap"
    assert plan.queries[0].required is True


def test_execute_research_with_fixture_adapter_returns_search_results():
    adapter = FixtureSearchAdapter(
        {
            "eth_price_context": [
                {
                    "title": "ETH perpetual price context",
                    "url": "https://example.test/eth",
                    "snippet": "ETH trades near 3500; funding neutral.",
                }
            ]
        }
    )
    plan = StaticResearchPlanner().plan(timeout_snapshot())

    audit = execute_research(plan, adapter)

    assert audit.results["eth_price_context"][0].snippet.startswith("ETH trades")


def test_execute_research_runs_queries_concurrently():
    class SlowAdapter:
        def search(self, query):
            time.sleep(0.2)
            return [SearchResult(title=query.name, url="https://example.test", snippet="ok")]

    plan = StaticResearchPlanner(max_queries=3).plan(timeout_snapshot())
    started = time.perf_counter()

    audit = execute_research(plan, SlowAdapter(), max_workers=3)

    elapsed = time.perf_counter() - started
    assert elapsed < 0.45
    assert not audit.unavailable


def test_static_leader_synthesizer_outputs_four_role_summary():
    adapter = FixtureSearchAdapter(
        {
            "eth_price_context": [
                {"title": "ETH", "url": "https://example.test/eth", "snippet": "ETH price context."}
            ],
            "eth_derivatives_context": [
                {"title": "ETH derivatives", "url": "https://example.test/derivatives", "snippet": "Funding neutral."}
            ],
        }
    )
    plan = StaticResearchPlanner(max_queries=2).plan(timeout_snapshot())
    audit = execute_research(plan, adapter)

    audit = StaticLeaderResearchSynthesizer().synthesize(timeout_snapshot(), audit)

    assert audit.leader_summary
    assert "bull_reviewer" in audit.leader_summary
    assert "bear_reviewer" in audit.leader_summary
    assert "data_quality_reviewer" in audit.leader_summary
    assert "execution_risk_reviewer" in audit.leader_summary


def test_llm_leader_synthesizer_receives_search_results_and_outputs_four_role_review(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        captured["payload"] = payload
        system_prompt = payload["messages"][0]["content"]
        assert "简体中文" in system_prompt
        assert "leader_finalizer" in system_prompt
        assert "reviewer" in system_prompt
        user_content = payload["messages"][1]["content"]
        assert "ETH search context from current web result" in user_content
        assert "bull_reviewer" in user_content
        assert "execution_risk_reviewer" in user_content
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": __import__("json").dumps(
                                {
                                    "leader_finalizer": {
                                        "summary": "ETH evidence is mixed; execution facts remain degraded.",
                                        "conflicts": ["search-derived context cannot replace OKX mark/index"],
                                        "gaps": ["precise CVD"],
                                    },
                                    "bull_reviewer": {
                                        "root_cause_chain": "stable funding -> less crowded longs -> upside trigger needs confirmation",
                                        "confirmation": "OKX mark reclaims trigger",
                                    },
                                    "bear_reviewer": {
                                        "root_cause_chain": "risk-off macro -> BTC weakness -> ETH beta downside",
                                        "confirmation": "BTC loses structure",
                                    },
                                    "data_quality_reviewer": {
                                        "quality": "search-derived, capped confidence",
                                        "confidence_cap_hint": 0.58,
                                    },
                                    "execution_risk_reviewer": {
                                        "risk": "manual only; no order placement",
                                        "required_before_trade": ["fresh mark", "fresh order book"],
                                    },
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = _openai_config()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    plan = StaticResearchPlanner(max_queries=1).plan(timeout_snapshot())
    audit = execute_research(
        plan,
        FixtureSearchAdapter(
            {
                "eth_price_context": [
                    {
                        "title": "ETH",
                        "url": "https://example.test/eth",
                        "snippet": "ETH search context from current web result",
                    }
                ]
            }
        ),
    )

    audit = OpenAICompatibleLeaderResearchSynthesizer(config, client=client).synthesize(timeout_snapshot(), audit)

    assert captured["payload"]["model"] == "gpt-test"
    assert audit.leader_summary["leader_finalizer"]["summary"].startswith("ETH evidence")
    assert audit.leader_summary["data_quality_reviewer"]["confidence_cap_hint"] == 0.58


def test_synthesize_search_evidence_adds_search_derived_points():
    adapter = FixtureSearchAdapter(
        {
            "eth_price_context": [
                {
                    "title": "ETH perpetual price context",
                    "url": "https://example.test/eth",
                    "snippet": "ETH trades near 3500; funding neutral.",
                }
            ]
        }
    )
    plan = StaticResearchPlanner().plan(timeout_snapshot())
    audit = execute_research(plan, adapter)

    enriched = synthesize_search_evidence(timeout_snapshot(), audit)

    assert "web_eth_price_context" in enriched.points
    point = enriched.points["web_eth_price_context"]
    assert isinstance(point, DataPoint)
    assert point.source == "search-derived"
    assert any(item.startswith("confidence_cap:0.58:") for item in enriched.unavailable)


def test_research_config_defaults_disabled():
    config = load_config("config/default.yaml")

    assert config.research.enabled is False
    assert config.research.search_provider == "disabled"


def test_responses_web_search_adapter_posts_web_search_tool(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        payload = __import__("json").loads(request.content)
        captured["payload"] = payload
        return httpx.Response(
            200,
            json={
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

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config("config/default.yaml")
    research = config.research.__class__(**{**config.research.__dict__, "search_provider": "responses_web_search"})
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
        research=research,
        security=config.security,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ResponsesWebSearchAdapter(config, client=client)

    results = adapter.search(
        ResearchQuery(
            name="eth_price_context",
            query="ETH latest market headline",
            purpose="test",
        )
    )

    assert captured["url"] == "https://example.test/v1/responses"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["tools"] == [{"type": "web_search"}]
    assert captured["payload"]["model"] == "gpt-test"
    assert "简体中文" in captured["payload"]["input"]
    assert results[0].source == "responses-web-search"
    assert "web_search_requests=1" in results[0].snippet


def test_research_llm_components_use_research_request_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = _openai_config()
    research = config.research.__class__(**{**config.research.__dict__, "request_timeout_seconds": 123})
    decision = config.decision.__class__(**{**config.decision.__dict__, "timeout_seconds": 999})
    config = config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=research,
        security=config.security,
    )

    assert ResponsesWebSearchAdapter(config).timeout == 123
    assert OpenAICompatibleResearchPlanner(config).timeout == 123
    assert OpenAICompatibleLeaderResearchSynthesizer(config).timeout == 123


def test_responses_web_search_adapter_rejects_zero_web_search_usage(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tool_usage": {"web_search": {"num_requests": 0}},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "No search used."}]}],
            },
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_config("config/default.yaml")
    research = config.research.__class__(**{**config.research.__dict__, "search_provider": "responses_web_search"})
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
        research=research,
        security=config.security,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ResponsesWebSearchAdapter(config, client=client)

    try:
        adapter.search(ResearchQuery(name="macro_context", query="crypto headline", purpose="test"))
    except RuntimeError as exc:
        assert "web_search" in str(exc)
    else:
        raise AssertionError("responses web search adapter should require actual web_search usage")


def _openai_config():
    config = load_config("config/default.yaml")
    decision = config.decision.__class__(
        **{
            **config.decision.__dict__,
            "openai_base_url": "https://example.test",
            "openai_model": "gpt-test",
        }
    )
    return config.__class__(
        app=config.app,
        trading=config.trading,
        market_data=config.market_data,
        decision=decision,
        notification=config.notification,
        scheduler=config.scheduler,
        research=config.research,
        security=config.security,
    )
