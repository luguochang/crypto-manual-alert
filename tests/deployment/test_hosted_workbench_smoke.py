from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "tools" / "deployment" / "smoke_hosted_workbench.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke_hosted_workbench", SMOKE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingHandler(BaseHTTPRequestHandler):
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
        status, content_type, response_body = self.routes.get(
            (method, self.path),
            (404, "application/json", {"ok": False, "error": {"code": "not_found", "message": "not found"}}),
        )
        if isinstance(response_body, str):
            encoded = response_body.encode("utf-8")
        else:
            encoded = json.dumps(response_body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _start_server(routes: dict[tuple[str, str], tuple[int, str, Any]]):
    class Handler(_RecordingHandler):
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


def test_hosted_workbench_smoke_checks_manual_run_and_detail_projection():
    module = _load_smoke_module()
    trace_id = "trace-hosted-123"
    api_routes = {
        ("GET", "/api/system/health"): (
            200,
            "application/json",
            {"ok": True, "data": {"service": "crypto-manual-alert"}},
        ),
        ("GET", "/api/system/config"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                    "decision": {"engine": "fixture"},
                    "market_data": {"provider": "fixture"},
                },
            },
        ),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace_id": trace_id,
                    "plan": {"manual_execution_required": True, "instrument": "ETH-USDT-SWAP"},
                    "verdict": {"allowed": False},
                    "business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"},
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
        ("GET", f"/api/runs/{trace_id}"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace": {"trace_id": trace_id, "allowed": False},
                    "plan_run": {
                        "business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"},
                        "parsed_plan": {"manual_execution_required": True},
                    },
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
    }
    frontend_routes = {
        ("GET", "/"): (200, "text/html", "<html><body>提醒控制台</body></html>"),
        ("GET", f"/runs/{trace_id}"): (200, "text/html", "<html><body>提醒详情</body></html>"),
    }
    api_server, api_handler = _start_server(api_routes)
    frontend_server, frontend_handler = _start_server(frontend_routes)
    try:
        result = module.run_smoke(
            api_base=_base_url(api_server),
            frontend_base=_base_url(frontend_server),
            symbol="ETH-USDT-SWAP",
            query="评估 ETH 手动提醒",
            horizon="6h",
            timeout=2.0,
        )
    finally:
        api_server.shutdown()
        frontend_server.shutdown()

    assert result["ok"] is True
    assert result["smoke_profile"] == "hosted_workbench"
    assert result["trace_id"] == trace_id
    assert result["manual_execution_required"] is True
    assert result["auto_order_enabled"] is False
    assert ("GET", "/api/system/health", None) in api_handler.calls
    assert ("GET", "/api/system/config", None) in api_handler.calls
    assert ("GET", "/", None) in frontend_handler.calls
    assert ("GET", f"/runs/{trace_id}", None) in frontend_handler.calls
    manual_call = next(call for call in api_handler.calls if call[0:2] == ("POST", "/api/runs/manual"))
    assert manual_call[2]["symbol"] == "ETH-USDT-SWAP"
    assert manual_call[2]["query"] == "评估 ETH 手动提醒"
    assert manual_call[2]["horizon"] == "6h"


