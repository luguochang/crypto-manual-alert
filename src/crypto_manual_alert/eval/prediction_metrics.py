from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .outcomes import DecisionOutcome


@dataclass(frozen=True)
class PredictionQualityMetrics:
    evaluation_target: str
    scored_count: int
    pending_count: int
    unscored_count: int
    no_trade_count: int
    direction_hit_rate: float | None
    target_hit_rate: float | None
    invalidation_hit_rate: float | None
    average_pnl_pct: float | None
    average_r_multiple: float | None
    brier_score: float | None
    unscored_reasons: dict[str, int]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "scored_count": self.scored_count,
            "pending_count": self.pending_count,
            "unscored_count": self.unscored_count,
            "no_trade_count": self.no_trade_count,
            "direction_hit_rate": self.direction_hit_rate,
            "target_hit_rate": self.target_hit_rate,
            "invalidation_hit_rate": self.invalidation_hit_rate,
            "average_pnl_pct": self.average_pnl_pct,
            "average_r_multiple": self.average_r_multiple,
            "brier_score": self.brier_score,
            "unscored_reasons": dict(self.unscored_reasons),
        }


def calculate_prediction_metrics(
    outcomes: list[DecisionOutcome],
    *,
    evaluation_target: str,
) -> PredictionQualityMetrics:
    selected = [outcome for outcome in outcomes if outcome.evaluation_target == evaluation_target]
    pending_count = 0
    unscored_count = 0
    no_trade_count = 0
    unscored_reasons: dict[str, int] = {}
    scored_results = []
    for outcome in selected:
        if outcome.can_score:
            scored_results.append(_score_outcome(outcome))
            continue
        reason = outcome.unscored_reason or "unknown_unscored_reason"
        if reason == "no_trade_action":
            no_trade_count += 1
            continue
        if reason == "pending_outcome":
            pending_count += 1
        else:
            unscored_count += 1
        unscored_reasons[reason] = unscored_reasons.get(reason, 0) + 1

    scored_count = len(scored_results)
    return PredictionQualityMetrics(
        evaluation_target=evaluation_target,
        scored_count=scored_count,
        pending_count=pending_count,
        unscored_count=unscored_count,
        no_trade_count=no_trade_count,
        direction_hit_rate=_rate([item["direction_hit"] for item in scored_results]),
        target_hit_rate=_rate([item["target_hit"] for item in scored_results]),
        invalidation_hit_rate=_rate([item["invalidation_hit"] for item in scored_results]),
        average_pnl_pct=_average([item["pnl_pct"] for item in scored_results]),
        average_r_multiple=_average([item["r_multiple"] for item in scored_results]),
        brier_score=_average([item["brier"] for item in scored_results if item["brier"] is not None]),
        unscored_reasons=unscored_reasons,
    )


def calculate_no_trade_metrics(outcomes: list[DecisionOutcome]) -> PredictionQualityMetrics:
    """Counterfactual "always no-trade" baseline over the same windows as real decisions.

    For every window where a real trade decision was scored, the no-trade baseline
    holds no position: PnL = 0, no direction bet (direction_hit_rate = None), and a
    0.5-probability reference Brier = 0.25. Comparing this baseline's average_pnl_pct
    (0.0) against a real target's average_pnl_pct answers "did the alerts beat doing
    nothing?". The baseline is advisory and never blocking.
    """
    trade_windows = [
        outcome
        for outcome in outcomes
        if outcome.can_score and outcome.normalized_action != "no trade"
    ]
    pending_count = sum(
        1
        for outcome in outcomes
        if not outcome.can_score and (outcome.unscored_reason == "pending_outcome")
    )
    return PredictionQualityMetrics(
        evaluation_target="no_trade",
        scored_count=len(trade_windows),
        pending_count=pending_count,
        unscored_count=0,
        no_trade_count=0,
        direction_hit_rate=None,
        target_hit_rate=None,
        invalidation_hit_rate=None,
        average_pnl_pct=0.0,
        average_r_multiple=0.0,
        brier_score=0.25,
        unscored_reasons={},
    )


def _score_outcome(outcome: DecisionOutcome) -> dict[str, float | bool | None]:
    entry = float(outcome.entry_price)  # can_score guarantees presence.
    stop = float(outcome.stop_price)
    target_1 = float(outcome.target_1)
    high = float(outcome.window.high_price)
    low = float(outcome.window.low_price)
    close = float(outcome.window.close_price)
    if _is_long(outcome):
        direction_hit = close > entry
        target_hit = high >= target_1
        invalidation_hit = low <= stop
        pnl_pct = (close - entry) / entry
        risk = entry - stop
        r_multiple = (close - entry) / risk if risk > 0 else None
    else:
        direction_hit = close < entry
        target_hit = low <= target_1
        invalidation_hit = high >= stop
        pnl_pct = (entry - close) / entry
        risk = stop - entry
        r_multiple = (entry - close) / risk if risk > 0 else None
    brier = _brier(outcome.probability, direction_hit)
    return {
        "direction_hit": direction_hit,
        "target_hit": target_hit,
        "invalidation_hit": invalidation_hit,
        "pnl_pct": pnl_pct,
        "r_multiple": r_multiple,
        "brier": brier,
    }


def _is_long(outcome: DecisionOutcome) -> bool:
    return "long" in outcome.normalized_action


def _brier(probability: float | None, direction_hit: bool) -> float | None:
    if probability is None:
        return None
    probability = max(0.0, min(float(probability), 1.0))
    observed = 1.0 if direction_hit else 0.0
    return (probability - observed) ** 2


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 6)


def _average(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 6)
