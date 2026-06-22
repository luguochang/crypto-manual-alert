from __future__ import annotations

from crypto_manual_alert.eval.counter_conflict_coverage import counter_conflict_coverage


def test_counter_conflict_coverage_detects_missing_refs_and_strongest_counter():
    coverage = counter_conflict_coverage(
        {
            "counter_thesis": ["Crowded longs can reverse."],
            "counter_thesis_refs": [],
            "strongest_counter_thesis_ref": None,
            "conflicts": ["trend_vs_crowding"],
            "conflict_refs": [],
        }
    )

    assert coverage["passed"] is False
    assert {
        "rule_id": "lead_synthesis_counter_thesis_refs_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_strongest_counter_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_conflict_refs_missing",
        "conflict_count": 1,
    } in coverage["violations"]


def test_counter_conflict_coverage_includes_lead_synthesis_artifact_gaps():
    coverage = counter_conflict_coverage(
        {
            "counter_thesis": ["Crowded longs can reverse."],
            "counter_thesis_refs": [{"contribution_id": "c-sentiment"}],
            "strongest_counter_thesis_ref": {"contribution_id": "c-sentiment"},
            "conflicts": ["trend_vs_crowding"],
            "conflict_refs": [{"conflict_id": "trend_vs_crowding"}],
        },
        lead_synthesis_artifact={
            "artifact_ref": "candidate:lead_synthesis",
            "counter_thesis_count": 1,
            "counter_thesis_refs": [],
            "strongest_counter_thesis_ref": None,
            "conflict_count": 1,
            "conflict_refs": [],
        },
    )

    assert coverage["passed"] is False
    assert {
        "rule_id": "lead_synthesis_artifact_counter_thesis_refs_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_artifact_strongest_counter_missing",
        "counter_thesis_count": 1,
    } in coverage["violations"]
    assert {
        "rule_id": "lead_synthesis_artifact_conflict_refs_missing",
        "conflict_count": 1,
    } in coverage["violations"]
