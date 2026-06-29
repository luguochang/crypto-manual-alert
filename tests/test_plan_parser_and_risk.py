from datetime import datetime, timezone

import pytest

from jiami_crypto_alert.config import load_config
from jiami_crypto_alert.domain import DataPoint, MarketSnapshot
from jiami_crypto_alert.market_data import FixtureMarketDataProvider
from jiami_crypto_alert.plan_parser import PlanParseError, parse_decision_plan
from jiami_crypto_alert.risk import check_plan


def snapshot(age_seconds=0):
    now = datetime.now(timezone.utc)
    timestamp_ms = int(now.timestamp() * 1000) - age_seconds * 1000
    return MarketSnapshot(
        symbol="ETH-USDT-SWAP",
        fetched_at=now,
        points={
            "last": DataPoint("last", 3500.0, timestamp_ms, "okx"),
            "mark": DataPoint("mark", 3499.0, timestamp_ms, "okx"),
            "index": DataPoint("index", 3498.0, timestamp_ms, "okx"),
            "funding_rate": DataPoint("funding_rate", 0.0001, timestamp_ms, "okx"),
            "open_interest": DataPoint("open_interest", 100000.0, timestamp_ms, "okx"),
            "order_book": DataPoint("order_book", {"asks": [["3501", "10"]], "bids": [["3499", "10"]]}, timestamp_ms, "okx"),
            "candles": DataPoint("candles", [[str(timestamp_ms), "3490", "3510", "3480", "3500"]], timestamp_ms, "okx"),
        },
        unavailable=[],
    )


def test_parse_valid_plan_from_json():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "reference_price": 3500,
  "entry_trigger": 3510,
  "stop_price": 3435,
  "target_1": 3580,
  "target_2": 3660,
  "probability": 0.61,
  "position_size_class": "light",
  "max_leverage": 2,
  "risk_pct": 0.25,
  "expires_in_seconds": 90,
  "why_not_opposite": "No downside confirmation.",
  "invalidation": "Loss of 3435.",
  "manual_execution_required": true
}
"""

    plan = parse_decision_plan(raw)

    assert plan.main_action == "trigger long"
    assert plan.manual_execution_required is True
    assert plan.stop_price == 3435


def test_parse_rejects_invalid_action():
    raw = '{"instrument":"ETH-USDT-SWAP","main_action":"wait","manual_execution_required":true}'

    with pytest.raises(PlanParseError, match="main_action"):
        parse_decision_plan(raw)


def test_parse_rejects_fenced_json():
    raw = """
```json
{"instrument":"ETH-USDT-SWAP","main_action":"no trade","manual_execution_required":true,"expires_in_seconds":90}
```
"""

    with pytest.raises(PlanParseError, match="strict JSON"):
        parse_decision_plan(raw)


def test_parse_rejects_extra_text_around_json():
    raw = 'analysis first {"instrument":"ETH-USDT-SWAP","main_action":"no trade","horizon":"6h","manual_execution_required":true,"expires_in_seconds":90}'

    with pytest.raises(PlanParseError, match="strict JSON"):
        parse_decision_plan(raw)


def test_parse_rejects_missing_required_fields():
    raw = '{"instrument":"ETH-USDT-SWAP","main_action":"no trade","manual_execution_required":true}'

    with pytest.raises(PlanParseError, match="horizon"):
        parse_decision_plan(raw)


def test_parse_rejects_manual_execution_false():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "manual_execution_required": false,
  "expires_in_seconds": 90
}
"""

    with pytest.raises(PlanParseError, match="manual_execution_required"):
        parse_decision_plan(raw)


def test_parse_rejects_manual_execution_as_string_false():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "manual_execution_required": "false",
  "expires_in_seconds": 90
}
"""

    with pytest.raises(PlanParseError, match="manual_execution_required"):
        parse_decision_plan(raw)


def test_parse_rejects_non_positive_expiry():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "manual_execution_required": true,
  "expires_in_seconds": 0
}
"""

    with pytest.raises(PlanParseError, match="expires_in_seconds"):
        parse_decision_plan(raw)


def test_parse_rejects_probability_outside_unit_interval():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "no trade",
  "horizon": "6h",
  "probability": 1.2,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""

    with pytest.raises(PlanParseError, match="probability"):
        parse_decision_plan(raw)


