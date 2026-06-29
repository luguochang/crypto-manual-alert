from __future__ import annotations

from pathlib import Path


CASE_BUILDER = Path("src/crypto_manual_alert/eval/case_builder.py")
EVAL_PACKAGE = Path("src/crypto_manual_alert/eval")


def test_case_builder_delegates_candidate_artifact_snapshot_summary():
    source = CASE_BUILDER.read_text(encoding="utf-8")

    assert "from .candidate_artifact_snapshots import artifact_snapshot_summary" in source
    assert "def _artifact_snapshot_summary(" not in source
    assert "def _lead_synthesis_snapshot_ref(" not in source
    assert "def _worker_manifest_snapshot_ref(" not in source
    assert "def _candidate_gate_snapshot_ref(" not in source
    assert "def _sanitize_for_artifact_hash(" not in source


def test_case_builder_delegates_context_artifact_summary():
    source = CASE_BUILDER.read_text(encoding="utf-8")

    assert "from .context_artifact_summary import context_artifacts_summary" in source
    assert "def _context_artifacts_summary(" not in source
    assert "def _context_gate_result_refs(" not in source
    assert "def _context_evidence_refs(" not in source
    assert "def _context_contribution_refs(" not in source


def test_case_builder_delegates_replayable_input_summary():
    source = CASE_BUILDER.read_text(encoding="utf-8")

    assert "from .replayable_input_summary import" in source
    assert "replayable_coverage_summary" in source
    assert "replayable_artifact_refs_summary" in source
    assert "def _replayable_coverage_summary(" not in source
    assert "def _replayable_artifact_refs_summary(" not in source
    assert "def _shadow_worker_refs(" not in source
    assert "def _worker_result_manifest_refs(" not in source
    assert "def _final_decision_output_ref(" not in source
    assert "def _final_input_selection_ref(" not in source
    assert "def _parsed_plan_ref(" not in source
    assert "def _gate_ref(" not in source
    assert "def _side_effect_policy_ref(" not in source
    assert "def _context_artifact_summary_ref(" not in source
    assert "def _version_lock_ref(" not in source
    assert "def _telemetry_refs(" not in source
    assert "def _evidence_snapshot_refs(" not in source
    assert "def _memory_snapshot_refs(" not in source
    assert "def _span_tree_refs(" not in source


def test_candidate_artifact_snapshot_module_is_explicit():
    assert (EVAL_PACKAGE / "candidate_artifact_snapshots.py").exists()


def test_context_artifact_summary_module_is_explicit():
    assert (EVAL_PACKAGE / "context_artifact_summary.py").exists()


def test_replayable_input_summary_module_is_explicit():
    assert (EVAL_PACKAGE / "replayable_input_summary.py").exists()


def test_replayable_input_summary_module_stays_side_effect_free():
    source = (EVAL_PACKAGE / "replayable_input_summary.py").read_text(encoding="utf-8")

    assert "Journal" not in source
    assert "EvalStore" not in source
    assert "workflow" not in source
    assert "crypto_manual_alert.notification" not in source
    assert "from .notification" not in source
    assert "decision.final_input" not in source
    assert "pre_final_input" not in source
    assert "final_engine" not in source
