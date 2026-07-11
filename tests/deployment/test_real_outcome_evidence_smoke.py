from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "tools" / "deployment" / "smoke_real_outcome_evidence.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke_real_outcome_evidence", SMOKE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingHandler(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, str, Any]] = {}
    calls: list[tuple[str, str]] = []

    def do_GET(self) -> None:
        self.calls.append(("GET", self.path))
        status, content_type, response_body = self.routes.get(
            ("GET", self.path),
            (404, "application/json", {"ok": False, "error": {"code": "not_found"}}),
        )
        encoded = (
            response_body.encode("utf-8")
            if isinstance(response_body, str)
            else json.dumps(response_body).encode("utf-8")
        )
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


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


def _outcomes_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"ok": True, "data": {"items": items}}


def _exchange_native_scored_outcome(
    *,
    decision_ref: str = "trace-real-1:legacy_final",
    symbol: str = "ETH-USDT-SWAP",
    collected_at: str = "2026-07-06T06:01:00+00:00",
) -> dict[str, Any]:
    return {
        "decision_ref": decision_ref,
        "evaluation_target": "legacy_final",
        "symbol": symbol,
        "action": "trigger long",
        "probability": 0.61,
        "entry_price": 3460.0,
        "stop_price": 3400.0,
        "target_1": 3600.0,
        "target_2": 3700.0,
        "window": {
            "name": "ETH-USDT-SWAP:21600s",
            "symbol": "ETH-USDT-SWAP",
            "interval": "1H",
            "source_type": "exchange_native",
            "window_start": "2026-07-06T00:00:00+00:00",
            "window_end": "2026-07-06T06:00:00+00:00",
            "collected_at": collected_at,
            "open_price": 3450.0,
            "high_price": 3550.0,
            "low_price": 3440.0,
            "close_price": 3540.0,
            "matured": True,
            "can_score_execution_outcome": True,
            "unscored_reason": None,
        },
        "can_score": True,
        "unscored_reason": None,
    }


def test_real_outcome_evidence_smoke_accepts_exchange_native_matured_scored_outcome():
    module = _load_smoke_module()
    routes = {
        ("GET", "/api/eval/outcomes"): (
            200,
            "application/json",
            _outcomes_response([_exchange_native_scored_outcome()]),
        ),
    }
    server, handler = _start_server(routes)
    try:
        result = module.run_smoke(api_base=_base_url(server), timeout=2.0)
    finally:
        server.shutdown()

    assert result["ok"] is True
    assert result["smoke_profile"] == "real_outcome_evidence"
    assert result["real_exchange_native_matured_outcome_proven"] is True
    assert result["matched_count"] == 1
    assert result["total_count"] == 1
    assert result["matched"][0]["decision_ref"] == "trace-real-1:legacy_final"
    assert ("GET", "/api/eval/outcomes") in handler.calls


def test_real_outcome_evidence_smoke_filters_by_symbol_and_collection_time():
    module = _load_smoke_module()
    routes = {
        ("GET", "/api/eval/outcomes"): (
            200,
            "application/json",
            _outcomes_response(
                [
                    _exchange_native_scored_outcome(
                        decision_ref="trace-btc-new:legacy_final",
                        symbol="BTC-USDT-SWAP",
                        collected_at="2026-07-09T00:05:00+00:00",
                    ),
                    _exchange_native_scored_outcome(
                        decision_ref="trace-eth-old:legacy_final",
                        symbol="ETH-USDT-SWAP",
                        collected_at="2026-07-08T23:59:59+00:00",
                    ),
                    _exchange_native_scored_outcome(
                        decision_ref="trace-eth-new:legacy_final",
                        symbol="ETH-USDT-SWAP",
                        collected_at="2026-07-09T00:05:00+00:00",
                    ),
                ]
            ),
        ),
    }
    server, _handler = _start_server(routes)
    try:
        result = module.run_smoke(
            api_base=_base_url(server),
            timeout=2.0,
            symbol="ETH-USDT-SWAP",
            collected_after="2026-07-09T00:00:00+00:00",
        )
    finally:
        server.shutdown()

    assert result["ok"] is True
    assert result["symbol"] == "ETH-USDT-SWAP"
    assert result["collected_after"] == "2026-07-09T00:00:00+00:00"
    assert result["total_count"] == 3
    assert result["matched_count"] == 1
    assert result["matched"][0]["decision_ref"] == "trace-eth-new:legacy_final"


def test_real_outcome_evidence_smoke_rejects_symbol_mismatches_even_when_other_real_outcomes_exist():
    module = _load_smoke_module()
    routes = {
        ("GET", "/api/eval/outcomes"): (
            200,
            "application/json",
            _outcomes_response(
                [
                    _exchange_native_scored_outcome(
                        decision_ref="trace-btc-real:legacy_final",
                        symbol="BTC-USDT-SWAP",
                        collected_at="2026-07-09T00:05:00+00:00",
                    )
                ]
            ),
        ),
    }
    server, _handler = _start_server(routes)
    try:
        with pytest.raises(module.RealOutcomeEvidenceError, match="no_real_exchange_native_matured_outcome"):
            module.run_smoke(
                api_base=_base_url(server),
                timeout=2.0,
                symbol="ETH-USDT-SWAP",
                collected_after="2026-07-09T00:00:00+00:00",
            )
    finally:
        server.shutdown()


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (
            {
                **_exchange_native_scored_outcome(),
                "window": {
                    **_exchange_native_scored_outcome()["window"],
                    "source_type": "mocked_outcome",
                },
                "can_score": False,
                "unscored_reason": "price_source_not_exchange_native",
            },
            "no_real_exchange_native_matured_outcome",
        ),
        (
            {
                **_exchange_native_scored_outcome(),
                "window": {
                    **_exchange_native_scored_outcome()["window"],
                    "matured": False,
                    "can_score_execution_outcome": False,
                    "unscored_reason": "pending_outcome",
                },
                "can_score": False,
                "unscored_reason": "pending_outcome",
            },
            "no_real_exchange_native_matured_outcome",
        ),
        (
            {
                **_exchange_native_scored_outcome(),
                "action": "no trade",
                "can_score": False,
                "unscored_reason": "no_trade_action",
            },
            "no_real_exchange_native_matured_outcome",
        ),
    ],
)
def test_real_outcome_evidence_smoke_rejects_non_real_or_unscored_outcomes(
    item: dict[str, Any],
    reason: str,
):
    module = _load_smoke_module()
    routes = {
        ("GET", "/api/eval/outcomes"): (
            200,
            "application/json",
            _outcomes_response([item]),
        ),
    }
    server, _handler = _start_server(routes)
    try:
        with pytest.raises(module.RealOutcomeEvidenceError, match=reason):
            module.run_smoke(api_base=_base_url(server), timeout=2.0)
    finally:
        server.shutdown()


def test_real_outcome_evidence_smoke_rejects_empty_outcomes():
    module = _load_smoke_module()
    routes = {
        ("GET", "/api/eval/outcomes"): (
            200,
            "application/json",
            _outcomes_response([]),
        ),
    }
    server, _handler = _start_server(routes)
    try:
        with pytest.raises(module.RealOutcomeEvidenceError, match="no_real_exchange_native_matured_outcome"):
            module.run_smoke(api_base=_base_url(server), timeout=2.0)
    finally:
        server.shutdown()
