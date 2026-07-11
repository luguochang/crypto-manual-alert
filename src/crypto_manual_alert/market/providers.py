from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import math
from typing import Any, Protocol

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.domain import DataPoint, MarketSnapshot


class MarketDataProvider(Protocol):
    def fetch_snapshot(self, symbol: str) -> MarketSnapshot:
        """Fetch a market snapshot for one instrument."""


class OkxPublicMarketDataProvider:
    """Exchange-native OKX public market data provider.

    Execution facts (mark/index/order_book) come from the market snapshot, not
    from the audit swarm. With provider=okx_public these points carry source
    "okx_public" which maps to source_type=exchange_native, satisfying the
    facts_gate so opening actions can be allowed.

    The optional ``http_get`` callable lets tests inject deterministic OKX
    responses instead of hitting the network, so the gate-unblock path is
    verifiable in CI. When ``http_get`` is None the provider performs real
    HTTP calls via httpx.
    """

    def __init__(
        self,
        config: Config,
        *,
        http_get: Callable[[str, dict[str, str]], Mapping[str, Any]] | None = None,
    ):
        self.config = config
        self.base_url = config.market_data.okx_base_url.rstrip("/")
        self.timeout = config.market_data.request_timeout_seconds
        self.http_get = http_get

    def fetch_snapshot(self, symbol: str) -> MarketSnapshot:
        fetched_at = datetime.now(timezone.utc)
        points: dict[str, DataPoint] = {}
        unavailable: list[str] = []

        for name, path, params, parser in [
            ("ticker", "/api/v5/market/ticker", {"instId": symbol}, self._parse_ticker),
            ("mark", "/api/v5/public/mark-price", {"instType": "SWAP", "instId": symbol}, self._parse_mark),
            (
                "index",
                "/api/v5/market/index-tickers",
                {"instId": _index_instrument_id(symbol)},
                self._parse_index,
            ),
            ("funding_rate", "/api/v5/public/funding-rate", {"instId": symbol}, self._parse_funding),
            (
                "open_interest",
                "/api/v5/public/open-interest",
                {"instType": "SWAP", "instId": symbol},
                self._parse_open_interest,
            ),
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
        if self.http_get is not None:
            payload = self.http_get(path, params)
        else:
            client_kwargs: dict[str, Any] = {
                "base_url": self.base_url,
                "timeout": self.timeout,
                "trust_env": self.config.market_data.http_trust_env,
            }
            if self.config.market_data.http_proxy:
                client_kwargs["proxy"] = self.config.market_data.http_proxy
            with httpx.Client(**client_kwargs) as client:
                response = client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
        if not isinstance(payload, Mapping):
            raise RuntimeError("OKX response payload must be an object")
        if str(payload.get("code")) != "0":
            raise RuntimeError(f"OKX returned code={payload.get('code')} msg={payload.get('msg')}")
        return dict(payload)

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
        return {"mark": DataPoint("mark", _required_finite_float(row.get("markPx"), "markPx"), ts, "okx_public")}

    def _parse_index(self, _: str, data: dict[str, Any]) -> dict[str, DataPoint]:
        row = self._first(data)
        ts = _int_or_none(row.get("ts"))
        return {"index": DataPoint("index", _required_finite_float(row.get("idxPx"), "idxPx"), ts, "okx_public")}

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
        asks = row.get("asks")
        bids = row.get("bids")
        if not _book_side_is_usable(asks) or not _book_side_is_usable(bids):
            raise RuntimeError("OKX order book must contain valid ask and bid levels")
        value = {"asks": asks, "bids": bids}
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


def _required_finite_float(value: Any, field_name: str) -> float:
    parsed = _float_or_none(value)
    if parsed is None or not math.isfinite(parsed):
        raise RuntimeError(f"OKX response field {field_name} must be a finite number")
    return parsed


def _index_instrument_id(symbol: str) -> str:
    normalized = symbol.strip()
    if normalized.upper().endswith("-SWAP"):
        return normalized[:-5]
    return normalized


def _book_side_is_usable(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(level, (list, tuple))
        and len(level) >= 2
        and _is_positive_finite_number(level[0])
        and _is_positive_finite_number(level[1])
        for level in value
    )


def _is_positive_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))
