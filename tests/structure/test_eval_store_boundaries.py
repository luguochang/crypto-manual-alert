from __future__ import annotations

from pathlib import Path


STORE = Path("src/crypto_manual_alert/eval/store.py")
EVAL_PACKAGE = Path("src/crypto_manual_alert/eval")


def test_store_delegates_promotion_artifact_validation():
    source = STORE.read_text(encoding="utf-8")

    assert "from .promotion_artifact_validation import validate_promotion_artifact" in source
    assert "validate_promotion_artifact(eval_run_id, str(artifact_type), artifact)" in source
    assert "def _validate_promotion_artifact(" not in source
    assert "def _promotion_artifact_ref_matches(" not in source
    assert "def _validate_config_change_review_request_artifact(" not in source


def test_store_delegates_candidate_artifact_validation():
    source = STORE.read_text(encoding="utf-8")

    assert "from .candidate_artifact_validation import" in source
    assert "validate_candidate_artifact_snapshot(snapshot)" in source
    assert "validate_candidate_artifact(case_id, artifact_type, artifact)" in source
    assert "candidate_artifact_ref(artifact)" in source
    assert "def _validate_candidate_artifact_snapshot(" not in source
    assert "def _validate_candidate_artifact(" not in source
    assert "def _candidate_artifact_ref(" not in source
    assert "CANDIDATE_ARTIFACT_TYPES = (" not in source


def test_store_delegates_row_and_json_conversion():
    source = STORE.read_text(encoding="utf-8")

    assert "from .store_rows import" in source
    assert "def _json(" not in source
    assert "def _load_json(" not in source
    assert "def _run_row(" not in source
    assert "def _case_to_row(" not in source
    assert "def _case_row(" not in source
    assert "def _frozen_input_row(" not in source
    assert "def _replay_row(" not in source
    assert "def _not_run_replay_result(" not in source
    assert "def _score_row(" not in source


def test_promotion_artifact_validation_module_is_explicit():
    assert (EVAL_PACKAGE / "promotion_artifact_validation.py").exists()


def test_candidate_artifact_validation_module_is_explicit():
    assert (EVAL_PACKAGE / "candidate_artifact_validation.py").exists()


def test_store_rows_module_is_explicit():
    assert (EVAL_PACKAGE / "store_rows.py").exists()


def test_store_schema_module_is_explicit():
    assert (EVAL_PACKAGE / "store_schema.py").exists()


def test_store_delegates_schema_initialization():
    source = STORE.read_text(encoding="utf-8")

    assert "from .store_schema import init_eval_store_schema" in source
    assert "init_eval_store_schema(conn)" in source
    assert "CREATE TABLE IF NOT EXISTS" not in source
    assert "def _ensure_columns(" not in source


def test_store_rows_contract_is_store_independent():
    source = (EVAL_PACKAGE / "store_rows.py").read_text(encoding="utf-8")

    assert "import sqlite3" not in source
    assert "EvalStore" not in source
    assert "workflow" not in source
    assert "journal" not in source
    assert "crypto_manual_alert.notification" not in source


def test_candidate_artifact_consistency_reuses_validation_artifact_types():
    source = (EVAL_PACKAGE / "candidate_artifact_consistency.py").read_text(encoding="utf-8")

    assert "from .candidate_artifact_validation import CANDIDATE_ARTIFACT_TYPES" in source
    assert "CANDIDATE_ARTIFACT_TYPES = [" not in source


def test_promotion_artifact_validation_contract_is_store_independent():
    source = (EVAL_PACKAGE / "promotion_artifact_validation.py").read_text(encoding="utf-8")

    assert "artifact: Any" in source
    assert "import sqlite3" not in source
    assert "EvalStore" not in source
    assert "workflow" not in source
    assert "journal" not in source
    assert "crypto_manual_alert.notification" not in source
    assert "from .notification" not in source


def test_candidate_artifact_validation_contract_is_store_independent():
    source = (EVAL_PACKAGE / "candidate_artifact_validation.py").read_text(encoding="utf-8")

    assert "import sqlite3" not in source
    assert "EvalStore" not in source
    assert "workflow" not in source
    assert "journal" not in source
    assert "crypto_manual_alert.notification" not in source
    assert "from .notification" not in source
