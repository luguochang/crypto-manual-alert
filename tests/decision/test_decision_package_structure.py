from __future__ import annotations

import sys

import crypto_manual_alert.decision as decision_package
from crypto_manual_alert.decision.candidate_audit import build_candidate_audit_payload
from crypto_manual_alert.decision.decision_input import (
    build_decision_input_candidate,
)
from crypto_manual_alert.decision.final_input import select_final_input
from crypto_manual_alert.decision.frozen_input import FrozenInput, stable_hash
from crypto_manual_alert.decision.gate_candidate import GateCandidateResult
from crypto_manual_alert.decision.plan_parse_step import run_plan_parse_step
from crypto_manual_alert.decision.plan_parser import PlanParseError, parse_decision_plan
from crypto_manual_alert.decision.pre_final_input import build_pre_final_input_payload
from crypto_manual_alert.decision.risk import check_plan


def test_decision_package_import_does_not_eagerly_import_implementation_modules():
    implementation_modules = [
        "crypto_manual_alert.decision.candidate_audit",
        "crypto_manual_alert.decision.decision_input",
        "crypto_manual_alert.decision.final_input",
        "crypto_manual_alert.decision.frozen_input",
    ]
    previous_modules = {name: sys.modules.pop(name, None) for name in implementation_modules}
    sys.modules.pop("crypto_manual_alert.decision", None)
    try:
        __import__("crypto_manual_alert.decision")

        for name in implementation_modules:
            assert name not in sys.modules
    finally:
        sys.modules.pop("crypto_manual_alert.decision", None)
        for name, module in previous_modules.items():
            if module is not None:
                sys.modules[name] = module


def test_decision_package_exports_candidate_builders_with_legacy_import_compatibility():
    candidate = build_decision_input_candidate(
        symbol="ETH-USDT-SWAP",
        trace_id="trace-1",
        evidence_packets=[],
        facts_gate={
            "passed": True,
            "severity": "ok",
            "missing_execution_facts": [],
            "blocked_action_classes": [],
        },
        agent_contributions=[],
        lead_synthesis={"decision_effect": "none"},
        legacy_plan={},
        verdict={},
    )

    assert GateCandidateResult
    assert candidate.decision_effect == "none"
    assert candidate.to_public_dict()["input_ref"] == "trace:trace-1:decision_input_candidate"
    assert decision_package.candidate_audit.build_candidate_audit_payload is build_candidate_audit_payload


def test_decision_package_exports_final_input_and_parser_boundaries():
    assert select_final_input
    assert run_plan_parse_step
    assert build_pre_final_input_payload


def test_decision_package_exports_plan_parser_frozen_input_and_risk_boundaries():
    assert parse_decision_plan
    assert PlanParseError
    assert FrozenInput
    assert stable_hash
    assert check_plan
