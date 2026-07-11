from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8011
MODEL = "mock-crypto-plan"


def chat_completion_payload(request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = request_payload or {}
    symbol = _extract_symbol(request_payload) or "ETH-USDT-SWAP"
    decision_plan = {
        "instrument": symbol,
        "main_action": "trigger long",
        "horizon": "6h",
        "reference_price": 3500.0,
        "entry_trigger": 3510.0,
        "stop_price": 3435.0,
        "target_1": 3580.0,
        "target_2": 3660.0,
        "probability": 0.58,
        "position_size_class": "light",
        "max_leverage": 2,
        "risk_pct": 0.25,
        "expires_in_seconds": 90,
        "why_not_opposite": "BTC 结构没有确认下行，资金费率也未显示过热。",
        "invalidation": "如果 ETH 跌破 3435，手动多头计划失效。",
        "unavailable_data": ["精确 CVD", "清算热力图"],
        "manual_execution_required": True,
        "notes": "mock LLM 路径：仅用于本地验证 OpenAI-compatible 代码链路，不是真实外部模型结论。",
    }
    content = json.dumps(decision_plan, ensure_ascii=False, separators=(",", ":"))
    prompt_tokens = max(1, len(json.dumps(request_payload, ensure_ascii=False, default=str)) // 4)
    completion_tokens = max(1, len(content) // 4)
    return {
        "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": str(request_payload.get("model") or MODEL),
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local OpenAI-compatible mock server for smoke tests.")
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


def _extract_symbol(request_payload: dict[str, Any]) -> str | None:
    for message in request_payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "")
        for symbol in ("ETH-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP"):
            if symbol in content:
                return symbol
    return None


class _Handler(BaseHTTPRequestHandler):
    server_version = "MockOpenAI/0.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            self._send_json({"ok": True, "service": "mock-openai"})
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send_json({"error": "not found"}, status=404)
            return
        payload = self._read_json()
        self._send_json(chat_completion_payload(payload))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    raise SystemExit(main())
