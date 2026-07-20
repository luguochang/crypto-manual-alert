from collections.abc import Callable

import httpx
import pytest

from crypto_alert_v2.providers.errors import ProviderUnavailable
from crypto_alert_v2.providers.okx import OkxProvider
from crypto_alert_v2.providers.retry_policy import RetryPolicy


def _response_data(path: str) -> list[object]:
    responses: dict[str, list[object]] = {
        "/api/v5/market/ticker": [
            {"instId": "BTC-USDT-SWAP", "last": "60123.4", "ts": "1720000000000"}
        ],
        "/api/v5/public/mark-price": [
            {"instId": "BTC-USDT-SWAP", "markPx": "60120.1", "ts": "1720000000001"}
        ],
        "/api/v5/market/index-tickers": [
            {"instId": "BTC-USDT", "idxPx": "60110.2", "ts": "1720000000002"}
        ],
        "/api/v5/public/funding-rate": [
            {
                "instId": "BTC-USDT-SWAP",
                "fundingRate": "0.00001",
                "fundingTime": "1720000800000",
            }
        ],
        "/api/v5/public/open-interest": [
            {"instId": "BTC-USDT-SWAP", "oi": "12345.67", "ts": "1720000000003"}
        ],
        "/api/v5/market/books": [
            {
                "asks": [["60124.0", "2.5", "0", "1"]],
                "bids": [["60122.8", "3.5", "0", "2"]],
                "ts": "1720000000004",
            }
        ],
        "/api/v5/market/candles": [
            ["1720000000000", "60000", "60200", "59900", "60123.4", "100"]
        ],
    }
    return responses[path]


def _no_wait_policy() -> RetryPolicy:
    return RetryPolicy(backoff_seconds=(0.0, 0.0), sleep=lambda _: None)


def test_provider_fetches_all_seven_public_gets_and_strips_swap_for_index() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"code": "0", "msg": "", "data": _response_data(request.url.path)},
        )

    with OkxProvider(
        transport=httpx.MockTransport(handler),
        retry_policy=_no_wait_policy(),
    ) as provider:
        snapshot = provider.fetch_snapshot(
            "BTC-USDT-SWAP",
            horizon="4h",
            correlation_id="corr-success",
        )

    assert snapshot.symbol == "BTC-USDT-SWAP"
    assert snapshot.provider == "okx"
    assert snapshot.venue == "OKX"
    assert snapshot.operation == "market_snapshot"
    assert snapshot.source_level == "exchange_native"
    assert snapshot.client_timestamp_ms > 0
    assert snapshot.clock_skew_ms == snapshot.client_timestamp_ms - 1720000000000
    assert len(snapshot.raw_hash) == 64
    assert snapshot.normalized_schema_version == "okx-market-snapshot/v1"
    assert snapshot.freshness_version == "exchange-timestamp/v1"
    assert len(requests) == 7
    assert {request.method for request in requests} == {"GET"}
    assert [request.url.path for request in requests] == [
        "/api/v5/market/ticker",
        "/api/v5/public/mark-price",
        "/api/v5/market/index-tickers",
        "/api/v5/public/funding-rate",
        "/api/v5/public/open-interest",
        "/api/v5/market/books",
        "/api/v5/market/candles",
    ]
    index_request = requests[2]
    assert index_request.url.params["instId"] == "BTC-USDT"
    assert requests[-1].url.params["bar"] == "4H"
    assert all(
        request.url.params.get("instId") == "BTC-USDT-SWAP"
        for request in requests[:2] + requests[3:]
    )

    forbidden_headers = {
        "authorization",
        "ok-access-key",
        "ok-access-sign",
        "ok-access-passphrase",
        "ok-access-timestamp",
    }
    assert all(
        not forbidden_headers.intersection(request.headers) for request in requests
    )


def test_provider_fails_closed_when_okx_returns_mixed_instruments() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        data = _response_data(request.url.path)
        if request.url.path == "/api/v5/public/mark-price":
            data.append(
                {
                    "instId": "ETH-USDT-SWAP",
                    "markPx": "3500",
                    "ts": "1720000000001",
                }
            )
        return httpx.Response(200, json={"code": "0", "msg": "", "data": data})

    with OkxProvider(
        transport=httpx.MockTransport(handler),
        retry_policy=_no_wait_policy(),
    ) as provider:
        with pytest.raises(ProviderUnavailable, match="instrument mismatch") as raised:
            provider.fetch_snapshot(
                "BTC-USDT-SWAP",
                correlation_id="corr-mixed",
            )

    assert len(requests) == 7
    assert raised.value.endpoint == "mark"
    assert raised.value.retryable is False
    assert raised.value.correlation_id == "corr-mixed"


@pytest.mark.parametrize("keyword", ["api_secret", "passphrase", "api_key"])
def test_provider_constructor_rejects_private_credentials(keyword: str) -> None:
    with pytest.raises(TypeError):
        OkxProvider(**{keyword: "must-not-be-accepted"})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "failure",
    [
        lambda request: httpx.Response(500, json={"code": "500", "data": []}),
        lambda request: (_ for _ in ()).throw(
            httpx.ReadTimeout("timeout", request=request)
        ),
    ],
)
def test_provider_retries_transient_failure_only_three_times(
    failure: Callable[[httpx.Request], httpx.Response],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return failure(request)

    with OkxProvider(
        transport=httpx.MockTransport(handler),
        retry_policy=_no_wait_policy(),
    ) as provider:
        with pytest.raises(ProviderUnavailable) as raised:
            provider.fetch_snapshot("BTC-USDT-SWAP", correlation_id="corr-failure")

    assert len(requests) == 3
    assert raised.value.provider == "okx"
    assert raised.value.endpoint == "ticker"
    assert raised.value.retryable is True
    assert raised.value.correlation_id == "corr-failure"


def test_default_httpx_transport_disables_its_own_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: list[int] = []

    def transport_factory(*, retries: int) -> httpx.BaseTransport:
        configured.append(retries)
        return httpx.MockTransport(lambda _: httpx.Response(500))

    monkeypatch.setattr(httpx, "HTTPTransport", transport_factory)

    with OkxProvider():
        pass

    assert configured == [0]


def test_provider_passes_only_the_explicit_market_proxy_to_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: list[dict[str, object]] = []

    class RecordingClient:
        def __init__(self, **kwargs: object) -> None:
            configured.append(kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", RecordingClient)

    with OkxProvider(proxy="http://127.0.0.1:7890"):
        pass

    assert len(configured) == 1
    assert configured[0]["proxy"] == "http://127.0.0.1:7890"
    assert configured[0]["trust_env"] is False


def test_provider_package_exports_only_typed_public_adapter_api() -> None:
    from crypto_alert_v2 import providers

    assert set(providers.__all__) == {
        "MarketSnapshot",
        "OkxProvider",
        "ProviderUnavailable",
        "RetryPolicy",
        "parse_okx_snapshot",
    }
