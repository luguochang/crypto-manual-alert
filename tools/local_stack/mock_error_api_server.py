from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8013
UNSAFE_MESSAGE = (
    "SQLITE_ERROR at /srv/app/data/eval/crypto-outcomes.db "
    "trace_id=abc request_json payload response_json parsed_plan "
    "BARK_DEVICE_KEY=secret https://api.day.app/device/body Bearer raw-secret api_key=secret"
)


def error_envelope(path: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": "LOCAL_STACK_FORCED_ERROR",
            "message": f"{UNSAFE_MESSAGE} path={path}",
            "detail": {
                "trace_id": "abc",
                "request_json": {"path": path, "BARK_DEVICE_KEY": "secret"},
            },
        },
    }


def system_config_envelope() -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "diagnostic": {
                "routes_enabled": True,
            },
            "readiness": {
                "overall": {"status": "blocked", "real_external_ready": False},
                "decision_engine": {"status": "fixture"},
                "openai_credentials": {"status": "missing"},
                "market_data": {"status": "fixture"},
                "liquidity_order_book": {"status": "not_configured"},
                "event_status": {"status": "not_configured"},
                "notification": {"status": "disabled"},
                "trading_safety": {"status": "manual_only"},
                "forbidden_env": {"status": "ok"},
                "prod_actionable": {
                    "status": "blocked",
                    "prod_actionable_ready": False,
                    "real_external_ready": False,
                    "event_ready": False,
                },
            },
        },
    }


def partial_run_detail_envelope() -> dict[str, Any]:
    """Return a valid core run detail with missing display projections.

    The frontend should keep this readable instead of collapsing the detail
    page when a mixed-version API omits product projection fields.
    """

    trace_id = "partial-detail-trace"
    plan_id = "partial-detail-plan"
    return {
        "ok": True,
        "data": {
            "trace": {
                "trace_id": trace_id,
                "status": "blocked",
                "run_type": "manual",
                "symbol": "ETH-USDT-SWAP",
                "created_at": "2026-07-09T10:00:00+08:00",
                "ended_at": None,
                "final_plan_id": plan_id,
                "final_action": "trigger long",
                "allowed": False,
                "span_count": 0,
                "llm_interaction_count": 0,
            },
            "plan_run": {
                "plan_id": plan_id,
                "status": "blocked",
                "parsed_plan": {
                    "plan_id": plan_id,
                    "instrument": "ETH-USDT-SWAP",
                    "main_action": "trigger long",
                    "horizon": "6h",
                    "manual_execution_required": True,
                    "expires_at": "2026-07-09T12:00:00+08:00",
                    "reference_price": 3500,
                    "entry_trigger": 3510,
                    "stop_price": 3435,
                    "target_1": 3580,
                    "target_2": 3660,
                    "probability": 0.58,
                },
                "verdict": {
                    "allowed": False,
                    "reasons": [UNSAFE_MESSAGE],
                    "warnings": [],
                },
                "business_summary": None,
                "agent_audit_view": {
                    "available": True,
                    "facts_gate": {
                        "passed": False,
                        "reasons": [UNSAFE_MESSAGE],
                        "missing_execution_facts": ["active_event_status"],
                    },
                    "gates": {
                        "production_control_gate": {
                            "allowed": False,
                            "reasons": [UNSAFE_MESSAGE],
                        }
                    },
                    "candidate_final_comparison": {
                        "production_final_input": False,
                        "candidate": {
                            "diagnosis": {
                                "blocking_reasons": [UNSAFE_MESSAGE],
                            }
                        },
                    },
                },
                "payload_keys": [],
            },
            "analysis": {},
            "spans": [],
            "llm_interactions": [],
            "badcases": [],
            "notification_history": [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local failing API server for Server Component error-state tests.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


class _Handler(BaseHTTPRequestHandler):
    server_version = "MockErrorAPI/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self._send_json({"ok": True, "service": "mock-error-api"})
            return
        if path == "/api/system/health":
            self._send_json(
                {
                    "ok": True,
                    "data": {"service": "ok", "storage": "ok", "mode": "SHADOW"},
                }
            )
            return
        if path == "/api/system/config":
            self._send_json(system_config_envelope())
            return
        if path == "/api/runs/partial-detail-trace":
            self._send_json(partial_run_detail_envelope())
            return
        if path.startswith("/api/eval/candidates"):
            self._send_json({"unexpected": "response_json trace_id=abc request_json=/srv/app/secret"}, status=200)
            return
        if path.startswith("/api/eval/outcomes"):
            self.close_connection = True
            return
        self._send_json(error_envelope(self.path), status=500)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._send_json(error_envelope(self.path), status=500)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    raise SystemExit(main())
