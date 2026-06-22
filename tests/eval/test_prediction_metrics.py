from __future__ import annotations

from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow
from crypto_manual_alert.eval.prediction_metrics import calculate_prediction_metrics


def test_prediction_metrics_score_long_and_short_outcomes_without_no_trade_pollution():
    outcomes = [
        _outcome(
            decision_ref="trace-1:legacy",
            target="legacy_final",
            action="trigger long",
            probability=0.70,
            entry=100,
            stop=95,
            target_1=108,
            high=109,
            low=98,
            close=106,
        ),
        _outcome(
            decision_ref="trace-2:legacy",
            target="legacy_final",
            action="trigger short",
            probability=0.60,
            entry=100,
            stop=104,
            target_1=94,
            high=101,
            low=93,
            close=95,
        ),
        _outcome(
            decision_ref="trace-3:legacy",
            target="legacy_final",
            action="no trade",
            probability=0.50,
            entry=None,
            stop=None,
            target_1=None,
            high=103,
            low=97,
            close=101,
        ),
    ]

    metrics = calculate_prediction_metrics(outcomes, evaluation_target="legacy_final")

    assert metrics.scored_count == 2
    assert metrics.no_trade_count == 1
    assert metrics.direction_hit_rate == 1.0
    assert metrics.target_hit_rate == 1.0
    assert metrics.invalidation_hit_rate == 0.0
    assert metrics.average_pnl_pct == 0.055
    assert metrics.average_r_multiple == 1.225
    assert metrics.brier_score == 0.125


def test_prediction_metrics_separate_evaluation_targets():
    outcomes = [
        _outcome(
            decision_ref="trace-1:legacy",
            target="legacy_final",
            action="trigger long",
            probability=0.70,
            entry=100,
            stop=95,
            target_1=108,
            high=109,
            low=98,
            close=106,
        ),
        _outcome(
            decision_ref="trace-1:candidate",
            target="swarm_candidate_final",
            action="trigger short",
            probability=0.60,
            entry=100,
            stop=104,
            target_1=94,
            high=109,
            low=98,
            close=106,
        ),
    ]

    metrics = calculate_prediction_metrics(outcomes, evaluation_target="swarm_candidate_final")

    assert metrics.evaluation_target == "swarm_candidate_final"
    assert metrics.scored_count == 1
    assert metrics.direction_hit_rate == 0.0
    assert metrics.invalidation_hit_rate == 1.0


def test_prediction_metrics_mark_pending_and_unscored_windows_explicitly():
    pending = _outcome(
        decision_ref="trace-pending:legacy",
        target="legacy_final",
        action="trigger long",
        probability=0.55,
        entry=100,
        stop=95,
        target_1=108,
        high=102,
        low=99,
        close=101,
        matured=False,
    )
    web_price = _outcome(
        decision_ref="trace-web:legacy",
        target="legacy_final",
        action="trigger long",
        probability=0.55,
        entry=100,
        stop=95,
        target_1=108,
        high=102,
        low=99,
        close=101,
        source_type="search_derived",
    )

    metrics = calculate_prediction_metrics([pending, web_price], evaluation_target="legacy_final")

    assert metrics.scored_count == 0
    assert metrics.pending_count == 1
    assert metrics.unscored_count == 1
    assert metrics.unscored_reasons == {
        "pending_outcome": 1,
        "price_source_not_exchange_native": 1,
    }


def _outcome(
    *,
    decision_ref: str,
    target: str,
    action: str,
    probability: float,
    entry: float | None,
    stop: float | None,
    target_1: float | None,
    high: float,
    low: float,
    close: float,
    matured: bool = True,
    source_type: str = "exchange_native",
) -> DecisionOutcome:
    return DecisionOutcome(
        decision_ref=decision_ref,
        evaluation_target=target,
        symbol="BTC-USDT-SWAP",
        action=action,
        probability=probability,
        entry_price=entry,
        stop_price=stop,
        target_1=target_1,
        target_2=None,
        window=OutcomeWindow(
            name="1h",
            symbol="BTC-USDT-SWAP",
            interval="1m",
            source_type=source_type,
            window_start="2026-07-04T01:00:00Z",
            window_end="2026-07-04T02:00:00Z",
            collected_at="2026-07-04T02:01:00Z",
            open_price=100,
            high_price=high,
            low_price=low,
            close_price=close,
            matured=matured,
        ),
    )


def test_no_trade_baseline_metrics_are_zero_pnl_counterfactual():
    """no-trade baseline: same windows as real trades, PnL=0, no direction bet."""
    from crypto_manual_alert.eval.prediction_metrics import calculate_no_trade_metrics

    outcomes = [
        _outcome(
            decision_ref="trace-1:legacy",
            target="legacy_final",
            action="trigger long",
            probability=0.70,
            entry=100,
            stop=95,
            target_1=108,
            high=109,
            low=98,
            close=106,
        ),
        _outcome(
            decision_ref="trace-2:legacy",
            target="legacy_final",
            action="trigger short",
            probability=0.60,
            entry=100,
            stop=104,
            target_1=94,
            high=101,
            low=93,
            close=96,
        ),
    ]
    metrics = calculate_no_trade_metrics(outcomes)
    assert metrics.evaluation_target == "no_trade"
    assert metrics.scored_count == 2  # two real trade windows
    assert metrics.average_pnl_pct == 0.0  # did nothing
    assert metrics.direction_hit_rate is None  # no bet
    assert metrics.brier_score == 0.25  # 0.5 probability reference
