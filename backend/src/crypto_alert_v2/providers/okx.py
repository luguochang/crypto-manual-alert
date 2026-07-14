import hashlib
import json
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence
from uuid import uuid4

import httpx

from crypto_alert_v2.providers.errors import ProviderUnavailable
from crypto_alert_v2.providers.models import (
    BookLevel,
    Candle,
    MarketSnapshot,
    OrderBook,
    Ticker,
)
from crypto_alert_v2.providers.retry_policy import RetryPolicy

SUPPORTED_SYMBOLS = frozenset(
    {"BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"}
)

_PUBLIC_ENDPOINTS = (
    ("ticker", "/api/v5/market/ticker"),
    ("mark", "/api/v5/public/mark-price"),
    ("index", "/api/v5/market/index-tickers"),
    ("funding", "/api/v5/public/funding-rate"),
    ("open_interest", "/api/v5/public/open-interest"),
    ("book", "/api/v5/market/books"),
    ("candles", "/api/v5/market/candles"),
)


def _failure(
    message: str,
    *,
    endpoint: str,
    correlation_id: str,
    retryable: bool = False,
) -> ProviderUnavailable:
    return ProviderUnavailable(
        message,
        provider="okx",
        endpoint=endpoint,
        retryable=retryable,
        correlation_id=correlation_id,
    )


def _data(
    envelope: Mapping[str, Any],
    *,
    endpoint: str,
    correlation_id: str,
) -> Sequence[Any]:
    code = envelope.get("code")
    if str(code) != "0":
        raise _failure(
            f"OKX {endpoint} returned code={code}",
            endpoint=endpoint,
            correlation_id=correlation_id,
        )
    data = envelope.get("data")
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)) or not data:
        raise _failure(
            f"OKX {endpoint} requires non-empty data",
            endpoint=endpoint,
            correlation_id=correlation_id,
        )
    return data


def _decimal(
    value: Any,
    *,
    endpoint: str,
    field: str,
    correlation_id: str,
    positive: bool,
) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        number = Decimal("NaN")
    if not number.is_finite() or (positive and number <= 0):
        qualifier = "finite positive" if positive else "finite"
        raise _failure(
            f"OKX {endpoint} requires {qualifier} {field}",
            endpoint=endpoint,
            correlation_id=correlation_id,
        )
    return number


def _timestamp(value: Any, *, endpoint: str, correlation_id: str) -> int:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp <= 0:
        raise _failure(
            f"OKX {endpoint} timestamp must be finite positive",
            endpoint=endpoint,
            correlation_id=correlation_id,
        )
    return timestamp


def _record(
    rows: Sequence[Any],
    *,
    endpoint: str,
    correlation_id: str,
) -> Mapping[str, Any]:
    record = rows[0]
    if not isinstance(record, Mapping):
        raise _failure(
            f"invalid OKX {endpoint} response shape",
            endpoint=endpoint,
            correlation_id=correlation_id,
        )
    return record


def _field(
    record: Mapping[str, Any],
    field: str,
    *,
    endpoint: str,
    correlation_id: str,
) -> Any:
    try:
        return record[field]
    except KeyError as exc:
        raise _failure(
            f"invalid OKX {endpoint} response shape: missing {field}",
            endpoint=endpoint,
            correlation_id=correlation_id,
        ) from exc


def _book_levels(
    book: Mapping[str, Any],
    side: str,
    *,
    correlation_id: str,
) -> tuple[BookLevel, ...]:
    rows = _field(book, side, endpoint="book", correlation_id=correlation_id)
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise _failure(
            f"invalid OKX book response shape: {side} must be rows",
            endpoint="book",
            correlation_id=correlation_id,
        )

    levels: list[BookLevel] = []
    for row in rows:
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or len(row) < 2
        ):
            raise _failure(
                f"invalid OKX book response shape: malformed {side} row",
                endpoint="book",
                correlation_id=correlation_id,
            )
        levels.append(
            BookLevel(
                _decimal(
                    row[0],
                    endpoint="book",
                    field=f"{side} price",
                    correlation_id=correlation_id,
                    positive=True,
                ),
                _decimal(
                    row[1],
                    endpoint="book",
                    field=f"{side} size",
                    correlation_id=correlation_id,
                    positive=True,
                ),
            )
        )
    return tuple(levels)


def _candles(
    rows: Sequence[Any],
    *,
    correlation_id: str,
) -> tuple[Candle, ...]:
    candles: list[Candle] = []
    for row in rows:
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or len(row) < 6
        ):
            raise _failure(
                "invalid OKX candles response shape: malformed candle row",
                endpoint="candles",
                correlation_id=correlation_id,
            )
        candles.append(
            Candle(
                exchange_timestamp_ms=_timestamp(
                    row[0], endpoint="candles", correlation_id=correlation_id
                ),
                open=_decimal(
                    row[1],
                    endpoint="candles",
                    field="open",
                    correlation_id=correlation_id,
                    positive=True,
                ),
                high=_decimal(
                    row[2],
                    endpoint="candles",
                    field="high",
                    correlation_id=correlation_id,
                    positive=True,
                ),
                low=_decimal(
                    row[3],
                    endpoint="candles",
                    field="low",
                    correlation_id=correlation_id,
                    positive=True,
                ),
                close=_decimal(
                    row[4],
                    endpoint="candles",
                    field="close",
                    correlation_id=correlation_id,
                    positive=True,
                ),
                volume=_decimal(
                    row[5],
                    endpoint="candles",
                    field="volume",
                    correlation_id=correlation_id,
                    positive=False,
                ),
            )
        )
    return tuple(candles)