def test_hosted_workbench_smoke_rejects_fixture_config_when_prod_config_required():
    module = _load_smoke_module()
    trace_id = "trace-hosted-fixture"
    api_routes = {
        ("GET", "/api/system/health"): (
            200,
            "application/json",
            {"ok": True, "data": {"service": "crypto-manual-alert"}},
        ),
        ("GET", "/api/system/config"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                    "decision": {"engine": "fixture", "candidate_sidecar_mode": "same_engine"},
                    "market_data": {"provider": "fixture"},
                    "notification": {"enabled": False},
                    "readiness": {"prod_actionable": {"status": "missing_env", "prod_actionable_ready": False}},
                },
            },
        ),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace_id": trace_id,
                    "plan": {"manual_execution_required": True, "instrument": "ETH-USDT-SWAP"},
                    "verdict": {"allowed": False},
                    "business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"},
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
        ("GET", f"/api/runs/{trace_id}"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace": {"trace_id": trace_id, "allowed": False},
                    "plan_run": {"business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"}},
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
    }
    frontend_routes = {
        ("GET", "/"): (200, "text/html", "<html><body>提醒控制台</body></html>"),
        ("GET", f"/runs/{trace_id}"): (200, "text/html", "<html><body>提醒详情</body></html>"),
    }
    api_server, _api_handler = _start_server(api_routes)
    frontend_server, _frontend_handler = _start_server(frontend_routes)
    try:
        with pytest.raises(module.HostedWorkbenchSmokeError, match="production config requires decision.engine=openai_compatible"):
            module.run_smoke(
                api_base=_base_url(api_server),
                frontend_base=_base_url(frontend_server),
                symbol="ETH-USDT-SWAP",
                query="评估 ETH 手动提醒",
                horizon="6h",
                timeout=2.0,
                require_prod_config=True,
            )
    finally:
        api_server.shutdown()
        frontend_server.shutdown()


def test_hosted_workbench_smoke_accepts_prod_config_with_explicit_runtime_boundary():
    module = _load_smoke_module()
    trace_id = "trace-hosted-prod"
    api_routes = {
        ("GET", "/api/system/health"): (
            200,
            "application/json",
            {"ok": True, "data": {"service": "crypto-manual-alert"}},
        ),
        ("GET", "/api/system/config"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                    "decision": {
                        "engine": "openai_compatible",
                        "candidate_sidecar_mode": "disabled",
                        "final_input_mode": "legacy_prompt",
                    },
                    "market_data": {"provider": "okx_public"},
                    "notification": {"enabled": True},
                    "macro_event": {"provider": "no_active_event"},
                    "workflow": {"execution_mode": "legacy_baseline"},
                    "readiness": {"prod_actionable": {"status": "ready", "prod_actionable_ready": True}},
                },
            },
        ),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace_id": trace_id,
                    "plan": {"manual_execution_required": True, "instrument": "ETH-USDT-SWAP"},
                    "verdict": {"allowed": True},
                    "business_summary": {
                        "title": "ETH-USDT-SWAP 手动提醒计划",
                        "notification": {"status": "sent"},
                    },
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
        ("GET", f"/api/runs/{trace_id}"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace": {"trace_id": trace_id, "allowed": True},
                    "plan_run": {
                        "business_summary": {
                            "title": "ETH-USDT-SWAP 手动提醒计划",
                            "notification": {"status": "sent"},
                        }
                    },
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
    }
    frontend_routes = {
        ("GET", "/"): (200, "text/html", "<html><body>提醒控制台</body></html>"),
        ("GET", f"/runs/{trace_id}"): (200, "text/html", "<html><body>提醒详情</body></html>"),
    }
    api_server, _api_handler = _start_server(api_routes)
    frontend_server, _frontend_handler = _start_server(frontend_routes)
    try:
        result = module.run_smoke(
            api_base=_base_url(api_server),
            frontend_base=_base_url(frontend_server),
            symbol="ETH-USDT-SWAP",
            query="评估 ETH 手动提醒",
            horizon="6h",
            timeout=2.0,
            require_prod_config=True,
        )
    finally:
        api_server.shutdown()
        frontend_server.shutdown()

    assert result["ok"] is True
    assert result["production_config_required"] is True
    assert result["production_config_ready"] is True
    assert result["decision_engine"] == "openai_compatible"
    assert result["decision_final_input_mode"] == "legacy_prompt"
    assert result["market_provider"] == "okx_public"
    assert result["notification_enabled"] is True
    assert result["macro_event_provider"] == "no_active_event"
    assert result["candidate_sidecar_mode"] == "disabled"
    assert result["workflow_execution_mode"] == "legacy_baseline"
    assert result["hosted_runtime_only_not_prod_actionable"] is True


