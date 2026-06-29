from __future__ import annotations

from pathlib import Path


DECISION_PACKAGE = Path("src/crypto_manual_alert/decision")


def test_replayable_input_entrypoint_delegates_ref_extraction_and_sanitization():
    source = (DECISION_PACKAGE / "replayable_input.py").read_text(encoding="utf-8")

    assert "def _observed_run_refs" not in source
    assert "def _worker_result_manifest" not in source
    assert "def _hash_payload" not in source
    assert "from crypto_manual_alert.decision.replay_observed_refs import" in source
    assert "observed_run_refs" in source
    assert "from crypto_manual_alert.decision.replay_worker_refs import" in source
    assert "from crypto_manual_alert.decision.replay_sanitization import hash_payload" in source


def test_replayable_input_support_modules_are_explicit():
    expected_modules = {
        "replay_observed_refs.py",
        "replay_sanitization.py",
        "replay_worker_refs.py",
    }

    assert expected_modules <= {path.name for path in DECISION_PACKAGE.glob("replay_*.py")}
