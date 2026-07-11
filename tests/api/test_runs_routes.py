from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from crypto_manual_alert.api.app import create_app
from crypto_manual_alert.decision.final_engine import OpenAICompatibleDecisionEngine
from crypto_manual_alert.domain import DecisionPlan, NotificationResult, RiskVerdict
from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow
from crypto_manual_alert.market.providers import OkxPublicMarketDataProvider
from crypto_manual_alert.research_pipeline.core import StaticResearchPlanner
from crypto_manual_alert.research_pipeline.leader_synthesizers import StaticLeaderResearchSynthesizer
from crypto_manual_alert.research_pipeline.search_adapters import DisabledSearchAdapter
from crypto_manual_alert.telemetry.observability import ObservabilityRecorder
from crypto_manual_alert.workflow.executor import RunExecutor
from crypto_manual_alert.workflow.legacy_plan_runner import PlanRunner
from crypto_manual_alert.workflow.results import DecisionStepResult


def _okx_http_get(path: str, params: dict[str, str]) -> dict:
    ts = str(int(time.time() * 1000))
    if path == "/api/v5/market/ticker":
        return {"code": "0", "data": [{"last": "3500", "bidPx": "3499", "askPx": "3501", "ts": ts}]}
    if path == "/api/v5/public/mark-price":
        return {"code": "0", "data": [{"markPx": "3499", "ts": ts}]}
    if path == "/api/v5/market/index-tickers":
        assert params == {"instId": "ETH-USDT"}
        return {"code": "0", "data": [{"instId": "ETH-USDT", "idxPx": "3498", "ts": ts}]}
    if path == "/api/v5/public/funding-rate":
        return {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": ts}]}
    if path == "/api/v5/public/open-interest":
        return {"code": "0", "data": [{"oi": "100000", "ts": ts}]}
    if path == "/api/v5/market/books":
        return {"code": "0", "data": [{"asks": [["3501", "10"]], "bids": [["3499", "10"]], "ts": ts}]}
    if path == "/api/v5/market/candles":
        return {"code": "0", "data": [[ts, "3490", "3510", "3480", "3500", "100"]]}
    raise AssertionError(f"unexpected OKX path: {path}")


def _with_complete_no_active_event_assertion(config):
    confirmed_at, valid_until = _future_no_active_event_window()
    return replace(
        config,
        macro_event=replace(
            config.macro_event,
            provider="no_active_event",
            no_active_event_operator_ref="ops:macro-desk",
            no_active_event_confirmed_at=confirmed_at,
            no_active_event_source_ref="calendar:operator-verified:no-high-impact",
            no_active_event_horizon="6h",
            no_active_event_valid_until=valid_until,
        ),
    )


def _decision_outcome(
    *,
    decision_ref: str,
    source_type: str,
    matured: bool,
    plan: dict,
    evaluation_target: str = "legacy_final",
) -> DecisionOutcome:
    return DecisionOutcome(
        decision_ref=decision_ref,
        evaluation_target=evaluation_target,
        symbol=plan["instrument"],
        action=plan["main_action"],
        probability=plan.get("probability"),
        entry_price=plan.get("entry_trigger"),
        stop_price=plan.get("stop_price"),
        target_1=plan.get("target_1"),
        target_2=plan.get("target_2"),
        window=OutcomeWindow(
            name="6h",
            symbol=plan["instrument"],
            interval="1H",
            source_type=source_type,
            window_start="2026-07-07T00:00:00+00:00",
            window_end="2026-07-07T06:00:00+00:00",
            collected_at="2026-07-07T06:01:00+00:00",
            open_price=100.0,
            high_price=112.0,
            low_price=96.0,
            close_price=108.0,
            matured=matured,
        ),
    )


def _future_no_active_event_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return (now - timedelta(minutes=30)).isoformat(), (now + timedelta(hours=6)).isoformat()


class _SuccessfulNotifier:
    def __init__(self):
        self.sent: list[tuple[str, bool]] = []

    def send(self, plan: DecisionPlan, verdict: RiskVerdict) -> NotificationResult:
        self.sent.append((plan.plan_id, verdict.allowed))
        return NotificationResult(ok=True, status_code=200)


class _OpenAIChatCompletionResponse:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {"content": self._content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 180,
                "completion_tokens": 96,
                "total_tokens": 276,
            },
        }


class _OpenAIChatCompletionClient:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    def post(self, url: str, *, headers: dict, json: dict) -> _OpenAIChatCompletionResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _OpenAIChatCompletionResponse(self.content)


