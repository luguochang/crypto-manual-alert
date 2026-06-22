from __future__ import annotations

from datetime import date

from crypto_manual_alert.eval.schema import EvalCase
from crypto_manual_alert.eval.store_rows import (
    case_row,
    case_to_row,
    dump_json,
    frozen_input_row,
    load_json,
    not_run_replay_result,
    replay_row,
    run_row,
    score_row,
)


def test_dump_json_keeps_stable_sorted_unicode_and_default_string_behavior():
    assert dump_json({"b": 1, "a": "中文", "day": date(2026, 7, 2)}) == (
        '{"a": "中文", "b": 1, "day": "2026-07-02"}'
    )


def test_load_json_keeps_empty_text_as_none():
    assert load_json("") is None
    assert load_json(None) is None
    assert load_json('{"a": 1}') == {"a": 1}


def test_run_row_decodes_metadata_json():
    assert run_row({"eval_run_id": "run-1", "metadata_json": '{"x": 1}'}) == {
        "eval_run_id": "run-1",
        "metadata": {"x": 1},
    }


def test_case_to_row_and_case_row_round_trip_safe_payload_fields():
    case = EvalCase(
        case_id="case-1",
        dataset_name="selected_badcases",
        source_trace_id="trace-1",
        source_badcase_id=1,
        created_at="2026-06-30T00:00:00+00:00",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        failure_category="grounding_error",
        severity="high",
        expected_behavior="expected",
        actual_behavior="actual",
        summary="summary",
        status="open",
        frozen_input_hash="frozen-hash",
        input_summary={"candidate_audit": {"status": "available"}},
        metadata={"source": "fixture"},
    )

    row_payload = case_to_row(case)
    assert row_payload["input_summary"] == {"candidate_audit": {"status": "available"}}
    assert row_payload["metadata"] == {"source": "fixture"}

    restored = case_row(
        {
            **{key: value for key, value in row_payload.items() if key not in {"input_summary", "metadata"}},
            "input_summary_json": dump_json(row_payload["input_summary"]),
            "metadata_json": dump_json(row_payload["metadata"]),
        }
    )
    assert restored == case


def test_frozen_input_row_decodes_payloads():
    frozen = frozen_input_row(
        {
            "frozen_input_hash": "hash",
            "schema_version": 1,
            "kind": "legacy_prompt",
            "source_trace_id": "trace-1",
            "source_badcase_id": 1,
            "input_json": '{"prompt": "safe"}',
            "public_summary_json": '{"symbol": "BTC"}',
            "metadata_json": '{"mode": "eval"}',
        }
    )

    assert frozen.input_payload == {"prompt": "safe"}
    assert frozen.public_summary == {"symbol": "BTC"}
    assert frozen.metadata == {"mode": "eval"}


def test_replay_row_decodes_booleans_payloads_and_drops_created_at():
    replay = replay_row(
        {
            "replay_id": "replay-1",
            "case_id": "case-1",
            "allowed": 1,
            "output_json": '{"candidate_replay": {"status": "available"}}',
            "metadata_json": '{"judge": "rules"}',
            "created_at": "2026-06-30T00:00:00+00:00",
        }
    )

    assert replay["allowed"] is True
    assert replay["output_payload"] == {"candidate_replay": {"status": "available"}}
    assert replay["metadata"] == {"judge": "rules"}
    assert "created_at" not in replay


def test_replay_row_preserves_none_allowed_and_decodes_zero_as_false():
    none_allowed = replay_row(
        {
            "replay_id": "replay-1",
            "case_id": "case-1",
            "allowed": None,
            "output_json": "",
            "metadata_json": "",
        }
    )
    false_allowed = replay_row(
        {
            "replay_id": "replay-2",
            "case_id": "case-1",
            "allowed": 0,
            "output_json": "null",
            "metadata_json": "null",
        }
    )

    assert none_allowed["allowed"] is None
    assert none_allowed["output_payload"] == {}
    assert none_allowed["metadata"] == {}
    assert false_allowed["allowed"] is False
    assert false_allowed["output_payload"] == {}
    assert false_allowed["metadata"] == {}


def test_not_run_replay_result_preserves_case_identity_without_side_effect_fields():
    result = not_run_replay_result(
        {
            "case_id": "case-1",
            "source_trace_id": "trace-1",
            "source_badcase_id": 1,
            "frozen_input_hash": "frozen-hash",
        }
    )

    assert result == {
        "status": "not_run",
        "mode": "none",
        "case_id": "case-1",
        "source_trace_id": "trace-1",
        "source_badcase_id": 1,
        "frozen_input_hash": "frozen-hash",
        "final_action": None,
        "allowed": None,
        "output_hash": None,
        "reason_summary": None,
        "error_message": None,
        "duration_ms": None,
        "metadata": {},
    }


def test_score_row_decodes_booleans_evidence_and_metadata():
    score = score_row(
        {
            "score_id": "score-1",
            "passed": 1,
            "needs_human_review": 0,
            "evidence_refs_json": '["ref-1"]',
            "metadata_json": '{"rule": "grounding"}',
        }
    )

    assert score["passed"] is True
    assert score["needs_human_review"] is False
    assert score["evidence_refs"] == ["ref-1"]
    assert score["metadata"] == {"rule": "grounding"}


def test_score_row_keeps_empty_evidence_refs_as_empty_list():
    score = score_row(
        {
            "score_id": "score-1",
            "passed": 0,
            "needs_human_review": 1,
            "evidence_refs_json": "",
            "metadata_json": "null",
        }
    )

    assert score["passed"] is False
    assert score["needs_human_review"] is True
    assert score["evidence_refs"] == []
    assert score["metadata"] is None
