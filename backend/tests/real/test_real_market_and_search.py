import os
from decimal import Decimal

import pytest

from crypto_alert_v2.providers.okx import OkxProvider
from crypto_alert_v2.providers.search import TavilySearchProvider
from crypto_alert_v2.config import get_settings

pytestmark = pytest.mark.skipif(
    os.getenv("REAL_PROVIDER_TESTS") != "1",
    reason="set REAL_PROVIDER_TESTS=1 to call the real OKX public API",
)


@pytest.mark.parametrize(
    "symbol",
    ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"],
)
def test_real_okx_market_snapshot_has_all_typed_exchange_native_data(
    symbol: str,
) -> None:
    settings = get_settings()
    with OkxProvider(proxy=settings.market_data_http_proxy) as provider:
        snapshot = provider.fetch_snapshot(
            symbol,
            correlation_id=f"real-okx-{symbol}",
        )

    assert snapshot.provider == "okx"
    assert snapshot.venue == "OKX"
    assert snapshot.source_level == "exchange_native"
    assert snapshot.symbol == symbol
    assert snapshot.index_symbol == symbol.removesuffix("-SWAP")
    assert snapshot.ticker.last > Decimal("0")
    assert snapshot.mark_price > Decimal("0")
    assert snapshot.index_price > Decimal("0")
    assert snapshot.funding_rate.is_finite()
    assert snapshot.open_interest > Decimal("0")
    assert snapshot.order_book.bids
    assert snapshot.order_book.asks
    assert snapshot.candles
    assert snapshot.candles[0].close > Decimal("0")
    assert len(snapshot.exchange_timestamps_ms) == 7
    assert snapshot.client_timestamp_ms > 0
    assert len(snapshot.raw_hash) == 64

    print(
        f"{symbol}: last={snapshot.ticker.last} mark={snapshot.mark_price} "
        f"index={snapshot.index_price} funding={snapshot.funding_rate} "
        f"oi={snapshot.open_interest} bids={len(snapshot.order_book.bids)} "
        f"asks={len(snapshot.order_book.asks)} candles={len(snapshot.candles)}"
    )


def test_real_tavily_search_returns_cited_provider_evidence() -> None:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        pytest.skip("TAVILY_API_KEY is required for real Tavily proof")

    evidence = TavilySearchProvider(api_key=api_key).search(
        "current Bitcoin macro market news"
    )

    assert evidence
    assert all(item.source == "tavily" for item in evidence)
    assert all(str(item.final_url).startswith("https://") for item in evidence)
    assert all(item.title and item.excerpt for item in evidence)
