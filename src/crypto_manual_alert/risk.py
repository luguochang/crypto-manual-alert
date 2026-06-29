from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from .config import Config
from .domain import OPENING_ACTIONS, DecisionPlan, MarketSnapshot, RiskVerdict


class ConfidenceCap(NamedTuple):
    value: float
    reason: str


DERIVATIVES_GAP_CAP = ConfidenceCap(0.58, "拥挤度或清算数据不可用")
CORE_EXECUTION_POINTS = ("mark", "index", "order_book")


def check_plan(plan: DecisionPlan, snapshot: MarketSnapshot, config: Config, now: datetime | None = None) -> RiskVerdict:
    current = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    warnings: list[str] = []

    if config.app.mode == "OFF":
        reasons.append("应用模式为 OFF")
    if not plan.manual_execution_required:
        reasons.append("计划未声明必须人工执行")
    if plan.instrument not in config.trading.allowed_symbols:
        reasons.append(f"交易品种不在允许列表：{plan.instrument}")
    if plan.expires_at <= current:
        reasons.append("计划已过期")
    if plan.main_action in OPENING_ACTIONS and plan.stop_price is None:
        reasons.append("开仓、触发或反手动作必须提供止损价")
    if plan.main_action in OPENING_ACTIONS and plan.entry_trigger is None:
        reasons.append("开仓、触发或反手动作必须提供触发价")
    if plan.main_action in OPENING_ACTIONS and not plan.invalidation.strip():
        reasons.append("开仓、触发或反手动作必须提供失效条件")
    if plan.main_action in OPENING_ACTIONS:
        missing_execution = [name for name in CORE_EXECUTION_POINTS if name not in snapshot.points]
        if missing_execution:
            reasons.append(f"核心执行行情缺失：{', '.join(missing_execution)}")
    if plan.risk_pct is not None and plan.risk_pct > config.trading.max_risk_per_trade_pct:
        reasons.append("risk_pct 超过配置的单笔最大风险")
    if plan.max_leverage is not None and plan.max_leverage > config.trading.max_leverage:
        reasons.append("max_leverage 超过配置的最大杠杆")

    confidence_cap = _confidence_cap_from_snapshot(snapshot)
    if confidence_cap and plan.probability is not None and plan.probability > confidence_cap.value:
        reasons.append(f"胜率超过置信度上限 {confidence_cap.value:.2f}：{confidence_cap.reason}")

    stale = _stale_points(snapshot, config, current)
    if stale:
        reasons.append(f"行情数据陈旧：{', '.join(stale)}")
    if snapshot.unavailable:
        warnings.append(f"不可用行情数据：{', '.join(snapshot.unavailable)}")
    if config.trading.auto_order_enabled:
        reasons.append("产品边界禁止自动下单")

    return RiskVerdict(allowed=not reasons, reasons=reasons, warnings=warnings)


def _confidence_cap_from_snapshot(snapshot: MarketSnapshot) -> ConfidenceCap | None:
    caps: list[ConfidenceCap] = []
    for item in snapshot.unavailable:
        parts = item.split(":", 2)
        if len(parts) != 3 or parts[0] != "confidence_cap":
            normalized = item.lower()
            if "liquidation heatmap" in normalized or "precise cvd" in normalized:
                caps.append(DERIVATIVES_GAP_CAP)
            continue
        try:
            value = float(parts[1])
        except ValueError:
            continue
        caps.append(ConfidenceCap(value=value, reason=parts[2]))
    if not caps:
        return None
    # 多个数据缺口同时给 cap 时，采用最保守的上限。
    return min(caps, key=lambda cap: cap.value)


def _stale_points(snapshot: MarketSnapshot, config: Config, now: datetime) -> list[str]:
    stale: list[str] = []
    for name, point in snapshot.points.items():
        age = point.age_seconds(now)
        threshold = _stale_threshold_seconds(name, config)
        if age is None or age > threshold:
            stale.append(name)
    return stale


def _stale_threshold_seconds(name: str, config: Config) -> int:
    if name == "candles":
        return _bar_to_seconds(config.market_data.candle_bar) + config.market_data.stale_market_data_seconds
    return config.market_data.stale_market_data_seconds


def _bar_to_seconds(candle_bar: str) -> int:
    normalized = candle_bar.strip().upper()
    if normalized.endswith("H"):
        return int(normalized[:-1] or "1") * 3600
    if normalized.endswith("M"):
        return int(normalized[:-1] or "1") * 60
    if normalized.endswith("D"):
        return int(normalized[:-1] or "1") * 86400
    return 3600
