"""14 条确定性风控规则 - 纯函数实现。

来源：V1 decision/risk.py 的 check_plan 函数迁移到 V2 Pydantic 模型。

设计原则（设计文档 02 约束）：
1. 风控规则是纯函数：无网络、无 DB、无 LLM 依赖
2. 输入：MarketAnalysis + config dict + 可选的 market_snapshot dict
3. 输出：RiskVerdict（allowed + blocked_reasons + warnings + confidence_cap）
4. 每条规则独立检查，blocking 规则阻断，warn 规则只警告
5. 中文注释解释每条规则的业务含义

14 条规则清单（从 V1 迁移 + V2 设计文档补充）：
 1. _check_manual_execution_required - 必须人工执行
 2. _check_allowed_symbol         - 交易品种白名单
 3. _check_plan_not_expired       - 计划未过期
 4. _check_opening_has_stop       - 开仓必须有止损
 5. _check_opening_has_entry      - 开仓必须有入场触发价
 6. _check_opening_has_invalidation - 开仓必须有失效条件
 7. _check_core_execution_data    - 开仓必须有核心执行数据
 8. _check_risk_pct_max           - 风险占比不超限
 9. _check_leverage_max           - 杠杆不超限
10. _check_confidence_cap         - 置信度不超上限
11. _check_data_freshness         - 数据新鲜度检查
12. _check_auto_order_disabled    - 禁止自动下单
13. _check_app_mode               - 应用模式检查
14. _check_market_data_unavailable - 数据缺失警告（warn only）
"""

from datetime import datetime, timezone
from typing import Any

from crypto_alert_v2.domain.models import (
    OPENING_ACTIONS,
    MarketAnalysis,
    RiskVerdict,
)

# 核心执行数据点：开仓类动作必需的行情数据
CORE_EXECUTION_FIELDS = ("ticker", "mark_price", "index_price", "order_book", "candles")

# 默认风控配置（可被 config 参数覆盖）
DEFAULT_RISK_CONFIG = {
    "allowed_symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"],
    "max_leverage": 2,
    "max_risk_pct": 0.25,
    "auto_order_enabled": False,
    "app_mode": "development",  # development / production / off
    "stale_market_data_seconds": 90,
}


