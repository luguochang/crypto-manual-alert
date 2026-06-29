from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .schema import EvalCase, EvalRun, EvalScore


class EvalStore:
    """独立 eval SQLite 存储，避免测评结果污染生产 journal 表。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_cases_dataset ON eval_cases(dataset_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_run_cases_run ON eval_run_cases(eval_run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_scores_run ON eval_scores(eval_run_id)")
            _ensure_columns(
                conn,
                "eval_scores",
                {
                    "source_trace_id": "TEXT NOT NULL DEFAULT ''",
                    "source_badcase_id": "INTEGER NOT NULL DEFAULT 0",
                },
            )

    def upsert_cases(self, cases: list[EvalCase]) -> None:
        with self.connect() as conn:
            for case in cases:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO eval_cases (
                        case_id, dataset_name, source_trace_id, source_badcase_id,
                        created_at, symbol, horizon, failure_category, severity,
                        expected_behavior, actual_behavior, summary, status,
                        frozen_input_hash, input_summary_json, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case.case_id,
                        case.dataset_name,
                        case.source_trace_id,
                        case.source_badcase_id,
                        case.created_at,
                        case.symbol,
                        case.horizon,
                        case.failure_category,
                        case.severity,
                        case.expected_behavior,
                        case.actual_behavior,
                        case.summary,
                        case.status,
                        case.frozen_input_hash,
                        _json(case.input_summary),
                        _json(case.metadata),
                    ),
                )

    def insert_run(self, run: EvalRun, cases: list[EvalCase], scores: list[EvalScore]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO eval_runs (
                    eval_run_id, dataset_name, mode, status, started_at, ended_at,
                    case_count, pass_count, fail_count, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.eval_run_id,
                    run.dataset_name,
                    run.mode,
                    run.status,
                    run.started_at,
                    run.ended_at,
                    run.case_count,
                    run.pass_count,
                    run.fail_count,
                    _json(run.metadata),
                ),
            )
            for case in cases:
                conn.execute(
                    """
                    INSERT INTO eval_run_cases (eval_run_id, case_id, case_json)
                    VALUES (?, ?, ?)
                    """,
                    (run.eval_run_id, case.case_id, _json(_case_to_row(case))),
                )
            for score in scores:
                conn.execute(
                    """
                    INSERT INTO eval_scores (
                        score_id, eval_run_id, case_id, source_trace_id, source_badcase_id,
                        judge_name, judge_type, score,
                        passed, severity, failure_category, reason_summary,
                        evidence_refs_json, needs_human_review, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        score.score_id,
                        score.eval_run_id,
                        score.case_id,
                        score.source_trace_id,
                        score.source_badcase_id,
                        score.judge_name,
                        score.judge_type,
                        score.score,
                        1 if score.passed else 0,
                        score.severity,
                        score.failure_category,
                        score.reason_summary,
                        _json(score.evidence_refs),
                        1 if score.needs_human_review else 0,
                        _json(score.metadata),
                    ),
                )

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM eval_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [_run_row(row) for row in rows]

    def get_run_detail(self, eval_run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            run = conn.execute("SELECT * FROM eval_runs WHERE eval_run_id = ?", (eval_run_id,)).fetchone()
            if run is None:
                return None
            scores = conn.execute(
                """
                SELECT *
                FROM eval_scores
                WHERE eval_run_id = ?
                ORDER BY case_id ASC, judge_name ASC
                """,
                (eval_run_id,),
            ).fetchall()
            cases = conn.execute(
                """
                SELECT case_json
                FROM eval_run_cases
                WHERE eval_run_id = ?
                ORDER BY id ASC
                """,
                (eval_run_id,),
            ).fetchall()
        return {
            "run": _run_row(run),
            "cases": [_load_json(row["case_json"]) for row in cases],
            "scores": [_score_row(row) for row in scores],
        }


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _load_json(text: str | None) -> Any:
    if not text:
        return None
    return json.loads(text)


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = _load_json(data.pop("metadata_json"))
    return data


def _case_to_row(case: EvalCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "dataset_name": case.dataset_name,
        "source_trace_id": case.source_trace_id,
        "source_badcase_id": case.source_badcase_id,
        "created_at": case.created_at,
        "symbol": case.symbol,
        "horizon": case.horizon,
        "failure_category": case.failure_category,
        "severity": case.severity,
        "expected_behavior": case.expected_behavior,
        "actual_behavior": case.actual_behavior,
        "summary": case.summary,
        "status": case.status,
        "frozen_input_hash": case.frozen_input_hash,
        "input_summary": case.input_summary,
        "metadata": case.metadata,
    }


def _score_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["passed"] = bool(data["passed"])
    data["needs_human_review"] = bool(data["needs_human_review"])
    data["evidence_refs"] = _load_json(data.pop("evidence_refs_json")) or []
    data["metadata"] = _load_json(data.pop("metadata_json"))
    return data
