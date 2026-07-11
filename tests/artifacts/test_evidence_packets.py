from __future__ import annotations

from datetime import datetime, timezone

from crypto_manual_alert.domain import DataPoint, MarketSnapshot
from crypto_manual_alert.artifacts.evidence import check_execution_facts, from_market_snapshot, from_research_audit
from crypto_manual_alert.research_pipeline import ResearchAudit, ResearchPlan, ResearchQuery, SearchResult


def _fresh_event_status(timestamp_ms: int, observed_at: datetime) -> DataPoint:
    return DataPoint(
        "active_event_status",
        {"status": "active_market_reaction", "refreshed_at": observed_at.isoformat()},
        timestamp_ms,
        "event_pool_refreshed",
    )


def _non_empty_book() -> dict[str, list[list[str]]]:
    return {"asks": [["3501", "10"]], "bids": [["3499", "10"]]}


def test_market_snapshot_maps_okx_points_to_exchange_native_execution_evidence():
    observed_at = datetime(2026, 6, 30, 1, 2, 3, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3499.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint(
                "order_book",
                {"asks": [["3501", "10"]], "bids": [["3499", "10"]]},
                timestamp_ms,
                "OKX",
            ),
        },
    )

    packets = from_market_snapshot(snapshot)

    by_type = {packet.data_type: packet for packet in packets}
    assert by_type["mark"].source_type == "exchange_native"
    assert by_type["mark"].source_name == "okx_public"
    assert by_type["mark"].can_satisfy_execution_fact is True
    assert by_type["mark"].freshness_status == "fresh"
    assert by_type["mark"].observed_at == observed_at
    assert by_type["mark"].retrieved_at == snapshot.fetched_at
    assert by_type["order_book"].source_type == "exchange_native"
    assert by_type["order_book"].can_satisfy_execution_fact is True


def test_exchange_native_execution_points_require_usable_non_empty_values():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", None, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", {"asks": [], "bids": []}, timestamp_ms, "okx_public"),
        },
    )

    packets = from_market_snapshot(snapshot)
    result = check_execution_facts(packets)
    by_type = {packet.data_type: packet for packet in packets}

    assert by_type["mark"].can_satisfy_execution_fact is True
    assert by_type["index"].can_satisfy_execution_fact is False
    assert by_type["order_book"].can_satisfy_execution_fact is False
    assert result.passed is False
    assert result.missing_execution_facts == ["index", "order_book"]
    assert "index: unusable value" in result.reasons
    assert "order_book: unusable value" in result.reasons


def test_exchange_native_order_book_rejects_malformed_levels():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", {"asks": [[]], "bids": [["3499", "10"]]}, timestamp_ms, "okx_public"),
            "active_event_status": _fresh_event_status(timestamp_ms, fetched_at),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is False
    assert result.missing_execution_facts == ["order_book"]
    assert "order_book: unusable value" in result.reasons


def test_empty_event_value_cannot_satisfy_event_fact_gate():
    fetched_at = datetime(2026, 7, 2, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "active_event_status": DataPoint("active_event_status", None, timestamp_ms, "event_pool"),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is False
    assert result.missing_execution_facts == []
    assert result.missing_event_facts == ["active_event_status"]


def test_exchange_native_auxiliary_points_are_not_core_execution_facts():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "binance_public"),
        },
    )

    packets = from_market_snapshot(snapshot)

    assert {packet.source_type for packet in packets} == {"exchange_native"}
    assert all(packet.freshness_status == "fresh" for packet in packets)
    assert all(packet.can_satisfy_execution_fact is False for packet in packets)


def test_search_derived_market_points_cannot_satisfy_mark_index_or_order_book_execution_facts():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "search-derived"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "web_search"),
            "order_book": DataPoint("order_book", {"asks": [], "bids": []}, timestamp_ms, "web"),
        },
    )

    packets = from_market_snapshot(snapshot)

    assert {packet.source_type for packet in packets} == {"search_derived"}
    assert all(packet.can_satisfy_execution_fact is False for packet in packets)
    assert all(packet.data_type in {"mark", "index", "order_book"} for packet in packets)


