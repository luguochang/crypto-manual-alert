from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from .config import Config
from .domain import OPENING_ACTIONS, DecisionPlan, MarketSnapshot, RiskVerdict, RuleHit


class ConfidenceCap(NamedTuple):
    value: float
    reason: str


DERIVATIVES_GAP_CAP = ConfidenceCap(0.58, "crowding or liquidation data unavailable")
CORE_EXECUTION_POINTS = ("mark", "index", "order_book")


def check_plan(plan: DecisionPlan, snapshot: MarketSnapshot, config: Config, now: datetime | None = None) -> RiskVerdict:
    """对模型输出做确定性风控校验，并把每条规则命中结构化记录下来。"""

    current = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    warnings: list[str] = []
    rule_hits: list[RuleHit] = []

    def block(
        rule_id: str,
        message: str,
        *,
        severity: str = "critical",
        evidence_refs: list[str] | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        reasons.append(message)
        rule_hits.append(
            RuleHit(
                rule_id=rule_id,
                passed=False,
                severity=severity,
                message=message,
                blocking=True,
                evidence_refs=evidence_refs or [],
                details=details or {},
            )
        )

    def warn(
        rule_id: str,
        message: str,
        *,
        evidence_refs: list[str] | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        warnings.append(message)
        rule_hits.append(
            RuleHit(
                rule_id=rule_id,
                passed=True,
                severity="medium",
                message=message,
                blocking=False,
                evidence_refs=evidence_refs or [],
                details=details or {},
            )
        )

    if config.app.mode == "OFF":
        block("app.mode.off", "应用模式为 OFF，禁止生成可执行操作。", evidence_refs=["config.app.mode"])
    if not plan.manual_execution_required:
        block(
            "manual_execution.required",
            "计划未声明必须人工执行。",
            evidence_refs=["plan.manual_execution_required"],
        )
    if plan.instrument not in config.trading.allowed_symbols:
        block(
            "instrument.allowed_symbol",
            f"交易品种不在允许列表：{plan.instrument}",
            evidence_refs=["plan.instrument", "config.trading.allowed_symbols"],
            details={"instrument": plan.instrument, "allowed_symbols": list(config.trading.allowed_symbols)},
        )
    if plan.expires_at <= current:
        block(
            "plan.expired",
            "计划已过期。",
            evidence_refs=["plan.expires_at"],
            details={"expires_at": plan.expires_at.isoformat(), "now": current.isoformat()},
        )
    if plan.main_action in OPENING_ACTIONS and plan.stop_price is None:
        block(
            "opening.stop_price.required",
            "开仓、触发或反手动作必须提供止损价。",
            evidence_refs=["plan.main_action", "plan.stop_price"],
        )
    if plan.main_action in OPENING_ACTIONS and plan.entry_trigger is None:
        block(
            "opening.entry_trigger.required",
            "开仓、触发或反手动作必须提供触发价。",
            evidence_refs=["plan.main_action", "plan.entry_trigger"],
        )
    if plan.main_action in OPENING_ACTIONS and not plan.invalidation.strip():
        block(
            "opening.invalidation.required",
            "开仓、触发或反手动作必须提供失效条件。",
            evidence_refs=["plan.main_action", "plan.invalidation"],
        )
    if plan.main_action in OPENING_ACTIONS:
        missing_execution = [name for name in CORE_EXECUTION_POINTS if name not in snapshot.points]
        if missing_execution:
            block(
                "market.core_execution.missing",
                f"核心执行行情缺失：{', '.join(missing_execution)}",
                severity="high",
                evidence_refs=["snapshot.points"],
                details={"missing": missing_execution},
            )
    if plan.risk_pct is not None and plan.risk_pct > config.trading.max_risk_per_trade_pct:
        block(
            "risk_pct.max",
            "risk_pct 超过配置的单笔最大风险。",
            evidence_refs=["plan.risk_pct", "config.trading.max_risk_per_trade_pct"],
            details={"risk_pct": plan.risk_pct, "max_risk_per_trade_pct": config.trading.max_risk_per_trade_pct},
        )
    if plan.max_leverage is not None and plan.max_leverage > config.trading.max_leverage:
        block(
            "leverage.max",
            "max_leverage 超过配置的最大杠杆。",
            evidence_refs=["plan.max_leverage", "config.trading.max_leverage"],
            details={"max_leverage": plan.max_leverage, "configured_max_leverage": config.trading.max_leverage},
        )

    confidence_cap = _confidence_cap_from_snapshot(snapshot)
    if confidence_cap and plan.probability is not None and plan.probability > confidence_cap.value:
        block(
            "confidence.probability.cap",
            f"胜率超过置信度上限 {confidence_cap.value:.2f}：{confidence_cap.reason}",
            severity="high",
            evidence_refs=["plan.probability", "snapshot.unavailable"],
            details={
                "configured_cap": confidence_cap.value,
                "plan_probability": plan.probability,
                "reason": confidence_cap.reason,
            },
        )

    stale = _stale_points(snapshot, config, current)
    if stale:
        block(
            "market.data.stale",
            f"行情数据陈旧：{', '.join(stale)}",
            severity="high",
            evidence_refs=["snapshot.points"],
            details={"stale_points": stale},
        )
    if snapshot.unavailable:
        warn(
            "market.data.unavailable",
            f"不可用行情数据：{', '.join(snapshot.unavailable)}",
            evidence_refs=["snapshot.unavailable"],
            details={"unavailable": list(snapshot.unavailable)},
        )
    if config.trading.auto_order_enabled:
        block(
            "product.auto_order.disabled",
            "产品边界禁止自动下单。",
            evidence_refs=["config.trading.auto_order_enabled"],
        )

    return RiskVerdict(allowed=not reasons, reasons=reasons, warnings=warnings, rule_hits=rule_hits)


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
