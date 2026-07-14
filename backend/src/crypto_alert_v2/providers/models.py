from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Ticker:
    last: Decimal
    exchange_timestamp_ms: int


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True, slots=True)
class OrderBook:
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    exchange_timestamp_ms: int


@dataclass(frozen=True, slots=True)
class Candle:
    exchange_timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    provider: str
    venue: str
    symbol: str
    index_symbol: str
    operation: str
    source_level: str
    client_timestamp_ms: int
    clock_skew_ms: int
    raw_hash: str
    normalized_schema_version: str
    freshness_version: str
    ticker: Ticker
    mark_price: Decimal
    index_price: Decimal
    funding_rate: Decimal
    open_interest: Decimal
    order_book: OrderBook
    candles: tuple[Candle, ...]
    exchange_timestamps_ms: tuple[tuple[str, int], ...]