def _production_like_decision_json() -> str:
    return json.dumps(
        {
            "instrument": "ETH-USDT-SWAP",
            "main_action": "trigger long",
            "horizon": "6h",
            "reference_price": 3500,
            "entry_trigger": 3510,
            "stop_price": 3435,
            "target_1": 3580,
            "target_2": 3660,
            "probability": 0.58,
            "position_size_class": "light",
            "max_leverage": 2,
            "risk_pct": 0.25,
            "expires_in_seconds": 90,
            "why_not_opposite": "BTC 结构尚未确认向下，ETH 触发位上方仍有反弹空间。",
            "invalidation": "如果 OKX mark price 跌破 3435，则本次手动提醒失效。",
            "unavailable_data": [],
            "manual_execution_required": True,
            "notes": "真实生产依赖由测试桩模拟返回；该测试只验证 production-intent 主链契约。",
        },
        ensure_ascii=False,
    )


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
    assert body["data"]["plan"]["plan_id"]
    assert body["data"]["plan"]["expires_at"]
    assert body["data"]["plan"]["instrument"] == "ETH-USDT-SWAP"
    assert body["data"]["plan"]["main_action"] == "trigger long"
    assert body["data"]["verdict"]["allowed"] is False
    assert any(
        hit["rule_id"] == "production_control.candidate.action_not_allowed"
        for hit in body["data"]["verdict"]["rule_hits"]
    )
    summary = body["data"]["business_summary"]
    assert summary["title"] == "ETH-USDT-SWAP 手动提醒计划"
    assert summary["decision_label"] == "本地样本"
    assert "本地样本" in summary["mode_notice"]
    assert "未调用真实 LLM" in summary["mode_notice"]
    assert summary["price_levels"]["entry_trigger"] == body["data"]["plan"]["entry_trigger"]
    assert summary["notification"]["status"] == "disabled"
    assert any("人工" in item for item in summary["next_steps"])
    assert any("不自动下单" in item for item in [summary["safety_notice"], *summary["next_steps"]])


