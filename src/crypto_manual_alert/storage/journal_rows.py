from __future__ import annotations

import json
import re
import sqlite3
from typing import TYPE_CHECKING, Any

from crypto_manual_alert.storage.business_summary import build_business_summary, safe_llm_completion_excerpt
from crypto_manual_alert.storage.agent_audit_view import build_agent_audit_view

if TYPE_CHECKING:
    from crypto_manual_alert.config.models import Config


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


def notification_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    ok = bool(row["ok"])
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "channel": "bark",
        "ok": ok,
        "status": "sent" if ok else "failed",
        "status_code": row["status_code"],
        "error": _redact_notification_error(row["error"]),
    }


def _redact_notification_error(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    text = re.sub(r"https?://[^\s]+", "<redacted-url>", text)
    text = re.sub(r"(?i)\bAuthorization\s*:\s*Bearer\s+[^\s,;}\]]+", "Authorization: Bearer <redacted>", text)
    text = re.sub(r"(?i)\b(?:device\s+key|bark\s+key)\s+[^\s,;}\]]+", "<redacted-secret>", text)
    text = re.sub(
        r"(?i)[\"']?\b(?:api[_-]?key|token|secret|device[_-]?key|bark[_-]?key|bark[_-]?device[_-]?key)\b[\"']?\s*[:=]\s*[\"']?[^\"'\s,;}\]]+[\"']?",
        "<redacted-secret>",
        text,
    )
    text = re.sub(r"(?i)\bBARK_DEVICE_KEY\b", "notification secret", text)
    text = re.sub(r"(?i)\b(?:device[_-]?key|bark[_-]?key|bark[_-]?device[_-]?key)\b", "notification secret", text)
    return text


def plan_run_row(
    row: sqlite3.Row,
    notification: dict[str, Any] | None = None,
    llm_interactions: list[sqlite3.Row] | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    payload = plan_payload(row)
    summary_payload = dict(payload)
    llm_summary = _llm_summary(llm_interactions or [])
    if llm_summary:
        summary_payload["llm_summary"] = llm_summary
    public = {
        "plan_id": row["plan_id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "trace_id": payload.get("trace_id"),
        "parsed_plan": payload.get("parsed_plan"),
        "verdict": payload.get("verdict"),
        "redaction": payload.get("redaction"),
        "facts_gate": payload.get("facts_gate"),
        "production_control_gate": payload.get("production_control_gate"),
        "run_context": payload.get("run_context"),
        "final_input_selection": payload.get("final_input_selection"),
        "main_path_contract": payload.get("main_path_contract"),
        "legacy_prompt_lifecycle": payload.get("legacy_prompt_lifecycle"),
        "business_summary": build_business_summary(
            plan=payload.get("parsed_plan") if isinstance(payload.get("parsed_plan"), dict) else {},
            verdict=payload.get("verdict") if isinstance(payload.get("verdict"), dict) else {},
            config=config,
            payload=summary_payload,
            notification=notification,
        ),
        "agent_audit_view": build_agent_audit_view(payload),
        "payload_keys": sorted(key for key in payload if key != "raw_decision"),
    }
    return {key: value for key, value in public.items() if value is not None}


def _llm_summary(rows: list[sqlite3.Row]) -> dict[str, Any] | None:
    for row in reversed(rows):
        data = dict(row)
        provider = str(data.get("provider") or "")
        if not provider:
            continue
        output_summary = load_json(data.get("output_summary_json"))
        return {
            "has_real_llm": provider != "fixture",
            "provider": provider,
            "model": data.get("model"),
            "status": data.get("status"),
            "duration_ms": data.get("duration_ms"),
            "total_tokens": data.get("total_tokens"),
            "finish_reason": data.get("finish_reason"),
            "output_summary": output_summary,
            "completion_excerpt": _completion_excerpt_from_llm_data(data, output_summary=output_summary),
        }
    return None


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
    data["completion_excerpt"] = _completion_excerpt_from_llm_data(data, output_summary=data["output_summary"])
    if not include_payloads:
        data.pop("request_json", None)
        data.pop("response_json", None)
    return data


def _completion_excerpt_from_llm_data(data: dict[str, Any], *, output_summary: Any | None = None) -> str | None:
    excerpt = safe_llm_completion_excerpt(output_summary)
    if excerpt:
        return excerpt
    response_payload = load_json(data.get("response_json"))
    return safe_llm_completion_excerpt(response_payload)


def badcase_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["summary"] = data.get("summary") or data.get("comment") or ""
    if "input_ref_json" in data:
        data["input_ref"] = load_json(data.pop("input_ref_json"))
    if "evidence_refs_json" in data:
        data["evidence_refs"] = load_json(data.pop("evidence_refs_json"))
    data["metadata"] = load_json(data.pop("metadata_json"))
    return data
