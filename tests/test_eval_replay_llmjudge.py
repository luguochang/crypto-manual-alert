from __future__ import annotations

import json
import sqlite3
import tempfile
from typing import Any

import httpx
import pytest

from crypto_manual_alert.eval.case_builder import EvalCaseBuilder
from crypto_manual_alert.eval.judges.llm import OpenAICompatibleLLMJudge
from crypto_manual_alert.eval.replay import ReplayRunner
from crypto_manual_alert.eval.runner import EvalRunner
from crypto_manual_alert.eval.store import EvalStore
from crypto_manual_alert.journal import Journal
from crypto_manual_alert.observability import ObservabilityRecorder


def test_eval_case_builder_persists_replayable_frozen_input(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]

    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)

    frozen = store.get_frozen_input(case.frozen_input_hash)
    assert frozen is not None
    assert frozen.input_payload["market_snapshot"]["symbol"] == "ETH-USDT-SWAP"
    assert frozen.source_trace_id == trace_id
    assert frozen.source_badcase_id == badcase_id
    assert "raw_decision" not in json.dumps(frozen.input_payload).lower()
    assert "request_json" not in json.dumps(frozen.input_payload).lower()


def test_replay_runner_writes_sidecar_output_without_prod_side_effects(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    builder = EvalCaseBuilder(journal)
    case = builder.build_cases(badcase_ids=[badcase_id])[0]
    store.upsert_cases([case])
    store.upsert_frozen_inputs(builder.last_frozen_inputs)
    before = _prod_counts(journal.path)

    output = ReplayRunner(store).replay(case)

    assert _prod_counts(journal.path) == before
    assert output.status == "completed"
    assert output.final_action == "no trade"
    assert output.allowed is True
    assert output.frozen_input_hash == case.frozen_input_hash
    assert store.get_replay_output(case.case_id)["status"] == "completed"


def test_eval_runner_judge_openai_uses_replay_and_real_llm_scores_without_prod_side_effects(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.db")
    store = EvalStore(tmp_path / "eval" / "crypto-eval.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    monkeypatch.setenv("OPENAI_API_KEY", "judge-key")
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        content = json.dumps(
            {
                "passed": True,
                "score": 0.82,
                "severity": "low",
                "failure_category": "none",
                "reason_summary": "证据、回放和预期行为没有发现直接冲突。",
                "evidence_refs": ["frozen_input_hash", "replay.output"],
                "needs_human_review": False,
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
            },
        )

    judge = OpenAICompatibleLLMJudge(
        base_url="https://judge.example",
        api_key="judge-key",
        model="judge-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    runner = EvalRunner(journal=journal, store=store, data_dir=tmp_path, llm_judge=judge)
    before = _all_prod_counts(journal.path)

    run = runner.run(badcase_ids=[badcase_id], mode="judge_openai")

    assert _all_prod_counts(journal.path) == before
    assert run.metadata["judge_provider"] == "openai_compatible"
    assert run.metadata["replay"]["completed"] == 1
    detail = store.get_run_detail(run.eval_run_id)
    scores = [score for score in detail["scores"] if score["judge_type"] == "llm"]
    assert len(scores) == 5
    assert {score["judge_name"] for score in scores} == {
        "llm.evidence_grounding",
        "llm.opposing_thesis",
        "llm.data_gap_honesty",
        "llm.execution_clarity",
        "llm.overconfidence",
    }
    assert all(score["metadata"]["duration_ms"] >= 0 for score in scores)
    assert all(score["metadata"]["total_tokens"] == 16 for score in scores)
    assert len(requests) == 5
    rendered_request = json.dumps(requests, ensure_ascii=False).lower()
    assert "judge-key" not in rendered_request
    assert "raw_decision" not in rendered_request
    assert "frozen_input_hash" in rendered_request
    assert detail["cases"][0]["replay_result"]["status"] == "completed"


def test_openai_llm_judge_invalid_json_returns_review_score():
    case = _minimal_case()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    judge = OpenAICompatibleLLMJudge(
        base_url="https://judge.example",
        api_key="judge-key",
        model="judge-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    scores = judge.evaluate("eval-run-id", case, replay_output={"status": "completed"})

    assert len(scores) == 5
    assert all(score.passed is False for score in scores)
    assert all(score.needs_human_review is True for score in scores)
    assert all(score.failure_category == "llm_judge_invalid_response" for score in scores)


def _seed_trace_with_frozen_input(journal: Journal) -> tuple[str, int]:
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP", horizon="6h")
    with recorder.span(trace_id, "decision.final", "decision.llm") as span:
        span.set_output({"raw_decision_chars": 120})
    with recorder.span(trace_id, "risk.check", "risk.check") as span:
        span.set_output({"allowed": True, "reasons": [], "rule_hits": []})
    recorder.finish_trace(trace_id, status="allowed", final_plan_id="plan_eval_seed", final_action="no trade", allowed=True)
    frozen_payload = {
        "skill": {"name": "crypto-macro-decision", "sha256": "skill-hash"},
        "market_snapshot": {
            "symbol": "ETH-USDT-SWAP",
            "fetched_at": "2026-06-30T00:00:00+00:00",
            "points": {},
            "unavailable": [],
        },
        "required_output": "strict JSON DecisionPlan",
    }
    journal.append_plan_run(
        "plan_eval_seed",
        "allowed",
        {
            "trace_id": trace_id,
            "frozen_input": {
                "schema_version": 1,
                "kind": "decision_prompt_packet",
                "sha256": "frozen-hash",
                "payload": frozen_payload,
            },
            "frozen_input_hash": "frozen-hash",
            "parsed_plan": {
                "instrument": "ETH-USDT-SWAP",
                "main_action": "no trade",
                "horizon": "6h",
                "manual_execution_required": True,
                "probability": 0.52,
                "why_not_opposite": "Short thesis lacks confirmation.",
                "invalidation": "Re-run if market breaks range.",
            },
            "verdict": {"allowed": True, "reasons": [], "warnings": [], "rule_hits": []},
            "analysis": {
                "reasoning_summary": "Seeded replayable plan.",
                "data_gaps": [],
                "risk_rule_hits": [],
            },
            "raw_decision": "must not leak",
        },
    )
    badcase_id = journal.record_badcase(
        trace_id=trace_id,
        plan_id="plan_eval_seed",
        category="grounding_error",
        severity="high",
        summary="replayable eval seed",
        expected_behavior="no trade is acceptable when evidence is thin",
        actual_behavior="no trade",
        eval_dataset_name="failure_cases",
        evidence_refs=["plan_run.frozen_input_hash", "plan_run.verdict"],
    )
    return trace_id, badcase_id


def _minimal_case():
    temp_dir = tempfile.TemporaryDirectory()
    journal = Journal(f"{temp_dir.name}/journal.db")
    _trace_id, badcase_id = _seed_trace_with_frozen_input(journal)
    return EvalCaseBuilder(journal).build_cases(badcase_ids=[badcase_id])[0]


def _prod_counts(path) -> dict[str, int]:
    with sqlite3.connect(path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes")
        }


def _all_prod_counts(path) -> dict[str, int]:
    with sqlite3.connect(path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes", "traces", "trace_spans", "llm_interactions")
        }