def test_manual_run_response_uses_persisted_business_summary(tmp_path):
    """手动提交后的即时结果必须和详情页使用同一份完整产品投影。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.post(
        "/api/runs/manual",
        json={"symbol": "ETH-USDT-SWAP", "query": "评估 ETH 手动操作计划", "horizon": "6h"},
    )

    assert response.status_code == 200
    body = response.json()
    trace_id = body["data"]["trace_id"]
    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    immediate_summary = body["data"]["business_summary"]
    immediate_review = body["data"]["result_review"]
    persisted_summary = detail_response.json()["data"]["plan_run"]["business_summary"]
    persisted_review = detail_response.json()["data"]["result_review"]
    assert immediate_summary == persisted_summary
    assert immediate_review == persisted_review
    assert immediate_review["status"] == "not_collected"
    assert immediate_review["label"] == "尚未产生复盘结果"
    assert immediate_review["quality_scope"] == "none"
    assert immediate_summary["risk_bullets"]
    assert immediate_summary["data_gap_bullets"]
    assert immediate_summary["evidence_bullets"]


@pytest.mark.parametrize(
    ("projection", "error_code"),
    [
        (None, "manual_run_projection_missing_detail"),
        ({}, "manual_run_projection_missing_plan_run"),
        (
            {
                "plan_run": {"parsed_plan": {}, "verdict": {}},
                "result_review": {"status": "not_collected"},
            },
            "manual_run_projection_missing_business_summary",
        ),
        (
            {
                "plan_run": {
                    "parsed_plan": {},
                    "verdict": {},
                    "business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"},
                },
            },
            "manual_run_projection_missing_result_review",
        ),
    ],
)
def test_manual_run_response_fails_loudly_when_persisted_projection_missing(tmp_path, projection, error_code):
    """手动运行成功后若持久化产品投影读不回，API 不能拼 fallback 伪装成功。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)

    class MissingProjectionRepository:
        def get_run_detail(self, trace_id, *, include_payloads=False):
            return projection

    app.state.query_repository = MissingProjectionRepository()
    client = TestClient(app)

    response = client.post(
        "/api/runs/manual",
        json={"symbol": "ETH-USDT-SWAP", "query": "评估 ETH 手动操作计划", "horizon": "6h"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["ok"] is False
    assert body["data"] is None
    assert body["error"]["code"] == error_code
    assert body["trace_id"]


def test_manual_run_response_preserves_normalized_plan_fields_when_payload_has_overlaps(tmp_path):
    """持久化 payload 可补充业务字段，但不能覆盖即时响应的稳定 plan shape。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)

    class OverlappingPayloadAdapter:
        def __init__(self, adapter_config, journal):
            self.journal = journal

        def run(self, context):
            trace_id = context.run_id
            self.journal.append_trace(
                trace_id=trace_id,
                created_at="2026-07-08T00:00:00+00:00",
                run_type=context.request.run_type,
                symbol=context.symbol,
                horizon=context.horizon,
                status="running",
                metadata={},
            )
            plan = DecisionPlan.from_payload(
                {
                    "instrument": context.symbol,
                    "main_action": "no trade",
                    "horizon": "6h",
                    "manual_execution_required": True,
                    "expires_in_seconds": 90,
                    "expires_at": None,
                    "reference_price": 3500,
                    "entry_trigger": None,
                    "stop_price": None,
                    "target_1": None,
                    "target_2": None,
                    "probability": 0.51,
                    "notes": "Raw payload contains extra business context.",
                    "extra_business_context": "kept for UI",
                }
            )
            verdict = RiskVerdict(allowed=False, reasons=["test block"])
            self.journal.append_plan_run(
                plan.plan_id,
                "blocked",
                {
                    "trace_id": trace_id,
                    "parsed_plan": plan.raw,
                    "verdict": verdict.to_public_dict(),
                    "analysis": {"data_gaps": ["event status"]},
                    "facts_gate": {"reasons": ["missing execution fact"], "missing_execution_facts": ["mark"]},
                    "production_control_gate": {"allowed": False, "reasons": ["test block"], "rule_hits": []},
                    "evidence_snapshot": {"source": "fixture", "symbol": context.symbol},
                },
            )
            app.state.journal.finish_trace(
                trace_id=trace_id,
                ended_at="2026-07-08T00:00:01+00:00",
                status="blocked",
                final_plan_id=plan.plan_id,
                final_action=plan.main_action,
                allowed=False,
                metadata={},
            )
            return DecisionStepResult(trace_id=trace_id, plan=plan, verdict=verdict)

    app.state.executor = RunExecutor(
        config=app.state.config,
        journal=app.state.journal,
        legacy_adapter_factory=OverlappingPayloadAdapter,
    )
    client = TestClient(app)

    response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})

    assert response.status_code == 200
    plan = response.json()["data"]["plan"]
    assert plan["plan_id"]
    assert isinstance(plan["expires_at"], str)
    assert plan["expires_at"] != "None"
    assert plan["expires_at"] is not None
    assert plan["extra_business_context"] == "kept for UI"
    assert plan["manual_execution_required"] is True


def test_manual_run_staging_actionable_path_allows_manual_review_without_auto_order(tmp_path):
    """H1 staging/actionable path must be proven through the real manual-run API.

    This test exercises the same entry point as the frontend: POST /api/runs/manual.
    It uses the staging overlay plus deterministic OKX public responses so the
    exchange-native execution facts and no-active-event assertion satisfy the
    production gate without using external network or trade keys.
    """
    app = create_app(config_paths=["config/default.yaml", "config/staging.yaml"], data_dir=tmp_path)
    app.state.config = _with_complete_no_active_event_assertion(app.state.config)

    class ActionableLegacyAdapter:
        def __init__(self, adapter_config, journal):
            self.runner = PlanRunner(
                adapter_config,
                journal,
                market_provider=OkxPublicMarketDataProvider(adapter_config, http_get=_okx_http_get),
            )

        def run(self, context):
            return self.runner.run_once(context.symbol, run_context=context)

    app.state.executor = RunExecutor(
        config=app.state.config,
        journal=app.state.journal,
        legacy_adapter_factory=ActionableLegacyAdapter,
    )
    client = TestClient(app)

    response = client.post(
        "/api/runs/manual",
        json={"symbol": "ETH-USDT-SWAP", "query": "评估 ETH 可人工复核计划", "horizon": "6h"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["plan"]["main_action"] == "trigger long"
    assert body["data"]["plan"]["manual_execution_required"] is True
    assert body["data"]["verdict"]["allowed"] is True
    assert body["data"]["business_summary"]["decision_label"] == "可人工复核"
    assert "本地/预发证明" in body["data"]["business_summary"]["mode_notice"]
    assert "不是生产成功" in body["data"]["business_summary"]["mode_notice"]
    assert "人工核对" in " ".join(body["data"]["business_summary"]["next_steps"])
    assert app.state.config.trading.auto_order_enabled is False
    assert app.state.config.trading.manual_execution_required is True

    trace_id = body["data"]["trace_id"]
    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["trace"]["allowed"] is True
    assert detail["trace"]["final_action"] == "trigger long"
    plan_run = detail["plan_run"]
    assert plan_run["verdict"]["allowed"] is True
    assert plan_run["business_summary"]["decision_label"] == "可人工复核"
    assert "本地/预发证明" in plan_run["business_summary"]["mode_notice"]
    assert "不是生产成功" in plan_run["business_summary"]["mode_notice"]
    assert plan_run["parsed_plan"]["manual_execution_required"] is True
    facts_gate = plan_run["agent_audit_view"]["facts_gate"]
    assert facts_gate["missing_execution_facts"] == []
    assert facts_gate["missing_event_facts"] == []
    production_gate = plan_run["agent_audit_view"]["gates"]["production_control_gate"]
    assert production_gate["allowed"] is True
    assert not any(
        hit["rule_id"] == "production_control.candidate.action_not_allowed"
        for hit in production_gate.get("rule_hits", [])
    )


def test_manual_run_production_intent_path_projects_model_notification_and_legacy_lineage(
    tmp_path,
    monkeypatch,
):
    """Production-intent API proof must cover the whole readable manual-alert chain.

    This is not a hosted production proof: the OpenAI-compatible decision response,
    OKX public HTTP, and Bark send are deterministic test doubles. It protects the
    production main path contract by exercising the real FastAPI entry, workflow,
    gates, persistence, notification journal, and UI-facing projections together.
    """

    confirmed_at, valid_until = _future_no_active_event_window()
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini-prod")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("BARK_DEVICE_KEY", "test-bark-device")
    monkeypatch.setenv("MACRO_EVENT_OPERATOR_REF", "ops:macro-desk")
    monkeypatch.setenv("MACRO_EVENT_CONFIRMED_AT", confirmed_at)
    monkeypatch.setenv("MACRO_EVENT_SOURCE_REF", "calendar:ops:no-high-impact")
    monkeypatch.setenv("MACRO_EVENT_ASSERTION_HORIZON", "6h")
    monkeypatch.setenv("MACRO_EVENT_VALID_UNTIL", valid_until)

    app = create_app(
        config_paths=["config/default.yaml", "config/prod.yaml", "config/staging.yaml"],
        data_dir=tmp_path,
    )
    openai_client = _OpenAIChatCompletionClient(_production_like_decision_json())
    notifier = _SuccessfulNotifier()

    class ProductionIntentLegacyAdapter:
        def __init__(self, adapter_config, journal):
            self.runner = PlanRunner(
                adapter_config,
                journal,
                market_provider=OkxPublicMarketDataProvider(adapter_config, http_get=_okx_http_get),
                decision_engine=OpenAICompatibleDecisionEngine(
                    base_url=adapter_config.decision.openai_base_url,
                    api_key="test-openai-key",
                    model=adapter_config.decision.openai_model,
                    timeout_seconds=adapter_config.decision.timeout_seconds,
                    client=openai_client,
                ),
                notifier=notifier,
                research_planner=StaticResearchPlanner(),
                search_adapter=DisabledSearchAdapter(),
                leader_synthesizer=StaticLeaderResearchSynthesizer(),
            )

        def run(self, context):
            return self.runner.run_once(context.symbol, run_context=context)

    app.state.executor = RunExecutor(
        config=app.state.config,
        journal=app.state.journal,
        legacy_adapter_factory=ProductionIntentLegacyAdapter,
    )
    client = TestClient(app)

    config_response = client.get("/api/system/config")
    assert config_response.status_code == 200
    readiness = config_response.json()["data"]["readiness"]["prod_actionable"]
    assert readiness["prod_actionable_ready"] is True
    assert readiness["production_main_path_ready"] is True
    assert readiness["candidate_sidecar_disabled"] is True
    assert readiness["main_path_blockers"] == []

    response = client.post(
        "/api/runs/manual",
        json={"symbol": "ETH-USDT-SWAP", "query": "生产意图主链契约 smoke", "horizon": "6h"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["plan"]["main_action"] == "trigger long"
    assert body["data"]["plan"]["manual_execution_required"] is True
    assert body["data"]["verdict"]["allowed"] is True
    summary = body["data"]["business_summary"]
    assert summary["decision_label"] == "可人工复核"
    assert "当前已满足人工复核门槛" in summary["mode_notice"]
    assert "真实外部模型" in summary["mode_notice"]
    assert "真实 OKX" in summary["mode_notice"]
    assert "Bark" in summary["mode_notice"]
    assert summary["generation_summary"]["provider"] == "openai_compatible"
    assert summary["generation_summary"]["model"] == "gpt-4.1-mini-prod"
    assert summary["generation_summary"]["status"] == "ok"
    assert summary["notification"]["status"] == "sent"
    assert summary["notification"]["status_code"] == 200
    assert body["data"]["notification"]["status"] == "sent"
    immediate_contract = body["data"]["main_path_contract"]
    assert immediate_contract["proof_level"] == "production-intent-contract"
    assert immediate_contract["production_success"] is False
    assert immediate_contract["hosted_proof_required"] is True
    assert immediate_contract["does_not_prove"] == "hosted_prod_actionable"
    assert immediate_contract["runtime_role"] == "production_main"
    assert immediate_contract["final_input_contract"]["mode"] == "legacy_prompt"
    assert immediate_contract["final_input_contract"]["candidate_sidecar_mode"] == "disabled"
    assert immediate_contract["manual_only"]["manual_execution_required"] is True
    assert immediate_contract["manual_only"]["auto_order_enabled"] is False

    assert len(openai_client.calls) == 1
    assert notifier.sent == [(body["data"]["plan"]["plan_id"], True)]

    trace_id = body["data"]["trace_id"]
    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["trace"]["allowed"] is True
    assert detail["trace"]["final_action"] == "trigger long"
    assert detail["notification"]["status"] == "sent"
    assert detail["notification_history"][0]["channel"] == "bark"
    assert detail["notification_history"][0]["status"] == "sent"
    assert detail["notification_history"][0]["status_code"] == 200

    plan_run = detail["plan_run"]
    assert plan_run["business_summary"] == summary
    assert plan_run["main_path_contract"] == immediate_contract
    assert plan_run["verdict"]["allowed"] is True
    assert plan_run["final_input_selection"]["mode"] == "legacy_prompt"
    facts_gate = plan_run["agent_audit_view"]["facts_gate"]
    assert facts_gate["missing_execution_facts"] == []
    assert facts_gate["missing_event_facts"] == []
    production_gate = plan_run["agent_audit_view"]["gates"]["production_control_gate"]
    assert production_gate["allowed"] is True
    lineage = plan_run["agent_audit_view"]["input_lineage"]
    assert lineage["production_final_input_mode"] == "legacy_prompt"
    assert plan_run["agent_audit_view"]["final_input_selection"]["mode"] == "legacy_prompt"

    llm_interaction = detail["llm_interactions"][0]
    assert llm_interaction["provider"] == "openai_compatible"
    assert llm_interaction["model"] == "gpt-4.1-mini-prod"
    assert llm_interaction["status"] == "ok"
    assert "request_json" not in llm_interaction
    assert "response_json" not in llm_interaction


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
    summary = detail["data"]["plan_run"]["business_summary"]
    assert summary["decision_label"] == "本地样本"
    assert summary["action_text"] == detail["data"]["plan_run"]["parsed_plan"]["main_action"]
    assert summary["price_levels"]["reference_price"] == detail["data"]["plan_run"]["parsed_plan"]["reference_price"]
    assert summary["risk_bullets"]
    assert summary["data_gap_bullets"]
    assert summary["notification"]["status"] == "disabled"
    assert "raw_decision" not in detail["data"]["plan_run"]
    assert all("request_json" not in item for item in detail["data"]["llm_interactions"])
    assert all("response_json" not in item for item in detail["data"]["llm_interactions"])


def test_run_list_projects_business_summary_and_notification_status(tmp_path):
    """提醒历史默认列表必须可读，不要求用户点进 raw/detail 才知道风险和通知状态。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    body = run_response.json()["data"]
    trace_id = body["trace_id"]
    plan_id = body["plan"]["plan_id"]

    app.state.journal.append_notification(plan_id, ok=True, status_code=200, error=None)

    list_response = client.get("/api/runs")

    assert list_response.status_code == 200
    item = list_response.json()["data"]["items"][0]
    assert item["trace_id"] == trace_id
    assert item["business_summary"]["decision_label"] == "本地样本"
    assert item["business_summary"]["action_text"] == "trigger long"
    assert item["business_summary"]["notification"]["status"] == "sent"
    assert item["business_summary"]["notification"]["status_code"] == 200
    assert "notification_history" not in item
    assert item["business_summary"]["risk_bullets"]
    assert item["business_summary"]["data_gap_bullets"]
    rendered = str(item)
    assert "raw_decision" not in rendered
    assert "request_json" not in rendered
    assert "response_json" not in rendered


def test_run_list_projects_result_review_status(tmp_path):
    """提醒历史默认列表应直接展示后续复盘状态，不要求用户进入详情页才知道结果是否已采集。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]

    list_response = client.get("/api/runs")

    assert list_response.status_code == 200
    item = list_response.json()["data"]["items"][0]
    assert item["trace_id"] == trace_id
    assert item["result_review"]["status"] == "not_collected"
    assert item["result_review"]["label"] == "尚未产生复盘结果"
    assert item["result_review"]["sample_count"] == 0
    assert item["result_review"]["can_score"] is False
    rendered = str(item)
    assert "decision_ref" not in rendered
    assert "mocked_outcome" not in rendered
    assert "exchange_native" not in rendered


def test_run_detail_projects_persisted_notification_status(tmp_path):
    """详情页业务摘要必须展示 journal 中真实记录的通知结果。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    plan_id = run_response.json()["data"]["plan"]["plan_id"]

    app.state.journal.append_notification(plan_id, ok=True, status_code=200, error=None)

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    notification = detail["plan_run"]["business_summary"]["notification"]
    assert notification["enabled"] is True
    assert notification["status"] == "sent"
    assert notification["status_code"] == 200
    assert notification["message"] == "Bark 已发送。"
    assert detail["notification"]["status"] == "sent"


def test_run_detail_notification_history_is_empty_without_notification_rows(tmp_path):
    """未发送通知时，详情页应明确返回空历史，而不是伪造成功记录。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["notification"]["status"] == "not_recorded"
    assert detail["notification_history"] == []
    assert detail["plan_run"]["business_summary"]["notification"]["status"] == "disabled"
    assert detail["result_review"]["status"] == "not_collected"
    assert detail["result_review"]["label"] == "尚未产生复盘结果"
    assert detail["result_review"]["quality_scope"] == "none"
    assert detail["result_review"]["sample_count"] == 0
    assert detail["result_review"]["can_score"] is False


def test_run_detail_links_mock_outcome_to_this_run_without_quality_claim(tmp_path):
    """单条提醒详情应能看到后续结果，但 mock outcome 必须保持可见性样本边界。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    run_data = run_response.json()["data"]
    trace_id = run_data["trace_id"]
    plan = run_data["plan"]
    plan_id = plan["plan_id"]

    app.state.outcome_store.upsert_outcomes(
        [
            _decision_outcome(
                decision_ref=f"{plan_id}:legacy_final",
                source_type="mocked_outcome",
                matured=True,
                plan=plan,
            ),
            _decision_outcome(
                decision_ref="other-plan:legacy_final",
                source_type="exchange_native",
                matured=True,
                plan=plan,
            )
        ]
    )

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    review = detail_response.json()["data"]["result_review"]
    assert review["status"] == "mock_visibility_only"
    assert review["label"] == "本地展示样本"
    assert review["message"] == "本地展示样本，不计入真实金融质量。"
    assert review["quality_scope"] == "visibility_only_not_financial_quality"
    assert review["sample_count"] == 1
    assert review["unscored_count"] == 1
    assert review["can_score"] is False
    assert review["items"][0]["source_label"] == "本地展示样本"
    assert review["items"][0]["target_label"] == "最终建议链路"
    assert review["items"][0]["unscored_label"] == "本地展示样本，不计入真实金融质量"
    assert "decision_ref" not in review["items"][0]


def test_run_detail_does_not_bind_trace_id_or_bare_plan_outcomes(tmp_path):
    """结果复盘只能关联当前最终 plan 的显式结果 ref，不能吃进宽泛标识。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    run_data = run_response.json()["data"]
    trace_id = run_data["trace_id"]
    plan = run_data["plan"]

    app.state.outcome_store.upsert_outcomes(
        [
            _decision_outcome(
                decision_ref=trace_id,
                source_type="exchange_native",
                matured=True,
                plan=plan,
            ),
            _decision_outcome(
                decision_ref=f"{trace_id}:legacy_final",
                source_type="exchange_native",
                matured=True,
                plan=plan,
            ),
            _decision_outcome(
                decision_ref=plan["plan_id"],
                source_type="exchange_native",
                matured=True,
                plan=plan,
            ),
        ]
    )

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    review = detail_response.json()["data"]["result_review"]
    assert review["status"] == "not_collected"
    assert review["sample_count"] == 0


def test_run_detail_links_exchange_native_scored_outcome_to_this_run(tmp_path):
    """交易所原生成熟结果样本才可以在单条提醒详情中标记为可评分。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    run_data = run_response.json()["data"]
    trace_id = run_data["trace_id"]
    plan = run_data["plan"]

    app.state.outcome_store.upsert_outcomes(
        [
            _decision_outcome(
                decision_ref=f"{plan['plan_id']}:legacy_final",
                source_type="exchange_native",
                matured=True,
                plan=plan,
            )
        ]
    )

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    review = detail_response.json()["data"]["result_review"]
    assert review["status"] == "scorable"
    assert review["label"] == "可评分"
    assert review["quality_scope"] == "exchange_native_financial_quality"
    assert review["sample_count"] == 1
    assert review["scored_count"] == 1
    assert review["can_score"] is True
    assert review["items"][0]["source_label"] == "交易所原生样本"
    assert review["items"][0]["unscored_label"] == "-"


def test_run_detail_keeps_mixed_real_and_mock_outcome_scope_honest(tmp_path):
    """混合样本不能把本地展示样本包进真实金融质量口径。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    run_data = run_response.json()["data"]
    trace_id = run_data["trace_id"]
    plan = run_data["plan"]

    app.state.outcome_store.upsert_outcomes(
        [
            _decision_outcome(
                decision_ref=f"{plan['plan_id']}:legacy_final",
                source_type="exchange_native",
                matured=True,
                plan=plan,
            ),
            _decision_outcome(
                decision_ref=f"{plan['plan_id']}:swarm_candidate_final",
                source_type="mocked_outcome",
                matured=True,
                plan=plan,
                evaluation_target="swarm_candidate_final",
            ),
        ]
    )

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    review = detail_response.json()["data"]["result_review"]
    assert review["status"] == "mixed_quality_scope"
    assert review["label"] == "部分可评分"
    assert review["quality_scope"] == "mixed_exchange_native_and_visibility_only"
    assert review["sample_count"] == 2
    assert review["scored_count"] == 1
    assert review["unscored_count"] == 1
    assert review["can_score"] is True
    assert "1 条交易所原生成熟样本可用于质量复盘" in review["message"]
    assert "其余样本不计入真实金融质量" in review["message"]


def test_run_detail_exposes_full_notification_history_without_payload_leak(tmp_path):
    """详情页需要展示完整通知历史，而不是只展示最后一次状态。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    plan_id = run_response.json()["data"]["plan"]["plan_id"]

    app.state.journal.append_notification(
        plan_id,
        ok=False,
        status_code=500,
        error="Bark timeout for https://api.day.app/device-secret/title?token=secret-token",
    )
    app.state.journal.append_notification(plan_id, ok=True, status_code=200, error=None)

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["notification"]["status"] == "sent"
    history = detail["notification_history"]
    assert [item["status"] for item in history] == ["sent", "failed"]
    assert [item["channel"] for item in history] == ["bark", "bark"]
    assert history[0]["status_code"] == 200
    assert history[1]["status_code"] == 500
    assert history[1]["error"] == "Bark timeout for <redacted-url>"
    assert [set(item) for item in history] == [
        {"id", "created_at", "channel", "ok", "status", "status_code", "error"},
        {"id", "created_at", "channel", "ok", "status", "status_code", "error"},
    ]
    rendered = str(history)
    assert plan_id not in rendered
    assert "BARK_DEVICE_KEY" not in rendered
    assert "device-secret" not in rendered
    assert "secret-token" not in rendered
    assert "https://api.day.app" not in rendered
    assert "request_json" not in rendered
    assert "response_json" not in rendered


def test_run_detail_redacts_notification_error_secret_shapes(tmp_path):
    """通知错误可能来自 HTTP/client 异常，API 投影层必须兜底脱敏。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    plan_id = run_response.json()["data"]["plan"]["plan_id"]

    app.state.journal.append_notification(
        plan_id,
        ok=False,
        status_code=401,
        error=(
            "Bark failed; Authorization: Bearer bearer-secret; "
            "BARK_DEVICE_KEY: bark-secret; {\"token\": \"json-token\", \"api_key\": \"api-secret\"}; "
            "device key device-secret"
        ),
    )

    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    history = detail_response.json()["data"]["notification_history"]
    error = history[0]["error"]
    assert "bearer-secret" not in error
    assert "bark-secret" not in error
    assert "json-token" not in error
    assert "api-secret" not in error
    assert "device-secret" not in error
    assert "BARK_DEVICE_KEY" not in error
    assert "device key" not in error.lower()
    assert "Authorization: Bearer <redacted>" in error
    assert "<redacted-secret>" in error


def test_manual_run_response_projects_notification_status(tmp_path):
    """同步手动运行响应应展示本次已写入的通知状态。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    notification = app.state.config.notification.__class__(
        **{**app.state.config.notification.__dict__, "enabled": True}
    )
    config = app.state.config.__class__(
        app=app.state.config.app,
        trading=app.state.config.trading,
        market_data=app.state.config.market_data,
        decision=app.state.config.decision,
        notification=notification,
        scheduler=app.state.config.scheduler,
        research=app.state.config.research,
        security=app.state.config.security,
        shadow=app.state.config.shadow,
        workflow=app.state.config.workflow,
        skill_providers=app.state.config.skill_providers,
        macro_event=app.state.config.macro_event,
        eval=app.state.config.eval,
    )
    app.state.config = config

    class SentNotifier:
        def send(self, plan, verdict):
            return NotificationResult(ok=True, status_code=200)

    class NotifyingLegacyAdapter:
        def __init__(self, adapter_config, journal):
            self.runner = PlanRunner(adapter_config, journal, notifier=SentNotifier())

        def run(self, context):
            return self.runner.run_once(context.symbol, run_context=context)

    app.state.executor = RunExecutor(
        config=config,
        journal=app.state.journal,
        legacy_adapter_factory=NotifyingLegacyAdapter,
    )
    client = TestClient(app)

    response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})

    assert response.status_code == 200
    notification_summary = response.json()["data"]["business_summary"]["notification"]
    assert notification_summary["enabled"] is True
    assert notification_summary["status"] == "sent"
    assert notification_summary["status_code"] == 200
    assert notification_summary["message"] == "Bark 已发送。"


