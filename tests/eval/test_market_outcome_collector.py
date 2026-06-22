from __future__ import annotations

from crypto_manual_alert.eval.market_outcome_collector import build_outcome_window_from_candles


def test_market_outcome_collector_builds_window_from_offline_exchange_candles():
    window = build_outcome_window_from_candles(
        name="1h",
        symbol="ETH-USDT-SWAP",
        interval="1m",
        source_type="exchange_native",
        window_start="2026-07-04T01:00:00Z",
        window_end="2026-07-04T02:00:00Z",
        collected_at="2026-07-04T02:01:00Z",
        candles=[
            {"open": 3000, "high": 3040, "low": 2990, "close": 3030},
            {"open": 3030, "high": 3065, "low": 3020, "close": 3050},
        ],
    )

    assert window.open_price == 3000
    assert window.high_price == 3065
    assert window.low_price == 2990
    assert window.close_price == 3050
    assert window.can_score_execution_outcome is True


def test_market_outcome_collector_marks_empty_or_immature_windows_pending():
    window = build_outcome_window_from_candles(
        name="4h",
        symbol="ETH-USDT-SWAP",
        interval="5m",
        source_type="exchange_native",
        window_start="2026-07-04T01:00:00Z",
        window_end="2026-07-04T05:00:00Z",
        collected_at="2026-07-04T02:00:00Z",
        candles=[],
        matured=False,
    )

    assert window.matured is False
    assert window.can_score_execution_outcome is False
    assert window.unscored_reason == "pending_outcome"
