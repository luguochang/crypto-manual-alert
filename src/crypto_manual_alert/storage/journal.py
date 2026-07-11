from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from crypto_manual_alert.storage.journal_rows import (
    badcase_row as _badcase_row,
    find_plan_run_for_trace as _find_plan_run_for_trace,
    llm_row as _llm_row,
    load_json as _load_json,
    notification_row as _notification_row,
    plan_analysis as _plan_analysis,
    plan_payload as _plan_payload,
    plan_run_row as _plan_run_row,
    span_row as _span_row,
    trace_row as _trace_row,
)
from crypto_manual_alert.storage.journal_schema import init_journal_schema

if TYPE_CHECKING:
    from crypto_manual_alert.config.models import Config


BADCASE_SEVERITIES = {"low", "medium", "high", "critical"}
BADCASE_SOURCES = {"user", "developer", "auto", "evaluator"}


class Journal:
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
            init_journal_schema(conn)

    def append_plan_run(self, plan_id: str, status: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO plan_runs (plan_id, created_at, status, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (plan_id, _now_iso(), status, json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)),
            )

    def append_notification(self, plan_id: str, ok: bool, status_code: int | None, error: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO notifications (plan_id, created_at, ok, status_code, error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (plan_id, _now_iso(), 1 if ok else 0, status_code, error),
            )

    def get_latest_notification(self, plan_id: str | None) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _notification_row(_find_notification_for_plan(conn, plan_id))

    def record_outcome(self, plan_id: str, outcome: str, notes: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO manual_outcomes (plan_id, created_at, outcome, notes)
                VALUES (?, ?, ?, ?)
                """,
                (plan_id, _now_iso(), outcome, notes),
            )

    def append_trace(
        self,
        *,
        trace_id: str,
        created_at: str,
        run_type: str,
        symbol: str,
        horizon: str | None,
        status: str,
        metadata: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO traces (
                    trace_id, created_at, run_type, symbol, horizon, status, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (trace_id, created_at, run_type, symbol, horizon, status, _json(metadata)),
            )

    def finish_trace(
        self,
        *,
        trace_id: str,
        ended_at: str,
        status: str,
        final_plan_id: str | None,
        final_action: str | None,
        allowed: bool | None,
        metadata: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE traces
                SET ended_at = ?,
                    status = ?,
                    final_plan_id = ?,
                    final_action = ?,
                    allowed = ?,
                    metadata_json = ?
                WHERE trace_id = ?
                """,
                (
                    ended_at,
                    status,
                    final_plan_id,
                    final_action,
                    None if allowed is None else 1 if allowed else 0,
                    _json(metadata),
                    trace_id,
                ),
            )

    def append_trace_span(
        self,
        *,
        span_id: str,
        trace_id: str,
        parent_span_id: str | None,
        span_name: str,
        span_type: str,
        started_at: str,
        ended_at: str,
        duration_ms: int,
        status: str,
        input_summary: Any,
        output_summary: Any,
        error_type: str | None,
        error_message: str | None,
        metadata: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO trace_spans (
                    span_id, trace_id, parent_span_id, span_name, span_type,
                    started_at, ended_at, duration_ms, status,
                    input_summary_json, output_summary_json,
                    error_type, error_message, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span_id,
                    trace_id,
                    parent_span_id,
                    span_name,
                    span_type,
                    started_at,
                    ended_at,
                    duration_ms,
                    status,
                    _json(input_summary),
                    _json(output_summary),
                    error_type,
                    error_message,
                    _json(metadata),
                ),
            )

    def append_llm_interaction(
        self,
        *,
        trace_id: str,
        span_id: str | None = None,
        created_at: str,
        component: str,
        provider: str,
        model: str,
        endpoint: str,
        status: str,
        input_hash: str,
        output_hash: str,
        input_summary: Any,
        output_summary: Any,
        request_json: str,
        response_json: str,
        error_type: str | None,
        error_message: str | None,
        duration_ms: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
        finish_reason: str | None = None,
        retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_interactions (
                    trace_id, span_id, created_at, component, provider, model, endpoint, status,
                    input_hash, output_hash, input_summary_json, output_summary_json,
                    request_json, response_json, error_type, error_message,
                    duration_ms, prompt_tokens, completion_tokens, total_tokens,
                    cost_usd, finish_reason, retry_count, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    span_id,
                    created_at,
                    component,
                    provider,
                    model,
                    endpoint,
                    status,
                    input_hash,
                    output_hash,
                    _json(input_summary),
                    _json(output_summary),
                    request_json,
                    response_json,
                    error_type,
                    error_message,
                    duration_ms,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost_usd,
                    finish_reason,
                    retry_count,
                    _json(metadata or {}),
                ),
            )

    def list_traces(
        self,
        limit: int = 20,
        *,
        offset: int = 0,
        status: str | None = None,
        symbol: str | None = None,
        allowed: bool | None = None,
        include_business_summary: bool = False,
        projection_config: "Config | None" = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("t.status = ?")
            params.append(status)
        if symbol:
            clauses.append("LOWER(t.symbol) LIKE ?")
            params.append(f"%{symbol.lower()}%")
        if allowed is not None:
            clauses.append("t.allowed = ?")
            params.append(1 if allowed else 0)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    t.*,
                    (SELECT COUNT(*) FROM trace_spans s WHERE s.trace_id = t.trace_id) AS span_count,
                    (SELECT COUNT(*) FROM llm_interactions l WHERE l.trace_id = t.trace_id) AS llm_interaction_count
                FROM traces t
                {where}
                ORDER BY t.created_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
            if include_business_summary:
                return [_trace_summary_row(conn, row, projection_config=projection_config) for row in rows]
        return [_trace_row(row) for row in rows]

    def get_trace_detail(
        self,
        trace_id: str,
        include_payloads: bool = False,
        *,
        projection_config: "Config | None" = None,
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            trace = conn.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
            if trace is None:
                return None
            plan_run = _find_plan_run_for_trace(conn, trace)
            spans = conn.execute(
                """
                SELECT *
                FROM trace_spans
                WHERE trace_id = ?
                ORDER BY started_at ASC
                """,
                (trace_id,),
            ).fetchall()
            llm_interactions = conn.execute(
                """
                SELECT *
                FROM llm_interactions
                WHERE trace_id = ?
                ORDER BY created_at ASC
                """,
                (trace_id,),
            ).fetchall()
            badcases = conn.execute(
                """
                SELECT *
                FROM badcases
                WHERE trace_id = ?
                ORDER BY created_at DESC
                """,
                (trace_id,),
            ).fetchall()
            notification = _find_notification_for_plan(conn, plan_run["plan_id"] if plan_run else None)
            notification_history = _find_notifications_for_plan(conn, plan_run["plan_id"] if plan_run else None)
        notification_data = _notification_row(notification)
        return {
            "trace": _trace_row(trace),
            "plan_run": _plan_run_row(
                plan_run,
                notification=notification_data,
                llm_interactions=llm_interactions,
                config=projection_config,
            ) if plan_run else None,
            "analysis": _plan_analysis(plan_run) if plan_run else {},
            "spans": [_span_row(row) for row in spans],
            "llm_interactions": [_llm_row(row, include_payloads=include_payloads) for row in llm_interactions],
            "badcases": [_badcase_row(row) for row in badcases],
            "notification": notification_data or _notification_fallback(),
            "notification_history": [_notification_row(row) for row in notification_history],
        }

    def get_plan_run_payload(self, plan_id: str) -> dict[str, Any] | None:
        """内部读取完整 plan_run payload，供 eval sidecar 构建冻结输入使用。"""

        with self.connect() as conn:
            row = conn.execute("SELECT * FROM plan_runs WHERE plan_id = ?", (plan_id,)).fetchone()
        if row is None:
            return None
        return _plan_payload(row)

    def record_badcase(
        self,
        *,
        trace_id: str | None = None,
        plan_id: str | None = None,
        category: str,
        severity: str,
        summary: str | None = None,
        comment: str | None = None,
        span_id: str | None = None,
        llm_interaction_id: int | None = None,
        source: str = "developer",
        expected_behavior: str | None = None,
        actual_behavior: str | None = None,
        input_snapshot_hash: str | None = None,
        input_ref: dict[str, Any] | None = None,
        evidence_refs: list[Any] | None = None,
        eval_dataset_name: str | None = None,
        status: str = "open",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        if not trace_id and not plan_id:
            raise ValueError("trace_id or plan_id is required")
        if severity not in BADCASE_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(BADCASE_SEVERITIES))}")
        if source not in BADCASE_SOURCES:
            raise ValueError(f"source must be one of: {', '.join(sorted(BADCASE_SOURCES))}")
        clean_summary = (summary or comment or "").strip()
        if not clean_summary:
            raise ValueError("summary is required")
        with self.connect() as conn:
            resolved_trace_id = trace_id or _trace_id_for_plan(conn, str(plan_id))
            if not resolved_trace_id:
                raise ValueError(f"trace_id not found for plan_id: {plan_id}")
            if conn.execute("SELECT 1 FROM traces WHERE trace_id = ?", (resolved_trace_id,)).fetchone() is None:
                raise ValueError(f"trace_id not found: {resolved_trace_id}")
            if plan_id:
                _validate_plan_belongs_to_trace(conn, str(plan_id), resolved_trace_id)
            if span_id and conn.execute(
                "SELECT 1 FROM trace_spans WHERE span_id = ? AND trace_id = ?",
                (span_id, resolved_trace_id),
            ).fetchone() is None:
                raise ValueError(f"span_id does not belong to trace_id: {span_id}")
            if llm_interaction_id and conn.execute(
                "SELECT 1 FROM llm_interactions WHERE id = ? AND trace_id = ?",
                (llm_interaction_id, resolved_trace_id),
            ).fetchone() is None:
                raise ValueError(f"llm_interaction_id does not belong to trace_id: {llm_interaction_id}")
            cursor = conn.execute(
                """
                INSERT INTO badcases (
                    trace_id, plan_id, span_id, llm_interaction_id, created_at,
                    category, severity, source, summary, comment,
                    expected_behavior, actual_behavior, input_snapshot_hash,
                    input_ref_json, evidence_refs_json, eval_dataset_name,
                    status, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_trace_id,
                    plan_id,
                    span_id,
                    llm_interaction_id,
                    _now_iso(),
                    category,
                    severity,
                    source,
                    clean_summary,
                    comment or clean_summary,
                    expected_behavior,
                    actual_behavior,
                    input_snapshot_hash,
                    _json(input_ref or {}),
                    _json(evidence_refs or []),
                    eval_dataset_name,
                    status,
                    _json(metadata or {}),
                ),
            )
            return int(cursor.lastrowid)

    def list_badcases(
        self,
        limit: int = 20,
        *,
        ids: list[int] | None = None,
        dataset: str | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        clean_limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        if ids:
            placeholders = ", ".join("?" for _ in ids)
            clauses.append(f"id IN ({placeholders})")
            params.extend(int(item) for item in ids)
        if dataset:
            clauses.append("eval_dataset_name = ?")
            params.append(dataset)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM badcases
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*params, clean_limit),
            ).fetchall()
        return [_badcase_row(row) for row in rows]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace_summary_row(
    conn: sqlite3.Connection,
    trace: sqlite3.Row,
    *,
    projection_config: "Config | None" = None,
) -> dict[str, Any]:
    summary = _trace_row(trace)
    plan_run = _find_plan_run_for_trace(conn, trace)
    if plan_run is None:
        summary["business_summary"] = None
        summary["notification"] = _notification_fallback()
        return summary

    llm_interactions = conn.execute(
        """
        SELECT *
        FROM llm_interactions
        WHERE trace_id = ?
        ORDER BY created_at ASC
        """,
        (trace["trace_id"],),
    ).fetchall()
    notification = _notification_row(_find_notification_for_plan(conn, plan_run["plan_id"]))
    public_plan_run = _plan_run_row(
        plan_run,
        notification=notification,
        llm_interactions=llm_interactions,
        config=projection_config,
    )
    summary["business_summary"] = public_plan_run.get("business_summary")
    summary["notification"] = notification or _notification_fallback()
    return summary


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _trace_id_for_plan(conn: sqlite3.Connection, plan_id: str) -> str | None:
    trace = conn.execute("SELECT trace_id FROM traces WHERE final_plan_id = ?", (plan_id,)).fetchone()
    if trace:
        return str(trace["trace_id"])
    row = conn.execute("SELECT payload_json FROM plan_runs WHERE plan_id = ?", (plan_id,)).fetchone()
    if not row:
        return None
    payload = _load_json(row["payload_json"])
    if isinstance(payload, dict) and payload.get("trace_id"):
        return str(payload["trace_id"])
    return None


def _find_notification_for_plan(conn: sqlite3.Connection, plan_id: str | None) -> sqlite3.Row | None:
    if not plan_id:
        return None
    return conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE plan_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (plan_id,),
    ).fetchone()


def _find_notifications_for_plan(conn: sqlite3.Connection, plan_id: str | None) -> list[sqlite3.Row]:
    if not plan_id:
        return []
    return conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE plan_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (plan_id,),
    ).fetchall()


def _notification_fallback() -> dict[str, Any]:
    return {
        "enabled": False,
        "channel": None,
        "status": "not_recorded",
        "message": "通知状态未记录。",
    }


def _validate_plan_belongs_to_trace(conn: sqlite3.Connection, plan_id: str, trace_id: str) -> None:
    resolved_trace_id = _trace_id_for_plan(conn, plan_id)
    if not resolved_trace_id:
        raise ValueError(f"plan_id not found: {plan_id}")
    if resolved_trace_id != trace_id:
        raise ValueError(f"plan_id does not belong to trace_id: {plan_id}")