def test_run_list_accepts_filter_and_pagination_params(tmp_path):
    """前端 Runs 工作台依赖真实查询参数，而不是本地拿最近 20 条假分页。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    app.state.journal.append_trace(
        trace_id="eth-allowed",
        created_at="2026-07-07T01:00:00+00:00",
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        status="running",
        metadata={},
    )
    app.state.journal.finish_trace(
        trace_id="eth-allowed",
        ended_at="2026-07-07T01:01:00+00:00",
        status="allowed",
        final_plan_id="plan-eth",
        final_action="trigger long",
        allowed=True,
        metadata={},
    )
    app.state.journal.append_trace(
        trace_id="btc-blocked",
        created_at="2026-07-07T02:00:00+00:00",
        run_type="manual",
        symbol="BTC-USDT-SWAP",
        horizon="6h",
        status="running",
        metadata={},
    )
    app.state.journal.finish_trace(
        trace_id="btc-blocked",
        ended_at="2026-07-07T02:01:00+00:00",
        status="blocked",
        final_plan_id="plan-btc",
        final_action="trigger short",
        allowed=False,
        metadata={},
    )
    app.state.journal.append_trace(
        trace_id="eth-failed",
        created_at="2026-07-07T03:00:00+00:00",
        run_type="manual",
        symbol="ETH-USDT-SWAP",
        horizon="6h",
        status="running",
        metadata={},
    )
    app.state.journal.finish_trace(
        trace_id="eth-failed",
        ended_at="2026-07-07T03:01:00+00:00",
        status="failed",
        final_plan_id=None,
        final_action=None,
        allowed=None,
        metadata={},
    )

    response = client.get("/api/runs?symbol=eth&status=allowed&allowed=true&limit=10&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert [item["trace_id"] for item in body["data"]["items"]] == ["eth-allowed"]
    assert body["data"]["items"][0]["allowed"] is True

    page_response = client.get("/api/runs?symbol=eth&limit=1&offset=0")
    page = page_response.json()["data"]
    assert [item["trace_id"] for item in page["items"]] == ["eth-failed"]
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert page["has_more"] is True
    assert page["next_offset"] == 1


def test_run_list_validation_errors_use_api_envelope(tmp_path):
    """FastAPI 参数校验错误也必须遵循统一 API envelope。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/runs?limit=abc")

    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["data"] is None
    assert body["trace_id"] is None
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"]
    assert body["error"]["details"]
    assert "detail" not in body["error"]
    assert any("limit" in str(item.get("loc", [])) for item in body["error"]["details"])


