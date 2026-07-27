from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_alert_v2.domain.models import Action


OutcomeStatus = Literal["scheduled", "pending", "matured", "insufficient", "failed"]
OutcomeBaseline = Literal["decision", "hold", "no_trade"]
OutcomeSource = Literal["exchange_native"]


class OutcomeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon: str = Field(min_length=1, max_length=32)
    observed_at: datetime
    source: OutcomeSource = "exchange_native"


class OutcomeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brier_score: float | None = Field(default=None, ge=0, le=1)
    mfe: Decimal | None = None
    mae: Decimal | None = None
    gross_return: Decimal | None = None
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal = Field(default=Decimal("0"), ge=0)
    funding: Decimal = Decimal("0")
    net_return: Decimal | None = None


class OutcomeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_version_id: str = Field(min_length=1, max_length=255)
    action: Action
    baseline: OutcomeBaseline
    predicted_probability: float | None = Field(default=None, ge=0, le=1)
    realized_label: float | None = Field(default=None, ge=0, le=1)
    window: OutcomeWindow
    status: OutcomeStatus
    metrics: OutcomeMetrics | None = None


def maturation_at(created_at: datetime, horizon: str) -> datetime:
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    normalized = horizon.strip().lower()
    units = {"m": 60, "h": 3600, "d": 86400}
    if len(normalized) < 2 or normalized[-1] not in units:
        raise ValueError("horizon must use a numeric m, h or d suffix")
    try:
        amount = int(normalized[:-1])
    except ValueError as exc:
        raise ValueError("horizon must use a numeric m, h or d suffix") from exc
    if amount <= 0:
        raise ValueError("horizon must be positive")
    return created_at + timedelta(seconds=amount * units[normalized[-1]])


def evaluate_outcome(
    *,
    action: Action,
    baseline: OutcomeBaseline,
    predicted_probability: float | None,
    realized_label: float | None,
    reference_price: Decimal,
    close_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    fees: Decimal = Decimal("0"),
    slippage: Decimal = Decimal("0"),
    funding: Decimal = Decimal("0"),
) -> OutcomeMetrics:
    for name, value in (
        ("reference_price", reference_price),
        ("close_price", close_price),
        ("high_price", high_price),
        ("low_price", low_price),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if high_price < max(reference_price, close_price) or low_price > min(
        reference_price, close_price
    ):
        raise ValueError("outcome prices are inconsistent")
    brier = None
    if predicted_probability is not None and realized_label is not None:
        brier = (predicted_probability - realized_label) ** 2
    direction = Decimal("-1") if action in {
        "open_short", "hold_short", "close_long", "flip_long_to_short", "trigger_short"
    } else Decimal("1")
    gross_return = direction * (close_price - reference_price) / reference_price
    mfe = direction * (high_price - reference_price) / reference_price
    mae = direction * (low_price - reference_price) / reference_price
    net_return = gross_return - fees - slippage - funding
    return OutcomeMetrics(
        brier_score=brier,
        mfe=mfe,
        mae=mae,
        gross_return=gross_return,
        fees=fees,
        slippage=slippage,
        funding=funding,
        net_return=net_return,
    )


def quality_is_reportable(*, sample_count: int, window_start: datetime, now: datetime) -> bool:
    if sample_count < 30:
        return False
    if window_start.tzinfo is None or now.tzinfo is None:
        raise ValueError("quality window timestamps must be timezone-aware")
    return now >= window_start


__all__ = [
    "OutcomeBaseline",
    "OutcomeMetrics",
    "OutcomeObservation",
    "OutcomeSource",
    "OutcomeStatus",
    "OutcomeWindow",
    "evaluate_outcome",
    "maturation_at",
    "quality_is_reportable",
]
