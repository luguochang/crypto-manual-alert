from __future__ import annotations

from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow
from crypto_manual_alert.eval.regime_slices import calculate_regime_slices


def test_regime_slices_calculate_metrics_per_market_regime():
    slices = calculate_regime_slices(
        [
            _outcome("trace-1", "risk_on_repair", close=106),
            _outcome("trace-2", "risk_off_pressure", close=94),
        ],
        evaluation_target="legacy_final",
    )

    by_regime = {item.regime: item for item in slices}
    assert by_regime["risk_on_repair"].metrics.direction_hit_rate == 1.0
    assert by_regime["risk_off_pressure"].metrics.direction_hit_rate == 0.0
    assert by_regime["risk_on_repair"].to_public_dict()["regime"] == "risk_on_repair"


def _outcome(decision_ref: str, regime: str, *, close: float) -> DecisionOutcome:
    return DecisionOutcome(
        decision_ref=decision_ref,
        evaluation_target="legacy_final",
        symbol="BTC-USDT-SWAP",
        action="trigger long",
        probability=0.6,
        entry_price=100,
        stop_price=95,
        target_1=108,
        target_2=None,
        regime=regime,
        window=OutcomeWindow(
            name="1h",
            symbol="BTC-USDT-SWAP",
            interval="1m",
            source_type="exchange_native",
            window_start="2026-07-04T01:00:00Z",
            window_end="2026-07-04T02:00:00Z",
            collected_at="2026-07-04T02:01:00Z",
            open_price=100,
            high_price=max(101, close),
            low_price=min(99, close),
            close_price=close,
            matured=True,
        ),
    )