def test_manual_run_preserves_position_and_risk_mode_in_trace_context(tmp_path):
    """前端传入的 position/risk_mode 不能被后端默默丢弃。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    run_response = client.post(
        "/api/runs/manual",
        json={
            "symbol": "ETH-USDT-SWAP",
            "query": "评估 ETH 手动操作计划",
            "horizon": "6h",
            "position": {"side": "long", "size": "0.5", "entry_price": 3200},
            "risk_mode": "conservative",
        },
    )
    trace_id = run_response.json()["data"]["trace_id"]
    detail_response = client.get(f"/api/runs/{trace_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    run_context = detail["trace"]["metadata"]["run_context"]
    assert run_context["position"] == {"side": "long", "size": "0.5", "entry_price": 3200}
    assert run_context["risk_mode"] == "conservative"
    assert detail["plan_run"]["run_context"]["position"] == run_context["position"]
    assert detail["plan_run"]["run_context"]["risk_mode"] == "conservative"
    assert detail["plan_run"]["payload_keys"]


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
    plan_run = detail["plan_run"]
    assert plan_run["facts_gate"]["severity"] == "hard_fail"
    assert "mark" in plan_run["facts_gate"]["missing_execution_facts"]
    assert plan_run["production_control_gate"]["allowed"] is False
    assert any(
        hit["rule_id"] == "production_control.candidate.action_not_allowed"
        for hit in plan_run["production_control_gate"]["rule_hits"]
    )
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


def test_run_detail_rejects_payload_inclusion_when_diagnostic_routes_are_disabled(tmp_path):
    """Raw LLM payload review must be behind an explicit diagnostic boundary."""

    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]

    response = client.get(f"/api/runs/{trace_id}?include_payloads=true")

    assert response.status_code == 403
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "diagnostic_routes_disabled"


def test_run_detail_can_include_sanitized_llm_payloads_for_trace_review(tmp_path, monkeypatch):
    """复盘页面显式请求时，应返回已脱敏的 LLM 请求/返回，方便 badcase 回放。"""
    monkeypatch.setenv("DIAGNOSTIC_ROUTES_ENABLED", "true")
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


def test_run_detail_projects_safe_llm_completion_excerpt_without_raw_payloads(tmp_path):
    """默认详情接口应展示模型原始返回安全摘录，但不暴露完整 LLM payload。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    completion = "模型原始返回：ETH 等待 3512 触发后人工复核，跌破 3468 则本次计划失效。"
    ObservabilityRecorder(app.state.journal).record_llm_interaction(
        trace_id=trace_id,
        component="decision.final",
        provider="openai_compatible",
        model="gpt-live",
        request_payload={"messages": [{"role": "user", "content": "分析 ETH"}], "api_key": "secret"},
        response_payload={"choices": [{"message": {"content": completion}}]},
        status="ok",
        duration_ms=456,
        finish_reason="stop",
    )

    response = client.get(f"/api/runs/{trace_id}")

    assert response.status_code == 200
    body = response.json()
    generation = body["data"]["plan_run"]["business_summary"]["generation_summary"]
    assert generation["raw_completion_excerpt"] == completion
    assert generation["raw_completion_label"] == "模型原始返回摘录"
    assert body["data"]["llm_interactions"][0]["completion_excerpt"] == completion
    assert "request_json" not in body["data"]["llm_interactions"][0]
    assert "response_json" not in body["data"]["llm_interactions"][0]
    rendered_generation = str(generation)
    assert "choices" not in rendered_generation
    assert "request_json" not in rendered_generation
    assert "response_json" not in rendered_generation
    assert "secret" not in str(body).lower()


