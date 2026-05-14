from __future__ import annotations

import sqlite3


def init_journal_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_locks (
            name TEXT PRIMARY KEY,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_runs (
            plan_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ok INTEGER NOT NULL,
            status_code INTEGER,
            error TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            outcome TEXT NOT NULL,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            trace_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            ended_at TEXT,
            run_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            horizon TEXT,
            status TEXT NOT NULL,
            final_plan_id TEXT,
            final_action TEXT,
            allowed INTEGER,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_spans (
            span_id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            parent_span_id TEXT,
            span_name TEXT NOT NULL,
            span_type TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            status TEXT NOT NULL,
            input_summary_json TEXT NOT NULL,
            output_summary_json TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            span_id TEXT,
            created_at TEXT NOT NULL,
            event_name TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            data_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            span_id TEXT,
            created_at TEXT NOT NULL,
            component TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            endpoint TEXT,
            status TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            output_hash TEXT NOT NULL,
            input_summary_json TEXT NOT NULL,
            output_summary_json TEXT NOT NULL,
            request_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            duration_ms INTEGER,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            cost_usd REAL,
            finish_reason TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL
        )
        """
    )
    _ensure_columns(
        conn,
        "llm_interactions",
        {
            "duration_ms": "INTEGER",
            "prompt_tokens": "INTEGER",
            "completion_tokens": "INTEGER",
            "total_tokens": "INTEGER",
            "cost_usd": "REAL",
            "finish_reason": "TEXT",
            "retry_count": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS badcases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            plan_id TEXT,
            span_id TEXT,
            llm_interaction_id INTEGER,
            created_at TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'developer',
            summary TEXT,
            comment TEXT NOT NULL,
            expected_behavior TEXT,
            actual_behavior TEXT,
            input_snapshot_hash TEXT,
            input_ref_json TEXT NOT NULL DEFAULT '{}',
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            eval_dataset_name TEXT,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    _ensure_columns(
        conn,
        "badcases",
        {
            "plan_id": "TEXT",
            "source": "TEXT NOT NULL DEFAULT 'developer'",
            "summary": "TEXT",
            "expected_behavior": "TEXT",
            "actual_behavior": "TEXT",
            "input_snapshot_hash": "TEXT",
            "input_ref_json": "TEXT NOT NULL DEFAULT '{}'",
            "evidence_refs_json": "TEXT NOT NULL DEFAULT '[]'",
            "eval_dataset_name": "TEXT",
        },
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_spans_trace_id ON trace_spans(trace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_interactions_trace_id ON llm_interactions(trace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_badcases_trace_id ON badcases(trace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_badcases_plan_id ON badcases(plan_id)")


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
