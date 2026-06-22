from __future__ import annotations

from typing import Any

from .outcomes import OutcomeWindow


def build_outcome_window_from_candles(
    *,
    name: str,
    symbol: str,
    interval: str,
    source_type: str,
    window_start: str,
    window_end: str,
    collected_at: str,
    candles: list[dict[str, Any]],
    matured: bool = True,
    fee_bps: float | None = None,
    slippage_bps: float | None = None,
    funding_bps: float | None = None,
) -> OutcomeWindow:
    """Build a frozen outcome window from already-collected candle rows.

    The function intentionally does not fetch live data. A separate manual or
    scheduled collector can supply exchange-native candles after the window is
    mature.
    """

    clean_candles = [item for item in candles if isinstance(item, dict)]
    if not clean_candles:
        return OutcomeWindow(
            name=name,
            symbol=symbol,
            interval=interval,
            source_type=source_type,
            window_start=window_start,
            window_end=window_end,
            collected_at=collected_at,
            open_price=None,
            high_price=None,
            low_price=None,
            close_price=None,
            matured=matured,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            funding_bps=funding_bps,
        )
    return OutcomeWindow(
        name=name,
        symbol=symbol,
        interval=interval,
        source_type=source_type,
        window_start=window_start,
        window_end=window_end,
        collected_at=collected_at,
        open_price=_required_price(clean_candles[0], "open"),
        high_price=max(_required_price(item, "high") for item in clean_candles),
        low_price=min(_required_price(item, "low") for item in clean_candles),
        close_price=_required_price(clean_candles[-1], "close"),
        matured=matured,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        funding_bps=funding_bps,
    )


def _required_price(candle: dict[str, Any], key: str) -> float:
    value = candle.get(key)
    if value is None or value == "":
        raise ValueError(f"candle missing {key}")
    return float(value)