def test_run_detail_business_summary_uses_persisted_mock_llm_interaction(tmp_path):
    """详情页从 journal 回读时，也必须保留 mock LLM 路径提示。"""
    app = create_app(config_paths=["config/default.yaml"], data_dir=tmp_path)
    client = TestClient(app)
    run_response = client.post("/api/runs/manual", json={"symbol": "ETH-USDT-SWAP"})
    trace_id = run_response.json()["data"]["trace_id"]
    ObservabilityRecorder(app.state.journal).record_llm_interaction(
        trace_id=trace_id,
        component="decision.final",
        provider="openai_compatible",
        model="mock-crypto-plan",
        request_payload={"messages": [{"role": "user", "content": "ETH-USDT-SWAP"}], "api_key": "secret"},
        response_payload={"choices": [{"message": {"content": "{}"}}]},
        status="ok",
        duration_ms=12,
    )

    response = client.get(f"/api/runs/{trace_id}")

    assert response.status_code == 200
    summary = response.json()["data"]["plan_run"]["business_summary"]
    assert summary["decision_label"] == "模拟 LLM"
    assert "mock LLM" in summary["mode_notice"]
    assert "未调用真实 LLM" not in summary["mode_notice"]
    generation = summary["generation_summary"]
    assert generation["mode_label"] == "模型链路演练"
    assert generation["model"] == "mock-crypto-plan"
    assert generation["status_label"] == "模型已返回"
    assert generation["duration_text"] == "12 ms"
    assert generation["response_summary"] == "模型结论：触发做多；置信度 58%。"
    assert response.json()["data"]["llm_interactions"][0]["model"] == "mock-crypto-plan"
    assert "request_json" not in response.json()["data"]["llm_interactions"][0]
    rendered = str(generation)
    assert "request_json" not in rendered
    assert "response_json" not in rendered
    assert "choices" not in rendered


def test_unknown_trace_returns_stable_error_envelope(tmp_path):
    """前端依赖稳定错误码，而不是解析中文错误文本。"""
    client = TestClient(create_app(config_paths=["config/default.yaml"], data_dir=tmp_path))

    response = client.get("/api/runs/not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "trace_not_found"
