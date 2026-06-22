from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_manual_alert.api.app import create_app
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder


def test_health_endpoint_reports_service_status(tmp_path):
    """健康检查接口用于前端和部署脚本确认 Python API 已启动。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["service"] == "crypto-manual-alert"
    assert body["data"]["storage"] == "sqlite"


def test_frontend_origin_can_preflight_manual_run(tmp_path):
    """浏览器从本地 Next.js 前端提交手动运行时，CORS 预检必须通过。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.options(
        "/api/runs/manual",
        headers={
            "Origin": "http://127.0.0.1:3001",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3001"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_manual_run_creates_trace_and_returns_plan_summary(tmp_path):
    """手动运行接口应复用现有 PlanRunner，并返回前端轮询需要的 trace_id。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.post(
        "/api/runs/manual",
        json={"symbol": "ETH-USDT-SWAP", "query": "评估 ETH 手动操作计划", "horizon": "6h"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["trace_id"]
    assert body["data"]["plan"]["instrument"] == "ETH-USDT-SWAP"
    assert body["data"]["plan"]["main_action"] == "trigger long"
    assert body["data"]["verdict"]["allowed"] is False
    assert any(
        hit["rule_id"] == "production_control.candidate.action_not_allowed"
        for hit in body["data"]["verdict"]["rule_hits"]
    )


def test_run_list_and_detail_hide_raw_payloads_by_default(tmp_path):
    """Runs 查询接口默认只给结构化摘要，不能把 raw_decision 或 LLM 原始请求暴露给前端。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]

    list_response = client.get("/api/runs")
    detail_response = client.get(f"/api/runs/{trace_id}")

    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["ok"] is True
    assert listed["data"]["items"][0]["trace_id"] == trace_id

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["ok"] is True
    assert detail["data"]["trace"]["trace_id"] == trace_id
    assert "raw_decision" not in detail["data"]["plan_run"]
    assert all("request_json" not in item for item in detail["data"]["llm_interactions"])
    assert all("response_json" not in item for item in detail["data"]["llm_interactions"])


def test_run_detail_exposes_sanitized_agent_audit_view(tmp_path):
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))
    run_response = client.post(
        "/api/runs/manual",
        json={"symbol": "ETH-USDT-SWAP", "query": "assess ETH manual operation", "horizon": "6h"},
    )
    trace_id = run_response.json()["data"]["trace_id"]

    response = client.get(f"/api/runs/{trace_id}")

    assert response.status_code == 200
    detail = response.json()["data"]
    audit = detail["plan_run"]["agent_audit_view"]
    assert audit["available"] is True
    assert audit["decision_effect"] == "audit_only_input_production_blocking_gate"
    assert audit["lead_plan"]["plan_id"]
    assert len(audit["lead_plan"]["tasks"]) == 7
    assert len(audit["workers"]) == 7
    assert any(worker["agent_name"] == "ExecutionRiskAgent" for worker in audit["workers"])
    assert audit["decision_input"]["mode"] == "pre_final_candidate"
    assert audit["query_semantics"]["mode"] == "audit_note"
    assert audit["query_semantics"]["drives_lead_plan"] is False
    assert audit["query_semantics"]["drives_final_input"] is False
    assert audit["symbol_consistency"] == {
        "request_symbol": "ETH-USDT-SWAP",
        "snapshot_symbol": "ETH-USDT-SWAP",
        "plan_instrument": "ETH-USDT-SWAP",
        "consistent": True,
    }
    assert audit["decision_input"]["input_ref"].endswith(":pre_final_decision_input")
    assert audit["candidate_final_comparison"]["status"] == "audit_only"
    assert audit["candidate_final_comparison"]["decision_effect"] == "none"
    assert audit["candidate_final_comparison"]["production_final_input"] is False
    assert audit["candidate_final_comparison"]["candidate"]["input_ref"].endswith(":pre_final_decision_input")
    assert audit["gates"]["production_control_gate"]["allowed"] is False
    assert isinstance(audit["tool_calls"], list)
    assert isinstance(audit["evidence_sources"], list)
    assert isinstance(audit["source_freshness"], list)
    assert set(audit["root_cause_graph"]) == {"nodes", "edges"}
    assert isinstance(audit["conflict_edges"], list)
    assert audit["input_lineage"]["production_final_input_mode"] == "legacy_prompt"
    assert audit["release_eval_gate"]["structural_gate"]["ready"] is False
    assert audit["release_eval_gate"]["financial_quality_gate"]["status"] == "not_configured"
    assert audit["final_input_selection"]["mode"] == "legacy_prompt"
    assert audit["runtime_flow"][0]["name"] == "market.fetch"
    assert audit["runtime_flow"][0]["source"] == "span_tree_refs"
    assert any(step["name"] == "shadow_swarm.worker" for step in audit["runtime_flow"])
    rendered = str(audit)
    assert "raw_decision" not in rendered
    assert "raw_candidate_decision" not in rendered
    assert "frozen_input" not in rendered


