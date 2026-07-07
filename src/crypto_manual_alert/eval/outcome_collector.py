from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from crypto_manual_alert.config import Config
from crypto_manual_alert.eval.market_outcome_collector import build_outcome_window_from_candles
from crypto_manual_alert.eval.outcome_store import OutcomeStore
from crypto_manual_alert.eval.outcomes import DecisionOutcome, OutcomeWindow


_HORIZON_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhdw])\s*$", re.IGNORECASE)
_HORIZON_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def horizon_seconds(horizon: str | None) -> float | None:
    """Parse a horizon string like '6h', '1d', '30m' into seconds. None if unparseable."""
    if not horizon:
        return None
    match = _HORIZON_RE.match(str(horizon))
    if not match:
        return None
    return float(match.group(1)) * _HORIZON_SECONDS[match.group(2).lower()]


@dataclass(frozen=True)
class PlanOutcomeInput:
    """Minimal plan projection needed to collect a market outcome.

    Carries only the decision fields required to score an outcome; raw prompts and
    LLM payloads are intentionally excluded — outcomes are scored from market data,
    not from the decision text.
    """

    decision_ref: str
    evaluation_target: str
    symbol: str
    action: str
    probability: float | None
    entry_price: float | None
    stop_price: float | None
    target_1: float | None
    target_2: float | None
    generated_at: datetime
    horizon_seconds: float


class OutcomeCollector:
    """Collects exchange-native market outcomes for past decisions.

    For each decision, after its horizon window has matured, this collector fetches
    OKX public candles covering the window, builds a frozen OutcomeWindow, and
    upserts a DecisionOutcome into OutcomeStore. This is the only path that feeds
    the financial_quality_gate with real data.

    The collector does not fetch live data for immature windows, does not write the
    production journal, and does not send notifications. It only reads market
    history and writes the eval sidecar store.
    """

    def __init__(
        self,
        config: Config,
        outcome_store: OutcomeStore,
        *,
        http_get: Callable[[str, dict[str, str]], Mapping[str, Any]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.outcome_store = outcome_store
        self.http_get = http_get
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, plan: PlanOutcomeInput) -> DecisionOutcome | None:
        now = self._clock()
        window_end = plan.generated_at + timedelta(seconds=plan.horizon_seconds)
        if window_end > now:
            return None  # horizon not matured; do not score early
        candles = self._fetch_window_candles(plan.symbol, plan.generated_at, window_end)
        window = build_outcome_window_from_candles(
            name=f"{plan.symbol}:{plan.horizon_seconds:.0f}s",
            symbol=plan.symbol,
            interval=self.config.market_data.candle_bar,
            source_type="exchange_native",
            window_start=plan.generated_at.isoformat(),
            window_end=window_end.isoformat(),
            collected_at=now.isoformat(),
            candles=candles,
            matured=True,
        )
        if not window.can_score_execution_outcome and plan.action.strip().lower() != "no trade":
            # Without complete price data we cannot score a trade outcome; record
            # the window anyway so the store reflects the collection attempt, but
            # only return a scoreable outcome when data is complete.
            outcome = self._build_outcome(plan, window)
            self.outcome_store.upsert_outcomes([outcome])
            return None
        outcome = self._build_outcome(plan, window)
        self.outcome_store.upsert_outcomes([outcome])
        return outcome

    def _build_outcome(self, plan: PlanOutcomeInput, window: OutcomeWindow) -> DecisionOutcome:
        return DecisionOutcome(
            decision_ref=plan.decision_ref,
            evaluation_target=plan.evaluation_target,
            symbol=plan.symbol,
            action=plan.action,
            probability=plan.probability,
            entry_price=plan.entry_price,
            stop_price=plan.stop_price,
            target_1=plan.target_1,
            target_2=plan.target_2,
            window=window,
        )

    def _fetch_window_candles(
        self,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch OKX history-candles covering [window_start, window_end].

        OKX /api/v5/market/history-candles returns rows in descending ts order:
        [ts, o, h, l, c, vol, volCcy, volCcyConfirm, confirm]. We page backward from
        window_end until we pass window_start, then convert to {open,high,low,close}
        dicts for build_outcome_window_from_candles.
        """
        start_ms = int(window_start.timestamp() * 1000)
        end_ms = int(window_end.timestamp() * 1000)
        rows: list[list[Any]] = []
        after_ms = end_ms
        for _ in range(20):  # bounded pagination; 20 * 100 candles is ample for typical horizons
            payload = self._get(
                "/api/v5/market/history-candles",
                {
                    "instId": symbol,
                    "bar": self.config.market_data.candle_bar,
                    "after": str(after_ms),
                    "limit": "100",
                },
            )
            data = payload.get("data") if isinstance(payload, Mapping) else None
            if not isinstance(data, list) or not data:
                break
            batch = [row for row in data if isinstance(row, list)]
            rows.extend(batch)
            oldest_ts = _row_ts(batch[-1])
            if oldest_ts is None or oldest_ts <= start_ms:
                break
            after_ms = oldest_ts
        candles: list[dict[str, Any]] = []
        for row in rows:
            ts = _row_ts(row)
            if ts is None or ts < start_ms or ts > end_ms:
                continue
            if len(row) < 5:
                continue
            candles.append(
                {
                    "ts": ts,
                    "open": _to_float(row[1]),
                    "high": _to_float(row[2]),
                    "low": _to_float(row[3]),
                    "close": _to_float(row[4]),
                }
            )
        candles.sort(key=lambda item: item["ts"])
        return candles

    def _get(self, path: str, params: dict[str, str]) -> Mapping[str, Any]:
        if self.http_get is not None:
            payload = self.http_get(path, params)
        else:
            base_url = self.config.market_data.okx_base_url.rstrip("/")
            with httpx.Client(base_url=base_url, timeout=self.config.market_data.request_timeout_seconds) as client:
                response = client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
        if not isinstance(payload, Mapping):
            raise RuntimeError("OKX response payload must be an object")
        if str(payload.get("code")) != "0":
            raise RuntimeError(f"OKX returned code={payload.get('code')} msg={payload.get('msg')}")
        return payload


def _row_ts(row: list[Any]) -> int | None:
    if not row:
        return None
    try:
        return int(float(row[0]))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float:
    if value is None or value == "":
        raise ValueError("candle field missing")
    return float(value)
