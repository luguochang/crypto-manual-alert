from __future__ import annotations

import sqlite3
from typing import Any

from fastapi.testclient import TestClient

from crypto_manual_alert.api.app import create_app
from crypto_manual_alert.observability import ObservabilityRecorder


def test_eval_candidates_expose_badcases_with_trace_context(tmp_path):
    """Eval 候选池应只读 badcase/trace 摘要，不能把 raw payload 泄露给前端。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    trace_id, badcase_id = _seed_badcase(app, expected_behavior="数据不足时必须 no trade")

    response = client.get("/api/eval/candidates?dataset=failure_cases&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    items = body["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == badcase_id
    assert items[0]["trace_id"] == trace_id
    assert items[0]["trace"]["final_action"] == "trigger long"
    assert items[0]["eval_dataset_name"] == "failure_cases"
    rendered = str(items).lower()
    assert "raw_decision" not in rendered
    assert "request_json" not in rendered
    assert "response_json" not in rendered


def test_eval_run_scores_cases_without_prod_side_effects(tmp_path):
    """Eval run 只能写 eval sidecar，不能新增生产 plan_runs、notifications 或 manual_outcomes。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    _trace_id, badcase_id = _seed_badcase(app, expected_behavior="数据不足时必须 no trade")
    before = _prod_table_counts(app.state.journal.path)

    response = client.post(
        "/api/eval/runs",
        json={"dataset_name": "failure_cases", "badcase_ids": [badcase_id], "mode": "judge_only_fixture"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    run_summary = body["data"]
    assert run_summary["case_count"] == 1
    assert run_summary["fail_count"] >= 1
    assert _prod_table_counts(app.state.journal.path) == before

    detail_response = client.get(f"/api/eval/runs/{run_summary['eval_run_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["run"]["eval_run_id"] == run_summary["eval_run_id"]
    assert detail["cases"][0]["source_badcase_id"] == badcase_id
    judge_names = {score["judge_name"] for score in detail["scores"]}
    assert "rule.expected_no_trade" in judge_names
    assert "llm.fixture_grounding" in judge_names
    assert "eval.side_effect_guard" in judge_names
    assert any(score["passed"] is False for score in detail["scores"])
    assert not any("raw_decision" in str(case).lower() for case in detail["cases"])


def test_eval_run_rejects_empty_selection(tmp_path):
    """没有可评估 case 时，API 应返回稳定错误，避免前端误以为已经完成测评。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.post("/api/eval/runs", json={"dataset_name": "missing_dataset"})

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "eval_no_cases"


def test_eval_apis_redact_badcase_and_plan_freeform_payloads(tmp_path):
    """badcase metadata/input_ref 和 parsed_plan 自由字段都不能把 secret/raw payload 带到 eval API。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    trace_id, badcase_id = _seed_badcase(
        app,
        expected_behavior="数据不足时必须 no trade",
        parsed_plan_extra={
            "secret": "openai-secret-value",
            "request_json": {"Authorization": "Bearer raw-token"},
            "raw_decision": "raw completion",
        },
        badcase_extra={
            "input_ref": {"api_key": "badcase-api-key", "nested": {"token": "badcase-token"}},
            "metadata": {"bark_device_key": "badcase-bark-key", "raw_payload": "raw badcase text"},
        },
    )

    candidate_body = client.get("/api/eval/candidates?dataset=failure_cases").json()
    run_body = client.post(
        "/api/eval/runs",
        json={"dataset_name": "failure_cases", "badcase_ids": [badcase_id], "mode": "judge_only_fixture"},
    ).json()
    detail_body = client.get(f"/api/eval/runs/{run_body['data']['eval_run_id']}").json()

    rendered = f"{candidate_body} {detail_body}".lower()
    assert trace_id in rendered
    for forbidden in [
        "openai-secret-value",
        "badcase-api-key",
        "badcase-token",
        "badcase-bark-key",
        "raw completion",
        "raw badcase text",
        "authorization",
        "request_json",
        "raw_decision",
    ]:
        assert forbidden not in rendered
    assert "<redacted>" in rendered


def test_eval_explicit_badcase_ids_can_select_older_cases_beyond_limit(tmp_path):
    """显式 badcase_ids 不能被最近列表 limit 截断，否则历史回归样本无法运行。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    _trace_id, older_badcase_id = _seed_badcase(app, expected_behavior="数据不足时必须 no trade")
    for index in range(5):
        _seed_badcase(
            app,
            expected_behavior="数据不足时必须 no trade",
            plan_id=f"plan_new_{index}",
            dataset_name="other_dataset",
        )

    response = client.post(
        "/api/eval/runs",
        json={"badcase_ids": [older_badcase_id], "mode": "judge_only_fixture", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["case_count"] == 1
    detail = client.get(f"/api/eval/runs/{body['data']['eval_run_id']}").json()["data"]
    assert detail["cases"][0]["source_badcase_id"] == older_badcase_id
    assert all(score["source_trace_id"] for score in detail["scores"])


def _seed_badcase(app: Any, *, expected_behavior: str, **kwargs: Any) -> tuple[str, int]:
    return _seed_badcase_with_options(app, expected_behavior=expected_behavior, **kwargs)


def _seed_badcase_with_options(
    app: Any,
    *,
    expected_behavior: str,
    plan_id: str = "plan_eval_seed",
    dataset_name: str = "failure_cases",
    parsed_plan_extra: dict[str, Any] | None = None,
    badcase_extra: dict[str, Any] | None = None,
) -> tuple[str, int]:
    journal = app.state.journal
    recorder = ObservabilityRecorder(journal)
    trace_id = recorder.start_trace(run_type="manual", symbol="ETH-USDT-SWAP", horizon="6h")
    with recorder.span(trace_id, "decision.final", "decision.llm") as span:
        span.set_output({"main_action": "trigger long", "probability": 0.72})
    with recorder.span(trace_id, "risk.check", "risk.check") as span:
        span.set_output({"allowed": True, "reasons": []})
    recorder.finish_trace(
        trace_id,
        status="allowed",
        final_plan_id=plan_id,
        final_action="trigger long",
        allowed=True,
    )
    parsed_plan = {
        "instrument": "ETH-USDT-SWAP",
        "main_action": "trigger long",
        "manual_execution_required": True,
        "probability": 0.72,
    }
    parsed_plan.update(parsed_plan_extra or {})
    journal.append_plan_run(
        plan_id,
        "allowed",
        {
            "trace_id": trace_id,
            "parsed_plan": parsed_plan,
            "verdict": {"allowed": True, "reasons": [], "warnings": []},
            "analysis": {
                "reasoning_summary": "fixture seed for eval regression",
                "data_gaps": ["precise CVD"],
            },
            "raw_decision": "raw completion must not leak into eval APIs",
        },
    )
    extra = badcase_extra or {}
    badcase_id = journal.record_badcase(
        trace_id=trace_id,
        plan_id=plan_id,
        category="grounding_error",
        severity="high",
        source="developer",
        summary="数据不足时仍给出可执行开仓动作",
        expected_behavior=expected_behavior,
        actual_behavior="输出 trigger long 且 allowed=true",
        eval_dataset_name=dataset_name,
        evidence_refs=["trace.final_action", "plan_run.verdict"],
        input_ref=extra.get("input_ref"),
        metadata=extra.get("metadata"),
    )
    return trace_id, badcase_id


def _prod_table_counts(db_path: str) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plan_runs", "notifications", "manual_outcomes")
        }
