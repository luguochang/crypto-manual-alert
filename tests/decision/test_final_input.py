from __future__ import annotations

from crypto_manual_alert.decision.final_input import select_final_input


def test_final_input_selector_returns_legacy_prompt_without_copying_or_mutating():
    prompt_packet = {"market_snapshot": {"symbol": "ETH-USDT-SWAP"}, "skill": {"name": "crypto"}}

    selection = select_final_input(
        final_input_mode="legacy_prompt",
        legacy_prompt_packet=prompt_packet,
        decision_input_candidate={"input_ref": "trace:1:decision_input_candidate"},
        switch_readiness={"ready": True},
    )

    assert selection.mode == "legacy_prompt"
    assert selection.input_payload is prompt_packet
    assert selection.to_public_dict() == {
        "mode": "legacy_prompt",
        "source_ref": "legacy_prompt_packet",
        "decision_effect": "production_final_input",
        "readiness_ready": False,
    }


def test_final_input_selector_returns_decision_input_when_readiness_and_candidate_validation_pass():
    decision_input = {
        "schema_version": 1,
        "mode": "candidate_audit",
        "decision_effect": "none",
        "input_ref": "trace:1:decision_input_candidate",
        "input_hash": "sha256:decision-input",
        "validation": {"passed": True, "violations": []},
        "effective_allowed_actions": ["no trade"],
        "lead_synthesis": {"included_contribution_ids": ["root", "sentiment", "quality", "risk"]},
    }

    selection = select_final_input(
        final_input_mode="decision_input",
        legacy_prompt_packet={"legacy": True},
        decision_input_candidate=decision_input,
        switch_readiness={"ready": True, "blocking_reasons": []},
    )

    assert selection.mode == "decision_input"
    assert selection.input_payload == {
        **decision_input,
        "mode": "production_final_input",
        "decision_effect": "production_final_input",
        "source_candidate_ref": "trace:1:decision_input_candidate",
        "source_candidate_hash": "sha256:decision-input",
    }
    assert decision_input["mode"] == "candidate_audit"
    assert decision_input["decision_effect"] == "none"
    assert selection.to_public_dict() == {
        "mode": "decision_input",
        "source_ref": "trace:1:decision_input_candidate",
        "decision_effect": "production_final_input",
        "readiness_ready": True,
    }


def test_final_input_selector_rejects_decision_input_when_switch_readiness_is_not_ready():
    legacy_prompt = {"legacy": True}

    selection = select_final_input(
        final_input_mode="decision_input",
        legacy_prompt_packet=legacy_prompt,
        decision_input_candidate={
            "input_ref": "trace:1:decision_input_candidate",
            "input_hash": "sha256:decision-input",
            "validation": {"passed": True},
        },
        switch_readiness={
            "ready": False,
            "blocking_reasons": ["candidate_gate_failed", "worker_hard_block"],
        },
    )

    assert selection.mode == "legacy_prompt"
    assert selection.input_payload is legacy_prompt
    assert selection.to_public_dict() == {
        "mode": "legacy_prompt",
        "source_ref": "legacy_prompt_packet",
        "decision_effect": "production_final_input",
        "readiness_ready": False,
        "fallback_reason": "decision_input_not_ready",
        "fallback_from_mode": "decision_input",
        "fallback_blocking_reasons": ["candidate_gate_failed", "worker_hard_block"],
        "candidate_input_ref": "trace:1:decision_input_candidate",
        "candidate_input_hash": "sha256:decision-input",
    }


def test_final_input_selector_rejects_invalid_decision_input_candidate():
    legacy_prompt = {"legacy": True}

    selection = select_final_input(
        final_input_mode="decision_input",
        legacy_prompt_packet=legacy_prompt,
        decision_input_candidate={
            "input_ref": "trace:1:decision_input_candidate",
            "input_hash": "sha256:decision-input",
            "validation": {"passed": False},
        },
        switch_readiness={"ready": True},
    )

    assert selection.mode == "legacy_prompt"
    assert selection.input_payload is legacy_prompt
    assert selection.to_public_dict()["fallback_reason"] == "decision_input_candidate_invalid"
    assert selection.to_public_dict()["candidate_input_ref"] == "trace:1:decision_input_candidate"