def test_manual_run_blocks_and_projects_symbol_mismatch(tmp_path):
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    run_response = client.post("/api/runs/manual", json={"symbol": "BTC-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    verdict = detail["plan_run"]["verdict"]
    audit = detail["plan_run"]["agent_audit_view"]
    assert audit["symbol_consistency"] == {
        "request_symbol": "BTC-USDT-SWAP",
        "snapshot_symbol": "BTC-USDT-SWAP",
        "plan_instrument": "ETH-USDT-SWAP",
        "consistent": False,
    }
    assert any(
        hit["rule_id"] == "production_control.symbol_consistency.mismatch" and hit["blocking"] is True
        for hit in verdict["rule_hits"]
    )


def test_manual_run_with_llm_tool_shadow_projects_real_tool_calls(tmp_path):
    config_path = tmp_path / "llm-tool-shadow.yaml"
    config_path.write_text(
        """
shadow:
  worker_mode: llm_tool_shadow
""".strip(),
        encoding="utf-8",
    )
    client = TestClient(create_app(config_paths=["config/default.yaml", str(config_path)], data_dir=tmp_path))

    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    audit = detail_response.json()["data"]["plan_run"]["agent_audit_view"]
    skill_names = {item["skill_name"] for item in audit["tool_calls"]}
    assert {"realtime_search", "root_cause_search", "market_sentiment", "liquidity_order_book"}.issubset(skill_names)
    assert all(item["status"] == "ok" for item in audit["tool_calls"])
    assert any(item["can_satisfy_execution_fact"] is True for item in audit["tool_calls"])
    liquidity_call = next(item for item in audit["tool_calls"] if item["skill_name"] == "liquidity_order_book")
    assert set(liquidity_call["fact_refs"]) == {"mark", "index", "order_book"}
    assert any(worker["agent_name"] == "LiveFactAgent" and worker["tool_call_artifact_count"] == 1 for worker in audit["workers"])
    assert any(worker["agent_name"] == "RootCauseAgent" and worker["tool_call_artifact_count"] == 1 for worker in audit["workers"])
    assert any(worker["agent_name"] == "ExecutionRiskAgent" and worker["tool_call_artifact_count"] == 1 for worker in audit["workers"])


def test_run_detail_can_include_sanitized_llm_payloads_for_trace_review(tmp_path):
    """复盘页面显式请求时，应返回已脱敏的 LLM 请求/返回，方便 badcase 回放。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    ObservabilityRecorder(app.state.journal).record_llm_interaction(
        trace_id=trace_id,
        component="decision.final",
        provider="openai_compatible",
        model="gpt-test",
        request_payload={"messages": [{"role": "user", "content": "分析 ETH"}], "api_key": "secret"},
        response_payload={"choices": [{"message": {"content": "结论摘要"}}]},
        status="ok",
        duration_ms=456,
        prompt_tokens=21,
        completion_tokens=9,
        total_tokens=30,
        finish_reason="stop",
    )

    response = client.get(f"/api/runs/{trace_id}?include_payloads=true")

    assert response.status_code == 200
    body = response.json()
    interactions = body["data"]["llm_interactions"]
    assert interactions
    assert "request_json" in interactions[0]
    assert "response_json" in interactions[0]
    assert interactions[0]["duration_ms"] == 456
    assert interactions[0]["prompt_tokens"] == 21
    assert interactions[0]["completion_tokens"] == 9
    assert interactions[0]["total_tokens"] == 30
    assert interactions[0]["finish_reason"] == "stop"
    rendered = str(interactions).lower()
    assert "secret" not in rendered
    assert "<redacted>" in rendered


def test_unknown_trace_returns_stable_error_envelope(tmp_path):
    """前端依赖稳定错误码，而不是解析中文错误文本。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/runs/not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "trace_not_found"
