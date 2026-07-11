from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8012


def okx_public_payload(path: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
    ts = str(int(time.time() * 1000))
    if path == "/api/v5/market/ticker":
        return {"code": "0", "data": [{"last": "3500", "bidPx": "3499", "askPx": "3501", "ts": ts}]}
    if path == "/api/v5/public/mark-price":
        return {"code": "0", "data": [{"instId": "ETH-USDT-SWAP", "markPx": "3499", "ts": ts}]}
    if path == "/api/v5/market/index-tickers":
        inst_id = ((query or {}).get("instId") or ["ETH-USDT"])[0]
        return {"code": "0", "data": [{"instId": inst_id, "idxPx": "3498", "ts": ts}]}
    if path == "/api/v5/public/funding-rate":
        return {"code": "0", "data": [{"fundingRate": "0.0001", "fundingTime": ts}]}
    if path == "/api/v5/public/open-interest":
        return {"code": "0", "data": [{"oi": "100000", "ts": ts}]}
    if path == "/api/v5/market/books":
        return {"code": "0", "data": [{"asks": [["3501", "10"]], "bids": [["3499", "10"]], "ts": ts}]}
    if path == "/api/v5/market/candles":
        return {"code": "0", "data": [[ts, "3490", "3510", "3480", "3500", "100"]]}
    if path == "/api/v5/market/history-candles":
        return {"code": "0", "data": _history_candles(query or {})}
    return {"code": "404", "msg": f"unsupported mock OKX path: {path}", "data": []}


def _history_candles(query: dict[str, list[str]]) -> list[list[str]]:
    after_values = query.get("after") or []
    try:
        end_ms = int(float(after_values[0])) if after_values else int(time.time() * 1000)
    except (TypeError, ValueError):
        end_ms = int(time.time() * 1000)
    hour_ms = 60 * 60 * 1000
    rows = [
        (end_ms - 1 * hour_ms, "3500", "3550", "3490", "3540"),
        (end_ms - 2 * hour_ms, "3490", "3510", "3480", "3500"),
        (end_ms - 3 * hour_ms, "3480", "3500", "3470", "3490"),
        (end_ms - 4 * hour_ms, "3470", "3490", "3460", "3480"),
        (end_ms - 5 * hour_ms, "3460", "3480", "3450", "3470"),
        (end_ms - 6 * hour_ms, "3450", "3470", "3440", "3460"),
    ]
    return [[str(ts), open_, high, low, close, "100", "100", "1", "1"] for ts, open_, high, low, close in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local OKX public market mock server for actionable smoke tests.")
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
    server_version = "MockOKX/0.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"ok": True, "service": "mock-okx"})
            return
        payload = okx_public_payload(parsed.path, parse_qs(parsed.query))
        status = 200 if payload.get("code") == "0" else 404
        self._send_json(payload, status=status)

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
