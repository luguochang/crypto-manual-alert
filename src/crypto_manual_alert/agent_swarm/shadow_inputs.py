from __future__ import annotations

from typing import Any

from crypto_manual_alert.artifacts.orchestration_inputs import build_audit_artifacts
from crypto_manual_alert.domain import MarketSnapshot
from crypto_manual_alert.research_pipeline import ResearchAudit


def build_shadow_audit_payload(
    *,
    trace_id: str,
    snapshot: MarketSnapshot | None,
    research_audit: ResearchAudit | None,
    audit_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return audit_payload or build_audit_artifacts(
        trace_id=trace_id,
        snapshot=snapshot,
        research_audit=research_audit,
    )


def build_shadow_worker_input_view(
    *,
    snapshot: MarketSnapshot | None,
    research_audit: ResearchAudit | None,
    audit_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "snapshot": _safe_worker_payload(snapshot.to_public_dict()) if snapshot else None,
        "research": _safe_worker_payload(research_audit.to_prompt_dict()) if research_audit else None,
        "facts_gate": audit_payload["facts_gate"],
        "evidence_packets": _safe_worker_payload(audit_payload["evidence_packets"]),
    }


def _safe_worker_payload(value: Any, *, path: str = "worker_input") -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if "snippet" in key_text.lower():
                safe[key_text] = f"{child_path}.redacted"
            elif key_text == "claims" and isinstance(item, list):
                safe[key_text] = [
                    f"{child_path}[{index}].redacted" for index, _claim in enumerate(item)
                ]
            elif key_text == "value" and _contains_snippet_payload(item):
                safe[key_text] = f"{child_path}.redacted"
            else:
                safe[key_text] = _safe_worker_payload(item, path=child_path)
        return safe
    if isinstance(value, list):
        return [_safe_worker_payload(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    return value


def _contains_snippet_payload(value: Any) -> bool:
    if isinstance(value, dict):
        return any("snippet" in str(key).lower() or _contains_snippet_payload(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_snippet_payload(item) for item in value)
    return False
