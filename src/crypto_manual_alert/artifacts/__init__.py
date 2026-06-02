"""Structured evidence and contribution artifacts."""

from typing import Any

__all__ = [
    "AgentContribution",
    "EvidencePacket",
    "FactsGateResult",
    "build_audit_artifacts",
    "check_execution_facts",
    "contribution_safety_ref_fields",
    "from_leader_summary",
    "from_market_snapshot",
    "from_research_audit",
]

_EXPORT_MODULES = {
    "AgentContribution": "crypto_manual_alert.artifacts.contributions",
    "EvidencePacket": "crypto_manual_alert.artifacts.evidence",
    "FactsGateResult": "crypto_manual_alert.artifacts.evidence",
    "build_audit_artifacts": "crypto_manual_alert.artifacts.orchestration_inputs",
    "check_execution_facts": "crypto_manual_alert.artifacts.evidence",
    "contribution_safety_ref_fields": "crypto_manual_alert.artifacts.contributions",
    "from_leader_summary": "crypto_manual_alert.artifacts.contributions",
    "from_market_snapshot": "crypto_manual_alert.artifacts.evidence",
    "from_research_audit": "crypto_manual_alert.artifacts.evidence",
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
