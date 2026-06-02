"""Lead planning and synthesis package."""

from typing import Any

__all__ = [
    "LeadAgent",
    "LeadPlanError",
    "LeadSynthesisArtifact",
    "LeadSynthesisCandidate",
    "build_default_lead_plan",
    "build_lead_synthesis_artifact",
    "build_lead_synthesis_candidate",
]

_EXPORT_MODULES = {
    "LeadAgent": "crypto_manual_alert.lead.agent",
    "LeadPlanError": "crypto_manual_alert.lead.agent",
    "LeadSynthesisArtifact": "crypto_manual_alert.lead.synthesis_artifact",
    "LeadSynthesisCandidate": "crypto_manual_alert.lead.synthesis",
    "build_default_lead_plan": "crypto_manual_alert.lead.default_plan",
    "build_lead_synthesis_artifact": "crypto_manual_alert.lead.synthesis_artifact",
    "build_lead_synthesis_candidate": "crypto_manual_alert.lead.synthesis",
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
