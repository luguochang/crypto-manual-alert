from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .outcomes import DecisionOutcome
from .prediction_metrics import PredictionQualityMetrics, calculate_prediction_metrics


@dataclass(frozen=True)
class RegimeSlice:
    regime: str
    metrics: PredictionQualityMetrics

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "metrics": self.metrics.to_public_dict(),
        }


def calculate_regime_slices(
    outcomes: list[DecisionOutcome],
    *,
    evaluation_target: str,
) -> list[RegimeSlice]:
    grouped: dict[str, list[DecisionOutcome]] = {}
    for outcome in outcomes:
        if outcome.evaluation_target != evaluation_target:
            continue
        grouped.setdefault(outcome.regime or "unknown", []).append(outcome)
    return [
        RegimeSlice(
            regime=regime,
            metrics=calculate_prediction_metrics(items, evaluation_target=evaluation_target),
        )
        for regime, items in sorted(grouped.items())
    ]
