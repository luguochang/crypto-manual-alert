from __future__ import annotations

from crypto_manual_alert.eval.financial_quality_gate import build_financial_quality_gate
from crypto_manual_alert.eval.prediction_metrics import PredictionQualityMetrics


def test_financial_quality_gate_reports_not_enough_samples_without_structural_block():
    gate = build_financial_quality_gate(
        PredictionQualityMetrics(
            evaluation_target="swarm_candidate_final",
            scored_count=2,
            pending_count=1,
            unscored_count=0,
            no_trade_count=0,
            direction_hit_rate=1.0,
            target_hit_rate=0.5,
            invalidation_hit_rate=0.0,
            average_pnl_pct=0.03,
            average_r_multiple=0.8,
            brier_score=0.12,
            unscored_reasons={},
        ),
        minimum_scored_count=30,
    )

    assert gate == {
        "schema_version": 1,
        "status": "not_enough_samples",
        "passed": False,
        "blocking": False,
        "decision_effect": "none",
        "evaluation_target": "swarm_candidate_final",
        "minimum_scored_count": 30,
        "observed_scored_count": 2,
        "blocking_reasons": ["financial_quality:not_enough_samples"],
        "metrics": {
            "scored_count": 2,
            "pending_count": 1,
            "unscored_count": 0,
            "no_trade_count": 0,
            "direction_hit_rate": 1.0,
            "target_hit_rate": 0.5,
            "invalidation_hit_rate": 0.0,
            "average_pnl_pct": 0.03,
            "average_r_multiple": 0.8,
            "brier_score": 0.12,
            "unscored_reasons": {},
        },
    }


def test_financial_quality_gate_blocks_candidate_promotion_when_quality_is_low():
    gate = build_financial_quality_gate(
        PredictionQualityMetrics(
            evaluation_target="swarm_candidate_final",
            scored_count=40,
            pending_count=0,
            unscored_count=0,
            no_trade_count=3,
            direction_hit_rate=0.48,
            target_hit_rate=0.2,
            invalidation_hit_rate=0.35,
            average_pnl_pct=-0.01,
            average_r_multiple=-0.2,
            brier_score=0.31,
            unscored_reasons={},
        ),
        minimum_scored_count=30,
        minimum_direction_hit_rate=0.52,
        maximum_brier_score=0.25,
    )

    assert gate["status"] == "failed"
    assert gate["passed"] is False
    assert gate["blocking"] is True
    assert gate["decision_effect"] == "none"
    assert gate["blocking_reasons"] == [
        "financial_quality:direction_hit_rate_below_threshold",
        "financial_quality:brier_score_above_threshold",
    ]


def test_financial_quality_gate_passes_when_metrics_meet_thresholds():
    gate = build_financial_quality_gate(
        PredictionQualityMetrics(
            evaluation_target="legacy_final",
            scored_count=35,
            pending_count=0,
            unscored_count=2,
            no_trade_count=5,
            direction_hit_rate=0.57,
            target_hit_rate=0.31,
            invalidation_hit_rate=0.18,
            average_pnl_pct=0.012,
            average_r_multiple=0.28,
            brier_score=0.21,
            unscored_reasons={"no_trade_action": 5},
        ),
        minimum_scored_count=30,
        minimum_direction_hit_rate=0.52,
        maximum_brier_score=0.25,
    )

    assert gate["status"] == "passed"
    assert gate["passed"] is True
    assert gate["blocking"] is False
    assert gate["blocking_reasons"] == []
