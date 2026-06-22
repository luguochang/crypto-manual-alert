from __future__ import annotations

from typing import Any

from .prediction_metrics import PredictionQualityMetrics


def build_financial_quality_gate(
    metrics: PredictionQualityMetrics,
    *,
    minimum_scored_count: int = 30,
    minimum_direction_hit_rate: float = 0.52,
    maximum_brier_score: float = 0.25,
) -> dict[str, Any]:
    reasons: list[str] = []
    if metrics.scored_count < minimum_scored_count:
        reasons.append("financial_quality:not_enough_samples")
        return _gate(
            metrics,
            status="not_enough_samples",
            passed=False,
            blocking=False,
            reasons=reasons,
            minimum_scored_count=minimum_scored_count,
        )
    if metrics.direction_hit_rate is None or metrics.direction_hit_rate < minimum_direction_hit_rate:
        reasons.append("financial_quality:direction_hit_rate_below_threshold")
    if metrics.brier_score is None or metrics.brier_score > maximum_brier_score:
        reasons.append("financial_quality:brier_score_above_threshold")
    return _gate(
        metrics,
        status="failed" if reasons else "passed",
        passed=not reasons,
        blocking=bool(reasons),
        reasons=reasons,
        minimum_scored_count=minimum_scored_count,
    )


def _gate(
    metrics: PredictionQualityMetrics,
    *,
    status: str,
    passed: bool,
    blocking: bool,
    reasons: list[str],
    minimum_scored_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "passed": passed,
        "blocking": blocking,
        "decision_effect": "none",
        "evaluation_target": metrics.evaluation_target,
        "minimum_scored_count": minimum_scored_count,
        "observed_scored_count": metrics.scored_count,
        "blocking_reasons": list(reasons),
        "metrics": metrics.to_public_dict(),
    }
