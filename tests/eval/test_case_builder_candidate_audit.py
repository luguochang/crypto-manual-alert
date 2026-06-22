from __future__ import annotations

import json

from crypto_manual_alert.decision.frozen_input import stable_hash
from crypto_manual_alert.eval.case_builder import _candidate_audit_summary


def test_candidate_audit_summary_prefers_audit_only_namespace():
    summary = _candidate_audit_summary(
        {
            "audit_only": {
                "decision_effect": "none",
                "decision_input_candidate": {
                    "input_ref": "trace:audit:decision_input_candidate",
                    "input_hash": "sha256:audit-decision",
                    "decision_effect": "none",
                    "evidence_refs": [],
                },
                "replayable_input_candidate": {
                    "input_ref": "trace:audit:replayable_input_candidate",
                    "input_hash": "sha256:audit-replayable",
                    "decision_effect": "none",
                    "coverage": {"worker_artifact_count": 4},
                    "artifact_refs": {},
                },
                "gate_candidate": {
                    "passed": True,
                    "severity": "ok",
                    "violations": [],
                    "blocked_actions": [],
                    "missing_facts": [],
                },
                "plan_semantic_candidate": {
                    "passed": True,
                    "severity": "ok",
                    "violations": [],
                },
                "final_decision_switch_readiness": {
                    "ready": True,
                    "blocking_reasons": [],
                },
            },
            "decision_input_candidate": {
                "input_ref": "trace:legacy-top-level:decision_input_candidate",
                "input_hash": "sha256:legacy",
            },
            "gate_candidate": {
                "passed": False,
                "severity": "hard_fail",
                "violations": [{"rule_id": "top_level_should_not_win"}],
            },
        }
    )

    assert summary["decision_input_candidate"]["input_ref"] == "trace:audit:decision_input_candidate"
    assert summary["decision_input_candidate"]["input_hash"] == "sha256:audit-decision"
    assert summary["gate_candidate"] == {
        "passed": True,
        "severity": "ok",
        "violations": [],
        "blocked_actions": [],
        "missing_facts": [],
    }
    assert summary["final_decision_switch_readiness"] == {
        "ready": True,
        "blocking_reasons": [],
    }


def test_candidate_audit_summary_preserves_context_artifact_refs_for_readback():
    summary = _candidate_audit_summary(
        {
            "audit_only": {
                "decision_effect": "none",
                "decision_input_candidate": {
                    "input_ref": "trace:audit:decision_input_candidate",
                    "input_hash": "sha256:audit-decision",
                    "decision_effect": "none",
                    "evidence_refs": [],
                },
                "replayable_input_candidate": {
                    "input_ref": "trace:audit:replayable_input_candidate",
                    "input_hash": "sha256:audit-replayable",
                    "decision_effect": "none",
                    "coverage": {"worker_artifact_count": 4},
                    "artifact_refs": {},
                },
                "gate_candidate": {"passed": True, "severity": "ok", "violations": []},
                "plan_semantic_candidate": {"passed": True, "severity": "ok", "violations": []},
                "final_decision_switch_readiness": {"ready": True, "blocking_reasons": []},
            },
            "run_context": {
                "artifacts": {
                    "lead_plan_ref": {"plan_id": "lead-1", "artifact_hash": "sha256:lead-plan"},
                    "gate_result_refs": {
                        "lead_synthesis_artifact": {
                            "artifact_ref": "candidate:lead_synthesis",
                            "artifact_hash": "sha256:lead-artifact",
                        },
                        "gate_candidate": {
                            "artifact_ref": "candidate:gate_candidate",
                            "artifact_hash": "sha256:gate",
                            "passed": True,
                        },
                    },
                }
            },
        }
    )

    assert summary["context_artifacts"]["lead_plan_ref"] == {
        "plan_id": "lead-1",
        "artifact_hash": "sha256:lead-plan",
    }
    assert summary["context_artifacts"]["gate_result_refs"]["lead_synthesis_artifact"] == {
        "artifact_ref": "candidate:lead_synthesis",
        "artifact_hash": "sha256:lead-artifact",
    }
    assert summary["context_artifacts"]["gate_result_refs"]["gate_candidate"] == {
        "artifact_ref": "candidate:gate_candidate",
        "artifact_hash": "sha256:gate",
        "passed": True,
    }