def test_parse_rejects_text_in_numeric_field():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "entry_trigger": "only if price breaks out",
  "manual_execution_required": true
}
"""

    with pytest.raises(PlanParseError, match="entry_trigger"):
        parse_decision_plan(raw)


def test_parse_rejects_numeric_string_field():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "entry_trigger": "3510",
  "stop_price": 3435,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""

    with pytest.raises(PlanParseError, match="entry_trigger"):
        parse_decision_plan(raw)


def test_risk_rejects_open_without_stop():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "open long",
  "horizon": "6h",
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""
    plan = parse_decision_plan(raw)
    config = load_config("config/default.yaml")

    verdict = check_plan(plan, snapshot(), config)

    assert verdict.allowed is False
    assert any("止损价" in reason for reason in verdict.reasons)


def test_risk_rejects_opening_plan_without_entry_trigger_or_invalidation():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "stop_price": 3435,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""
    plan = parse_decision_plan(raw)
    config = load_config("config/default.yaml")

    verdict = check_plan(plan, snapshot(), config)

    assert verdict.allowed is False
    assert any("触发价" in reason for reason in verdict.reasons)
    assert any("失效条件" in reason for reason in verdict.reasons)


def test_risk_rejects_stale_market_data():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "stop_price": 3435,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""
    plan = parse_decision_plan(raw)
    config = load_config("config/default.yaml")

    verdict = check_plan(plan, snapshot(age_seconds=999), config)

    assert verdict.allowed is False
    assert any("行情数据陈旧" in reason for reason in verdict.reasons)


def test_risk_does_not_mark_current_hour_candle_stale_by_ticker_threshold():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "stop_price": 3435,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""
    now = datetime.now(timezone.utc)
    candle_ts = int((now.timestamp() - 1800) * 1000)
    fresh_ts = int(now.timestamp() * 1000)
    snap = snapshot()
    points = {
        **snap.points,
        "last": DataPoint("last", 3500.0, fresh_ts, "okx"),
        "mark": DataPoint("mark", 3500.0, fresh_ts, "okx"),
        "index": DataPoint("index", 3500.0, fresh_ts, "okx"),
        "order_book": DataPoint("order_book", {"asks": [], "bids": []}, fresh_ts, "okx"),
        "candles": DataPoint("candles", [[str(candle_ts), "3490", "3510", "3480", "3500"]], candle_ts, "okx"),
    }
    plan = parse_decision_plan(raw)
    config = load_config("config/default.yaml")

    verdict = check_plan(plan, MarketSnapshot("ETH-USDT-SWAP", now, points, []), config, now=now)

    assert not any("行情数据陈旧：candles" in reason for reason in verdict.reasons)


def test_risk_rejects_opening_plan_when_core_execution_facts_missing():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "stop_price": 3435,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""
    plan = parse_decision_plan(raw)
    config = load_config("config/default.yaml")
    snap = snapshot()
    points = dict(snap.points)
    points.pop("order_book")

    verdict = check_plan(plan, MarketSnapshot(snap.symbol, snap.fetched_at, points, []), config)

    assert verdict.allowed is False
    assert any("核心执行行情缺失" in reason for reason in verdict.reasons)


def test_risk_rejects_probability_above_confidence_cap():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "stop_price": 3435,
  "probability": 0.61,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""
    plan = parse_decision_plan(raw)
    config = load_config("config/default.yaml")
    snap = snapshot()
    snap = MarketSnapshot(
        symbol=snap.symbol,
        fetched_at=snap.fetched_at,
        points=snap.points,
        unavailable=["confidence_cap:0.58:liquidation heatmap unavailable"],
    )

    verdict = check_plan(plan, snap, config)

    assert verdict.allowed is False
    assert any("置信度上限" in reason for reason in verdict.reasons)


def test_fixture_snapshot_applies_confidence_cap_for_missing_crowding_data():
    raw = """
{
  "instrument": "ETH-USDT-SWAP",
  "main_action": "trigger long",
  "horizon": "6h",
  "stop_price": 3435,
  "probability": 0.61,
  "manual_execution_required": true,
  "expires_in_seconds": 90
}
"""
    plan = parse_decision_plan(raw)
    config = load_config("config/default.yaml")
    snap = FixtureMarketDataProvider().fetch_snapshot("ETH-USDT-SWAP")

    verdict = check_plan(plan, snap, config)

    assert verdict.allowed is False
    assert any("置信度上限" in reason for reason in verdict.reasons)
