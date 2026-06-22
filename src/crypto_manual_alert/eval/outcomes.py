from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TRADE_ACTION_KEYWORDS = {
    "open long",
    "hold long",
    "trigger long",
    "flip short to long",
    "open short",
    "hold short",
    "trigger short",
    "flip long to short",
}


@dataclass(frozen=True)
class OutcomeWindow:
    """Frozen offline market outcome window for one scoring horizon."""

    name: str
    symbol: str
    interval: str
    source_type: str
    window_start: str
    window_end: str
    collected_at: str
    open_price: float | None
    high_price: float | None
    low_price: float | None
    close_price: float | None
    matured: bool
    fee_bps: float | None = None
    slippage_bps: float | None = None
    funding_bps: float | None = None

    @property
    def unscored_reason(self) -> str | None:
        if not self.matured:
            return "pending_outcome"
        if self.source_type != "exchange_native":
            return "price_source_not_exchange_native"
        if any(value is None for value in (self.open_price, self.high_price, self.low_price, self.close_price)):
            return "price_window_incomplete"
        return None

    @property
    def can_score_execution_outcome(self) -> bool:
        return self.unscored_reason is None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "interval": self.interval,
            "source_type": self.source_type,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "collected_at": self.collected_at,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "matured": self.matured,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "funding_bps": self.funding_bps,
            "can_score_execution_outcome": self.can_score_execution_outcome,
            "unscored_reason": self.unscored_reason,
        }


@dataclass(frozen=True)
class DecisionOutcome:
    """One final or candidate decision joined with one frozen outcome window."""

    decision_ref: str
    evaluation_target: str
    symbol: str
    action: str
    probability: float | None
    entry_price: float | None
    stop_price: float | None
    target_1: float | None
    target_2: float | None
    window: OutcomeWindow
    regime: str | None = None

    @property
    def normalized_action(self) -> str:
        return self.action.strip().lower()

    @property
    def unscored_reason(self) -> str | None:
        if self.normalized_action == "no trade":
            return "no_trade_action"
        if self.normalized_action not in TRADE_ACTION_KEYWORDS:
            return "unsupported_action"
        if self.window.unscored_reason is not None:
            return self.window.unscored_reason
        if self.entry_price is None or self.stop_price is None or self.target_1 is None:
            return "missing_trade_levels"
        return None

    @property
    def can_score(self) -> bool:
        return self.unscored_reason is None

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "decision_ref": self.decision_ref,
            "evaluation_target": self.evaluation_target,
            "symbol": self.symbol,
            "action": self.action,
            "probability": self.probability,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "window": self.window.to_public_dict(),
            "can_score": self.can_score,
            "unscored_reason": self.unscored_reason,
        }
        if self.regime is not None:
            payload["regime"] = self.regime
        return payload


def outcome_from_public_dict(payload: dict[str, Any]) -> DecisionOutcome:
    window_payload = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    window = OutcomeWindow(
        name=str(window_payload.get("name") or ""),
        symbol=str(window_payload.get("symbol") or payload.get("symbol") or ""),
        interval=str(window_payload.get("interval") or ""),
        source_type=str(window_payload.get("source_type") or ""),
        window_start=str(window_payload.get("window_start") or ""),
        window_end=str(window_payload.get("window_end") or ""),
        collected_at=str(window_payload.get("collected_at") or ""),
        open_price=_optional_float(window_payload.get("open_price")),
        high_price=_optional_float(window_payload.get("high_price")),
        low_price=_optional_float(window_payload.get("low_price")),
        close_price=_optional_float(window_payload.get("close_price")),
        matured=bool(window_payload.get("matured")),
        fee_bps=_optional_float(window_payload.get("fee_bps")),
        slippage_bps=_optional_float(window_payload.get("slippage_bps")),
        funding_bps=_optional_float(window_payload.get("funding_bps")),
    )
    return DecisionOutcome(
        decision_ref=str(payload.get("decision_ref") or ""),
        evaluation_target=str(payload.get("evaluation_target") or ""),
        symbol=str(payload.get("symbol") or ""),
        action=str(payload.get("action") or ""),
        probability=_optional_float(payload.get("probability")),
        entry_price=_optional_float(payload.get("entry_price")),
        stop_price=_optional_float(payload.get("stop_price")),
        target_1=_optional_float(payload.get("target_1")),
        target_2=_optional_float(payload.get("target_2")),
        regime=str(payload.get("regime")) if payload.get("regime") is not None else None,
        window=window,
    )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)

