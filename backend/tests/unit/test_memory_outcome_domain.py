from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from crypto_alert_v2.domain.memory import MemoryRecord, safe_memory_injection
from crypto_alert_v2.domain.outcome import (
    evaluate_outcome,
    maturation_at,
    quality_is_reportable,
)


NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)


def memory(**overrides: object) -> MemoryRecord:
    payload: dict[str, object] = {
        "memory_id": uuid4(),
        "scope": "workspace",
        "purpose": "profile",
        "key": "risk_mode",
        "content": {"risk_mode": "conservative"},
        "expires_at": NOW + timedelta(days=1),
    }
    payload.update(overrides)
    return MemoryRecord.model_validate(payload)


def test_memory_injection_filters_disabled_expired_and_historical_facts() -> None:
    safe = memory()
    disabled = memory(enabled=False, key="disabled")
    expired = memory(expires_at=NOW)
    historical = memory(key="old_result", content={"recommendation": "open_long"})

    injected = safe_memory_injection(
        [safe, disabled, expired, historical],
        now=NOW,
    )

    assert len(injected) == 1
    assert injected[0].memory_id == safe.memory_id
    assert injected[0].content == {"risk_mode": "conservative"}


def test_event_memory_requires_refresh_timestamp_and_is_injectable_only_when_safe() -> None:
    with pytest.raises(ValueError, match="refreshed_at"):
        memory(purpose="event")
    event = memory(
        purpose="event",
        refreshed_at=NOW,
        content={"headline": "A refreshed event context"},
    )
    assert len(safe_memory_injection([event], now=NOW)) == 1


def test_outcome_maturation_and_metrics_are_deterministic() -> None:
    assert maturation_at(NOW, "4h") == NOW + timedelta(hours=4)
    metrics = evaluate_outcome(
        action="open_long",
        baseline="decision",
        predicted_probability=0.8,
        realized_label=1,
        reference_price=Decimal("100"),
        close_price=Decimal("110"),
        high_price=Decimal("115"),
        low_price=Decimal("95"),
        fees=Decimal("0.01"),
        slippage=Decimal("0.02"),
        funding=Decimal("0.01"),
    )
    assert metrics.brier_score == pytest.approx(0.04)
    assert metrics.mfe == Decimal("0.15")
    assert metrics.mae == Decimal("-0.05")
    assert metrics.net_return == Decimal("0.06")


def test_quality_is_not_reportable_until_sample_and_window_boundaries_pass() -> None:
    assert not quality_is_reportable(
        sample_count=29,
        window_start=NOW - timedelta(days=30),
        now=NOW,
    )
    assert not quality_is_reportable(
        sample_count=30,
        window_start=NOW + timedelta(minutes=1),
        now=NOW,
    )
    assert quality_is_reportable(
        sample_count=30,
        window_start=NOW - timedelta(days=30),
        now=NOW,
    )
