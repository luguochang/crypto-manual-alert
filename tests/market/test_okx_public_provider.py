from __future__ import annotations

from dataclasses import replace

from crypto_manual_alert.config import load_config
from crypto_manual_alert.market.providers import OkxPublicMarketDataProvider


def test_okx_provider_fetches_index_from_index_tickers_with_swap_underlying_symbol():
    config = load_config("config/default.yaml")
    calls: list[tuple[str, dict[str, str]]] = []

    def http_get(path: str, params: dict[str, str]):
        calls.append((path, params))
        if path == "/api/v5/market/ticker":
            return {
                "code": "0",
                "data": [{"last": "3500", "bidPx": "3499", "askPx": "3501", "ts": "1783751852091"}],
            }
        if path == "/api/v5/public/mark-price":
            return {"code": "0", "data": [{"markPx": "3499.5", "ts": "1783751852091"}]}
        if path == "/api/v5/market/index-tickers":
            return {"code": "0", "data": [{"instId": "ETH-USDT", "idxPx": "3498.5", "ts": "1783751852091"}]}
        if path == "/api/v5/public/funding-rate":
            return {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": "1783751852091"}]}
        if path == "/api/v5/public/open-interest":
            return {"code": "0", "data": [{"oi": "100000", "ts": "1783751852091"}]}
        if path == "/api/v5/market/books":
            return {
                "code": "0",
                "data": [{"asks": [["3501", "10"]], "bids": [["3499", "10"]], "ts": "1783751852091"}],
            }
        if path == "/api/v5/market/candles":
            return {"code": "0", "data": [["1783751852091", "3490", "3510", "3480", "3500", "100"]]}
        raise AssertionError(f"unexpected OKX path: {path}")

    provider = OkxPublicMarketDataProvider(config, http_get=http_get)

    snapshot = provider.fetch_snapshot("ETH-USDT-SWAP")

    assert snapshot.points["mark"].value == 3499.5
    assert snapshot.points["index"].value == 3498.5
    assert snapshot.unavailable == []
    assert (
        "/api/v5/market/index-tickers",
        {"instId": "ETH-USDT"},
    ) in calls
    mark_call = next(params for path, params in calls if path == "/api/v5/public/mark-price")
    assert mark_call == {"instType": "SWAP", "instId": "ETH-USDT-SWAP"}


def test_okx_provider_rejects_index_payload_without_numeric_index_price():
    config = load_config("config/default.yaml")
    config = replace(config, market_data=replace(config.market_data, candle_limit=1))

    def http_get(path: str, params: dict[str, str]):
        if path == "/api/v5/market/index-tickers":
            return {"code": "0", "data": [{"instId": params["instId"], "idxPx": None, "ts": "1783751852091"}]}
        if path == "/api/v5/market/ticker":
            return {"code": "0", "data": [{"last": "3500", "bidPx": "3499", "askPx": "3501", "ts": "1783751852091"}]}
        if path == "/api/v5/public/mark-price":
            return {"code": "0", "data": [{"markPx": "3499.5", "ts": "1783751852091"}]}
        if path == "/api/v5/public/funding-rate":
            return {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": "1783751852091"}]}
        if path == "/api/v5/public/open-interest":
            return {"code": "0", "data": [{"oi": "100000", "ts": "1783751852091"}]}
        if path == "/api/v5/market/books":
            return {"code": "0", "data": [{"asks": [["3501", "10"]], "bids": [["3499", "10"]], "ts": "1783751852091"}]}
        if path == "/api/v5/market/candles":
            return {"code": "0", "data": [["1783751852091", "3490", "3510", "3480", "3500", "100"]]}
        raise AssertionError(f"unexpected OKX path: {path}")

    snapshot = OkxPublicMarketDataProvider(config, http_get=http_get).fetch_snapshot("ETH-USDT-SWAP")

    assert "index" not in snapshot.points
    assert "index: RuntimeError" in snapshot.unavailable


def test_okx_provider_rejects_malformed_order_book_levels():
    config = load_config("config/default.yaml")

    def http_get(path: str, params: dict[str, str]):
        if path == "/api/v5/market/ticker":
            return {"code": "0", "data": [{"last": "3500", "bidPx": "3499", "askPx": "3501", "ts": "1783751852091"}]}
        if path == "/api/v5/public/mark-price":
            return {"code": "0", "data": [{"markPx": "3499.5", "ts": "1783751852091"}]}
        if path == "/api/v5/market/index-tickers":
            return {"code": "0", "data": [{"instId": params["instId"], "idxPx": "3498.5", "ts": "1783751852091"}]}
        if path == "/api/v5/public/funding-rate":
            return {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": "1783751852091"}]}
        if path == "/api/v5/public/open-interest":
            return {"code": "0", "data": [{"oi": "100000", "ts": "1783751852091"}]}
        if path == "/api/v5/market/books":
            return {"code": "0", "data": [{"asks": [[]], "bids": [["3499", "10"]], "ts": "1783751852091"}]}
        if path == "/api/v5/market/candles":
            return {"code": "0", "data": [["1783751852091", "3490", "3510", "3480", "3500", "100"]]}
        raise AssertionError(f"unexpected OKX path: {path}")

    snapshot = OkxPublicMarketDataProvider(config, http_get=http_get).fetch_snapshot("ETH-USDT-SWAP")

    assert "order_book" not in snapshot.points
    assert "order_book: RuntimeError" in snapshot.unavailable