def test_core_execution_fact_fallback_matrix_cannot_satisfy_execution_facts():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "coinglass_api"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "html_page"),
            "order_book": DataPoint("order_book", {"asks": [], "bids": []}, timestamp_ms, "web_search"),
        },
    )

    packets = from_market_snapshot(snapshot)
    result = check_execution_facts(packets)

    assert {packet.source_type for packet in packets} == {
        "aggregator_api",
        "web_derived",
        "search_derived",
    }
    assert all(packet.fallback_used is True for packet in packets)
    assert all(packet.can_satisfy_execution_fact is False for packet in packets)
    assert result.passed is False
    assert result.missing_execution_facts == ["index", "mark", "order_book"]
    assert result.blocked_action_classes == ["opening", "trigger", "flip"]
    assert result.fallback_used is True
    assert result.fallback_source_types == ["aggregator_api", "search_derived", "web_derived"]


def test_aggregator_market_points_are_tiered_but_cannot_satisfy_execution_facts():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={"open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "coinglass_api")},
    )

    packet = from_market_snapshot(snapshot)[0]

    assert packet.source_type == "aggregator_api"
    assert packet.source_tier == 2
    assert packet.can_satisfy_execution_fact is False


def test_auxiliary_fallback_sources_are_marked_and_cap_confidence():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "coinglass_api"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "html_page"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "web_search"),
            "active_event_status": _fresh_event_status(timestamp_ms, fetched_at),
        },
    )

    packets = from_market_snapshot(snapshot)
    by_type = {packet.data_type: packet for packet in packets}
    result = check_execution_facts(packets)
    public = result.to_public_dict()

    assert by_type["funding"].source_type == "aggregator_api"
    assert by_type["funding"].source_tier == 2
    assert by_type["funding"].fallback_used is True
    assert by_type["funding"].fallback_reason == "source_fallback:aggregator_api"
    assert by_type["funding"].confidence_cap == 0.58
    assert by_type["open_interest"].source_type == "web_derived"
    assert by_type["open_interest"].source_tier == 3
    assert by_type["open_interest"].fallback_used is True
    assert by_type["liquidation"].source_type == "search_derived"
    assert by_type["liquidation"].source_tier == 4
    assert by_type["liquidation"].fallback_used is True
    assert result.passed is True
    assert result.severity == "soft_downgrade"
    assert public["missing_auxiliary_facts"] == []
    assert public["fallback_used"] is True
    assert public["fallback_source_types"] == ["aggregator_api", "search_derived", "web_derived"]
    assert public["confidence_cap"] == 0.58
    assert public["confidence_cap_reasons"] == ["facts_gate:fallback_source_used"]


def test_stale_auxiliary_fallback_source_is_missing_and_cap_confidence():
    stale_observed_at = datetime(2026, 6, 30, 1, 2, 3, tzinfo=timezone.utc)
    fresh_observed_at = datetime(2026, 6, 30, 1, 7, 3, tzinfo=timezone.utc)
    stale_timestamp_ms = int(stale_observed_at.timestamp() * 1000)
    fresh_timestamp_ms = int(fresh_observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 6, 30, 1, 7, 4, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, fresh_timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, fresh_timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), fresh_timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, fresh_timestamp_ms, "coinglass_api"),
            "open_interest": DataPoint("open_interest", 100000.0, stale_timestamp_ms, "coinglass_api"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, stale_timestamp_ms, "web_search"),
            "active_event_status": _fresh_event_status(fresh_timestamp_ms, fresh_observed_at),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is True
    assert result.severity == "soft_downgrade"
    assert result.missing_auxiliary_facts == ["liquidation", "open_interest"]
    assert result.fallback_used is True
    assert result.confidence_cap == 0.58
    assert set(result.confidence_cap_reasons) == {
        "facts_gate:derivatives_facts_missing",
        "facts_gate:fallback_source_used",
    }


def test_official_and_web_derived_sources_are_classified_with_priority_tiers():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="BTC-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "macro_event": DataPoint("macro_event", "FOMC minutes", timestamp_ms, "fomc_official"),
            "macro_context": DataPoint("macro_context", "news page", timestamp_ms, "html_page"),
        },
    )

    by_name = {packet.name: packet for packet in from_market_snapshot(snapshot)}

    assert by_name["macro_event"].source_type == "official"
    assert by_name["macro_event"].source_tier == 1
    assert by_name["macro_context"].source_type == "web_derived"
    assert by_name["macro_context"].source_tier == 3


