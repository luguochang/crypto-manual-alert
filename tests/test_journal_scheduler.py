from datetime import timedelta
import json
import sqlite3

from crypto_manual_alert.journal import Journal
from crypto_manual_alert.observability import ObservabilityRecorder
from crypto_manual_alert.scheduler import JobLock, run_scheduler


def test_journal_connect_closes_after_context(tmp_path):
    journal = Journal(tmp_path / "journal.db")

    with journal.connect() as conn:
        conn.execute("SELECT 1")

    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("journal connection should be closed after context exit")


def test_job_lock_prevents_overlap(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    lock = JobLock(journal, "plan-run", ttl=timedelta(minutes=30))

    assert lock.acquire() is True
    assert lock.acquire() is False

    lock.release()
    assert lock.acquire() is True


def test_scheduler_continues_after_job_failure(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    lock = JobLock(journal, "plan-run", ttl=timedelta(minutes=30))
    calls = {"count": 0}

    def job():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")

    run_scheduler(0, lock, job, max_iterations=2)

    assert calls["count"] == 2


def test_observability_records_trace_span_and_llm_interaction(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)

    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    with recorder.span(trace_id, "decision.final", "decision.llm", input_summary={"symbol": "ETH-USDT-SWAP"}) as span:
        span.set_output({"action": "no trade"})
    recorder.record_llm_interaction(
        trace_id=trace_id,
        component="decision.final",
        provider="openai_compatible",
        model="gpt-test",
        request_payload={"messages": [{"role": "user", "content": "分析 ETH"}], "api_key": "secret"},
        response_payload={"choices": [{"message": {"content": "结论摘要"}}]},
        status="ok",
        duration_ms=321,
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
        cost_usd=0.001,
        finish_reason="stop",
        retry_count=2,
    )
    recorder.finish_trace(trace_id, status="ok", final_action="no trade", allowed=True)

    with journal.connect() as conn:
        trace = conn.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
        span_row = conn.execute("SELECT * FROM trace_spans WHERE trace_id = ?", (trace_id,)).fetchone()
        llm = conn.execute("SELECT * FROM llm_interactions WHERE trace_id = ?", (trace_id,)).fetchone()

    assert trace["status"] == "ok"
    assert span_row["span_name"] == "decision.final"
    assert span_row["status"] == "ok"
    assert json.loads(span_row["output_summary_json"])["action"] == "no trade"
    assert llm["component"] == "decision.final"
    assert llm["status"] == "ok"
    assert "secret" not in llm["request_json"]
    assert llm["input_hash"]
    assert llm["output_hash"]
    assert llm["duration_ms"] == 321
    assert llm["prompt_tokens"] == 11
    assert llm["completion_tokens"] == 7
    assert llm["total_tokens"] == 18
    assert llm["cost_usd"] == 0.001
    assert llm["finish_reason"] == "stop"
    assert llm["retry_count"] == 2


def test_journal_migrates_existing_llm_interaction_table(tmp_path):
    db_path = tmp_path / "journal.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE llm_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            span_id TEXT,
            created_at TEXT NOT NULL,
            component TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            endpoint TEXT,
            status TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            output_hash TEXT NOT NULL,
            input_summary_json TEXT NOT NULL,
            output_summary_json TEXT NOT NULL,
            request_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    Journal(db_path)

    with sqlite3.connect(db_path) as migrated:
        columns = {row[1] for row in migrated.execute("PRAGMA table_info(llm_interactions)").fetchall()}

    assert "duration_ms" in columns
    assert "prompt_tokens" in columns
    assert "completion_tokens" in columns
    assert "total_tokens" in columns
    assert "finish_reason" in columns
    assert "retry_count" in columns
    assert "cost_usd" in columns


def test_journal_can_query_trace_detail_and_record_badcase(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)

    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    with recorder.span(trace_id, "risk.check", "risk.check", input_summary={"plan": "p1"}) as span:
        span.set_output({"allowed": False, "reasons": ["核心执行行情缺失"]})
    recorder.record_llm_interaction(
        trace_id=trace_id,
        component="decision.final",
        provider="openai_compatible",
        model="gpt-test",
        request_payload={"messages": [{"role": "user", "content": "分析 ETH"}], "api_key": "secret"},
        response_payload={"choices": [{"message": {"content": "结论摘要"}}]},
        status="ok",
    )
    recorder.finish_trace(trace_id, status="blocked", final_action="no trade", allowed=False)
    journal.append_plan_run(
        "plan_1",
        "blocked",
        {
            "trace_id": trace_id,
            "analysis": {"reasoning_summary": "证据不足，禁止交易", "risk_rule_hits": ["core data missing"]},
            "raw_decision": "raw completion should stay out of trace-show by default",
        },
    )

    listed = journal.list_traces(limit=5)
    detail = journal.get_trace_detail(trace_id)
    badcase_id = journal.record_badcase(
        trace_id=trace_id,
        plan_id="plan_1",
        span_id=detail["spans"][0]["span_id"],
        llm_interaction_id=detail["llm_interactions"][0]["id"],
        category="grounding_error",
        severity="high",
        summary="模型引用了不可靠证据",
        expected_behavior="数据不足时必须 no trade",
        actual_behavior="输出缺少证据映射",
        source="developer",
        eval_dataset_name="failure_cases",
    )
    badcases = journal.list_badcases(limit=5)
    detail_after_badcase = journal.get_trace_detail(trace_id)

    assert listed[0]["trace_id"] == trace_id
    assert listed[0]["span_count"] == 1
    assert listed[0]["llm_interaction_count"] == 1
    assert detail["trace"]["trace_id"] == trace_id
    assert detail["plan_run"]["plan_id"] == "plan_1"
    assert detail["analysis"]["reasoning_summary"] == "证据不足，禁止交易"
    assert "raw_decision" not in detail["plan_run"]
    assert detail["spans"][0]["span_name"] == "risk.check"
    assert detail["llm_interactions"][0]["component"] == "decision.final"
    assert "request_json" not in detail["llm_interactions"][0]
    assert badcase_id > 0
    assert badcases[0]["trace_id"] == trace_id
    assert badcases[0]["category"] == "grounding_error"
    assert badcases[0]["summary"] == "模型引用了不可靠证据"
    assert badcases[0]["eval_dataset_name"] == "failure_cases"
    assert detail_after_badcase["badcases"][0]["id"] == badcase_id


def test_observability_links_llm_interaction_to_active_span(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")

    with recorder.span(trace_id, "decision.final", "decision.llm") as span:
        recorder.record_llm_interaction(
            trace_id=trace_id,
            component="decision.final",
            provider="openai_compatible",
            model="gpt-test",
            request_payload={"messages": [{"role": "user", "content": "分析 ETH"}]},
            response_payload={"choices": [{"message": {"content": "结论摘要"}}]},
            status="ok",
        )
        span_id = span.span_id

    with journal.connect() as conn:
        row = conn.execute("SELECT span_id FROM llm_interactions WHERE trace_id = ?", (trace_id,)).fetchone()

    assert row["span_id"] == span_id


def test_record_badcase_rejects_cross_trace_span_or_llm(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    recorder = ObservabilityRecorder(journal)
    trace_a = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP")
    trace_b = recorder.start_trace(run_type="manual", symbol="BTC-USDT-SWAP")

    with recorder.span(trace_a, "decision.final", "decision.llm") as span:
        recorder.record_llm_interaction(
            trace_id=trace_a,
            component="decision.final",
            provider="openai_compatible",
            model="gpt-test",
            request_payload={"messages": []},
            response_payload={"choices": []},
        )
        span_id = span.span_id
    with journal.connect() as conn:
        llm_id = conn.execute("SELECT id FROM llm_interactions WHERE trace_id = ?", (trace_a,)).fetchone()["id"]

    try:
        journal.record_badcase(
            trace_id=trace_b,
            span_id=span_id,
            category="grounding_error",
            severity="high",
            summary="跨 trace span 不应被接受",
        )
    except ValueError as exc:
        assert "span_id" in str(exc)
    else:
        raise AssertionError("cross-trace span_id should be rejected")

    try:
        journal.record_badcase(
            trace_id=trace_b,
            llm_interaction_id=llm_id,
            category="grounding_error",
            severity="high",
            summary="跨 trace LLM 不应被接受",
        )
    except ValueError as exc:
        assert "llm_interaction_id" in str(exc)
    else:
        raise AssertionError("cross-trace llm_interaction_id should be rejected")