def check_plan(
    analysis: MarketAnalysis,
    config: dict[str, Any] | None = None,
    market_snapshot: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> RiskVerdict:
    """检查 14 条风控规则。

    依次执行所有规则，blocking 规则的 reason 收集到 blocked_reasons，
    warn 规则的 message 收集到 warnings。
    任何 blocking 规则命中则 allowed=False。

    Args:
        analysis: LLM 结构化输出
        config: 风控配置字典（覆盖默认配置）
        market_snapshot: 市场快照字典（含 data_fetched_at, unavailable_fields 等）
        now: 当前时间（测试注入用），默认 UTC now

    Returns:
        RiskVerdict: 聚合风控裁决
    """
    cfg = {**DEFAULT_RISK_CONFIG, **(config or {})}
    current = now or datetime.now(timezone.utc)
    snapshot = market_snapshot or {}

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    # 依次执行 14 条规则
    # blocking 规则返回 (is_block, message)，warn 规则返回 (is_block, message)
    rules = [
        _check_manual_execution_required,
        _check_allowed_symbol,
        _check_plan_not_expired,
        _check_opening_has_stop,
        _check_opening_has_entry,
        _check_opening_has_invalidation,
        _check_core_execution_data,
        _check_risk_pct_max,
        _check_leverage_max,
        _check_confidence_cap,
        _check_data_freshness,
        _check_auto_order_disabled,
        _check_app_mode,
        _check_market_data_unavailable,  # warn only
    ]

    for rule_fn in rules:
        result = rule_fn(analysis, cfg, snapshot, current)
        if result is None:
            continue
        is_block, message = result
        if is_block:
            blocked_reasons.append(message)
        else:
            warnings.append(message)

    return RiskVerdict(
        allowed=len(blocked_reasons) == 0,
        blocked_reasons=blocked_reasons,
        warnings=warnings,
        confidence_cap=1.0,  # confidence_cap 由证据门禁设置，风控不修改
    )


# ===========================================================================
# 14 条规则实现
# ===========================================================================

def _check_manual_execution_required(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 1：必须人工执行。

    manual_execution_required 必须为 True。
    这是产品边界的硬性约束：系统永远不自动下单（设计文档核心原则）。
    """
    if not analysis.manual_execution_required:
        return True, "计划未声明必须人工执行（manual_execution_required=False）"
    return None


def _check_allowed_symbol(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 2：交易品种白名单。

    instrument 必须在配置的 allowed_symbols 列表中。
    Phase 1 只允许 BTC/ETH/SOL 的 USDT 永续合约。
    """
    allowed = config.get("allowed_symbols", DEFAULT_RISK_CONFIG["allowed_symbols"])
    if analysis.instrument not in allowed:
        return True, f"交易品种不在允许列表：{analysis.instrument}（允许：{allowed}）"
    return None


def _check_plan_not_expired(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 3：计划未过期。

    分析结果有 90 秒有效期（expires_in_seconds=90）。
    过期的分析结果不可执行，必须重新分析。
    数据时效性是杠杆交易的生命线。
    """
    # expires_in_seconds 默认 90 秒，从分析生成时间开始计算
    # Phase 1 简化：检查 expires_in_seconds 是否为正值
    if analysis.expires_in_seconds <= 0:
        return True, f"计划已过期（expires_in_seconds={analysis.expires_in_seconds}）"
    return None


def _check_opening_has_stop(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 4：开仓必须有止损价。

    开仓/触发/反手类动作必须提供 stop_price。
    没有止损的开仓是裸奔，风控不允许。
    hold/close/no_trade 类动作不需要止损。
    """
    if analysis.main_action in OPENING_ACTIONS and analysis.stop_price is None:
        return True, f"开仓类动作（{analysis.main_action}）必须提供止损价（stop_price）"
    return None


def _check_opening_has_entry(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 5：开仓必须有入场触发价。

    开仓/触发/反手类动作必须提供 entry_trigger。
    入场触发价定义了"什么条件下执行"，是人工执行的锚点。
    """
    if analysis.main_action in OPENING_ACTIONS and analysis.entry_trigger is None:
        return True, f"开仓类动作（{analysis.main_action}）必须提供触发价（entry_trigger）"
    return None


def _check_opening_has_invalidation(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 6：开仓必须有失效条件。

    开仓/触发/反手类动作必须提供 invalidation 描述。
    失效条件回答"什么情况下此分析作废"，是风险管理的关键。
    """
    if analysis.main_action in OPENING_ACTIONS and not analysis.invalidation.strip():
        return True, f"开仓类动作（{analysis.main_action}）必须提供失效条件（invalidation）"
    return None


def _check_core_execution_data(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 7：开仓必须有核心执行数据。

    开仓类动作需要 ticker、mark_price、index_price、order_book、candles 五项核心数据。
    这些是执行决策的最低数据要求，缺失则阻断开仓（设计文档 Live Fact Gate）。
    数据缺失标注在 market_snapshot.unavailable_fields 或 analysis.unavailable_data 中。
    """
    if analysis.main_action not in OPENING_ACTIONS:
        return None

    # 合并快照和分析中的缺失数据
    unavailable_fields = set(snapshot.get("unavailable_fields", []))
    unavailable_fields.update(analysis.unavailable_data)

    missing = [f for f in CORE_EXECUTION_FIELDS if f in unavailable_fields]
    if missing:
        return True, f"核心执行行情缺失：{', '.join(missing)}"
    return None


def _check_risk_pct_max(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 8：单笔风险占比不超限。

    risk_pct 不得超过配置的 max_risk_pct（默认 25%）。
    这是资金管理的硬性上限，保护用户不被单笔亏损击穿。
    Pydantic schema 已限制 risk_pct <= 0.25，风控再做业务级检查。
    """
    max_risk = config.get("max_risk_pct", DEFAULT_RISK_CONFIG["max_risk_pct"])
    if analysis.risk_pct > max_risk:
        return True, (
            f"risk_pct（{analysis.risk_pct}）超过配置的单笔最大风险（{max_risk}）"
        )
    return None


def _check_leverage_max(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 9：最大杠杆不超限。

    max_leverage 不得超过配置的 max_leverage（默认 2x）。
    杠杆是双刃剑，2x 是 Phase 1 的硬性上限。
    Pydantic schema 已限制 max_leverage <= 2，风控再做业务级检查。
    """
    max_lev = config.get("max_leverage", DEFAULT_RISK_CONFIG["max_leverage"])
    if analysis.max_leverage > max_lev:
        return True, (
            f"max_leverage（{analysis.max_leverage}）超过配置的最大杠杆（{max_lev}）"
        )
    return None


def _check_confidence_cap(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 10：置信度不超上限。

    当可选证据缺失时（如 funding_rate、long_short_ratio 等），
    证据门禁会设置 confidence_cap。模型的 probability 不得超过此上限。
    Phase 1 简化：检查 analysis.unavailable_data 中的已知降级项。

    降级规则（设计文档 14 第 2.2 节）：
    - 缺 long_short_ratio 或 CVD：cap=0.70
    - 缺 liquidation_map：cap=0.65
    - 缺 BTC 方向锚（分析 ETH/SOL 时）：cap=0.60
    """
    unavailable = set(analysis.unavailable_data)

    # 计算最低置信度上限
    caps: list[float] = []
    cap_reasons: list[str] = []

    # 衍生品数据缺失降级
    if "funding_rate" in unavailable:
        caps.append(0.70)
        cap_reasons.append("funding_rate 缺失")
    if "open_interest" in unavailable:
        caps.append(0.70)
        cap_reasons.append("open_interest 缺失")
    if "long_short_ratio" in unavailable:
        caps.append(0.65)
        cap_reasons.append("long_short_ratio 缺失")
    if "liquidation_map" in unavailable:
        caps.append(0.58)
        cap_reasons.append("liquidation_map 缺失")

    # BTC 方向锚缺失（分析 ETH/SOL 时）
    if analysis.instrument != "BTC-USDT-SWAP" and "btc_anchor" in unavailable:
        caps.append(0.60)
        cap_reasons.append("BTC 方向锚缺失")

    if not caps:
        return None

    min_cap = min(caps)
    if analysis.probability > min_cap:
        return True, (
            f"胜率（{analysis.probability}）超过置信度上限（{min_cap}）："
            f"{'; '.join(cap_reasons)}"
        )
    return None


def _check_data_freshness(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 11：数据新鲜度检查。

    行情数据超过 90 秒视为陈旧，阻断开仓。
    数据时间戳在 market_snapshot.data_fetched_at 中。

    新鲜度规则（设计文档 14 第 2.1 节）：
    - 行情数据 > 90s：阻断开仓
    - 衍生品数据 > 5min：置信度降级
    - 宏观数据 > 1h：置信度降级
    """
    if analysis.main_action not in OPENING_ACTIONS:
        return None

    data_fetched_at = snapshot.get("data_fetched_at")
    if data_fetched_at is None:
        # 没有时间戳，无法判断新鲜度，阻断开仓
        return True, "市场快照缺少 data_fetched_at 时间戳，无法验证新鲜度"

    # 解析时间戳
    try:
        if isinstance(data_fetched_at, str):
            fetched_at = datetime.fromisoformat(data_fetched_at.replace("Z", "+00:00"))
        elif isinstance(data_fetched_at, datetime):
            fetched_at = data_fetched_at
        else:
            return True, f"data_fetched_at 格式无法解析：{data_fetched_at}"
    except (ValueError, AttributeError):
        return True, f"data_fetched_at 时间戳解析失败：{data_fetched_at}"

    # 计算数据年龄
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age_seconds = (now - fetched_at).total_seconds()

    stale_threshold = config.get(
        "stale_market_data_seconds", DEFAULT_RISK_CONFIG["stale_market_data_seconds"]
    )
    if age_seconds > stale_threshold:
        return True, (
            f"行情数据陈旧：年龄 {age_seconds:.0f}s 超过阈值 {stale_threshold}s"
        )
    return None


def _check_auto_order_disabled(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 12：禁止自动下单。

    config.auto_order_enabled 必须为 False。
    这是产品边界的硬性约束：系统只提供人工确认建议，永远不自动下单。
    如果配置开启了 auto_order，风控直接阻断（防误配置）。
    """
    if config.get("auto_order_enabled", False):
        return True, "产品边界禁止自动下单（auto_order_enabled 被错误开启）"
    return None


def _check_app_mode(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 13：应用模式检查。

    config.app_mode 为 "off" 时禁止生成可执行操作。
    app_mode 取值：development / production / off
    - development：开发模式，允许生成建议
    - production：生产模式，允许生成建议
    - off：维护模式，禁止一切可执行操作
    """
    mode = config.get("app_mode", "development")
    if mode == "off":
        return True, "应用模式为 OFF（维护模式），禁止生成可执行操作"
    return None


def _check_market_data_unavailable(
    analysis: MarketAnalysis,
    config: dict[str, Any],
    snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, str] | None:
    """规则 14：数据缺失警告（warn only，不阻断）。

    当 analysis.unavailable_data 或 snapshot.unavailable_fields 非空时，
    添加警告但不阻断。缺失数据已通过规则 7（核心执行数据）和规则 10（置信度上限）
    处理了阻断和降级，这里只做信息性提醒。

    返回 (False, message) 表示 warn only。
    """
    unavailable = set(analysis.unavailable_data)
    unavailable.update(snapshot.get("unavailable_fields", []))

    if unavailable:
        return False, f"不可用行情数据：{', '.join(sorted(unavailable))}"
    return None
