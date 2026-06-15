"""Candidate decision-input and gate building blocks.

This package is still audit/candidate-only. Production FinalDecisionAgent input
remains locked to the legacy prompt until a separate manual switch review.
"""

from typing import Any

_SUBMODULE_EXPORTS = {
    "candidate_audit",
    "candidate_final_decision",
    "decision_input",
    "final_input",
    "frozen_input",
    "gate_candidate",
    "plan_parse_step",
    "plan_parser",
    "pre_final_input",
    "pre_final_input_gate",
    "production_control_gate",
    "replay_observed_refs",
    "replay_sanitization",
    "replay_worker_refs",
    "replayable_input",
    "risk",
    "switch_readiness",
}

__all__ = [
    "DecisionInputCandidate",
    "PreFinalDecisionInput",
    "build_candidate_audit_payload",
    "build_decision_input_candidate",
    "build_pre_final_decision_input",
    "evaluate_pre_final_input_gate",
    "run_candidate_final_decision_sidecar",
]

_EXPORT_MODULES = {
    "DecisionInputCandidate": "crypto_manual_alert.decision.decision_input",
    "PreFinalDecisionInput": "crypto_manual_alert.decision.decision_input",
    "build_candidate_audit_payload": "crypto_manual_alert.decision.candidate_audit",
    "build_decision_input_candidate": "crypto_manual_alert.decision.decision_input",
    "build_pre_final_decision_input": "crypto_manual_alert.decision.decision_input",
    "evaluate_pre_final_input_gate": "crypto_manual_alert.decision.pre_final_input_gate",
    "run_candidate_final_decision_sidecar": "crypto_manual_alert.decision.candidate_final_decision",
}


def __getattr__(name: str) -> Any:
    import importlib

    if name in _SUBMODULE_EXPORTS:
        return importlib.import_module(f"{__name__}.{name}")
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = importlib.import_module(_EXPORT_MODULES[name])
    return getattr(module, name)
