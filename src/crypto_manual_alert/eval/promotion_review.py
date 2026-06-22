from __future__ import annotations

from typing import Any

from crypto_manual_alert.eval.release_gate import build_release_gate_summary
from crypto_manual_alert.eval.schema import EvalReplayOutput, EvalScore
from crypto_manual_alert.eval.store import EvalStore


def upsert_promotion_review_artifacts(
    store: EvalStore,
    *,
    eval_run_id: str,
    artifacts: dict[str, dict[str, Any]],
    replay_outputs: dict[str, EvalReplayOutput],
    scores: list[EvalScore],
    minimum_case_count: int = 1,
    schema_valid_rate_threshold: float = 0.0,
    required_badcase_severities: list[str] | None = None,
) -> dict[str, Any]:
    """Persist manual promotion-review artifacts and recompute the release gate.

    This is an eval sidecar workflow entry. It does not approve promotion, does
    not modify production config, and does not write production journal or
    notification records.
    """

    run_detail = store.get_run_detail(eval_run_id)
    if run_detail is None:
        raise ValueError(f"eval run not found: {eval_run_id}")

    if artifacts:
        store.upsert_promotion_artifacts(eval_run_id, artifacts)

    promotion_artifacts = store.get_promotion_artifacts(eval_run_id)
    return build_release_gate_summary(
        scores=scores,
        replay_outputs=replay_outputs,
        cases=run_detail.get("cases") if isinstance(run_detail.get("cases"), list) else [],
        eval_run_id=eval_run_id,
        promotion_artifacts=promotion_artifacts,
        minimum_case_count=minimum_case_count,
        schema_valid_rate_threshold=schema_valid_rate_threshold,
        required_badcase_severities=required_badcase_severities or [],
    )