def parse_okx_snapshot(
    symbol_or_envelopes: str | Mapping[str, Mapping[str, Any]],
    envelopes: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    correlation_id: str = "unknown",
    client_timestamp_ms: int | None = None,
) -> MarketSnapshot:
    if isinstance(symbol_or_envelopes, str):
        symbol = symbol_or_envelopes
        payloads = envelopes
    else:
        payloads = symbol_or_envelopes
        try:
            symbol = str(payloads["ticker"]["data"][0]["instId"])
        except (KeyError, IndexError, TypeError):
            symbol = ""

    if symbol not in SUPPORTED_SYMBOLS:
        raise _failure(
            f"unsupported OKX SWAP symbol: {symbol}",
            endpoint="snapshot",
            correlation_id=correlation_id,
        )
    if payloads is None:
        raise _failure(
            "OKX snapshot payload is required",
            endpoint="snapshot",
            correlation_id=correlation_id,
        )

    parsed: dict[str, Sequence[Any]] = {}
    for endpoint in (
        "ticker",
        "mark",
        "index",
        "funding",
        "open_interest",
        "book",
        "candles",
    ):
        try:
            envelope = payloads[endpoint]
        except KeyError as exc:
            raise _failure(
                f"OKX snapshot missing {endpoint} response",
                endpoint=endpoint,
                correlation_id=correlation_id,
            ) from exc
        parsed[endpoint] = _data(
            envelope,
            endpoint=endpoint,
            correlation_id=correlation_id,
        )

    ticker = _record(parsed["ticker"], endpoint="ticker", correlation_id=correlation_id)
    mark = _record(parsed["mark"], endpoint="mark", correlation_id=correlation_id)
    index = _record(parsed["index"], endpoint="index", correlation_id=correlation_id)
    funding = _record(parsed["funding"], endpoint="funding", correlation_id=correlation_id)
    open_interest = _record(
        parsed["open_interest"],
        endpoint="open_interest",
        correlation_id=correlation_id,
    )
    book = _record(parsed["book"], endpoint="book", correlation_id=correlation_id)

    ticker_last = _decimal(
        _field(ticker, "last", endpoint="ticker", correlation_id=correlation_id),
        endpoint="ticker",
        field="last",
        correlation_id=correlation_id,
        positive=True,
    )
    mark_price = _decimal(
        _field(mark, "markPx", endpoint="mark", correlation_id=correlation_id),
        endpoint="mark",
        field="markPx",
        correlation_id=correlation_id,
        positive=True,
    )
    index_price = _decimal(
        _field(index, "idxPx", endpoint="index", correlation_id=correlation_id),
        endpoint="index",
        field="idxPx",
        correlation_id=correlation_id,
        positive=True,
    )
    funding_rate = _decimal(
        _field(
            funding,
            "fundingRate",
            endpoint="funding",
            correlation_id=correlation_id,
        ),
        endpoint="funding",
        field="fundingRate",
        correlation_id=correlation_id,
        positive=False,
    )
    open_interest_amount = _decimal(
        _field(
            open_interest,
            "oi",
            endpoint="open_interest",
            correlation_id=correlation_id,
        ),
        endpoint="open_interest",
        field="oi",
        correlation_id=correlation_id,
        positive=True,
    )

    bids = _book_levels(book, "bids", correlation_id=correlation_id)
    asks = _book_levels(book, "asks", correlation_id=correlation_id)
    if not bids or not asks:
        raise _failure(
            "OKX book requires both bids and asks",
            endpoint="book",
            correlation_id=correlation_id,
        )
    candle_values = _candles(parsed["candles"], correlation_id=correlation_id)

    timestamps = (
        (
            "ticker",
            _timestamp(
                _field(ticker, "ts", endpoint="ticker", correlation_id=correlation_id),
                endpoint="ticker",
                correlation_id=correlation_id,
            ),
        ),
        (
            "mark",
            _timestamp(
                _field(mark, "ts", endpoint="mark", correlation_id=correlation_id),
                endpoint="mark",
                correlation_id=correlation_id,
            ),
        ),
        (
            "index",
            _timestamp(
                _field(index, "ts", endpoint="index", correlation_id=correlation_id),
                endpoint="index",
                correlation_id=correlation_id,
            ),
        ),
        (
            "funding",
            _timestamp(
                _field(
                    funding,
                    "fundingTime",
                    endpoint="funding",
                    correlation_id=correlation_id,
                ),
                endpoint="funding",
                correlation_id=correlation_id,
            ),
        ),
        (
            "open_interest",
            _timestamp(
                _field(
                    open_interest,
                    "ts",
                    endpoint="open_interest",
                    correlation_id=correlation_id,
                ),
                endpoint="open_interest",
                correlation_id=correlation_id,
            ),
        ),
        (
            "book",
            _timestamp(
                _field(book, "ts", endpoint="book", correlation_id=correlation_id),
                endpoint="book",
                correlation_id=correlation_id,
            ),
        ),
        ("candles", candle_values[0].exchange_timestamp_ms),
    )

    return MarketSnapshot(
        provider="okx",
        venue="OKX",
        symbol=symbol,
        index_symbol=symbol.removesuffix("-SWAP"),
        operation="market_snapshot",
        source_level="exchange_native",
        client_timestamp_ms=(
            observed_at_ms := client_timestamp_ms or time.time_ns() // 1_000_000
        ),
        clock_skew_ms=observed_at_ms - timestamps[0][1],
        raw_hash=hashlib.sha256(
            json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        normalized_schema_version="okx-market-snapshot/v1",
        freshness_version="exchange-timestamp/v1",
        ticker=Ticker(ticker_last, timestamps[0][1]),
        mark_price=mark_price,
        index_price=index_price,
        funding_rate=funding_rate,
        open_interest=open_interest_amount,
        order_book=OrderBook(
            bids=bids,
            asks=asks,
            exchange_timestamp_ms=dict(timestamps)["book"],
        ),
        candles=candle_values,
        exchange_timestamps_ms=timestamps,
    )


class OkxProvider:
    """Small adapter for the seven OKX public SWAP market-data GETs."""

    def __init__(
        self,
        *,
        base_url: str = "https://www.okx.com",
        proxy: str | None = None,
        transport: httpx.BaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if transport is None:
            transport = httpx.HTTPTransport(retries=0)
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            transport=transport,
            proxy=proxy,
            trust_env=False,
            follow_redirects=False,
            headers={"Accept": "application/json"},
        )
        self._retry_policy = retry_policy or RetryPolicy()

    def __enter__(self) -> "OkxProvider":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_snapshot(
        self,
        symbol: str,
        *,
        correlation_id: str | None = None,
    ) -> MarketSnapshot:
        correlation = correlation_id or uuid4().hex
        if symbol not in SUPPORTED_SYMBOLS:
            raise _failure(
                f"unsupported OKX SWAP symbol: {symbol}",
                endpoint="snapshot",
                correlation_id=correlation,
            )

        def fetch_once(remaining_seconds: float) -> MarketSnapshot:
            deadline = self._retry_policy.monotonic() + remaining_seconds
            envelopes: dict[str, Mapping[str, Any]] = {}
            for endpoint, path in _PUBLIC_ENDPOINTS:
                request_timeout = deadline - self._retry_policy.monotonic()
                if request_timeout <= 0:
                    raise _failure(
                        "OKX snapshot exceeded its total request budget",
                        endpoint=endpoint,
                        correlation_id=correlation,
                        retryable=True,
                    )
                envelopes[endpoint] = self._get_public_json(
                    path,
                    params=self._params(endpoint, symbol),
                    endpoint=endpoint,
                    correlation_id=correlation,
                    timeout=request_timeout,
                )
            return parse_okx_snapshot(
                symbol,
                envelopes,
                correlation_id=correlation,
            )

        return self._retry_policy.execute(fetch_once)

    @staticmethod
    def _params(endpoint: str, symbol: str) -> dict[str, str]:
        if endpoint == "index":
            return {"instId": symbol.removesuffix("-SWAP")}
        params = {"instId": symbol}
        if endpoint in {"mark", "open_interest"}:
            params["instType"] = "SWAP"
        elif endpoint == "book":
            params["sz"] = "20"
        elif endpoint == "candles":
            params.update({"bar": "1H", "limit": "100"})
        return params

    def _get_public_json(
        self,
        path: str,
        *,
        params: Mapping[str, str],
        endpoint: str,
        correlation_id: str,
        timeout: float,
    ) -> Mapping[str, Any]:
        try:
            response = self._client.get(path, params=params, timeout=timeout)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise _failure(
                f"OKX {endpoint} request failed: {type(exc).__name__}",
                endpoint=endpoint,
                correlation_id=correlation_id,
                retryable=True,
            ) from exc

        if response.status_code >= 400:
            raise _failure(
                f"OKX {endpoint} returned HTTP {response.status_code}",
                endpoint=endpoint,
                correlation_id=correlation_id,
                retryable=response.status_code == 429 or response.status_code >= 500,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise _failure(
                f"OKX {endpoint} returned invalid JSON",
                endpoint=endpoint,
                correlation_id=correlation_id,
            ) from exc
        if not isinstance(payload, Mapping):
            raise _failure(
                f"OKX {endpoint} response must be an object",
                endpoint=endpoint,
                correlation_id=correlation_id,
            )
        return payload
