from __future__ import annotations

import pytest

from crypto_alert_v2.evaluation.review_graph import graph


def test_candidate_review_uses_one_official_interrupt_payload() -> None:
    result = graph.invoke(
        {
            "candidate_id": "candidate-1",
            "candidate_version": "rule-v2",
            "rationale": "Require frozen gates.",
        },
        {"configurable": {"thread_id": "candidate-review-test"}},
    )

    interrupts = result["__interrupt__"]
    assert len(interrupts) == 1
    assert interrupts[0].value == {
        "kind": "candidate_review",
        "schema_version": "1.0",
        "candidate_id": "candidate-1",
        "candidate_version": "rule-v2",
        "rationale": "Require frozen gates.",
        "allowed_actions": ["approve", "reject"],
    }


def test_candidate_review_rejects_unknown_resumed_action() -> None:
    with pytest.raises(ValueError, match="approve or reject"):
        # Exercise the validation branch without invoking an interrupt by passing
        # a narrow monkeypatch-compatible response through the function boundary.
        import crypto_alert_v2.evaluation.review_graph as review_graph

        original = review_graph.interrupt
        review_graph.interrupt = lambda _: {"action": "edit"}  # type: ignore[assignment]
        try:
            review_graph.request_candidate_review(
                {
                    "candidate_id": "candidate-1",
                    "candidate_version": "rule-v2",
                    "rationale": "Require frozen gates.",
                }
            )
        finally:
            review_graph.interrupt = original
