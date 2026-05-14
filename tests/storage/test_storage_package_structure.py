from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_storage_journal_canonical_path_is_available():
    from crypto_manual_alert.storage.journal import Journal

    assert Journal.__name__ == "Journal"


def test_storage_journal_schema_has_canonical_module():
    schema_module = Path("src/crypto_manual_alert/storage/journal_schema.py")
    journal_source = Path("src/crypto_manual_alert/storage/journal.py").read_text(encoding="utf-8")

    assert schema_module.exists()
    assert "from crypto_manual_alert.storage.journal_schema import init_journal_schema" in journal_source
    assert "init_journal_schema(conn)" in journal_source
    assert "CREATE TABLE IF NOT EXISTS" not in journal_source
    assert "ALTER TABLE" not in journal_source
    assert "CREATE INDEX IF NOT EXISTS" not in journal_source


def test_storage_journal_rows_have_canonical_module():
    rows_module = Path("src/crypto_manual_alert/storage/journal_rows.py")
    journal_source = Path("src/crypto_manual_alert/storage/journal.py").read_text(encoding="utf-8")

    assert rows_module.exists()
    assert "from crypto_manual_alert.storage.journal_rows import" in journal_source
    for helper_name in (
        "_load_json",
        "_find_plan_run_for_trace",
        "_plan_payload",
        "_plan_run_row",
        "_plan_analysis",
        "_trace_row",
        "_span_row",
        "_llm_row",
        "_badcase_row",
    ):
        assert f"def {helper_name}(" not in journal_source


def test_storage_package_import_does_not_eagerly_import_implementation_modules():
    sys.modules.pop("crypto_manual_alert.storage", None)
    sys.modules.pop("crypto_manual_alert.storage.journal", None)
    sys.modules.pop("crypto_manual_alert.storage.journal_rows", None)
    sys.modules.pop("crypto_manual_alert.storage.journal_schema", None)
    sys.modules.pop("crypto_manual_alert.storage.query_repository", None)

    storage = importlib.import_module("crypto_manual_alert.storage")

    assert "crypto_manual_alert.storage.journal" not in sys.modules
    assert "crypto_manual_alert.storage.journal_rows" not in sys.modules
    assert "crypto_manual_alert.storage.journal_schema" not in sys.modules
    assert "crypto_manual_alert.storage.query_repository" not in sys.modules
    journal_module = importlib.import_module("crypto_manual_alert.storage.journal")
    query_repository_module = importlib.import_module("crypto_manual_alert.storage.query_repository")

    assert storage.Journal is journal_module.Journal
    assert storage.JournalQueryRepository is query_repository_module.JournalQueryRepository
