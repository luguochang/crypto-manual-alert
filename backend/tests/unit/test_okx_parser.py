from copy import deepcopy
from decimal import Decimal

import pytest

from crypto_alert_v2.providers.errors import ProviderUnavailable
from crypto_alert_v2.providers.models import MarketSnapshot
from crypto_alert_v2.providers.okx import parse_okx_snapshot


def _okx_envelopes() -> dict[str, dict[str, object]]:
    return {
        "ticker": {
            "code": "0",
            "msg": "",
            "data": [{"instId": "BTC-USDT-SWAP", "last": "60123.4", "ts": "1720000000000"}],
        },
        "mark": {
            "code": "0",
            "msg": "",
            "data": [{"instId": "BTC-USDT-SWAP", "markPx": "60120.1", "ts": "1720000000001"}],
        },
        "index": {
            "code": "0",
            "msg": "",
            "data": [{"instId": "BTC-USDT", "idxPx": "60110.2", "ts": "1720000000002"}],
        },
        "funding": {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "fundingRate": "-0.0000125",
                    "fundingTime": "1720000800000",
                }
            ],
        },
        "open_interest": {
            "code": "0",
            "msg": "",
            "data": [{"instId": "BTC-USDT-SWAP", "oi": "12345.67", "ts": "1720000000003"}],
        },
        "book": {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "asks": [["60124.0", "2.5", "0", "1"]],
                    "bids": [["60122.8", "3.5", "0", "2"]],
                    "ts": "1720000000004",
                }
            ],
        },
        "candles": {
            "code": "0",
            "msg": "",
            "data": [
                [
                    "1720000000000",
                    "60000",
                    "60200",
                    "59900",
                    "60123.4",
                    "100",
                    "1.5",
                    "90000",
                    "1",
                ]
            ],
        },
    }


def test_okx_parser_returns_decimal_dtos_not_raw_envelopes() -> None:
    snapshot = parse_okx_snapshot("BTC-USDT-SWAP", _okx_envelopes())

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.symbol == "BTC-USDT-SWAP"
    assert snapshot.index_symbol == "BTC-USDT"
    assert snapshot.ticker.last == Decimal("60123.4")
    assert snapshot.mark_price == Decimal("60120.1")
    assert snapshot.index_price == Decimal("60110.2")
    assert snapshot.funding_rate == Decimal("-0.0000125")
    assert snapshot.open_interest == Decimal("12345.67")
    assert snapshot.order_book.asks[0].price == Decimal("60124.0")
    assert snapshot.order_book.bids[0].size == Decimal("3.5")
    assert snapshot.candles[0].close == Decimal("60123.4")
    assert not hasattr(snapshot, "raw")


@pytest.mark.parametrize(
    ("endpoint", "mutate", "message"),
    [
        (
            "ticker",
            lambda payload: payload["ticker"].update(code="50001", msg="exchange failure"),
            "code=50001",
        ),
        (
            "mark",
            lambda payload: payload["mark"].update(data=[]),
            "non-empty data",
        ),
        (
            "index",
            lambda payload: payload["index"]["data"][0].update(idxPx="NaN"),
            "finite positive",
        ),
        (
            "open_interest",
            lambda payload: payload["open_interest"]["data"][0].update(oi="0"),
            "finite positive",
        ),
        (
            "book",
            lambda payload: payload["book"]["data"][0].update(bids=[]),
            "both bids and asks",
        ),
        (
            "candles",
            lambda payload: payload["candles"]["data"][0].__setitem__(4, "0"),
            "finite positive close",
        ),
    ],
)
def test_okx_parser_rejects_invalid_provider_data(
    endpoint: str,
    mutate: object,
    message: str,
) -> None:
    payload = deepcopy(_okx_envelopes())
    mutate(payload)  # type: ignore[operator]

    with pytest.raises(ProviderUnavailable, match=message) as raised:
        parse_okx_snapshot(
            "BTC-USDT-SWAP",
            payload,
            correlation_id="corr-parser",
        )

    assert raised.value.provider == "okx"
    assert raised.value.endpoint == endpoint
    assert raised.value.retryable is False
    assert raised.value.correlation_id == "corr-parser"


def test_okx_parser_rejects_unsupported_non_swap_symbol() -> None:
    with pytest.raises(ProviderUnavailable, match="unsupported OKX SWAP symbol"):
        parse_okx_snapshot("DOGE-USDT-SWAP", _okx_envelopes())


@pytest.mark.parametrize(
    ("endpoint", "mutate"),
    [
        ("ticker", lambda payload: payload["ticker"]["data"][0].pop("last")),
        ("mark", lambda payload: payload["mark"]["data"][0].pop("markPx")),
        ("index", lambda payload: payload["index"]["data"][0].pop("idxPx")),
        ("funding", lambda payload: payload["funding"]["data"][0].pop("fundingRate")),
        (
            "open_interest",
            lambda payload: payload["open_interest"]["data"][0].pop("oi"),
        ),
        ("book", lambda payload: payload["book"]["data"][0].update(bids=[["1"]])),
        ("candles", lambda payload: payload["candles"].update(data=[["1", "2"]])),
    ],
)
def test_okx_parser_wraps_malformed_shapes_with_endpoint_context(
    endpoint: str,
    mutate: object,
) -> None:
    payload = deepcopy(_okx_envelopes())
    mutate(payload)  # type: ignore[operator]

    with pytest.raises(ProviderUnavailable) as raised:
        parse_okx_snapshot(
            "BTC-USDT-SWAP",
            payload,
            correlation_id="corr-shape",
        )

    assert raised.value.provider == "okx"
    assert raised.value.endpoint == endpoint
    assert raised.value.retryable is False
    assert raised.value.correlation_id == "corr-shape"
