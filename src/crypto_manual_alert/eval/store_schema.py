from __future__ import annotations

import sqlite3


def init_eval_store_schema(conn: sqlite3.Connection) -> None:
    """Create and migrate tables for the independent eval sidecar store."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_cases (
            case_id TEXT PRIMARY KEY,
            dataset_name TEXT NOT NULL,
            source_trace_id TEXT NOT NULL,
            source_badcase_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            symbol TEXT NOT NULL,
            horizon TEXT,
            failure_category TEXT NOT NULL,
            severity TEXT NOT NULL,
            expected_behavior TEXT NOT NULL,
            actual_behavior TEXT NOT NULL,
            summary TEXT NOT NULL,
            status TEXT NOT NULL,
            frozen_input_hash TEXT NOT NULL,
            input_summary_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_runs (
            eval_run_id TEXT PRIMARY KEY,
            dataset_name TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            case_count INTEGER NOT NULL,
            pass_count INTEGER NOT NULL,
            fail_count INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_run_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eval_run_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_scores (
            score_id TEXT PRIMARY KEY,
            eval_run_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            source_trace_id TEXT NOT NULL DEFAULT '',
            source_badcase_id INTEGER NOT NULL DEFAULT 0,
            judge_name TEXT NOT NULL,
            judge_type TEXT NOT NULL,
            score REAL,
            passed INTEGER NOT NULL,
            severity TEXT NOT NULL,
            failure_category TEXT NOT NULL,
            reason_summary TEXT NOT NULL,
            evidence_refs_json TEXT NOT NULL,
            needs_human_review INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_frozen_inputs (
            frozen_input_hash TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            kind TEXT NOT NULL,
            source_trace_id TEXT NOT NULL,
            source_badcase_id INTEGER NOT NULL,
            input_json TEXT NOT NULL,
            public_summary_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_replay_outputs (
            replay_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            source_trace_id TEXT NOT NULL,
            source_badcase_id INTEGER NOT NULL,
            frozen_input_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            mode TEXT NOT NULL,
            final_action TEXT,
            allowed INTEGER,
            output_hash TEXT,
            reason_summary TEXT,
            error_message TEXT,
            duration_ms INTEGER,
            output_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_promotion_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eval_run_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_ref TEXT NOT NULL,
            artifact_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(eval_run_id, artifact_type)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_candidate_artifacts (
            case_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_ref TEXT NOT NULL,
            artifact_hash TEXT NOT NULL,
            artifact_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(case_id, artifact_type)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_cases_dataset ON eval_cases(dataset_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_run_cases_run ON eval_run_cases(eval_run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_scores_run ON eval_scores(eval_run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_replay_outputs_case ON eval_replay_outputs(case_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_promotion_artifacts_run "
        "ON eval_promotion_artifacts(eval_run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_candidate_artifacts_case "
        "ON eval_candidate_artifacts(case_id)"
    )
    _ensure_columns(
        conn,
        "eval_scores",
        {
            "source_trace_id": "TEXT NOT NULL DEFAULT ''",
            "source_badcase_id": "INTEGER NOT NULL DEFAULT 0",
        },
    )


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
