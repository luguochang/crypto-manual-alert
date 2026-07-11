from __future__ import annotations

import importlib.util
import socket
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx

from crypto_manual_alert.config import load_config
from crypto_manual_alert.eval.outcome_collector import (
    OutcomeCollector,
    PlanOutcomeInput,
    horizon_seconds,
    horizon_seconds_values,
)
from crypto_manual_alert.eval.outcome_store import OutcomeStore


ROOT = Path(__file__).resolve().parents[2]
LOCAL_STACK_TOOLS = ROOT / "tools" / "local_stack"


def _config(tmp_path):
    config = load_config("config/default.yaml")
    from dataclasses import replace

    return replace(config, app=replace(config.app, data_dir=str(tmp_path)))


def _candle(ts_ms: int, o: str, h: str, l: str, c: str, vol: str = "100") -> list:
    return [str(ts_ms), o, h, l, c, vol, vol, "1", "1"]


def _load_mock_okx_server():
    path = LOCAL_STACK_TOOLS / "mock_okx_server.py"
    spec = importlib.util.spec_from_file_location("mock_okx_server_for_outcome_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(LOCAL_STACK_TOOLS))
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_horizon_seconds_parses_common_units():
    assert horizon_seconds("6h") == 6 * 3600
    assert horizon_seconds("1d") == 86400
    assert horizon_seconds("30m") == 1800
    assert horizon_seconds(None) is None
    assert horizon_seconds("nonsense") is None


def test_horizon_seconds_values_expands_default_ui_multi_horizon():
    assert horizon_seconds_values("6h/12h/1d/3d") == [
        6 * 3600,
        12 * 3600,
        24 * 3600,
        3 * 24 * 3600,
    ]
    assert horizon_seconds_values("6h") == [6 * 3600]
    assert horizon_seconds_values("6h/nope") == []


def test_collect_upserts_scored_outcome_for_matured_window(tmp_path):
    config = _config(tmp_path)
    store = OutcomeStore(tmp_path / "outcomes.db")
    now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    generated_at = now - timedelta(hours=12)  # window [12h ago, 6h ago] is matured
    horizon = 6 * 3600

    # Candle window covers [generated_at, generated_at + 6h]; price rises so a long
    # would be a hit. We assert the window is recorded with OHLC, not the score itself.
    start_ms = int(generated_at.timestamp() * 1000)
    hour = 3600 * 1000
    candles_payload = {
        "code": "0",
        "data": [
            _candle(start_ms + 5 * hour, "3500", "3550", "3490", "3540", "100"),  # desc order
            _candle(start_ms + 4 * hour, "3490", "3510", "3480", "3500", "100"),
            _candle(start_ms + 3 * hour, "3480", "3500", "3470", "3490", "100"),
            _candle(start_ms + 2 * hour, "3470", "3490", "3460", "3480", "100"),
            _candle(start_ms + 1 * hour, "3460", "3480", "3450", "3470", "100"),
            _candle(start_ms + 0 * hour, "3450", "3470", "3440", "3460", "100"),
        ],
    }

    def http_get(path, params):
        assert path == "/api/v5/market/history-candles"
        assert params["instId"] == "ETH-USDT-SWAP"
        return candles_payload

    collector = OutcomeCollector(config, store, http_get=http_get, clock=lambda: now)
    plan = PlanOutcomeInput(
        decision_ref="plan-1",
        evaluation_target="legacy_final",
        symbol="ETH-USDT-SWAP",
        action="trigger long",
        probability=0.6,
        entry_price=3460.0,
        stop_price=3400.0,
        target_1=3600.0,
        target_2=3700.0,
        generated_at=generated_at,
        horizon_seconds=horizon,
    )

    outcome = collector.collect(plan)

    assert outcome is not None
    assert outcome.window.can_score_execution_outcome is True
    assert outcome.window.open_price == 3450.0
    assert outcome.window.close_price == 3540.0
    assert outcome.window.high_price == 3550.0
    assert outcome.window.low_price == 3440.0
    assert outcome.window.source_type == "exchange_native"

    persisted = store.list_outcomes(evaluation_target="legacy_final")
    assert len(persisted) == 1
    assert persisted[0].decision_ref == "plan-1"
    assert persisted[0].window.close_price == 3540.0


def test_collect_fetches_exchange_native_window_from_local_mock_okx_http(tmp_path):
    from dataclasses import replace

    mock_okx = _load_mock_okx_server()
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), mock_okx._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = _config(tmp_path)
        config = replace(
            config,
            market_data=replace(
                config.market_data,
                provider="okx_public",
                okx_base_url=f"http://127.0.0.1:{port}",
                candle_bar="1H",
            ),
        )
        store = OutcomeStore(tmp_path / "outcomes.db")
        now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
        plan = PlanOutcomeInput(
            decision_ref="plan-local-mock-okx",
            evaluation_target="legacy_final",
            symbol="ETH-USDT-SWAP",
            action="trigger long",
            probability=0.6,
            entry_price=3500.0,
            stop_price=3420.0,
            target_1=3560.0,
            target_2=3650.0,
            generated_at=now - timedelta(hours=12),
            horizon_seconds=6 * 3600,
        )

        outcome = OutcomeCollector(config, store, clock=lambda: now).collect(plan)

        assert outcome is not None
        assert outcome.window.source_type == "exchange_native"
        assert outcome.window.can_score_execution_outcome is True
        assert outcome.can_score is True
        assert outcome.window.open_price == 3450.0
        assert outcome.window.close_price == 3540.0
        assert outcome.window.high_price == 3550.0
        assert outcome.window.low_price == 3440.0
        persisted = store.list_outcomes(evaluation_target="legacy_final")
        assert len(persisted) == 1
        assert persisted[0].decision_ref == "plan-local-mock-okx"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_collect_skips_immature_window_without_upsert(tmp_path):
    config = _config(tmp_path)
    store = OutcomeStore(tmp_path / "outcomes.db")
    now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    generated_at = now - timedelta(hours=1)  # 6h horizon not yet matured

    def http_get(path, params):
        raise AssertionError("collector must not fetch candles for an immature window")

    collector = OutcomeCollector(config, store, http_get=http_get, clock=lambda: now)
    plan = PlanOutcomeInput(
        decision_ref="plan-2",
        evaluation_target="legacy_final",
        symbol="ETH-USDT-SWAP",
        action="trigger long",
        probability=0.6,
        entry_price=3460.0,
        stop_price=3400.0,
        target_1=3600.0,
        target_2=3700.0,
        generated_at=generated_at,
        horizon_seconds=6 * 3600,
    )

    assert collector.collect(plan) is None
    assert store.list_outcomes() == []


def test_default_http_client_ignores_environment_proxy(monkeypatch, tmp_path):
    config = _config(tmp_path)
    store = OutcomeStore(tmp_path / "outcomes.db")
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "0", "data": []}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path, params):
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)

    collector = OutcomeCollector(config, store)
    payload = collector._get("/api/v5/market/history-candles", {"instId": "ETH-USDT-SWAP"})

    assert payload == {"code": "0", "data": []}
    assert captured["trust_env"] is False
