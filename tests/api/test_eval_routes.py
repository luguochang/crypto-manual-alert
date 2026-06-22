from __future__ import annotations

import sqlite3
from typing import Any

from fastapi.testclient import TestClient

from crypto_manual_alert.api.app import create_app
from crypto_manual_alert.eval.errors import EvalRunError
from crypto_manual_alert.eval.runner import EvalRunner
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder


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


def test_eval_outcomes_endpoint_exposes_collected_samples(tmp_path):
    """GET /api/eval/outcomes 返回 OutcomeStore 中已收集的 outcome（脱敏 public dict）。"""
    from crypto_manual_alert.eval.outcome_store import OutcomeStore
    from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow

    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    store = app.state.outcome_store
    window = OutcomeWindow(
        name="ETH-USDT-SWAP:21600s",
        symbol="ETH-USDT-SWAP",
        interval="1H",
        source_type="exchange_native",
        window_start="2026-07-06T00:00:00+00:00",
        window_end="2026-07-06T06:00:00+00:00",
        collected_at="2026-07-06T06:01:00+00:00",
        open_price=3450.0,
        high_price=3550.0,
        low_price=3440.0,
        close_price=3540.0,
        matured=True,
    )
    store.upsert_outcomes(
        [
            DecisionOutcome(
                decision_ref="plan-1",
                evaluation_target="legacy_final",
                symbol="ETH-USDT-SWAP",
                action="trigger long",
                probability=0.6,
                entry_price=3460.0,
                stop_price=3400.0,
                target_1=3600.0,
                target_2=3700.0,
                window=window,
            )
        ]
    )

    response = client.get("/api/eval/outcomes?evaluation_target=legacy_final")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    items = body["data"]["items"]
    assert len(items) == 1
    assert items[0]["decision_ref"] == "plan-1"
    assert items[0]["evaluation_target"] == "legacy_final"
    assert items[0]["window"]["close_price"] == 3540.0
    assert items[0]["window"]["source_type"] == "exchange_native"
    assert items[0]["can_score"] is True


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
    financial_quality_gate = run_summary["metadata"]["financial_quality_gate"]
    assert financial_quality_gate["status"] == "not_enough_samples"
    assert financial_quality_gate["decision_effect"] == "none"
    assert financial_quality_gate["structural_release_gate_blocking"] is False
    assert financial_quality_gate["blocking"] is False
    assert "financial_quality" not in run_summary["metadata"]["release_gate"]["hard_gate_results"]
    assert _prod_table_counts(app.state.journal.path) == before

    detail_response = client.get(f"/api/eval/runs/{run_summary['eval_run_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["run"]["eval_run_id"] == run_summary["eval_run_id"]
    assert detail["run"]["metadata"]["financial_quality_gate"] == financial_quality_gate
    assert detail["cases"][0]["source_badcase_id"] == badcase_id
    assert detail["cases"][0]["frozen_input_hash"]
    assert detail["cases"][0]["replay_result"]["status"] in {"completed", "failed"}
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


def test_eval_run_persists_json_and_markdown_report_artifacts(tmp_path):
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    _trace_id, badcase_id = _seed_badcase(app, expected_behavior="data gap requires no trade")

    response = client.post(
        "/api/eval/runs",
        json={"dataset_name": "failure_cases", "badcase_ids": [badcase_id], "mode": "judge_only_fixture"},
    )

    assert response.status_code == 200
    run = response.json()["data"]
    metadata = run["metadata"]
    assert metadata["report_json_ref"]
    assert metadata["report_markdown_ref"]
    report_json = tmp_path / metadata["report_json_ref"]
    report_markdown = tmp_path / metadata["report_markdown_ref"]
    assert report_json.exists()
    assert report_markdown.exists()
    assert run["eval_run_id"] in report_markdown.read_text(encoding="utf-8")
    assert "failure_cases" in report_json.read_text(encoding="utf-8")


def test_eval_run_detail_keeps_case_snapshot_for_historical_runs(tmp_path):
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    _trace_id, badcase_id = _seed_badcase(app, expected_behavior="first expected behavior")

    first = client.post(
        "/api/eval/runs",
        json={"badcase_ids": [badcase_id], "mode": "judge_only_fixture"},
    ).json()["data"]
    app.state.journal.record_badcase(
        trace_id=_trace_id,
        plan_id="plan_eval_seed",
        category="grounding_error",
        severity="high",
        summary="same source changed later",
        expected_behavior="second expected behavior",
        actual_behavior="changed",
        eval_dataset_name="failure_cases",
    )
    second = client.post(
        "/api/eval/runs",
        json={"dataset_name": "failure_cases", "mode": "judge_only_fixture"},
    ).json()["data"]

    first_detail = client.get(f"/api/eval/runs/{first['eval_run_id']}").json()["data"]
    second_detail = client.get(f"/api/eval/runs/{second['eval_run_id']}").json()["data"]
    assert first_detail["cases"][0]["expected_behavior"] == "first expected behavior"
    assert any(case["expected_behavior"] == "second expected behavior" for case in second_detail["cases"])


def test_eval_rule_judge_covers_action_schema_and_opening_requirements(tmp_path):
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    _trace_id, badcase_id = _seed_badcase(
        app,
        expected_behavior="opening plan must have manual flag, entry, stop and invalidation",
        parsed_plan_extra={
            "main_action": "market buy now",
            "manual_execution_required": False,
            "entry_trigger": None,
            "stop_price": None,
            "invalidation": "",
        },
    )

    response = client.post(
        "/api/eval/runs",
        json={"badcase_ids": [badcase_id], "mode": "judge_only_fixture"},
    )

    assert response.status_code == 200
    detail = client.get(f"/api/eval/runs/{response.json()['data']['eval_run_id']}").json()["data"]
    scores = {score["judge_name"]: score for score in detail["scores"]}
    assert scores["rule.action_enum"]["passed"] is False
    assert scores["rule.manual_only"]["passed"] is False
    assert scores["rule.opening_requirements"]["passed"] is False


def test_eval_cheap_mode_skips_fixture_llm_and_keeps_side_effect_guard(tmp_path):
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    _trace_id, badcase_id = _seed_badcase(app, expected_behavior="data gap requires no trade")
    before = _prod_table_counts(app.state.journal.path)

    response = client.post(
        "/api/eval/runs",
        json={"badcase_ids": [badcase_id], "mode": "cheap"},
    )

    assert response.status_code == 200
    assert _prod_table_counts(app.state.journal.path) == before
    detail = client.get(f"/api/eval/runs/{response.json()['data']['eval_run_id']}").json()["data"]
    judge_names = {score["judge_name"] for score in detail["scores"]}
    assert "llm.fixture_grounding" not in judge_names
    assert "rule.action_enum" in judge_names
    assert "eval.side_effect_guard" in judge_names
    assert detail["run"]["metadata"]["judge_provider"] == "disabled"


def test_eval_run_rejects_forbidden_trade_secret_env(tmp_path, monkeypatch):
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    _trace_id, badcase_id = _seed_badcase(app, expected_behavior="data gap requires no trade")
    monkeypatch.setenv("OKX_TRADE_API_KEY", "must-not-be-visible-to-eval")

    response = client.post(
        "/api/eval/runs",
        json={"badcase_ids": [badcase_id], "mode": "cheap"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "eval_forbidden_secret_env"
    assert app.state.eval_store.list_runs() == []


def test_eval_run_returns_stable_error_when_runner_fails(tmp_path):
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)

    class FailingRunner:
        def run(self, **kwargs: Any):
            raise EvalRunError("failed to persist eval run: OperationalError")

    app.state.eval_runner = FailingRunner()

    response = client.post("/api/eval/runs", json={"mode": "cheap"})

    assert response.status_code == 500
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "eval_run_failed"


def test_eval_runner_cleans_report_artifacts_when_store_insert_fails(tmp_path):
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    _trace_id, badcase_id = _seed_badcase(app, expected_behavior="data gap requires no trade")

    class FailingStore:
        path = tmp_path / "eval" / "crypto-eval.db"

        def upsert_cases(self, cases: list[Any]) -> None:
            return None

        def upsert_frozen_inputs(self, frozen_inputs: list[Any]) -> None:
            return None

        def get_frozen_input(self, frozen_input_hash: str) -> Any:
            return None

        def insert_replay_output(self, output: Any) -> None:
            return None

        def insert_run(self, run: Any, cases: list[Any], scores: list[Any]) -> None:
            raise sqlite3.OperationalError("database is locked")

    runner = EvalRunner(journal=app.state.journal, store=FailingStore(), data_dir=tmp_path)

    try:
        runner.run(badcase_ids=[badcase_id], mode="cheap")
    except EvalRunError as exc:
        assert exc.code == "eval_run_failed"
    else:
        raise AssertionError("EvalRunError was not raised")
    report_dir = tmp_path / "eval" / "reports"
    assert not report_dir.exists() or list(report_dir.iterdir()) == []


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
