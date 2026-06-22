from __future__ import annotations

from crypto_manual_alert.eval.side_effect_proof import build_no_production_side_effect_proof


def test_no_production_side_effect_proof_records_zero_deltas_as_safe():
    before = _counts(plan_runs=2, notifications=1, traces=5, trace_spans=9, llm_interactions=3)
    fingerprints = _fingerprints()

    proof = build_no_production_side_effect_proof(
        eval_run_id="eval-run",
        before_counts=before,
        after_counts=dict(before),
        before_fingerprints=fingerprints,
        after_fingerprints=dict(fingerprints),
    )

    assert proof == {
        "schema_version": 1,
        "artifact_type": "no_production_side_effect_proof",
        "artifact_ref": "eval:eval-run:no_production_side_effect_proof",
        "eval_run_id": "eval-run",
        "decision_effect": "none",
        "production_final_input": False,
        "notification_input": False,
        "live_order_input": False,
        "passed": True,
        "checked_tables": [
            "plan_runs",
            "notifications",
            "manual_outcomes",
            "traces",
            "trace_spans",
            "llm_interactions",
        ],
        "before_counts": before,
        "after_counts": before,
        "deltas": {
            "plan_runs": 0,
            "notifications": 0,
            "manual_outcomes": 0,
            "traces": 0,
            "trace_spans": 0,
            "llm_interactions": 0,
        },
        "before_fingerprints": fingerprints,
        "after_fingerprints": fingerprints,
        "fingerprint_deltas": {},
        "blocking_reasons": [],
    }


def test_no_production_side_effect_proof_blocks_any_positive_production_delta():
    before = _counts(plan_runs=1)
    after = dict(before)
    after["plan_runs"] = 2
    fingerprints = _fingerprints()

    proof = build_no_production_side_effect_proof(
        eval_run_id="eval-run",
        before_counts=before,
        after_counts=after,
        before_fingerprints=fingerprints,
        after_fingerprints=dict(fingerprints),
    )

    assert proof["passed"] is False
    assert proof["deltas"]["plan_runs"] == 1
    assert proof["deltas"]["notifications"] == 0
    assert proof["blocking_reasons"] == ["production_side_effect_delta_detected"]


def test_no_production_side_effect_proof_requires_complete_count_inputs():
    try:
        build_no_production_side_effect_proof(
            eval_run_id="eval-run",
            before_counts={"plan_runs": 1},
            after_counts={"plan_runs": 1},
            before_fingerprints=_fingerprints(),
            after_fingerprints=_fingerprints(),
        )
    except ValueError as exc:
        assert "missing side-effect count" in str(exc)
    else:
        raise AssertionError("incomplete counts should fail closed")


def test_no_production_side_effect_proof_blocks_count_stable_fingerprint_changes():
    counts = _counts(plan_runs=1)
    before_fingerprints = _fingerprints(plan_runs="sha256:before")
    after_fingerprints = _fingerprints(plan_runs="sha256:after")
    proof = build_no_production_side_effect_proof(
        eval_run_id="eval-run",
        before_counts=counts,
        after_counts=dict(counts),
        before_fingerprints=before_fingerprints,
        after_fingerprints=after_fingerprints,
    )

    assert proof["passed"] is False
    assert proof["fingerprint_deltas"] == {"plan_runs": True}
    assert proof["blocking_reasons"] == ["production_side_effect_fingerprint_changed"]


def _counts(**overrides: int) -> dict[str, int]:
    counts = {
        "plan_runs": 0,
        "notifications": 0,
        "manual_outcomes": 0,
        "traces": 0,
        "trace_spans": 0,
        "llm_interactions": 0,
    }
    counts.update(overrides)
    return counts


def _fingerprints(**overrides: str) -> dict[str, str]:
    fingerprints = {
        "plan_runs": "sha256:plan_runs",
        "notifications": "sha256:notifications",
        "manual_outcomes": "sha256:manual_outcomes",
        "traces": "sha256:traces",
        "trace_spans": "sha256:trace_spans",
        "llm_interactions": "sha256:llm_interactions",
    }
    fingerprints.update(overrides)
    return fingerprints
