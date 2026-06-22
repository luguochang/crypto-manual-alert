from __future__ import annotations

from crypto_manual_alert.eval.candidate_artifact_validation import (
    candidate_artifact_ref,
    validate_candidate_artifact,
    validate_candidate_artifact_snapshot,
)


def test_validate_candidate_artifact_snapshot_accepts_no_effect_snapshot():
    validate_candidate_artifact_snapshot(
        {
            "decision_effect": "none",
            "production_final_input": False,
            "notification_input": False,
        }
    )


def test_validate_candidate_artifact_snapshot_rejects_production_side_effect_flags():
    for unsafe_fields in (
        {"production_final_input": True},
        {"notification_input": True},
        {"decision_effect": "production_final_input"},
    ):
        snapshot = {
            "decision_effect": "none",
            "production_final_input": False,
            "notification_input": False,
            **unsafe_fields,
        }
        try:
            validate_candidate_artifact_snapshot(snapshot)
        except ValueError as exc:
            assert "candidate artifact snapshot decision_effect must be none" in str(exc)
        else:
            raise AssertionError("effectful candidate artifact snapshot should fail")


def test_validate_candidate_artifact_requires_artifact_hash():
    try:
        validate_candidate_artifact(
            "case-1",
            "lead_synthesis",
            {"artifact_ref": "candidate:lead_synthesis", "decision_effect": "none"},
        )
    except ValueError as exc:
        assert "candidate artifact artifact_hash is required" in str(exc)
    else:
        raise AssertionError("candidate artifact without artifact_hash should fail")


def test_validate_candidate_artifact_requires_no_effect_marker():
    try:
        validate_candidate_artifact(
            "case-1",
            "lead_synthesis",
            {
                "artifact_ref": "candidate:lead_synthesis",
                "decision_effect": "production_final_input",
                "artifact_hash": "sha256:lead",
            },
        )
    except ValueError as exc:
        assert "candidate artifact decision_effect must be none" in str(exc)
    else:
        raise AssertionError("effectful candidate artifact should fail")


def test_validate_candidate_artifact_rejects_malformed_decision_input_ref():
    try:
        validate_candidate_artifact(
            "case-1",
            "decision_input_candidate",
            {
                "input_ref": "trace:trace-1:not_decision_input",
                "input_hash": "sha256:decision",
                "decision_effect": "none",
                "artifact_hash": "sha256:decision-artifact",
            },
        )
    except ValueError as exc:
        assert "candidate decision input artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("malformed decision input candidate ref should fail")


def test_validate_candidate_artifact_rejects_malformed_replayable_input_ref():
    try:
        validate_candidate_artifact(
            "case-1",
            "replayable_input_candidate",
            {
                "input_ref": "trace:trace-1:not_replayable_input",
                "input_hash": "sha256:replayable",
                "decision_effect": "none",
                "artifact_hash": "sha256:replayable-artifact",
            },
        )
    except ValueError as exc:
        assert "candidate replayable input artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("malformed replayable input candidate ref should fail")


def test_validate_candidate_artifact_rejects_malformed_static_artifact_ref():
    try:
        validate_candidate_artifact(
            "case-1",
            "gate_candidate",
            {
                "artifact_ref": "candidate:not_gate_candidate",
                "decision_effect": "none",
                "artifact_hash": "sha256:gate",
            },
        )
    except ValueError as exc:
        assert "candidate artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("malformed candidate artifact ref should fail")


def test_validate_candidate_artifact_requires_input_ref_for_input_candidates():
    try:
        validate_candidate_artifact(
            "case-1",
            "decision_input_candidate",
            {
                "input_hash": "sha256:decision",
                "decision_effect": "none",
                "artifact_hash": "sha256:decision-artifact",
            },
        )
    except ValueError as exc:
        assert "candidate decision input artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("candidate input artifact without input_ref should fail")


def test_candidate_artifact_ref_prefers_input_ref_over_artifact_ref():
    assert (
        candidate_artifact_ref(
            {
                "input_ref": "trace:trace-1:decision_input_candidate",
                "artifact_ref": "candidate:decision_input_candidate",
            }
        )
        == "trace:trace-1:decision_input_candidate"
    )


def test_candidate_artifact_ref_falls_back_to_artifact_ref_or_empty_string():
    assert candidate_artifact_ref({"artifact_ref": "candidate:lead_synthesis"}) == "candidate:lead_synthesis"
    assert candidate_artifact_ref({}) == ""


def test_validate_replayable_candidate_without_input_ref_keeps_legacy_error_order():
    try:
        validate_candidate_artifact(
            "case-1",
            "replayable_input_candidate",
            {
                "input_hash": "sha256:replayable",
                "decision_effect": "none",
                "artifact_hash": "sha256:replayable-artifact",
            },
        )
    except ValueError as exc:
        assert "candidate replayable input artifact_ref mismatch" in str(exc)
    else:
        raise AssertionError("replayable input artifact without input_ref should fail")


def test_validate_unknown_candidate_artifact_type_keeps_current_permissive_behavior():
    validate_candidate_artifact(
        "case-1",
        "unknown_candidate_artifact",
        {
            "artifact_ref": "candidate:anything",
            "decision_effect": "none",
            "artifact_hash": "sha256:unknown",
        },
    )
