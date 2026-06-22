from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from crypto_manual_alert.decision.frozen_input import stable_hash

from .candidate_artifact_validation import (
    CANDIDATE_ARTIFACT_TYPES,
    candidate_artifact_ref,
    validate_candidate_artifact,
    validate_candidate_artifact_snapshot,
)
from .promotion_artifact_validation import validate_promotion_artifact
from .schema import EvalCase, EvalFrozenInput, EvalReplayOutput, EvalRun, EvalScore
from .store_schema import init_eval_store_schema
from .store_rows import (
    case_row,
    case_to_row,
    dump_json,
    frozen_input_row,
    load_json,
    not_run_replay_result,
    replay_row,
    run_row,
    score_row,
)


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
            init_eval_store_schema(conn)

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
                        dump_json(case.input_summary),
                        dump_json(case.metadata),
                    ),
                )
                _insert_candidate_artifacts(conn, case.case_id, case.input_summary)

    def upsert_frozen_inputs(self, frozen_inputs: list[EvalFrozenInput]) -> None:
        with self.connect() as conn:
            for frozen in frozen_inputs:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO eval_frozen_inputs (
                        frozen_input_hash, schema_version, kind, source_trace_id,
                        source_badcase_id, input_json, public_summary_json, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        frozen.frozen_input_hash,
                        frozen.schema_version,
                        frozen.kind,
                        frozen.source_trace_id,
                        frozen.source_badcase_id,
                        dump_json(frozen.input_payload),
                        dump_json(frozen.public_summary),
                        dump_json(frozen.metadata),
                    ),
                )

    def get_frozen_input(self, frozen_input_hash: str) -> EvalFrozenInput | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM eval_frozen_inputs WHERE frozen_input_hash = ?",
                (frozen_input_hash,),
            ).fetchone()
        return frozen_input_row(row) if row else None

    def get_case(self, case_id: str) -> EvalCase | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM eval_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        return case_row(row) if row else None

    def insert_replay_output(self, output: EvalReplayOutput) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_replay_outputs (
                    replay_id, case_id, source_trace_id, source_badcase_id,
                    frozen_input_hash, status, mode, final_action, allowed,
                    output_hash, reason_summary, error_message, duration_ms,
                    output_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    output.replay_id,
                    output.case_id,
                    output.source_trace_id,
                    output.source_badcase_id,
                    output.frozen_input_hash,
                    output.status,
                    output.mode,
                    output.final_action,
                    None if output.allowed is None else (1 if output.allowed else 0),
                    output.output_hash,
                    output.reason_summary,
                    output.error_message,
                    output.duration_ms,
                    dump_json(output.output_payload),
                    dump_json(output.metadata),
                ),
            )

    def get_replay_output(self, case_id: str, *, mode: str | None = None) -> dict[str, Any] | None:
        where = "case_id = ?"
        params: tuple[Any, ...] = (case_id,)
        if mode is not None:
            where = "case_id = ? AND mode = ?"
            params = (case_id, mode)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM eval_replay_outputs
                WHERE {where}
                ORDER BY created_at DESC, replay_id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return replay_row(row) if row else None

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
                    dump_json(run.metadata),
                ),
            )
            for case in cases:
                conn.execute(
                    """
                    INSERT INTO eval_run_cases (eval_run_id, case_id, case_json)
                    VALUES (?, ?, ?)
                    """,
                    (run.eval_run_id, case.case_id, dump_json(case_to_row(case))),
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
                        dump_json(score.evidence_refs),
                        1 if score.needs_human_review else 0,
                        dump_json(score.metadata),
                    ),
                )
            _insert_promotion_artifacts(
                conn,
                run.eval_run_id,
                run.metadata.get("promotion_artifacts") if isinstance(run.metadata, dict) else None,
            )

    def upsert_promotion_artifacts(self, eval_run_id: str, artifacts: dict[str, dict[str, Any]]) -> None:
        with self.connect() as conn:
            _insert_promotion_artifacts(conn, eval_run_id, artifacts)

    def get_promotion_artifacts(self, eval_run_id: str) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT artifact_type, artifact_json
                FROM eval_promotion_artifacts
                WHERE eval_run_id = ?
                ORDER BY artifact_type ASC
                """,
                (eval_run_id,),
            ).fetchall()
        artifacts: dict[str, dict[str, Any]] = {}
        for row in rows:
            artifact = load_json(row["artifact_json"]) or {}
            if isinstance(artifact, dict):
                artifacts[str(row["artifact_type"])] = artifact
        return artifacts

    def get_candidate_artifacts(
        self,
        case_id: str,
        *,
        include_store_metadata: bool = False,
    ) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT artifact_type, artifact_hash, artifact_json
                FROM eval_candidate_artifacts
                WHERE case_id = ?
                ORDER BY artifact_type ASC
                """,
                (case_id,),
            ).fetchall()
        artifacts: dict[str, dict[str, Any]] = {}
        for row in rows:
            artifact = load_json(row["artifact_json"]) or {}
            if isinstance(artifact, dict):
                if include_store_metadata:
                    artifact = dict(artifact)
                    artifact["stored_artifact_hash"] = str(row["artifact_hash"])
                artifacts[str(row["artifact_type"])] = artifact
        return artifacts

    def get_candidate_artifact_hash(self, case_id: str, artifact_type: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT artifact_hash
                FROM eval_candidate_artifacts
                WHERE case_id = ? AND artifact_type = ?
                """,
                (case_id, artifact_type),
            ).fetchone()
        return str(row["artifact_hash"]) if row else None

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
        return [run_row(row) for row in rows]

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
            replay_rows = conn.execute(
                """
                SELECT *
                FROM eval_replay_outputs
                WHERE case_id IN (
                    SELECT case_id FROM eval_run_cases WHERE eval_run_id = ?
                )
                ORDER BY created_at DESC
                """,
                (eval_run_id,),
            ).fetchall()
        replay_by_case: dict[str, dict[str, Any]] = {}
        for row in replay_rows:
            replay = replay_row(row)
            replay_by_case.setdefault(str(replay["case_id"]), replay)
        case_payloads = []
        for row in cases:
            payload = load_json(row["case_json"])
            if isinstance(payload, dict):
                payload["replay_result"] = replay_by_case.get(str(payload.get("case_id"))) or not_run_replay_result(payload)
            case_payloads.append(payload)
        return {
            "run": run_row(run),
            "cases": case_payloads,
            "scores": [score_row(row) for row in scores],
        }


def _insert_promotion_artifacts(
    conn: sqlite3.Connection,
    eval_run_id: str,
    artifacts: dict[str, dict[str, Any]] | None,
) -> None:
    if not artifacts:
        return
    if not isinstance(artifacts, dict):
        raise ValueError("promotion artifacts must be a mapping")
    for artifact_type, artifact in artifacts.items():
        validate_promotion_artifact(eval_run_id, str(artifact_type), artifact)
        conn.execute(
            """
            INSERT INTO eval_promotion_artifacts (
                eval_run_id, artifact_type, artifact_ref, artifact_json
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(eval_run_id, artifact_type) DO UPDATE SET
                artifact_ref = excluded.artifact_ref,
                artifact_json = excluded.artifact_json
            """,
            (
                eval_run_id,
                str(artifact_type),
                str(artifact["artifact_ref"]),
                dump_json(artifact),
            ),
        )


def _insert_candidate_artifacts(
    conn: sqlite3.Connection,
    case_id: str,
    input_summary: dict[str, Any],
) -> None:
    if not isinstance(input_summary, dict):
        return
    candidate_audit = input_summary.get("candidate_audit")
    if not isinstance(candidate_audit, dict):
        return
    snapshot = candidate_audit.get("artifact_snapshot")
    if not isinstance(snapshot, dict):
        return
    validate_candidate_artifact_snapshot(snapshot)
    for artifact_type in CANDIDATE_ARTIFACT_TYPES:
        artifact = snapshot.get(artifact_type)
        if not isinstance(artifact, dict):
            continue
        validate_candidate_artifact(case_id, artifact_type, artifact)
        artifact_ref = candidate_artifact_ref(artifact)
        conn.execute(
            """
            INSERT OR REPLACE INTO eval_candidate_artifacts (
                case_id, artifact_type, artifact_ref, artifact_hash, artifact_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_id,
                artifact_type,
                artifact_ref,
                stable_hash(artifact),
                dump_json(artifact),
            ),
        )