def test_research_audit_maps_search_results_to_search_derived_non_execution_evidence():
    plan = ResearchPlan(
        queries=[
            ResearchQuery(
                name="eth_price_context",
                query="ETH mark price latest",
                purpose="fallback context",
            )
        ],
        reason="core market data unavailable",
    )
    result = SearchResult(
        title="ETH context",
        url="https://example.test/eth",
        snippet="ETH trades near 3500 in public search context.",
        source="responses-web-search",
    )
    audit = ResearchAudit(plan=plan, results={"eth_price_context": [result]}, unavailable=["macro_context: timeout"])

    packets = from_research_audit("ETH-USDT-SWAP", audit)

    assert len(packets) == 1
    packet = packets[0]
    assert packet.name == "eth_price_context"
    assert packet.symbol == "ETH-USDT-SWAP"
    assert packet.data_type == "news"
    assert packet.source_type == "search_derived"
    assert packet.source_name == "responses-web-search"
    assert packet.source_url == "https://example.test/eth"
    assert packet.can_satisfy_execution_fact is False
    assert packet.confidence_cap == 0.58
    assert packet.claims == ["ETH context", "ETH trades near 3500 in public search context."]
    assert packet.trace_ref == "research:eth_price_context:0"


def test_facts_gate_hard_fails_when_execution_facts_are_only_search_derived():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "search-derived"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "web_search"),
            "order_book": DataPoint("order_book", {"asks": [], "bids": []}, timestamp_ms, "web"),
            "active_event_status": _fresh_event_status(timestamp_ms, fetched_at),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is False
    assert result.severity == "hard_fail"
    assert result.missing_execution_facts == ["index", "mark", "order_book"]
    assert result.blocked_action_classes == ["opening", "trigger", "flip"]
    assert all("search_derived" in reason for reason in result.reasons)
    assert result.to_public_dict()["fallback_used"] is True
    assert "facts_gate:fallback_source_used" in result.to_public_dict()["confidence_cap_reasons"]


def test_stale_exchange_native_points_cannot_satisfy_execution_facts():
    observed_at = datetime(2026, 6, 30, 1, 2, 3, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 6, 30, 1, 2, 20, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public", status="stale"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "active_event_status": _fresh_event_status(timestamp_ms, observed_at),
        },
    )

    packets = from_market_snapshot(snapshot)
    result = check_execution_facts(packets)

    mark_packet = next(packet for packet in packets if packet.data_type == "mark")
    assert mark_packet.freshness_status == "stale"
    assert mark_packet.can_satisfy_execution_fact is False
    assert result.passed is False
    assert result.severity == "hard_fail"
    assert result.missing_execution_facts == ["mark"]
    assert result.blocked_action_classes == ["opening", "trigger", "flip"]
    assert result.reasons == ["mark: stale"]


def test_fresh_active_event_status_satisfies_event_fact_gate():
    observed_at = datetime(2026, 7, 2, 1, 2, 3, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "coinglass_api"),
            "active_event_status": DataPoint(
                "active_event_status",
                {"status": "active_market_reaction", "refreshed_at": "2026-07-02T01:02:03+00:00"},
                timestamp_ms,
                "event_pool_refreshed",
            ),
        },
    )

    packets = from_market_snapshot(snapshot)
    by_type = {packet.data_type: packet for packet in packets}
    result = check_execution_facts(packets)

    assert by_type["active_event_status"].source_type == "event_pool"
    assert by_type["active_event_status"].freshness_status == "fresh"
    assert by_type["active_event_status"].can_satisfy_execution_fact is False
    assert result.passed is True
    assert result.severity == "soft_downgrade"
    assert result.missing_event_facts == []


def test_fresh_official_active_event_status_satisfies_event_fact_gate():
    observed_at = datetime(2026, 7, 2, 1, 2, 3, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "okx_public"),
            "active_event_status": DataPoint(
                "active_event_status",
                {"status": "released", "refreshed_at": "2026-07-02T01:02:03+00:00"},
                timestamp_ms,
                "bls_official",
            ),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is True
    assert result.missing_event_facts == []


def test_complete_macro_event_surprise_fields_do_not_cap_confidence():
    observed_at = datetime(2026, 7, 2, 12, 31, 0, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="BTC-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 12, 31, 30, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 60000.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 59980.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "okx_public"),
            "active_event_status": _fresh_event_status(timestamp_ms, observed_at),
            "macro_event": DataPoint(
                "macro_event",
                {
                    "event_name": "US June NFP",
                    "consensus": "180k",
                    "actual": "145k",
                    "surprise": "cooler_than_expected",
                    "market_reaction": {"dxy": "down", "yields": "down", "btc": "up"},
                    "released_at": "2026-07-02T12:30:00+00:00",
                },
                timestamp_ms,
                "bls_official",
            ),
        },
    )

    by_type = {packet.data_type: packet for packet in from_market_snapshot(snapshot)}
    result = check_execution_facts(list(by_type.values()))

    assert by_type["macro_event"].source_type == "official"
    assert by_type["macro_event"].source_tier == 1
    assert result.passed is True
    assert result.severity == "ok"
    assert result.missing_macro_facts == []
    assert result.confidence_cap is None


