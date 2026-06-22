from __future__ import annotations

from typing import Any

from crypto_manual_alert.config import EvalFinancialQualityConfig

from .financial_quality_gate import build_financial_quality_gate
from .outcome_store import OutcomeStore
from .prediction_metrics import calculate_no_trade_metrics, calculate_prediction_metrics


def build_financial_quality_summary(
    *,
    outcome_store: OutcomeStore | None,
    config: EvalFinancialQualityConfig,
) -> dict[str, Any]:
    """Build advisory financial quality metadata from frozen offline outcomes."""

    targets = list(config.evaluation_targets)
    if outcome_store is None:
        return {
            "schema_version": 1,
            "status": "not_configured",
            "decision_effect": "none",
            "structural_release_gate_blocking": False,
            "blocking": False,
            "blocking_reasons": ["financial_quality:outcome_store_not_configured"],
            "evaluation_targets": targets,
            "target_gates": [],
        }

    target_gates = []
    for target in targets:
        outcomes = outcome_store.list_outcomes(evaluation_target=target)
        metrics = calculate_prediction_metrics(outcomes, evaluation_target=target)
        target_gate = build_financial_quality_gate(
            metrics,
            minimum_scored_count=config.minimum_scored_count,
            minimum_direction_hit_rate=config.minimum_direction_hit_rate,
            maximum_brier_score=config.maximum_brier_score,
        )
        target_gates.append(
            {
                **target_gate,
                "structural_release_gate_blocking": False,
                "brier_event_label": "window_direction_hit",
            }
        )

    # Counterfactual no-trade baseline: derived from all real outcomes' windows,
    # never blocking. Lets reviewers compare alert PnL against "did nothing" (=0).
    all_outcomes = outcome_store.list_outcomes()
    no_trade_metrics = calculate_no_trade_metrics(all_outcomes)
    no_trade_gate = build_financial_quality_gate(
        no_trade_metrics,
        minimum_scored_count=config.minimum_scored_count,
        minimum_direction_hit_rate=config.minimum_direction_hit_rate,
        maximum_brier_score=config.maximum_brier_score,
    )
    target_gates.append(
        {
            **no_trade_gate,
            "status": "baseline_reference",
            "passed": True,
            "blocking": False,
            "blocking_reasons": [],
            "structural_release_gate_blocking": False,
            "brier_event_label": "no_trade_counterfactual",
        }
    )

    blocking_reasons = _dedupe(
        [
            str(reason)
            for gate in target_gates
            if gate.get("blocking") is True
            for reason in gate.get("blocking_reasons", [])
        ]
    )
    statuses = [str(gate.get("status")) for gate in target_gates]
    if any(status == "failed" for status in statuses):
        status = "failed"
    elif any(status == "not_enough_samples" for status in statuses):
        status = "not_enough_samples"
    elif target_gates:
        status = "passed"
    else:
        status = "not_configured"

    return {
        "schema_version": 1,
        "status": status,
        "decision_effect": "none",
        "structural_release_gate_blocking": False,
        "blocking": bool(blocking_reasons),
        "blocking_reasons": blocking_reasons,
        "evaluation_targets": targets,
        "target_gates": target_gates,
    }


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
