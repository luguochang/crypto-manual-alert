from __future__ import annotations

import sqlite3

from crypto_manual_alert.config import EvalConfig, EvalFinancialQualityConfig
from crypto_manual_alert.eval.outcome_store import OutcomeStore
from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow
from crypto_manual_alert.eval.runner import EvalRunner
from crypto_manual_alert.eval.store import EvalStore
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder


def test_eval_runner_marks_financial_quality_not_configured_without_outcome_store(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_badcase(journal)

    run = EvalRunner(journal=journal, store=store, data_dir=tmp_path).run(
        badcase_ids=[badcase_id],
        mode="cheap",
    )

    financial_gate = run.metadata["financial_quality_gate"]
    assert financial_gate == {
        "schema_version": 1,
        "status": "not_configured",
        "decision_effect": "none",
        "structural_release_gate_blocking": False,
        "blocking": False,
        "blocking_reasons": ["financial_quality:outcome_store_not_configured"],
        "evaluation_targets": ["legacy_final", "swarm_candidate_final"],
        "target_gates": [],
    }
    assert "financial_quality" not in run.metadata["release_gate"]["hard_gate_results"]


def test_eval_runner_attaches_financial_quality_gate_from_offline_outcomes_without_prod_side_effects(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    outcome_store = OutcomeStore(tmp_path / "eval" / "crypto-outcomes.db")
    _trace_id, badcase_id = _seed_badcase(journal)
    outcome_store.upsert_outcomes(
        [
            _scored_long_outcome("swarm-candidate:1"),
            _scored_long_outcome("swarm-candidate:2"),
        ]
    )
    before = _prod_table_counts(journal.path)
    config = EvalConfig(
        financial_quality=EvalFinancialQualityConfig(
            evaluation_targets=["swarm_candidate_final"],
            minimum_scored_count=2,
            minimum_direction_hit_rate=0.5,
            maximum_brier_score=0.2,
        )
    )

    run = EvalRunner(
        journal=journal,
        store=store,
        outcome_store=outcome_store,
        data_dir=tmp_path,
        eval_config=config,
    ).run(badcase_ids=[badcase_id], mode="cheap")

    assert _prod_table_counts(journal.path) == before
    financial_gate = run.metadata["financial_quality_gate"]
    assert financial_gate["schema_version"] == 1
    assert financial_gate["status"] == "passed"
    assert financial_gate["decision_effect"] == "none"
    assert financial_gate["structural_release_gate_blocking"] is False
    assert financial_gate["blocking"] is False
    assert financial_gate["blocking_reasons"] == []
    assert financial_gate["evaluation_targets"] == ["swarm_candidate_final"]
    assert financial_gate["target_gates"][0]["evaluation_target"] == "swarm_candidate_final"
    assert financial_gate["target_gates"][0]["metrics"]["scored_count"] == 2
    assert financial_gate["target_gates"][0]["metrics"]["direction_hit_rate"] == 1.0
    assert financial_gate["target_gates"][0]["metrics"]["brier_score"] == 0.09
    assert "financial_quality" not in run.metadata["release_gate"]["hard_gate_results"]

    persisted = store.get_run_detail(run.eval_run_id)
    assert persisted is not None
    assert persisted["run"]["metadata"]["financial_quality_gate"] == financial_gate


def _seed_badcase(journal: Journal) -> tuple[str, int]:
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP", horizon="6h")
    with recorder.span(trace_id, "decision.final", "decision.llm") as span:
        span.set_output({"main_action": "trigger long", "probability": 0.72})
    with recorder.span(trace_id, "risk.check", "risk.check") as span:
        span.set_output({"allowed": True, "reasons": []})
    recorder.finish_trace(
        trace_id,
        status="allowed",
        final_plan_id="plan_eval_financial_quality",
        final_action="trigger long",
        allowed=True,
    )
    journal.append_plan_run(
        "plan_eval_financial_quality",
        "allowed",
        {
            "trace_id": trace_id,
            "parsed_plan": {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "trigger long",
                "manual_execution_required": True,
                "probability": 0.72,
            },
            "verdict": {"allowed": True, "reasons": [], "warnings": []},
            "analysis": {"reasoning_summary": "fixture seed", "data_gaps": []},
            "raw_decision": "raw completion must not leak",
        },
    )
    badcase_id = journal.record_badcase(
        trace_id=trace_id,
        plan_id="plan_eval_financial_quality",
        category="grounding_error",
        severity="high",
        summary="financial quality eval seed",
        expected_behavior="opening plans require later outcome scoring",
        actual_behavior="trigger long",
        eval_dataset_name="failure_cases",
        evidence_refs=["trace.final_action", "plan_run.verdict"],
    )
    return trace_id, badcase_id


def _scored_long_outcome(decision_ref: str) -> DecisionOutcome:
    return DecisionOutcome(
        decision_ref=decision_ref,
        evaluation_target="swarm_candidate_final",
        symbol="ETH-USDT-SWAP",
        action="trigger long",
        probability=0.7,
        entry_price=100.0,
        stop_price=95.0,
        target_1=105.0,
        target_2=110.0,
        window=OutcomeWindow(
            name="4h",
            symbol="ETH-USDT-SWAP",
            interval="1H",
            source_type="exchange_native",
            window_start="2026-07-04T00:00:00+00:00",
            window_end="2026-07-04T04:00:00+00:00",
            collected_at="2026-07-04T04:05:00+00:00",
            open_price=100.0,
            high_price=106.0,
            low_price=99.0,
            close_price=104.0,
            matured=True,
            fee_bps=2.0,
            slippage_bps=1.0,
            funding_bps=0.0,
        ),
    )


def _prod_table_counts(db_path: str) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes", "traces", "trace_spans", "llm_interactions")
        }
