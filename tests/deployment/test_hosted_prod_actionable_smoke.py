from __future__ import annotations

import importlib.util
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "deployment" / "smoke_hosted_prod_actionable.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("smoke_hosted_prod_actionable", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Handler(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, str, Any]] = {}
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def do_GET(self) -> None:
        self._respond("GET")

    def do_POST(self) -> None:
        self._respond("POST")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _respond(self, method: str) -> None:
        payload = None
        if method == "POST":
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body) if body else None
        self.calls.append((method, self.path, payload))
        status, content_type, body = self.routes.get(
            (method, self.path),
            (404, "application/json", {"ok": False, "error": {"code": "not_found"}}),
        )
        encoded = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _start_server(routes: dict[tuple[str, str], tuple[int, str, Any]]):
    class Handler(_Handler):
        pass

    Handler.routes = routes
    Handler.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, Handler


def _base_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}"


def _prod_config() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "trading": {"manual_execution_required": True, "auto_order_enabled": False},
        "decision": {
            "engine": "openai_compatible",
            "final_input_mode": "legacy_prompt",
            "candidate_sidecar_mode": "disabled",
        },
        "market_data": {"provider": "okx_public"},
        "notification": {"enabled": True},
        "macro_event": {
            "provider": "no_active_event",
            "operator_ref": "ops:macro-desk",
            "confirmed_at": now.isoformat(),
            "source_ref": "calendar:no-high-impact",
            "assertion_horizon": "6h",
            "valid_until": (now + timedelta(hours=6)).isoformat(),
        },
        "workflow": {"execution_mode": "legacy_baseline"},
        "readiness": {
            "prod_actionable": {
                "status": "ready",
                "prod_actionable_ready": True,
                "production_main_path_ready": True,
                "main_path_blockers": [],
            }
        },
    }


def _run_detail(
    trace_id: str,
    *,
    notification_status: str = "sent",
    notification_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc) + timedelta(seconds=5)
    return {
        "trace": {"trace_id": trace_id, "allowed": True},
        "plan_run": {
            "parsed_plan": {"manual_execution_required": True, "main_action": "trigger long"},
            "verdict": {"allowed": True},
            "business_summary": {
                "decision_label": "可人工复核",
                "notification": {"enabled": True, "status": notification_status},
            },
            "agent_audit_view": {
                "available": True,
                "query_semantics": {"mode": "audit_note", "drives_final_input": False},
                "input_lineage": {"production_final_input_mode": "legacy_prompt"},
                "gates": {"production_control_gate": {"allowed": True}},
                "evidence_sources": [
                    {
                        "evidence_ref": "evidence:okx-mark",
                        "source_type": "exchange_native",
                        "source_tier": "exchange_native",
                        "freshness_status": "fresh",
                        "can_satisfy_execution_fact": True,
                    }
                ],
                "source_freshness": [
                    {
                        "source_type": "exchange_native",
                        "source_tier": "exchange_native",
                        "freshness_status": "fresh",
                        "count": 3,
                        "can_satisfy_execution_fact_count": 3,
                        "missing_execution_facts": [],
                    }
                ],
            },
        },
        "llm_interactions": [
            {
                "component": "decision.final",
                "provider": "openai_compatible",
                "model": "real-production-model",
                "endpoint": "/v1/chat/completions",
                "status": "ok",
                "total_tokens": 900,
            }
        ],
        "notification_history": notification_history
        if notification_history is not None
        else [
            {
                "channel": "bark",
                "status": notification_status,
                "ok": notification_status == "sent",
                "status_code": 200 if notification_status == "sent" else 500,
                "created_at": now.isoformat(),
            }
        ],
        "result_review": {"status": "not_collected"},
    }


def _routes(trace_id: str, *, detail: dict[str, Any] | None = None) -> dict[tuple[str, str], tuple[int, str, Any]]:
    return {
        ("GET", "/api/system/health"): (
            200,
            "application/json",
            {"ok": True, "data": {"service": "crypto-manual-alert"}},
        ),
        ("GET", "/api/system/config"): (200, "application/json", {"ok": True, "data": _prod_config()}),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace_id": trace_id,
                    "plan": {"manual_execution_required": True, "instrument": "ETH-USDT-SWAP"},
                    "verdict": {"allowed": True},
                    "business_summary": {"notification": {"status": "sent"}},
                    "result_review": {"status": "not_collected"},
                },
            },
        ),
        ("GET", f"/api/runs/{trace_id}"): (
            200,
            "application/json",
            {"ok": True, "data": detail or _run_detail(trace_id)},
        ),
    }


def _routes_with_config(
    trace_id: str,
    config: dict[str, Any],
    *,
    detail: dict[str, Any] | None = None,
) -> dict[tuple[str, str], tuple[int, str, Any]]:
    routes = _routes(trace_id, detail=detail)
    routes[("GET", "/api/system/config")] = (200, "application/json", {"ok": True, "data": config})
    return routes