def test_macro_event_with_only_name_is_incomplete_and_caps_confidence():
    observed_at = datetime(2026, 7, 2, 12, 31, 0, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="BTC-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 12, 31, 30, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 60000.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 59980.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "okx_public"),
            "active_event_status": _fresh_event_status(timestamp_ms, observed_at),
            "macro_event": DataPoint("macro_event", {"event_name": "US June NFP"}, timestamp_ms, "bls_official"),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))
    public = result.to_public_dict()

    assert result.passed is True
    assert result.severity == "soft_downgrade"
    assert result.missing_macro_facts == [
        "macro_event.actual",
        "macro_event.consensus",
        "macro_event.market_reaction",
        "macro_event.released_at",
        "macro_event.surprise",
    ]
    assert public["confidence_cap"] == 0.58
    assert public["confidence_cap_reasons"] == ["facts_gate:macro_surprise_incomplete"]


def test_macro_event_missing_market_reaction_is_incomplete_even_from_official_source():
    observed_at = datetime(2026, 7, 2, 12, 31, 0, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="BTC-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 12, 31, 30, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 60000.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 59980.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "okx_public"),
            "active_event_status": _fresh_event_status(timestamp_ms, observed_at),
            "macro_event": DataPoint(
                "macro_event",
                {
                    "event_name": "US June NFP",
                    "consensus": "180k",
                    "actual": "145k",
                    "surprise": "cooler_than_expected",
                    "released_at": "2026-07-02T12:30:00+00:00",
                },
                timestamp_ms,
                "bls_official",
            ),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is True
    assert result.severity == "soft_downgrade"
    assert result.missing_macro_facts == ["macro_event.market_reaction"]
    assert result.confidence_cap == 0.58
    assert result.confidence_cap_reasons == ["facts_gate:macro_surprise_incomplete"]


def test_any_incomplete_macro_event_keeps_macro_surprise_downgrade():
    observed_at = datetime(2026, 7, 2, 12, 31, 0, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    complete_macro = {
        "event_name": "US June NFP",
        "consensus": "180k",
        "actual": "145k",
        "surprise": "cooler_than_expected",
        "market_reaction": {"dxy": "down", "yields": "down", "btc": "up"},
        "released_at": "2026-07-02T12:30:00+00:00",
    }
    snapshot = MarketSnapshot(
        symbol="BTC-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 12, 31, 30, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 60000.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 59980.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "okx_public"),
            "active_event_status": _fresh_event_status(timestamp_ms, observed_at),
            "macro_event_complete": DataPoint("macro_event", complete_macro, timestamp_ms, "bls_official"),
            "macro_event_incomplete": DataPoint(
                "macro_event",
                {**complete_macro, "market_reaction": {}},
                timestamp_ms,
                "bls_official",
            ),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is True
    assert result.severity == "soft_downgrade"
    assert result.missing_macro_facts == ["macro_event.market_reaction"]
    assert result.confidence_cap_reasons == ["facts_gate:macro_surprise_incomplete"]


def test_missing_active_event_status_hard_blocks_directional_actions():
    observed_at = datetime(2026, 7, 2, 1, 2, 3, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, timestamp_ms, "okx_public"),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is False
    assert result.severity == "hard_fail"
    assert result.missing_event_facts == ["active_event_status"]
    assert result.blocked_action_classes == ["opening", "trigger", "flip"]
    assert "active_event_status: missing" in result.reasons
    assert result.confidence_cap == 0.55
    assert result.confidence_cap_reasons == ["facts_gate:event_status_stale"]


def test_stale_event_pool_status_hard_blocks_directional_actions():
    event_observed_at = datetime(2026, 6, 19, 1, 2, 3, tzinfo=timezone.utc)
    market_observed_at = datetime(2026, 7, 2, 1, 2, 3, tzinfo=timezone.utc)
    event_timestamp_ms = int(event_observed_at.timestamp() * 1000)
    market_timestamp_ms = int(market_observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, market_timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, market_timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), market_timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, market_timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, market_timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, market_timestamp_ms, "okx_public"),
            "active_event_status": DataPoint(
                "active_event_status",
                {"status": "active_market_reaction", "refreshed_at": "2026-06-19T01:02:03+00:00"},
                event_timestamp_ms,
                "event_pool",
            ),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))
    public = result.to_public_dict()

    assert result.passed is False
    assert result.severity == "hard_fail"
    assert result.missing_execution_facts == []
    assert result.missing_event_facts == ["active_event_status"]
    assert result.blocked_action_classes == ["opening", "trigger", "flip"]
    assert "active_event_status: stale" in result.reasons
    assert public["confidence_cap"] == 0.55
    assert public["confidence_cap_reasons"] == ["facts_gate:event_status_stale"]