def test_hosted_workbench_smoke_rejects_local_okx_base_when_prod_config_required():
    module = _load_smoke_module()
    trace_id = "trace-hosted-local-okx"
    api_routes = {
        ("GET", "/api/system/health"): (
            200,
            "application/json",
            {"ok": True, "data": {"service": "crypto-manual-alert"}},
        ),
        ("GET", "/api/system/config"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                    "decision": {
                        "engine": "openai_compatible",
                        "candidate_sidecar_mode": "disabled",
                        "final_input_mode": "legacy_prompt",
                    },
                    "market_data": {
                        "provider": "okx_public",
                        "okx_base_url": "http://127.0.0.1:8012",
                    },
                    "notification": {"enabled": True},
                    "macro_event": {"provider": "no_active_event"},
                    "workflow": {"execution_mode": "legacy_baseline"},
                    "readiness": {
                        "market_data": {"status": "ready", "provider": "okx_public"},
                        "prod_actionable": {"status": "ready", "prod_actionable_ready": True},
                    },
                },
            },
        ),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace_id": trace_id,
                    "plan": {"manual_execution_required": True, "instrument": "ETH-USDT-SWAP"},
                    "verdict": {"allowed": True},
                    "business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"},
                    "result_review": {"status": "not_collected"},
                },
            },
        ),
    }
    frontend_routes = {
        ("GET", "/"): (200, "text/html", "<html><body>提醒控制台</body></html>"),
    }
    api_server, _api_handler = _start_server(api_routes)
    frontend_server, _frontend_handler = _start_server(frontend_routes)
    try:
        with pytest.raises(
            module.HostedWorkbenchSmokeError,
            match="market_data.okx_base_url unset or https://www.okx.com",
        ):
            module.run_smoke(
                api_base=_base_url(api_server),
                frontend_base=_base_url(frontend_server),
                symbol="ETH-USDT-SWAP",
                query="评估 ETH 手动提醒",
                horizon="6h",
                timeout=2.0,
                require_prod_config=True,
            )
    finally:
        api_server.shutdown()
        frontend_server.shutdown()


def test_hosted_workbench_smoke_rejects_unsafe_market_readiness_when_prod_config_required():
    module = _load_smoke_module()
    trace_id = "trace-hosted-unsafe-market"
    api_routes = {
        ("GET", "/api/system/health"): (
            200,
            "application/json",
            {"ok": True, "data": {"service": "crypto-manual-alert"}},
        ),
        ("GET", "/api/system/config"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                    "decision": {
                        "engine": "openai_compatible",
                        "candidate_sidecar_mode": "disabled",
                        "final_input_mode": "legacy_prompt",
                    },
                    "market_data": {"provider": "okx_public", "okx_base_url": "https://www.okx.com"},
                    "notification": {"enabled": True},
                    "macro_event": {"provider": "no_active_event"},
                    "workflow": {"execution_mode": "legacy_baseline"},
                    "readiness": {
                        "market_data": {"status": "unsafe", "provider": "okx_public"},
                        "prod_actionable": {"status": "ready", "prod_actionable_ready": True},
                    },
                },
            },
        ),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace_id": trace_id,
                    "plan": {"manual_execution_required": True, "instrument": "ETH-USDT-SWAP"},
                    "verdict": {"allowed": True},
                    "business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"},
                    "result_review": {"status": "not_collected"},
                },
            },
        ),
    }
    frontend_routes = {
        ("GET", "/"): (200, "text/html", "<html><body>提醒控制台</body></html>"),
    }
    api_server, _api_handler = _start_server(api_routes)
    frontend_server, _frontend_handler = _start_server(frontend_routes)
    try:
        with pytest.raises(
            module.HostedWorkbenchSmokeError,
            match="readiness.market_data.status!=unsafe",
        ):
            module.run_smoke(
                api_base=_base_url(api_server),
                frontend_base=_base_url(frontend_server),
                symbol="ETH-USDT-SWAP",
                query="评估 ETH 手动提醒",
                horizon="6h",
                timeout=2.0,
                require_prod_config=True,
            )
    finally:
        api_server.shutdown()
        frontend_server.shutdown()


