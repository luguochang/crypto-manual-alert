from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from .config import Config
from .domain import DataPoint, MarketSnapshot


class MarketDataProvider(Protocol):
    def fetch_snapshot(self, symbol: str) -> MarketSnapshot:
        """Fetch a market snapshot for one instrument."""


class OkxPublicMarketDataProvider:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.market_data.okx_base_url.rstrip("/")
        self.timeout = config.market_data.request_timeout_seconds

    def fetch_snapshot(self, symbol: str) -> MarketSnapshot:
        fetched_at = datetime.now(timezone.utc)
        points: dict[str, DataPoint] = {}
        unavailable: list[str] = []

        for name, path, params, parser in [
            ("ticker", "/api/v5/market/ticker", {"instId": symbol}, self._parse_ticker),
            ("mark", "/api/v5/public/mark-price", {"instType": "SWAP", "instId": symbol}, self._parse_mark),
            ("funding_rate", "/api/v5/public/funding-rate", {"instId": symbol}, self._parse_funding),
            ("open_interest", "/api/v5/public/open-interest", {"instType": "SWAP", "instId": symbol}, self._parse_open_interest),
            (
                "order_book",
                "/api/v5/market/books",
                {"instId": symbol, "sz": str(self.config.market_data.order_book_depth)},
                self._parse_book,
            ),
            (
                "candles",
                "/api/v5/market/candles",
                {"instId": symbol, "bar": self.config.market_data.candle_bar, "limit": str(self.config.market_data.candle_limit)},
                self._parse_candles,
            ),
        ]:
            try:
                data = self._get(path, params)
                parsed = parser(name, data)
                points.update(parsed)
            except Exception as exc:  # noqa: BLE001 - adapter should degrade per endpoint
                unavailable.append(f"{name}: {type(exc).__name__}")

        return MarketSnapshot(symbol=symbol, fetched_at=fetched_at, points=points, unavailable=unavailable)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            response = client.get(path, params=params)
            response.raise_for_status()
            data = response.json()
        if data.get("code") != "0":
            raise RuntimeError(f"OKX returned code={data.get('code')} msg={data.get('msg')}")
        return data

    def _first(self, data: dict[str, Any]) -> dict[str, Any]:
        rows = data.get("data") or []
        if not rows:
            raise RuntimeError("OKX response data is empty")
        return rows[0]

    def _parse_ticker(self, _: str, data: dict[str, Any]) -> dict[str, DataPoint]:
        row = self._first(data)
        ts = _int_or_none(row.get("ts"))
        return {
            "last": DataPoint("last", _float_or_none(row.get("last")), ts, "okx_public"),
            "bid": DataPoint("bid", _float_or_none(row.get("bidPx")), ts, "okx_public"),
            "ask": DataPoint("ask", _float_or_none(row.get("askPx")), ts, "okx_public"),
        }

    def _parse_mark(self, _: str, data: dict[str, Any]) -> dict[str, DataPoint]:
        row = self._first(data)
        ts = _int_or_none(row.get("ts"))
        return {
            "mark": DataPoint("mark", _float_or_none(row.get("markPx")), ts, "okx_public"),
            "index": DataPoint("index", _float_or_none(row.get("idxPx")), ts, "okx_public"),
        }

    def _parse_funding(self, _: str, data: dict[str, Any]) -> dict[str, DataPoint]:
        row = self._first(data)
        ts = _int_or_none(row.get("fundingTime")) or _int_or_none(row.get("ts"))
        return {"funding_rate": DataPoint("funding_rate", _float_or_none(row.get("fundingRate")), ts, "okx_public")}

    def _parse_open_interest(self, _: str, data: dict[str, Any]) -> dict[str, DataPoint]:
        row = self._first(data)
        ts = _int_or_none(row.get("ts"))
        return {"open_interest": DataPoint("open_interest", _float_or_none(row.get("oi")), ts, "okx_public")}

    def _parse_book(self, _: str, data: dict[str, Any]) -> dict[str, DataPoint]:
        row = self._first(data)
        ts = _int_or_none(row.get("ts"))
        value = {"asks": row.get("asks") or [], "bids": row.get("bids") or []}
        return {"order_book": DataPoint("order_book", value, ts, "okx_public")}

    def _parse_candles(self, _: str, data: dict[str, Any]) -> dict[str, DataPoint]:
        rows = data.get("data") or []
        if not rows:
            raise RuntimeError("OKX candles are empty")
        ts = _int_or_none(rows[0][0])
        return {"candles": DataPoint("candles", rows, ts, "okx_public")}


class FixtureMarketDataProvider:
    def fetch_snapshot(self, symbol: str) -> MarketSnapshot:
        now = datetime.now(timezone.utc)
        ts = int(now.timestamp() * 1000)
        return MarketSnapshot(
            symbol=symbol,
            fetched_at=now,
            points={
                "last": DataPoint("last", 3500.0, ts, "fixture"),
                "mark": DataPoint("mark", 3499.0, ts, "fixture"),
                "index": DataPoint("index", 3498.0, ts, "fixture"),
                "funding_rate": DataPoint("funding_rate", 0.0001, ts, "fixture"),
                "open_interest": DataPoint("open_interest", 100000.0, ts, "fixture"),
                "order_book": DataPoint(
                    "order_book",
                    {"asks": [["3501", "10"]], "bids": [["3499", "10"]]},
                    ts,
                    "fixture",
                ),
                "candles": DataPoint(
                    "candles",
                    [[str(ts), "3490", "3510", "3480", "3500", "100"]],
                    ts,
                    "fixture",
                ),
            },
            unavailable=["precise CVD", "liquidation heatmap"],
        )


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))
