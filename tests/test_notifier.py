from datetime import datetime, timedelta, timezone

import httpx

from jiami_crypto_alert.config import load_config
from jiami_crypto_alert.domain import DecisionPlan, RiskVerdict
from jiami_crypto_alert.notifier import BarkNotificationSink


def test_bark_notification_url_encodes_slashes(monkeypatch):
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        return httpx.Response(200, json={"code": 200, "message": "success"})

    monkeypatch.setattr("jiami_crypto_alert.notifier.httpx.get", fake_get)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device/key")
    config = load_config("config/default.yaml")
    plan = DecisionPlan(
        plan_id="p1",
        instrument="ETH-USDT-SWAP",
        main_action="trigger long",
        horizon="6h",
        manual_execution_required=True,
        generated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=90),
        entry_trigger=3510,
        stop_price=3435,
        target_1=3580,
        target_2=3660,
        probability=0.61,
        max_leverage=2,
        risk_pct=0.25,
        why_not_opposite="T1/T2 slash should be encoded",
    )

    result = BarkNotificationSink(config).send(plan, RiskVerdict(allowed=True, reasons=[]))

    assert result.ok is True
    assert "%2F" in captured["url"]
    assert "T1/T2" not in captured["url"]

