from __future__ import annotations

import sys

from crypto_manual_alert.artifacts import AgentContribution as AgentContributionFromPackage
from crypto_manual_alert.artifacts import EvidencePacket as EvidencePacketFromPackage
from crypto_manual_alert.artifacts import build_audit_artifacts as build_audit_artifacts_from_package
from crypto_manual_alert.artifacts.contributions import (
    FORBIDDEN_EXECUTABLE_FIELDS,
    MIGRATION_STAGE,
    REVIEWER_KEYS,
    AgentContribution,
    from_leader_summary,
)
from crypto_manual_alert.artifacts.evidence import (
    EXCHANGE_SOURCE_HINTS,
    EXECUTION_FACT_TYPES,
    SEARCH_CONFIDENCE_CAP,
    SEARCH_SOURCE_HINTS,
    EvidencePacket,
    FactsGateResult,
    check_execution_facts,
    from_market_snapshot,
    from_research_audit,
)
from crypto_manual_alert.artifacts.orchestration_inputs import build_audit_artifacts


def test_artifacts_package_import_does_not_eagerly_import_implementation_modules():
    implementation_modules = [
        "crypto_manual_alert.artifacts.contributions",
        "crypto_manual_alert.artifacts.evidence",
        "crypto_manual_alert.artifacts.orchestration_inputs",
    ]
    previous_modules = {name: sys.modules.pop(name, None) for name in implementation_modules}
    sys.modules.pop("crypto_manual_alert.artifacts", None)
    try:
        __import__("crypto_manual_alert.artifacts")

        for name in implementation_modules:
            assert name not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.artifacts", None)
        for name, module in previous_modules.items():
            if module is not None:
                sys.modules[name] = module


def test_artifacts_package_exports_canonical_objects():
    assert AgentContributionFromPackage is AgentContribution
    assert EvidencePacketFromPackage is EvidencePacket
    assert build_audit_artifacts_from_package is build_audit_artifacts
    assert isinstance(MIGRATION_STAGE, str)
    assert MIGRATION_STAGE
    assert REVIEWER_KEYS
    assert FORBIDDEN_EXECUTABLE_FIELDS
    assert EXECUTION_FACT_TYPES
    assert EXCHANGE_SOURCE_HINTS
    assert SEARCH_SOURCE_HINTS
    assert SEARCH_CONFIDENCE_CAP < 1
    assert callable(from_leader_summary)
    assert callable(check_execution_facts)
    assert callable(from_market_snapshot)
    assert callable(from_research_audit)
    assert FactsGateResult