def test_hosted_prod_actionable_smoke_requires_real_run_level_evidence():
    module = _load_module()
    trace_id = "trace-prod-actionable"
    server, handler = _start_server(_routes(trace_id))
    try:
        result = module.run_smoke(
            api_base=_base_url(server),
            symbol="ETH-USDT-SWAP",
            query="真实生产门禁：验证 ETH 人工提醒",
            horizon="6h",
            timeout=2.0,
            allow_local_api_base=True,
        )
    finally:
        server.shutdown()

    assert result["ok"] is True
    assert result["smoke_profile"] == "hosted_prod_actionable"
    assert result["proof_level"] == "prod-actionable"
    assert result["trace_id"] == trace_id
    assert result["allowed"] is True
    assert result["manual_execution_required"] is True
    assert result["auto_order_enabled"] is False
    assert result["llm_interaction_status"] == "ok"
    assert result["market_evidence"] == "exchange_native_fresh_execution_fact"
    assert result["notification_status"] == "sent"
    manual_call = next(call for call in handler.calls if call[0:2] == ("POST", "/api/runs/manual"))
    assert manual_call[2]["query"] == "真实生产门禁：验证 ETH 人工提醒"


def test_hosted_prod_actionable_smoke_can_write_proof_manifest(tmp_path, monkeypatch):
    module = _load_module()
    trace_id = "trace-prod-proof-output"
    proof_path = tmp_path / "hosted-prod-actionable-proof.json"
    server, _handler = _start_server(_routes(trace_id))
    monkeypatch.setattr(module, "_assert_public_https_api_base", lambda *_args, **_kwargs: None)
    try:
        exit_code = module.main(
            [
                "--api-base",
                _base_url(server),
                "--symbol",
                "ETH-USDT-SWAP",
                "--query",
                "真实生产门禁：验证 ETH 人工提醒",
                "--horizon",
                "6h",
                "--timeout",
                "2",
                "--proof-output",
                str(proof_path),
            ]
        )
    finally:
        server.shutdown()

    assert exit_code == 0
    manifest = json.loads(proof_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "2026-07-09.hosted-prod-actionable-proof.v1"
    assert manifest["smoke_profile"] == "hosted_prod_actionable"
    assert manifest["proof_level"] == "prod-actionable"
    assert manifest["trace_id"] == trace_id
    assert manifest["api_base_url"] == _base_url(server)
    assert manifest["prod_actionable_proven"] is True
    assert manifest["real_outcome_proven"] is False
    assert manifest["does_not_prove"] == "hosted_real_outcome"
    assert manifest["config_digest"]
    assert manifest["run_detail_digest"]
    assert manifest["run_detail_summary"]["allowed"] is True
    assert manifest["run_detail_summary"]["manual_execution_required"] is True
    assert manifest["run_detail_summary"]["decision_final_model"] == "real-production-model"
    assert manifest["run_detail_summary"]["exchange_native_fresh_evidence"] is True
    assert manifest["run_detail_summary"]["bark_sent"] is True


def test_hosted_prod_actionable_smoke_rejects_localhost_api_base_by_default():
    module = _load_module()
    trace_id = "trace-prod-localhost"
    server, _handler = _start_server(_routes(trace_id))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="public HTTPS API base"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_ready_config_without_macro_event_metadata():
    module = _load_module()
    trace_id = "trace-prod-missing-macro-metadata"
    config = _prod_config()
    config["macro_event"].pop("operator_ref")
    config["macro_event"].pop("valid_until")
    config["readiness"]["prod_actionable"]["status"] = "ready"
    config["readiness"]["prod_actionable"]["prod_actionable_ready"] = True
    server, _handler = _start_server(_routes_with_config(trace_id, config))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="macro_event metadata"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_expired_macro_event_assertion():
    module = _load_module()
    trace_id = "trace-prod-expired-macro-event"
    config = _prod_config()
    config["macro_event"]["valid_until"] = "2000-01-01T00:00:00+00:00"
    server, _handler = _start_server(_routes_with_config(trace_id, config))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="unexpired macro_event valid_until"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_macro_event_valid_until_without_timezone():
    module = _load_module()
    trace_id = "trace-prod-macro-event-no-timezone"
    config = _prod_config()
    config["macro_event"]["valid_until"] = "2999-01-01T00:00:00"
    server, _handler = _start_server(_routes_with_config(trace_id, config))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="unexpired macro_event valid_until"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_mock_model_even_when_other_evidence_passes():
    module = _load_module()
    trace_id = "trace-prod-mock-model"
    detail = _run_detail(trace_id)
    detail["llm_interactions"][0]["model"] = "mock-crypto-plan"
    server, _handler = _start_server(_routes(trace_id, detail=detail))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="real non-mock"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_mock_model_name_infix():
    module = _load_module()
    trace_id = "trace-prod-mock-model-infix"
    detail = _run_detail(trace_id)
    detail["llm_interactions"][0]["model"] = "gpt-mock-prod"
    server, _handler = _start_server(_routes(trace_id, detail=detail))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="real non-mock"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_missing_bark_sent_evidence():
    module = _load_module()
    trace_id = "trace-prod-no-bark"
    server, _handler = _start_server(_routes(trace_id, detail=_run_detail(trace_id, notification_status="failed")))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="Bark notification must be sent"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_old_bark_sent_notification():
    module = _load_module()
    trace_id = "trace-prod-old-bark-sent"
    detail = _run_detail(
        trace_id,
        notification_history=[
            {
                "channel": "bark",
                "status": "sent",
                "ok": True,
                "status_code": 200,
                "created_at": "2000-01-01T00:00:00+00:00",
            }
        ],
    )
    server, _handler = _start_server(_routes(trace_id, detail=detail))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="Bark notification must be sent"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_non_2xx_bark_sent_notification():
    module = _load_module()
    trace_id = "trace-prod-bark-sent-500"
    detail = _run_detail(
        trace_id,
        notification_history=[
            {
                "channel": "bark",
                "status": "sent",
                "ok": True,
                "status_code": 500,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )
    server, _handler = _start_server(_routes(trace_id, detail=detail))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="Bark notification must be sent"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_bark_failure_even_when_ok_flag_is_true():
    module = _load_module()
    trace_id = "trace-prod-bark-failed-ok-true"
    detail = _run_detail(
        trace_id,
        notification_history=[{"channel": "bark", "status": "failed", "ok": True}],
    )
    server, _handler = _start_server(_routes(trace_id, detail=detail))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="Bark notification must be sent"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_non_bark_sent_notification():
    module = _load_module()
    trace_id = "trace-prod-non-bark-sent"
    detail = _run_detail(
        trace_id,
        notification_history=[{"channel": "email", "status": "sent", "ok": True}],
    )
    server, _handler = _start_server(_routes(trace_id, detail=detail))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="Bark notification must be sent"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_requires_main_path_readiness_fields():
    module = _load_module()
    trace_id = "trace-prod-main-path-not-ready"
    config = _prod_config()
    config["readiness"]["prod_actionable"]["production_main_path_ready"] = False
    config["readiness"]["prod_actionable"]["main_path_blockers"] = [
        "workflow.execution_mode must be legacy_baseline for prod-actionable"
    ]
    server, _handler = _start_server(_routes_with_config(trace_id, config))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="production main path"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_hostname_resolving_private_ip(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "_hostname_addresses", lambda hostname: ["10.0.0.5"], raising=False)

    with pytest.raises(module.HostedProdActionableSmokeError, match="public HTTPS API base"):
        module._assert_public_https_api_base("https://prod.example.test", allow_local_api_base=False)


def test_hosted_prod_actionable_smoke_rejects_missing_exchange_native_evidence():
    module = _load_module()
    trace_id = "trace-prod-no-exchange-evidence"
    detail = _run_detail(trace_id)
    detail["plan_run"]["agent_audit_view"]["evidence_sources"][0]["source_type"] = "fixture"
    detail["plan_run"]["agent_audit_view"]["source_freshness"][0]["source_type"] = "fixture"
    detail["plan_run"]["agent_audit_view"]["source_freshness"][0]["can_satisfy_execution_fact_count"] = 0
    server, _handler = _start_server(_routes(trace_id, detail=detail))
    try:
        with pytest.raises(module.HostedProdActionableSmokeError, match="exchange-native fresh execution evidence"):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_local_okx_base_url_even_with_ready_provider():
    module = _load_module()
    trace_id = "trace-prod-local-okx-base"
    config = _prod_config()
    config["market_data"]["okx_base_url"] = "http://127.0.0.1:8012"
    config["readiness"]["market_data"] = {"status": "ready", "provider": "okx_public"}
    server, _handler = _start_server(_routes_with_config(trace_id, config))
    try:
        with pytest.raises(
            module.HostedProdActionableSmokeError,
            match="market_data.okx_base_url unset or https://www.okx.com",
        ):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()


def test_hosted_prod_actionable_smoke_rejects_unsafe_market_readiness():
    module = _load_module()
    trace_id = "trace-prod-unsafe-market"
    config = _prod_config()
    config["market_data"]["okx_base_url"] = "https://www.okx.com"
    config["readiness"]["market_data"] = {"status": "unsafe", "provider": "okx_public"}
    server, _handler = _start_server(_routes_with_config(trace_id, config))
    try:
        with pytest.raises(
            module.HostedProdActionableSmokeError,
            match="readiness.market_data.status!=unsafe",
        ):
            module.run_smoke(
                api_base=_base_url(server),
                symbol="ETH-USDT-SWAP",
                query="真实生产门禁：验证 ETH 人工提醒",
                horizon="6h",
                timeout=2.0,
                allow_local_api_base=True,
            )
    finally:
        server.shutdown()
