from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_manual_alert.api.app import create_app
from crypto_manual_alert.observability import ObservabilityRecorder


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
    assert body["data"]["verdict"]["allowed"] is True


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
    )

    response = client.get(f"/api/runs/{trace_id}?include_payloads=true")

    assert response.status_code == 200
    body = response.json()
    interactions = body["data"]["llm_interactions"]
    assert interactions
    assert "request_json" in interactions[0]
    assert "response_json" in interactions[0]
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
