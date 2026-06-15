from __future__ import annotations

import logging
from typing import Any

from crypto_manual_alert.decision.decision_input import build_pre_final_decision_input


logger = logging.getLogger(__name__)


def build_pre_final_input_payload(
    *,
    trace_id: str,
    symbol: str,
    audit_payload: dict[str, Any],
    shadow_swarm_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the audit-only structured input available before final decision."""

    try:
        return build_pre_final_decision_input(
            symbol=symbol,
            trace_id=trace_id,
            evidence_packets=audit_payload["evidence_packets"],
            facts_gate=audit_payload["facts_gate"],
            agent_contributions=_decision_input_contributions(audit_payload, shadow_swarm_audit),
            lead_synthesis=_decision_input_lead_synthesis(shadow_swarm_audit),
        ).to_public_dict()
    except Exception as exc:  # noqa: BLE001 - pre-final input is audit-only until promoted.
        logger.exception("pre-final decision input failed")
        return {
            "schema_version": 1,
            "mode": "pre_final_candidate",
            "decision_effect": "none",
            "trace_id": trace_id,
            "symbol": symbol,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "validation": {
                "passed": False,
                "severity": "hard_fail",
                "violations": [{"rule_id": "pre_final_decision_input.build_failed"}],
            },
        }


def _decision_input_contributions(
    audit_payload: dict[str, Any], shadow_swarm_audit: dict[str, Any] | None
) -> list[dict[str, Any]]:
    worker_results = shadow_swarm_audit.get("worker_results") if isinstance(shadow_swarm_audit, dict) else None
    if isinstance(worker_results, list) and worker_results:
        return [
            result.get("contribution")
            for result in worker_results
            if isinstance(result, dict) and isinstance(result.get("contribution"), dict)
        ]
    return list(audit_payload.get("agent_contributions") or [])


def _decision_input_lead_synthesis(shadow_swarm_audit: dict[str, Any] | None) -> dict[str, Any]:
    lead_synthesis = shadow_swarm_audit.get("lead_synthesis") if isinstance(shadow_swarm_audit, dict) else None
    if not isinstance(lead_synthesis, dict):
        raise ValueError("shadow_swarm_audit.lead_synthesis is required for pre-final DecisionInput")
    return lead_synthesis
