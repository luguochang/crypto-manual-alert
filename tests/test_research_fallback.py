from datetime import datetime, timezone
import threading
import time

import httpx

from crypto_manual_alert.config import load_config
from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.journal import Journal
from crypto_manual_alert.observability import ObservabilityRecorder, record_llm_interaction, use_observability
from crypto_manual_alert.research import (
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
    lock = threading.Lock()
    active = 0
    max_active = 0

    class SlowAdapter:
        def search(self, query):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.3)
            try:
                return [SearchResult(title=query.name, url="https://example.test", snippet="ok")]
            finally:
                with lock:
                    active -= 1

    plan = StaticResearchPlanner(max_queries=3).plan(timeout_snapshot())

    audit = execute_research(plan, SlowAdapter(), max_workers=3)

    assert max_active > 1
    assert not audit.unavailable


def test_execute_research_records_query_level_spans_without_serializing_work(tmp_path):
    lock = threading.Lock()
    active = 0
    max_active = 0

    class SlowAdapter:
        def search(self, query):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.3)
            try:
                return [SearchResult(title=query.name, url="https://example.test", snippet="ok")]
            finally:
                with lock:
                    active -= 1

    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    plan = StaticResearchPlanner(max_queries=3).plan(timeout_snapshot())

    audit = execute_research(plan, SlowAdapter(), max_workers=3, recorder=recorder, trace_id=trace_id)

    with journal.connect() as conn:
        rows = conn.execute(
            """
            SELECT span_name, duration_ms, status, metadata_json, output_summary_json
            FROM trace_spans
            WHERE trace_id = ?
            ORDER BY started_at ASC
            """,
            (trace_id,),
        ).fetchall()

    assert max_active > 1
    assert not audit.unavailable
    assert [row["span_name"] for row in rows] == ["research.search.query"] * 3
    assert {__import__("json").loads(row["metadata_json"])["query_name"] for row in rows} == {
        query.name for query in plan.queries
    }
    assert all(__import__("json").loads(row["output_summary_json"])["result_count"] == 1 for row in rows)


def test_execute_research_links_threaded_llm_calls_to_query_span(tmp_path):
    class RecordingAdapter:
        def search(self, query):
            record_llm_interaction(
                component="research.web_search",
                provider="test",
                model="fixture",
                endpoint="/v1/responses",
                request_payload={"input": query.query},
                response_payload={
                    "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                    "output": [{"content": [{"type": "output_text", "text": "ok"}]}],
                },
                status="ok",
                duration_ms=25,
                prompt_tokens=5,
                completion_tokens=7,
                total_tokens=12,
            )
            return [SearchResult(title=query.name, url="https://example.test", snippet="ok")]

    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    plan = StaticResearchPlanner(max_queries=1).plan(timeout_snapshot())

    execute_research(plan, RecordingAdapter(), max_workers=1, recorder=recorder, trace_id=trace_id)

    with journal.connect() as conn:
        span = conn.execute("SELECT span_id FROM trace_spans WHERE trace_id = ?", (trace_id,)).fetchone()
        llm = conn.execute(
            "SELECT span_id, component, prompt_tokens, completion_tokens, total_tokens FROM llm_interactions WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()

    assert span is not None
    assert llm["component"] == "research.web_search"
    assert llm["span_id"] == span["span_id"]
    assert llm["prompt_tokens"] == 5
    assert llm["completion_tokens"] == 7
    assert llm["total_tokens"] == 12


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


def test_responses_web_search_adapter_posts_web_search_tool(monkeypatch, tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        payload = __import__("json").loads(request.content)
        captured["payload"] = payload
        return httpx.Response(
            200,
            json={
                "usage": {"input_tokens": 13, "output_tokens": 17, "total_tokens": 30},
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
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")

    with use_observability(recorder, trace_id):
        results = adapter.search(
            ResearchQuery(
                name="eth_price_context",
                query="ETH latest market headline",
                purpose="test",
            )
        )
    with journal.connect() as conn:
        row = conn.execute(
            "SELECT prompt_tokens, completion_tokens, total_tokens, duration_ms FROM llm_interactions WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()

    assert captured["url"] == "https://example.test/v1/responses"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["tools"] == [{"type": "web_search"}]
    assert captured["payload"]["model"] == "gpt-test"
    assert "简体中文" in captured["payload"]["input"]
    assert results[0].source == "responses-web-search"
    assert "web_search_requests=1" in results[0].snippet
    assert row["prompt_tokens"] == 13
    assert row["completion_tokens"] == 17
    assert row["total_tokens"] == 30
    assert row["duration_ms"] >= 0


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