def test_hosted_workbench_smoke_requires_legacy_prompt_final_input_when_prod_config_required():
    module = _load_smoke_module()
    trace_id = "trace-hosted-decision-input"
    api_routes = {
        ("GET", "/api/system/health"): (
            200,
            "application/json",
            {"ok": True, "data": {"service": "crypto-manual-alert"}},
        ),
        ("GET", "/api/system/config"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trading": {"manual_execution_required": True, "auto_order_enabled": False},
                    "decision": {
                        "engine": "openai_compatible",
                        "candidate_sidecar_mode": "disabled",
                        "final_input_mode": "decision_input",
                    },
                    "market_data": {"provider": "okx_public"},
                    "notification": {"enabled": True},
                    "macro_event": {"provider": "no_active_event"},
                    "workflow": {"execution_mode": "legacy_baseline"},
                    "readiness": {"prod_actionable": {"status": "ready", "prod_actionable_ready": True}},
                },
            },
        ),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace_id": trace_id,
                    "plan": {"manual_execution_required": True, "instrument": "ETH-USDT-SWAP"},
                    "verdict": {"allowed": True},
                    "business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"},
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
        ("GET", f"/api/runs/{trace_id}"): (
            200,
            "application/json",
            {
                "ok": True,
                "data": {
                    "trace": {"trace_id": trace_id, "allowed": True},
                    "plan_run": {"business_summary": {"title": "ETH-USDT-SWAP 手动提醒计划"}},
                    "result_review": {"status": "not_collected"},
                },
                "trace_id": trace_id,
            },
        ),
    }
    frontend_routes = {
        ("GET", "/"): (200, "text/html", "<html><body>提醒控制台</body></html>"),
        ("GET", f"/runs/{trace_id}"): (200, "text/html", "<html><body>提醒详情</body></html>"),
    }
    api_server, _api_handler = _start_server(api_routes)
    frontend_server, _frontend_handler = _start_server(frontend_routes)
    try:
        with pytest.raises(
            module.HostedWorkbenchSmokeError,
            match="production config requires decision.final_input_mode=legacy_prompt",
        ):
            module.run_smoke(
                api_base=_base_url(api_server),
                frontend_base=_base_url(frontend_server),
                symbol="ETH-USDT-SWAP",
                query="评估 ETH 手动提醒",
                horizon="6h",
                timeout=2.0,
                require_prod_config=True,
            )
    finally:
        api_server.shutdown()
        frontend_server.shutdown()


def test_hosted_workbench_smoke_fails_loudly_when_manual_projection_is_missing():
    module = _load_smoke_module()
    api_routes = {
        ("GET", "/api/system/health"): (200, "application/json", {"ok": True, "data": {}}),
        ("GET", "/api/system/config"): (
            200,
            "application/json",
            {"ok": True, "data": {"trading": {"manual_execution_required": True, "auto_order_enabled": False}}},
        ),
        ("POST", "/api/runs/manual"): (
            200,
            "application/json",
            {"ok": True, "data": {"trace_id": "trace-missing", "plan": {"manual_execution_required": True}}},
        ),
    }
    frontend_routes = {
        ("GET", "/"): (200, "text/html", "<html><body>提醒控制台</body></html>"),
    }
    api_server, _api_handler = _start_server(api_routes)
    frontend_server, _frontend_handler = _start_server(frontend_routes)
    try:
        with pytest.raises(module.HostedWorkbenchSmokeError, match="business_summary"):
            module.run_smoke(
                api_base=_base_url(api_server),
                frontend_base=_base_url(frontend_server),
                symbol="ETH-USDT-SWAP",
                query="评估 ETH 手动提醒",
                horizon="6h",
                timeout=2.0,
            )
    finally:
        api_server.shutdown()
        frontend_server.shutdown()
