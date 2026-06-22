from __future__ import annotations

import json

from crypto_manual_alert.eval.shadow_final_comparison import (
    build_candidate_final_legacy_comparison,
    build_shadow_legacy_comparison,
)


def test_shadow_legacy_comparison_reports_safe_action_diff_without_raw_payload():
    comparison = build_shadow_legacy_comparison(
        observed_output={
            "parsed_plan": {
                "main_action": "trigger long",
                "probability": 0.61,
                "raw_prompt": "must not leak",
            }
        },
        shadow_final={
            "status": "completed",
            "decision_effect": "none",
            "shadow_final_summary": {
                "main_action": "no trade",
                "probability": 0.52,
                "raw_output": "must not leak",
            },
        },
    )

    assert comparison == {
        "status": "available",
        "decision_effect": "none",
        "legacy_observed_summary": {
            "main_action": "trigger long",
            "probability": 0.61,
        },
        "shadow_final_summary": {
            "main_action": "no trade",
            "probability": 0.52,
        },
        "main_action_match": False,
        "probability_delta": -0.09,
        "differences": ["main_action_changed", "probability_changed"],
    }
    rendered = json.dumps(comparison, ensure_ascii=False).lower()
    assert "raw_prompt" not in rendered
    assert "raw_output" not in rendered
    assert "must not leak" not in rendered


def test_shadow_legacy_comparison_requires_completed_no_effect_shadow_final():
    comparison = build_shadow_legacy_comparison(
        observed_output={"parsed_plan": {"main_action": "no trade"}},
        shadow_final={
            "status": "completed",
            "decision_effect": "production_final_input",
            "shadow_final_summary": {"main_action": "no trade"},
        },
    )

    assert comparison == {
        "status": "missing_shadow_final",
        "decision_effect": "none",
        "differences": ["shadow_final_unavailable"],
    }


def test_candidate_final_legacy_comparison_reports_safe_action_diff_without_raw_payload():
    comparison = build_candidate_final_legacy_comparison(
        observed_output={
            "parsed_plan": {
                "main_action": "trigger long",
                "probability": 0.61,
                "raw_prompt": "must not leak",
            }
        },
        candidate_final_decision={
            "artifact_type": "candidate_final_decision",
            "mode": "candidate_final_sidecar",
            "decision_effect": "none",
            "production_final_input": False,
            "input_gate_passed": True,
            "raw_candidate_decision": json.dumps(
                {
                    "instrument": "ETH-USDT-SWAP",
                    "main_action": "no trade",
                    "probability": 0.52,
                    "raw_output": "must not leak",
                }
            ),
        },
    )

    assert comparison == {
        "status": "available",
        "decision_effect": "none",
        "legacy_observed_summary": {
            "main_action": "trigger long",
            "probability": 0.61,
        },
        "candidate_final_summary": {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "no trade",
            "probability": 0.52,
        },
        "main_action_match": False,
        "probability_delta": -0.09,
        "differences": ["main_action_changed", "probability_changed"],
    }
    rendered = json.dumps(comparison, ensure_ascii=False).lower()
    assert "raw_prompt" not in rendered
    assert "raw_output" not in rendered
    assert "must not leak" not in rendered


def test_candidate_final_legacy_comparison_requires_no_effect_sidecar():
    comparison = build_candidate_final_legacy_comparison(
        observed_output={"parsed_plan": {"main_action": "no trade"}},
        candidate_final_decision={
            "artifact_type": "candidate_final_decision",
            "decision_effect": "production_final_input",
            "production_final_input": True,
            "input_gate_passed": True,
            "raw_candidate_decision": '{"main_action":"no trade"}',
        },
    )

    assert comparison == {
        "status": "missing_candidate_final",
        "decision_effect": "none",
        "differences": ["candidate_final_unavailable"],
    }
