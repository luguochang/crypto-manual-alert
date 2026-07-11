from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .outcomes import DecisionOutcome, outcome_from_public_dict


class OutcomeStore:
    """Independent SQLite store for offline decision outcomes."""

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
                CREATE TABLE IF NOT EXISTS eval_decision_outcomes (
                    decision_ref TEXT NOT NULL,
                    evaluation_target TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    window_name TEXT NOT NULL,
                    outcome_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (decision_ref, evaluation_target, window_name)
                )
                """
            )
            _ensure_multi_window_primary_key(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_eval_decision_outcomes_target
                ON eval_decision_outcomes(evaluation_target)
                """
            )

    def upsert_outcomes(self, outcomes: list[DecisionOutcome]) -> None:
        with self.connect() as conn:
            for outcome in outcomes:
                conn.execute(
                    """
                    INSERT INTO eval_decision_outcomes (
                        decision_ref, evaluation_target, symbol, window_name, outcome_json
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(decision_ref, evaluation_target, window_name) DO UPDATE SET
                        evaluation_target = excluded.evaluation_target,
                        symbol = excluded.symbol,
                        window_name = excluded.window_name,
                        outcome_json = excluded.outcome_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        outcome.decision_ref,
                        outcome.evaluation_target,
                        outcome.symbol,
                        outcome.window.name,
                        json.dumps(outcome.to_public_dict(), ensure_ascii=False, sort_keys=True),
                    ),
                )

    def list_outcomes(self, *, evaluation_target: str | None = None) -> list[DecisionOutcome]:
        where = ""
        params: tuple[str, ...] = ()
        if evaluation_target is not None:
            where = "WHERE evaluation_target = ?"
            params = (evaluation_target,)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT outcome_json
                FROM eval_decision_outcomes
                {where}
                ORDER BY decision_ref ASC, window_name ASC
                """,
                params,
            ).fetchall()
        outcomes: list[DecisionOutcome] = []
        for row in rows:
            payload = json.loads(str(row["outcome_json"]))
            if isinstance(payload, dict):
                outcomes.append(outcome_from_public_dict(payload))
        return outcomes

    def list_outcomes_by_decision_refs(self, decision_refs: list[str]) -> list[DecisionOutcome]:
        """Return outcomes for exact decision refs in stable target/window order."""

        refs = sorted({ref for ref in decision_refs if ref})
        if not refs:
            return []
        placeholders = ", ".join("?" for _ in refs)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT outcome_json
                FROM eval_decision_outcomes
                WHERE decision_ref IN ({placeholders})
                ORDER BY decision_ref ASC, evaluation_target ASC, window_name ASC
                """,
                tuple(refs),
            ).fetchall()
        outcomes: list[DecisionOutcome] = []
        for row in rows:
            payload = json.loads(str(row["outcome_json"]))
            if isinstance(payload, dict):
                outcomes.append(outcome_from_public_dict(payload))
        return outcomes


def _ensure_multi_window_primary_key(conn: sqlite3.Connection) -> None:
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(eval_decision_outcomes)").fetchall()]
    primary_keys = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(eval_decision_outcomes)").fetchall()
        if int(row["pk"] or 0) > 0
    ]
    if primary_keys != ["decision_ref"] or "window_name" not in columns:
        return
    conn.execute("ALTER TABLE eval_decision_outcomes RENAME TO eval_decision_outcomes_legacy")
    conn.execute(
        """
        CREATE TABLE eval_decision_outcomes (
            decision_ref TEXT NOT NULL,
            evaluation_target TEXT NOT NULL,
            symbol TEXT NOT NULL,
            window_name TEXT NOT NULL,
            outcome_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (decision_ref, evaluation_target, window_name)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO eval_decision_outcomes (
            decision_ref, evaluation_target, symbol, window_name, outcome_json, updated_at
        )
        SELECT decision_ref, evaluation_target, symbol, window_name, outcome_json, updated_at
        FROM eval_decision_outcomes_legacy
        """
    )
    conn.execute("DROP TABLE eval_decision_outcomes_legacy")