def test_candidate_audit_summary_preserves_controlled_shadow_audit_only_marker():
    summary = _candidate_audit_summary(
        {
            "controlled_shadow": {
                "mode": "top_level_should_not_win",
                "audit_only": False,
                "raw_decision": "must not leak",
            },
            "audit_only": {
                "decision_effect": "none",
                "controlled_shadow": {
                    "mode": "controlled_shadow",
                    "audit_only": True,
                    "production_final_input": False,
                    "notification_input": False,
                    "reason": "controlled shadow audit only",
                    "raw_decision": "must not leak",
                },
                "decision_input_candidate": {
                    "input_ref": "trace:audit:decision_input_candidate",
                    "input_hash": "sha256:audit-decision",
                    "decision_effect": "none",
                    "evidence_refs": [],
                },
                "replayable_input_candidate": {
                    "input_ref": "trace:audit:replayable_input_candidate",
                    "input_hash": "sha256:audit-replayable",
                    "decision_effect": "none",
                    "coverage": {"worker_artifact_count": 7},
                    "artifact_refs": {},
                },
                "gate_candidate": {"passed": False, "severity": "hard_fail", "violations": []},
                "plan_semantic_candidate": {"passed": True, "severity": "ok", "violations": []},
                "final_decision_switch_readiness": {"ready": False, "blocking_reasons": []},
            },
        }
    )

    assert summary["controlled_shadow"] == {
        "mode": "controlled_shadow",
        "audit_only": True,
        "production_final_input": False,
        "notification_input": False,
        "reason": "controlled shadow audit only",
    }
    assert "must not leak" not in str(summary)


def test_candidate_audit_summary_preserves_safe_replayable_observed_run_refs():
    summary = _candidate_audit_summary(
        {
            "audit_only": {
                "decision_effect": "none",
                "decision_input_candidate": {
                    "input_ref": "trace:audit:decision_input_candidate",
                    "input_hash": "sha256:audit-decision",
                    "decision_effect": "none",
                },
                "replayable_input_candidate": {
                    "input_ref": "trace:audit:replayable_input_candidate",
                    "input_hash": "sha256:audit-replayable",
                    "decision_effect": "none",
                    "coverage": {
                        "worker_artifact_count": 4,
                        "has_lead_synthesis_artifact": True,
                        "has_final_decision_output": True,
                        "has_final_input_selection": True,
                        "has_parsed_plan": True,
                        "has_production_control_gate": True,
                        "has_risk_gate_result": True,
                        "has_side_effect_policy": True,
                        "has_context_artifact_summary": True,
                        "has_version_lock": True,
                    },
                    "artifact_refs": {
                        "final_decision_output": {
                            "output_ref": "trace:audit:final_decision_output",
                            "output_hash": "sha256:final-raw",
                            "char_count": 128,
                            "stored_raw": False,
                            "raw_decision": "must not leak",
                        },
                        "final_input_selection": {
                            "mode": "legacy_prompt",
                            "source_ref": "legacy_prompt_packet",
                            "selection_hash": "sha256:selection",
                        },
                        "parsed_plan": {
                            "plan_ref": "trace:audit:parsed_plan",
                            "plan_id": "plan-1",
                            "main_action": "no trade",
                            "plan_hash": "sha256:plan",
                            "raw_payload": "must not leak",
                        },
                        "production_control_gate": {
                            "gate_ref": "trace:audit:production_control_gate",
                            "gate_hash": "sha256:control",
                            "allowed": False,
                            "rule_ids": ["production_control.worker_hard_block"],
                            "raw_details": "must not leak",
                        },
                        "risk_gate_result": {
                            "gate_ref": "trace:audit:risk_gate_result",
                            "gate_hash": "sha256:risk",
                            "allowed": False,
                            "rule_ids": ["risk.max_leverage"],
                        },
                        "side_effect_policy": {
                            "allow_production_journal_write": True,
                            "allow_notification_intent": True,
                            "policy_hash": "sha256:policy",
                        },
                        "context_artifact_summary": {
                            "evidence_count": 2,
                            "contribution_count": 4,
                            "artifact_hash": "sha256:context",
                            "raw_context": "must not leak",
                        },
                        "version_lock": {
                            "version_lock_ref": "trace:audit:version_lock",
                            "version_lock_hash": "sha256:version-lock",
                            "config_hash": "sha256:config",
                            "skill_hashes": {"crypto-macro-decision": "sha256:skill"},
                            "prompt_hashes": {"legacy_final_prompt": "sha256:prompt"},
                            "model": "gpt-fixture",
                            "rule_hashes": {"risk_gate": "sha256:risk-rules"},
                            "redaction_policy_hash": "sha256:redaction",
                            "raw_prompt": "must not leak",
                        },
                    },
                },
                "gate_candidate": {"passed": True, "severity": "ok", "violations": []},
                "plan_semantic_candidate": {"passed": True, "severity": "ok", "violations": []},
                "final_decision_switch_readiness": {"ready": True, "blocking_reasons": []},
            }
        }
    )

    refs = summary["replayable_input_candidate"]["artifact_refs"]
    assert summary["replayable_input_candidate"]["coverage"] == {
        "has_context_artifact_summary": True,
        "has_final_input_selection": True,
        "has_final_decision_output": True,
        "has_lead_synthesis_artifact": True,
        "has_parsed_plan": True,
        "has_production_control_gate": True,
        "has_risk_gate_result": True,
        "has_side_effect_policy": True,
        "has_version_lock": True,
        "worker_artifact_count": 4,
    }
    assert refs["final_decision_output"] == {
        "output_ref": "trace:audit:final_decision_output",
        "output_hash": "sha256:final-raw",
        "char_count": 128,
        "stored_raw": False,
    }
    assert refs["final_input_selection"] == {
        "mode": "legacy_prompt",
        "source_ref": "legacy_prompt_packet",
        "selection_hash": "sha256:selection",
    }
    assert refs["parsed_plan"] == {
        "plan_ref": "trace:audit:parsed_plan",
        "plan_id": "plan-1",
        "main_action": "no trade",
        "plan_hash": "sha256:plan",
    }
    assert refs["production_control_gate"] == {
        "gate_ref": "trace:audit:production_control_gate",
        "gate_hash": "sha256:control",
        "allowed": False,
        "rule_ids": ["production_control.worker_hard_block"],
    }
    assert refs["risk_gate_result"] == {
        "gate_ref": "trace:audit:risk_gate_result",
        "gate_hash": "sha256:risk",
        "allowed": False,
        "rule_ids": ["risk.max_leverage"],
    }
    assert refs["side_effect_policy"] == {
        "allow_production_journal_write": True,
        "allow_notification_intent": True,
        "policy_hash": "sha256:policy",
    }
    assert refs["context_artifact_summary"] == {
        "evidence_count": 2,
        "contribution_count": 4,
        "artifact_hash": "sha256:context",
    }
    assert refs["version_lock"] == {
        "version_lock_ref": "trace:audit:version_lock",
        "version_lock_hash": "sha256:version-lock",
        "config_hash": "sha256:config",
        "skill_hashes": {"crypto-macro-decision": "sha256:skill"},
        "prompt_hashes": {"legacy_final_prompt": "sha256:prompt"},
        "model": "gpt-fixture",
        "rule_hashes": {"risk_gate": "sha256:risk-rules"},
        "redaction_policy_hash": "sha256:redaction",
    }
    assert "must not leak" not in str(summary)


