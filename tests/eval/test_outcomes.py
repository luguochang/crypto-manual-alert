from __future__ import annotations

from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow


def test_outcome_window_requires_exchange_native_source_for_scored_execution_outcome():
    window = OutcomeWindow(
        name="1h",
        symbol="ETH-USDT-SWAP",
        interval="1m",
        source_type="search_derived",
        window_start="2026-07-04T01:00:00Z",
        window_end="2026-07-04T02:00:00Z",
        collected_at="2026-07-04T02:01:00Z",
        open_price=3000,
        high_price=3060,
        low_price=2980,
        close_price=3040,
        matured=True,
    )

    assert window.can_score_execution_outcome is False
    assert window.unscored_reason == "price_source_not_exchange_native"


def test_decision_outcome_preserves_target_identity_and_public_summary():
    window = OutcomeWindow(
        name="4h",
        symbol="BTC-USDT-SWAP",
        interval="5m",
        source_type="exchange_native",
        window_start="2026-07-04T01:00:00Z",
        window_end="2026-07-04T05:00:00Z",
        collected_at="2026-07-04T05:01:00Z",
        open_price=100000,
        high_price=102500,
        low_price=99500,
        close_price=101500,
        matured=True,
    )
    outcome = DecisionOutcome(
        decision_ref="trace-1:legacy_final",
        evaluation_target="legacy_final",
        symbol="BTC-USDT-SWAP",
        action="trigger long",
        probability=0.62,
        entry_price=100000,
        stop_price=99000,
        target_1=102000,
        target_2=104000,
        window=window,
    )

    assert outcome.can_score is True
    assert outcome.to_public_dict() == {
        "decision_ref": "trace-1:legacy_final",
        "evaluation_target": "legacy_final",
        "symbol": "BTC-USDT-SWAP",
        "action": "trigger long",
        "probability": 0.62,
        "entry_price": 100000,
        "stop_price": 99000,
        "target_1": 102000,
        "target_2": 104000,
        "window": window.to_public_dict(),
        "can_score": True,
        "unscored_reason": None,
    }


def test_no_trade_outcome_is_explicitly_unscored_not_a_failed_trade():
    window = OutcomeWindow(
        name="1h",
        symbol="ETH-USDT-SWAP",
        interval="1m",
        source_type="exchange_native",
        window_start="2026-07-04T01:00:00Z",
        window_end="2026-07-04T02:00:00Z",
        collected_at="2026-07-04T02:01:00Z",
        open_price=3000,
        high_price=3010,
        low_price=2990,
        close_price=3005,
        matured=True,
    )
    outcome = DecisionOutcome(
        decision_ref="trace-1:swarm_candidate",
        evaluation_target="swarm_candidate_final",
        symbol="ETH-USDT-SWAP",
        action="no trade",
        probability=0.51,
        entry_price=None,
        stop_price=None,
        target_1=None,
        target_2=None,
        window=window,
    )

    assert outcome.can_score is False
    assert outcome.unscored_reason == "no_trade_action"
