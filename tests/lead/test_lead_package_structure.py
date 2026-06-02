from __future__ import annotations

import sys

from crypto_manual_alert.lead import LeadAgent as LeadAgentFromPackage
from crypto_manual_alert.lead.agent import LeadAgent, LeadPlanError
from crypto_manual_alert.lead.synthesis import DEFAULT_REQUIRED_AGENTS, LeadSynthesisCandidate, build_lead_synthesis_candidate
from crypto_manual_alert.lead.synthesis_artifact import (
    RAW_FIELD_NAMES,
    LeadSynthesisArtifact,
    build_lead_synthesis_artifact,
)


def test_lead_package_import_does_not_eagerly_import_implementation_modules():
    implementation_modules = [
        "crypto_manual_alert.lead.agent",
        "crypto_manual_alert.lead.synthesis",
        "crypto_manual_alert.lead.synthesis_artifact",
    ]
    previous_modules = {name: sys.modules.pop(name, None) for name in implementation_modules}
    sys.modules.pop("crypto_manual_alert.lead", None)
    try:
        __import__("crypto_manual_alert.lead")

        for name in implementation_modules:
            assert name not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.lead", None)
        for name, module in previous_modules.items():
            if module is not None:
                sys.modules[name] = module


def test_lead_package_exports_canonical_objects():
    assert LeadAgentFromPackage is LeadAgent
    assert LeadPlanError
    assert DEFAULT_REQUIRED_AGENTS
    assert LeadSynthesisCandidate
    assert build_lead_synthesis_candidate
    assert RAW_FIELD_NAMES
    assert LeadSynthesisArtifact
    assert build_lead_synthesis_artifact