def test_candidate_audit_summary_preserves_safe_candidate_final_sidecar_summary():
    raw_candidate_decision = json.dumps(
        {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "no trade",
            "probability": 0.53,
            "raw_output": "must not leak",
        }
    )

    summary = _candidate_audit_summary(
        {
            "audit_only": {
                "decision_effect": "none",
                "decision_input_candidate": {
                    "input_ref": "trace:audit:decision_input_candidate",
                    "input_hash": "sha256:audit-decision",
                    "decision_effect": "none",
                },
                "replayable_input_candidate": {
                    "input_ref": "trace:audit:replayable_input_candidate",
                    "input_hash": "sha256:audit-replayable",
                    "decision_effect": "none",
                    "coverage": {},
                    "artifact_refs": {},
                },
                "candidate_final_decision": {
                    "artifact_type": "candidate_final_decision",
                    "mode": "candidate_final_sidecar",
                    "decision_effect": "none",
                    "production_final_input": False,
                    "input_ref": "trace:audit:pre_final_decision_input",
                    "input_hash": "sha256:pre-final",
                    "input_gate_passed": True,
                    "raw_candidate_decision": raw_candidate_decision,
                    "error": None,
                },
                "gate_candidate": {"passed": True, "severity": "ok", "violations": []},
                "plan_semantic_candidate": {"passed": True, "severity": "ok", "violations": []},
                "final_decision_switch_readiness": {"ready": False, "blocking_reasons": []},
            }
        }
    )

    assert summary["candidate_final_decision"] == {
        "artifact_type": "candidate_final_decision",
        "mode": "candidate_final_sidecar",
        "decision_effect": "none",
        "production_final_input": False,
        "input_ref": "trace:audit:pre_final_decision_input",
        "input_hash": "sha256:pre-final",
        "input_gate_passed": True,
        "candidate_final_summary": {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "no trade",
            "probability": 0.53,
        },
        "candidate_final_output_hash": stable_hash({"raw_candidate_decision": raw_candidate_decision}),
        "error": None,
    }
    assert "raw_candidate_decision" not in str(summary)
    assert "must not leak" not in str(summary)
