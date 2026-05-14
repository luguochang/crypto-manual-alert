from __future__ import annotations

import json
import sqlite3
from typing import Any

from crypto_manual_alert.storage.agent_audit_view import build_agent_audit_view


def load_json(text: str | None) -> Any:
    if not text:
        return None
    return json.loads(text)


def find_plan_run_for_trace(conn: sqlite3.Connection, trace: sqlite3.Row) -> sqlite3.Row | None:
    final_plan_id = trace["final_plan_id"]
    if final_plan_id:
        row = conn.execute("SELECT * FROM plan_runs WHERE plan_id = ?", (final_plan_id,)).fetchone()
        if row:
            return row
    for row in conn.execute("SELECT * FROM plan_runs ORDER BY created_at DESC").fetchall():
        payload = load_json(row["payload_json"])
        if isinstance(payload, dict) and payload.get("trace_id") == trace["trace_id"]:
            return row
    return None


def plan_payload(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    payload = load_json(row["payload_json"])
    return payload if isinstance(payload, dict) else {}


def plan_run_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = plan_payload(row)
    public = {
        "plan_id": row["plan_id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "trace_id": payload.get("trace_id"),
        "parsed_plan": payload.get("parsed_plan"),
        "verdict": payload.get("verdict"),
        "redaction": payload.get("redaction"),
        "agent_audit_view": build_agent_audit_view(payload),
        "payload_keys": sorted(key for key in payload if key != "raw_decision"),
    }
    return {key: value for key, value in public.items() if value is not None}


def plan_analysis(row: sqlite3.Row | None) -> dict[str, Any]:
    analysis = plan_payload(row).get("analysis")
    return analysis if isinstance(analysis, dict) else {}


def trace_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["allowed"] = None if data.get("allowed") is None else bool(data["allowed"])
    data["metadata"] = load_json(data.pop("metadata_json"))
    return data


def span_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["input_summary"] = load_json(data.pop("input_summary_json"))
    data["output_summary"] = load_json(data.pop("output_summary_json"))
    data["metadata"] = load_json(data.pop("metadata_json"))
    return data


def llm_row(row: sqlite3.Row, include_payloads: bool) -> dict[str, Any]:
    data = dict(row)
    data["input_summary"] = load_json(data.pop("input_summary_json"))
    data["output_summary"] = load_json(data.pop("output_summary_json"))
    data["metadata"] = load_json(data.pop("metadata_json"))
    if not include_payloads:
        data.pop("request_json", None)
        data.pop("response_json", None)
    return data


def badcase_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["summary"] = data.get("summary") or data.get("comment") or ""
    if "input_ref_json" in data:
        data["input_ref"] = load_json(data.pop("input_ref_json"))
    if "evidence_refs_json" in data:
        data["evidence_refs"] = load_json(data.pop("evidence_refs_json"))
    data["metadata"] = load_json(data.pop("metadata_json"))
    return data
