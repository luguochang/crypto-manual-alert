from __future__ import annotations

import json

from crypto_manual_alert.skills.facade import SkillTaskContext
from crypto_manual_alert.skills.liquidity_order_book import LiquidityOrderBookSkill
from crypto_manual_alert.skills.liquidity_order_book.providers import (
    OkxPublicOrderBookProvider,
    OrderBookFactRefs,
    OrderBookRequest,
)


class RecordingOrderBookProvider:
    def __init__(self) -> None:
        self.request: OrderBookRequest | None = None

    def fetch(self, request: OrderBookRequest) -> OrderBookFactRefs:
        self.request = request
        return OrderBookFactRefs(
            mark_ref="exchange:okx:ETH-USDT-SWAP:mark:trace-liquidity",
            index_ref="exchange:okx:ETH-USDT-SWAP:index:trace-liquidity",
            order_book_ref="exchange:okx:ETH-USDT-SWAP:order_book:trace-liquidity",
        )


def test_liquidity_order_book_skill_records_exchange_native_fact_refs():
    provider = RecordingOrderBookProvider()
    context = SkillTaskContext(
        skill_name="liquidity_order_book",
        task_id="skill:liquidity_order_book",
        symbol="ETH-USDT-SWAP",
        trace_id="trace-liquidity",
        query="execution liquidity check",
        input_view={},
        max_depth=1,
        timeout_seconds=10,
    )

    public = LiquidityOrderBookSkill(provider=provider).run(context).to_public_dict()

    assert provider.request == OrderBookRequest(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-liquidity",
        task_id="skill:liquidity_order_book",
    )
    assert public["source_type"] == "exchange_native"
    assert public["can_satisfy_execution_fact"] is True
    assert public["fact_refs"] == {
        "mark": "exchange:okx:ETH-USDT-SWAP:mark:trace-liquidity",
        "index": "exchange:okx:ETH-USDT-SWAP:index:trace-liquidity",
        "order_book": "exchange:okx:ETH-USDT-SWAP:order_book:trace-liquidity",
    }


class FakeOkxHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, params: dict[str, str]) -> dict[str, object]:
        self.calls.append((path, params))
        if path == "/api/v5/public/mark-price":
            return {
                "code": "0",
                "data": [
                    {
                        "instId": "ETH-USDT-SWAP",
                        "markPx": "3500.1",
                        "idxPx": "3499.8",
                        "ts": "1783317600000",
                    }
                ],
            }
        if path == "/api/v5/market/books":
            return {
                "code": "0",
                "data": [
                    {
                        "asks": [["3501.0", "2.5"]],
                        "bids": [["3499.0", "3.0"]],
                        "ts": "1783317600000",
                    }
                ],
            }
        raise AssertionError(f"unexpected path: {path}")


def test_okx_public_order_book_provider_returns_refs_without_raw_order_book_payload():
    http = FakeOkxHttp()
    provider = OkxPublicOrderBookProvider(
        http_get=http.get,
        clock_ms=lambda: 1783317600000,
    )

    refs = provider.fetch(
        OrderBookRequest(
            symbol="ETH-USDT-SWAP",
            trace_id="trace-liquidity",
            task_id="skill:liquidity_order_book",
        )
    )

    assert http.calls == [
        (
            "/api/v5/public/mark-price",
            {"instType": "SWAP", "instId": "ETH-USDT-SWAP"},
        ),
        (
            "/api/v5/market/books",
            {"instId": "ETH-USDT-SWAP", "sz": "20"},
        ),
    ]
    public = refs.to_fact_refs()
    assert set(public) == {"mark", "index", "order_book"}
    assert all(value.startswith("exchange:okx_public:ETH-USDT-SWAP:trace-liquidity:") for value in public.values())
    rendered = json.dumps(public, ensure_ascii=False)
    assert "3501.0" not in rendered
    assert "3499.0" not in rendered
    assert "asks" not in rendered
    assert "bids" not in rendered


class StaleOkxHttp(FakeOkxHttp):
    def get(self, path: str, params: dict[str, str]) -> dict[str, object]:
        payload = super().get(path, params)
        payload["data"][0]["ts"] = "1000"
        return payload


def test_okx_public_order_book_provider_rejects_stale_exchange_native_facts():
    provider = OkxPublicOrderBookProvider(
        http_get=StaleOkxHttp().get,
        clock_ms=lambda: 1783317600000,
        max_age_seconds=60,
    )

    try:
        provider.fetch(
            OrderBookRequest(
                symbol="ETH-USDT-SWAP",
                trace_id="trace-stale-liquidity",
                task_id="skill:liquidity_order_book",
            )
        )
    except RuntimeError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale exchange-native liquidity facts must not produce refs")
