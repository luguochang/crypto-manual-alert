from __future__ import annotations

from typing import Any


def project_release_eval_gate(payload: dict[str, Any]) -> dict[str, Any]:
    structural = _mapping(payload.get("final_decision_switch_readiness"))
    production_control = _mapping(payload.get("production_control_gate"))
    financial_quality = _mapping(payload.get("financial_quality_gate"))
    if not financial_quality:
        financial_quality = {
            "status": "not_configured",
            "reason": "financial_quality_gate_not_configured",
            "blocking": False,
        }
    return {
        "structural_gate": _drop_none(
            {
                "gate_ref": "final_decision_switch_readiness",
                "ready": structural.get("ready", False),
                "reasons": _string_list(structural.get("reasons")),
                "blocking_reasons": _string_list(structural.get("blocking_reasons")),
            }
        ),
        "production_control_gate": _drop_none(
            {
                "gate_ref": "production_control_gate",
                "allowed": production_control.get("allowed"),
                "reasons": _string_list(production_control.get("reasons")),
            }
        ),
        "financial_quality_gate": financial_quality,
    }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
