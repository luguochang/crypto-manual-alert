from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from crypto_manual_alert.config import load_config
from crypto_manual_alert.market.event_status import NoActiveEventStatusProvider, build_event_status_provider


def test_no_active_event_provider_records_operator_assertion_metadata():
    provider = NoActiveEventStatusProvider(
        operator_ref="ops:macro-desk",
        confirmed_at="2026-07-09T09:30:00+08:00",
        source_ref="calendar:forexfactory:2026-07-09:no-high-impact",
        horizon="6h",
        valid_until="2026-07-09T15:30:00+08:00",
        clock=datetime(2026, 7, 9, 1, 30, tzinfo=timezone.utc),
    )

    point = provider.active_event_status("ETH-USDT-SWAP")

    assert point.name == "active_event_status"
    assert point.source == "event_pool"
    assert point.status == "ok"
    assert point.timestamp_ms == 1783560600000
    assert point.value == {
        "status": "no_active_event",
        "symbol": "ETH-USDT-SWAP",
        "assertion": "operator_confirmed_no_scheduled_macro_event",
        "provider": "no_active_event",
        "operator_ref": "ops:macro-desk",
        "confirmed_at": "2026-07-09T09:30:00+08:00",
        "source_ref": "calendar:forexfactory:2026-07-09:no-high-impact",
        "horizon": "6h",
        "valid_until": "2026-07-09T15:30:00+08:00",
        "metadata_complete": True,
    }


def test_event_status_provider_uses_macro_event_config_metadata():
    config = load_config("config/default.yaml")
    config = replace(
        config,
        macro_event=replace(
            config.macro_event,
            provider="no_active_event",
            no_active_event_operator_ref="ops:macro-desk",
            no_active_event_confirmed_at="2026-07-09T09:30:00+08:00",
            no_active_event_source_ref="calendar:forexfactory:2026-07-09:no-high-impact",
            no_active_event_horizon="6h",
            no_active_event_valid_until="2026-07-09T15:30:00+08:00",
        ),
    )

    provider = build_event_status_provider(config)
    point = provider.active_event_status("BTC-USDT-SWAP")

    assert point is not None
    assert isinstance(point.value, dict)
    assert point.value["operator_ref"] == "ops:macro-desk"
    assert point.value["confirmed_at"] == "2026-07-09T09:30:00+08:00"
    assert point.value["source_ref"] == "calendar:forexfactory:2026-07-09:no-high-impact"
    assert point.value["horizon"] == "6h"
    assert point.value["valid_until"] == "2026-07-09T15:30:00+08:00"
    assert point.value["metadata_complete"] is True
