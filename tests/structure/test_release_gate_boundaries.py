from __future__ import annotations

from pathlib import Path


RELEASE_GATE = Path("src/crypto_manual_alert/eval/release_gate.py")
EVAL_PACKAGE = Path("src/crypto_manual_alert/eval")


def test_release_gate_delegates_promotion_review_state_machine():
    source = RELEASE_GATE.read_text(encoding="utf-8")

    assert "from .release_promotion_review import promotion_review" in source
    assert "def _promotion_review(" not in source
    assert "def _required_artifact_status(" not in source
    assert "def _valid_promotion_artifact(" not in source
    assert "def _valid_manual_release_decision(" not in source
    assert "def _valid_config_change_review_request(" not in source


def test_release_promotion_review_module_is_explicit():
    assert (EVAL_PACKAGE / "release_promotion_review.py").exists()
