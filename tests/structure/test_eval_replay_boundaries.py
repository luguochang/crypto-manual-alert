from __future__ import annotations

from pathlib import Path


REPLAY = Path("src/crypto_manual_alert/eval/replay.py")
EVAL_PACKAGE = Path("src/crypto_manual_alert/eval")


def test_replay_delegates_artifact_snapshot_consistency():
    source = REPLAY.read_text(encoding="utf-8")

    assert "from .candidate_artifact_consistency import artifact_snapshot_consistency" in source
    assert "def _artifact_snapshot_consistency(" not in source
    assert "CANDIDATE_ARTIFACT_TYPES" not in source


def test_replay_delegates_worker_manifest_consistency():
    source = REPLAY.read_text(encoding="utf-8")

    assert "from .worker_manifest_consistency import" in source
    assert "worker_manifest_consistency" in source
    assert "def _worker_manifest_consistency(" not in source
    assert "def _lead_synthesis_worker_drop_violations(" not in source
    assert "def _lead_synthesis_optional_worker_drop_advisories(" not in source
    assert "def _manifest_item_required(" not in source


def test_replay_delegates_context_artifact_consistency():
    source = REPLAY.read_text(encoding="utf-8")

    assert "from .context_artifact_consistency import context_artifact_consistency" in source
    assert "def _context_artifact_consistency(" not in source
    assert "def _append_context_candidate_artifact_violations(" not in source


def test_replay_delegates_complete_replay_refs():
    source = REPLAY.read_text(encoding="utf-8")

    assert "from .complete_replay_refs import" in source
    assert "def _complete_replay_refs(" not in source
    assert "def _complete_replay_missing_refs(" not in source
    assert "COMPLETE_REPLAY_REF_KEYS" not in source


def test_replay_delegates_counter_conflict_coverage():
    source = REPLAY.read_text(encoding="utf-8")

    assert "from .counter_conflict_coverage import counter_conflict_coverage" in source
    assert "def _counter_conflict_coverage(" not in source
    assert "lead_synthesis_artifact_counter_conflict_violations" not in source
    assert "artifact_ref_count" not in source


def test_replay_delegates_shadow_final_comparison():
    source = REPLAY.read_text(encoding="utf-8")

    assert "from .shadow_final_comparison import build_shadow_legacy_comparison" in source
    assert "def _shadow_legacy_comparison(" not in source


def test_candidate_artifact_consistency_module_is_explicit():
    assert (EVAL_PACKAGE / "candidate_artifact_consistency.py").exists()


def test_worker_manifest_consistency_module_is_explicit():
    assert (EVAL_PACKAGE / "worker_manifest_consistency.py").exists()


def test_context_artifact_consistency_module_is_explicit():
    assert (EVAL_PACKAGE / "context_artifact_consistency.py").exists()


def test_complete_replay_refs_module_is_explicit():
    assert (EVAL_PACKAGE / "complete_replay_refs.py").exists()


def test_counter_conflict_coverage_module_is_explicit():
    assert (EVAL_PACKAGE / "counter_conflict_coverage.py").exists()


def test_shadow_final_comparison_module_is_explicit():
    assert (EVAL_PACKAGE / "shadow_final_comparison.py").exists()