def test_event_pool_status_uses_payload_refreshed_at_for_freshness():
    market_observed_at = datetime(2026, 7, 2, 1, 2, 3, tzinfo=timezone.utc)
    market_timestamp_ms = int(market_observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, market_timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, market_timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), market_timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, market_timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, market_timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, market_timestamp_ms, "okx_public"),
            "active_event_status": DataPoint(
                "active_event_status",
                {"status": "active_market_reaction", "refreshed_at": "2026-06-19T01:02:03+00:00"},
                market_timestamp_ms,
                "event_pool_refreshed",
            ),
        },
    )

    packets = from_market_snapshot(snapshot)
    event_packet = next(packet for packet in packets if packet.data_type == "active_event_status")
    result = check_execution_facts(packets)

    assert event_packet.freshness_status == "stale"
    assert result.passed is False
    assert result.missing_event_facts == ["active_event_status"]


def test_event_status_without_timestamp_or_refreshed_at_hard_blocks_directional_actions():
    market_observed_at = datetime(2026, 7, 2, 1, 2, 3, tzinfo=timezone.utc)
    market_timestamp_ms = int(market_observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 7, 2, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, market_timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, market_timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), market_timestamp_ms, "okx_public"),
            "funding": DataPoint("funding_rate", 0.0001, market_timestamp_ms, "okx_public"),
            "open_interest": DataPoint("open_interest", 100000.0, market_timestamp_ms, "okx_public"),
            "liquidation": DataPoint("liquidation_heatmap", {"cluster": "below"}, market_timestamp_ms, "okx_public"),
            "active_event_status": DataPoint(
                "active_event_status",
                {"status": "active_market_reaction"},
                None,
                "event_pool_refreshed",
            ),
        },
    )

    packets = from_market_snapshot(snapshot)
    event_packet = next(packet for packet in packets if packet.data_type == "active_event_status")
    result = check_execution_facts(packets)

    assert event_packet.freshness_status == "unknown"
    assert result.passed is False
    assert result.missing_event_facts == ["active_event_status"]


def test_old_exchange_native_points_are_stale_by_data_type_ttl():
    observed_at = datetime(2026, 6, 30, 1, 0, 0, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 6, 30, 1, 10, 1, tzinfo=timezone.utc),
        points={"mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public")},
    )

    packet = from_market_snapshot(snapshot)[0]

    assert packet.freshness_status == "stale"
    assert packet.can_satisfy_execution_fact is False


def test_conflicting_exchange_native_execution_facts_are_hard_failed():
    fetched_at = datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc)
    timestamp_ms = int(fetched_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=fetched_at,
        points={
            "mark_okx": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "mark_binance": DataPoint("mark", 3525.0, timestamp_ms, "binance_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))

    assert result.passed is False
    assert result.severity == "hard_fail"
    assert result.missing_execution_facts == ["mark"]
    assert result.conflicting_execution_facts == ["mark"]
    assert "mark: conflicting exchange_native values" in result.reasons


def test_facts_gate_caps_confidence_when_derivatives_or_liquidation_facts_are_missing():
    observed_at = datetime(2026, 6, 30, 1, 2, 3, tzinfo=timezone.utc)
    timestamp_ms = int(observed_at.timestamp() * 1000)
    snapshot = MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=datetime(2026, 6, 30, 1, 2, 5, tzinfo=timezone.utc),
        points={
            "mark": DataPoint("mark", 3500.0, timestamp_ms, "okx_public"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx_public"),
            "order_book": DataPoint("order_book", _non_empty_book(), timestamp_ms, "okx_public"),
            "active_event_status": _fresh_event_status(timestamp_ms, observed_at),
        },
    )

    result = check_execution_facts(from_market_snapshot(snapshot))
    public = result.to_public_dict()

    assert result.passed is True
    assert result.severity == "soft_downgrade"
    assert public["missing_execution_facts"] == []
    assert public["missing_auxiliary_facts"] == ["funding", "liquidation", "open_interest"]
    assert public["blocked_action_classes"] == []
    assert public["confidence_cap"] == 0.58
    assert public["confidence_cap_reasons"] == ["facts_gate:derivatives_facts_missing"]
