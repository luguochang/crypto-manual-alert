"""证据门禁 - 检查证据是否充足。

来源：14-system-prompt-and-evidence-gates.md 第 2.5 节。

设计原则：
1. 纯函数：无网络、无 DB、无 LLM 依赖
2. 必需证据缺失 -> 阻断开仓（sufficient=False）
3. 可选证据缺失 -> 降级置信度（confidence_cap 降低）
4. 新鲜度检查：行情 > 90s 阻断，衍生品 > 5min 降级，宏观 > 1h 降级

证据分级（设计文档 14 第 2.1-2.2 节）：
- 必需证据：ticker, mark_price, index_price, order_book, candles, 宏观事件扫描
- 可选证据：funding_rate, open_interest, long_short_ratio, CVD, liquidation_map, ETF flows
"""

from datetime import datetime, timezone
from typing import Any

from crypto_alert_v2.domain.models import (
    OPENING_ACTIONS,
    EvidenceVerdict,
)

# ===========================================================================
# 必需证据项（缺失则阻断开仓）
# ===========================================================================

REQUIRED_MARKET_FIELDS = frozenset({
    "ticker", "mark_price", "index_price", "order_book", "candles",
})

# 宏观状态必需项（仅开仓类动作需要）
REQUIRED_MACRO_FIELDS = frozenset({
    "vix", "real_yield_10y", "dxy", "macro_event_scan",
})

# ===========================================================================
# 可选证据项及缺失时的置信度上限
# ===========================================================================

OPTIONAL_FIELD_CAPS: dict[str, float] = {
    "funding_rate": 0.70,
    "open_interest": 0.70,
    "long_short_ratio": 0.65,
    "cvd_taker_delta": 0.65,
    "liquidation_map": 0.58,
    "etf_flows": 0.70,
    "stablecoin_supply": 0.75,
    "btc_anchor": 0.60,  # 分析 ETH/SOL 时 BTC 方向锚缺失
}

# 行情数据新鲜度阈值（秒）
STALE_MARKET_THRESHOLD = 90

# 衍生品数据新鲜度阈值（秒）
STALE_DERIVATIVES_THRESHOLD = 300  # 5 分钟

# 宏观数据新鲜度阈值（秒）
STALE_MACRO_THRESHOLD = 3600  # 1 小时


def check_evidence_sufficiency(
    market_snapshot: dict[str, Any] | None,
    research_bundle: dict[str, Any] | None,
    main_action: str,
    instrument: str = "BTC-USDT-SWAP",
    now: datetime | None = None,
) -> EvidenceVerdict:
    """检查证据是否充足。

    实现设计文档 14 第 2.5 节的 check_evidence_sufficiency 函数。

    流程：
    1. 检查必需市场数据（ticker/mark/index/order_book/candles）
    2. 检查数据新鲜度（> 90s 阻断）
    3. 检查宏观事件状态（仅开仓类动作需要）
    4. 检查可选数据缺失 -> 降级 confidence_cap
    5. 返回 EvidenceVerdict

    Args:
        market_snapshot: 市场快照字典，包含 ticker/mark_price/index_price 等字段
        research_bundle: 研究结果字典，包含 macro_findings 等
        main_action: 主动作枚举值
        instrument: 交易标的（用于判断是否需要 BTC 方向锚）
        now: 当前时间（测试注入用）

    Returns:
        EvidenceVerdict: 证据门禁判定结果
    """
    current = now or datetime.now(timezone.utc)
    snapshot = market_snapshot or {}
    research = research_bundle or {}

    missing_required: list[str] = []
    missing_optional: list[str] = []
    warnings: list[str] = []
    confidence_cap = 1.0

    # --- 步骤 1：必需市场数据检查 ---
    for field in REQUIRED_MARKET_FIELDS:
        if snapshot.get(field) is None:
            missing_required.append(field)

    # --- 步骤 2：数据新鲜度检查 ---
    data_fetched_at = snapshot.get("data_fetched_at")
    if data_fetched_at is not None:
        age_seconds = _calculate_age_seconds(data_fetched_at, current)
        if age_seconds is not None:
            if age_seconds > STALE_MARKET_THRESHOLD:
                missing_required.append("data_freshness")
                warnings.append(
                    f"行情数据陈旧：年龄 {age_seconds:.0f}s 超过阈值 {STALE_MARKET_THRESHOLD}s"
                )
    elif main_action in OPENING_ACTIONS:
        # 开仓类动作必须有 data_fetched_at
        missing_required.append("data_fetched_at")

    # 如果必需数据缺失，直接返回不充足（不需要检查可选数据）
    if missing_required:
        return EvidenceVerdict(
            sufficient=False,
            confidence_cap=0.0,
            missing_required=missing_required,
            missing_optional=[],
            warnings=warnings,
        )

    # --- 步骤 3：宏观事件检查（仅开仓类动作）---
    if main_action in OPENING_ACTIONS:
        macro_findings = research.get("macro_findings")
        if not macro_findings:
            missing_required.append("macro_event_status")
            return EvidenceVerdict(
                sufficient=False,
                confidence_cap=0.0,
                missing_required=missing_required,
                missing_optional=[],
                warnings=warnings + ["开仓类动作需要宏观事件状态，但研究包为空"],
            )

    # --- 步骤 4：可选数据缺失降级 ---
    # 检查每个可选字段，缺失则降低 confidence_cap
    for field, cap in OPTIONAL_FIELD_CAPS.items():
        # BTC 方向锚只在分析 ETH/SOL 时需要
        if field == "btc_anchor" and instrument == "BTC-USDT-SWAP":
            continue

        if snapshot.get(field) is None:
            missing_optional.append(field)
            confidence_cap = min(confidence_cap, cap)
            warnings.append(f"{field} 缺失，置信度上限降至 {cap}")

    # 衍生品数据新鲜度检查（降级，不阻断）
    derivatives_fields = ["funding_rate", "open_interest"]
    for field in derivatives_fields:
        field_data = snapshot.get(field)
        if field_data and isinstance(field_data, dict):
            field_ts = field_data.get("fetched_at") or field_data.get("ts")
            if field_ts:
                age = _calculate_age_seconds(field_ts, current)
                if age is not None and age > STALE_DERIVATIVES_THRESHOLD:
                    confidence_cap = min(confidence_cap, 0.70)
                    warnings.append(
                        f"{field} 数据陈旧（{age:.0f}s），置信度降级至 70%"
                    )

    # --- 步骤 5：返回最终判定 ---
    return EvidenceVerdict(
        sufficient=True,
        confidence_cap=confidence_cap,
        missing_required=[],
        missing_optional=missing_optional,
        warnings=warnings,
    )


def _calculate_age_seconds(
    timestamp_value: Any,
    now: datetime,
) -> float | None:
    """从时间戳值计算数据年龄（秒）。

    支持多种时间戳格式：
    - ISO 8601 字符串（含/不含 Z 后缀）
    - datetime 对象
    - Unix 时间戳（int/float）
    """
    try:
        if isinstance(timestamp_value, str):
            # ISO 8601 字符串
            ts = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        elif isinstance(timestamp_value, datetime):
            ts = timestamp_value
        elif isinstance(timestamp_value, (int, float)):
            # Unix 时间戳（秒）
            ts = datetime.fromtimestamp(timestamp_value, tz=timezone.utc)
        else:
            return None

        # 确保 timezone-aware
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return (now - ts).total_seconds()
    except (ValueError, TypeError, OSError):
        return None
