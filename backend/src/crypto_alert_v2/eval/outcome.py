"""Outcome 追踪 - 成熟窗口后的真实结果采集与指标计算。

来源：V2重构方案评审与补充建议_修订版.md 第 6.6 节。

成熟窗口：分析生成后 4h/12h/24h（对应 horizon）。

指标：
| 指标               | 定义             | 计算方式                        |
|--------------------|------------------|---------------------------------|
| Hit Rate           | 方向判断正确率    | 正确数 / 总数                   |
| Brier Score        | 概率校准         | (1/N) * sum((p_i - o_i)^2)     |
| MFE                | 最大有利偏移      | 入场后最大盈利                   |
| MAE                | 最大不利偏移      | 入场后最大亏损                   |
| PnL                | 模拟盈亏         | 按入场/止损/止盈模拟             |
| No-Trade Baseline  | 不交易基准收益    | 用于验证是否优于不交易           |

分级门禁：
| 阶段     | 样本数 | 覆盖时间 | 门禁内容                              |
|----------|--------|----------|---------------------------------------|
| 管道证明 | 1      | -        | 证明 outcome 采集管道可用              |
| Beta     | 50+    | 7天      | Hit Rate >= 55%, 无重大风控失误        |
| GA       | 200+   | 30天     | Hit Rate >= 60%, Brier < 0.25, 风控 100%|
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ===========================================================================
# 成熟窗口定义
# ===========================================================================

class MaturityWindow(str, Enum):
    """成熟窗口期（对应分析 horizon）。"""
    H4 = "4h"    # 4 小时
    H12 = "12h"  # 12 小时
    H24 = "24h"  # 24 小时


WINDOW_DURATION: dict[MaturityWindow, timedelta] = {
    MaturityWindow.H4: timedelta(hours=4),
    MaturityWindow.H12: timedelta(hours=12),
    MaturityWindow.H24: timedelta(hours=24),
}


def compute_maturity_window(
    created_at: datetime,
    horizon: str,
) -> tuple[datetime, datetime]:
    """计算成熟窗口的起止时间。

    Args:
        created_at: 分析创建时间
        horizon: 分析周期（"4h" / "12h" / "24h"）

    Returns:
        (window_start, window_end) 元组
    """
    try:
        window = MaturityWindow(horizon)
    except ValueError:
        # 默认 4h
        window = MaturityWindow.H4

    duration = WINDOW_DURATION[window]
    window_start = created_at
    window_end = created_at + duration
    return window_start, window_end


def is_mature(
    created_at: datetime,
    horizon: str,
    now: datetime | None = None,
) -> bool:
    """检查分析是否已到成熟窗口。

    Args:
        created_at: 分析创建时间
        horizon: 分析周期
        now: 当前时间（默认 UTC now）

    Returns:
        True 如果已过成熟窗口
    """
    now = now or datetime.now(timezone.utc)
    _, window_end = compute_maturity_window(created_at, horizon)
    return now >= window_end


# ===========================================================================
# K 线数据结构
# ===========================================================================

@dataclass
class Candle:
    """K 线数据。"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


# ===========================================================================
# Outcome 计算结果
# ===========================================================================

class OutcomeResult(BaseModel):
    """单次分析的 outcome 计算结果。"""
    analysis_id: str = Field(description="关联的分析 ID")
    symbol: str = Field(description="交易标的")
    direction: str = Field(description="分析方向: long/short/neutral")
    window: str = Field(description="成熟窗口: 4h/12h/24h")
    window_start: datetime = Field(description="窗口开始时间")
    window_end: datetime = Field(description="窗口结束时间")
    open_price: float | None = Field(default=None, description="窗口开始价格")
    high_price: float | None = Field(default=None, description="窗口内最高价")
    low_price: float | None = Field(default=None, description="窗口内最低价")
    close_price: float | None = Field(default=None, description="窗口结束价格")

    # 方向命中
    direction_hit: bool | None = Field(default=None, description="方向是否正确")
    target_hit: bool | None = Field(default=None, description="是否触达目标价")
    invalidation_hit: bool | None = Field(default=None, description="是否触达失效条件")

    # 概率校准
    predicted_probability: float | None = Field(default=None, description="预测胜率")
    brier_score: float | None = Field(default=None, description="Brier Score")

    # 盈亏指标
    pnl_pct: float | None = Field(default=None, description="模拟盈亏百分比")
    mfe: float | None = Field(default=None, description="MFE - 最大有利偏移")
    mae: float | None = Field(default=None, description="MAE - 最大不利偏移")
    r_multiple: float | None = Field(default=None, description="R 倍数")

    # 基准对比
    no_trade_baseline_pnl: float | None = Field(
        default=None, description="不交易基准收益百分比"
    )
    alpha: float | None = Field(default=None, description="超额收益 = pnl - baseline")

    # 状态
    scoring_status: str = Field(
        default="pending", description="pending/scored/unscoreable"
    )
    unscoreable_reason: str | None = Field(default=None)


# ===========================================================================
# 指标计算函数
# ===========================================================================

def calculate_direction_hit(
    direction: str,
    open_price: float,
    close_price: float,
) -> bool:
    """计算方向命中率。

    long: close > open 为正确
    short: close < open 为正确
    neutral: 总是正确（不需要方向判断）
    """
    if direction == "long":
        return close_price > open_price
    elif direction == "short":
        return close_price < open_price
    else:  # neutral
        return True


def calculate_brier_score(
    predicted_probability: float,
    actual_outcome: float,
) -> float:
    """计算 Brier Score。

    Brier Score = (p - o)^2

    其中 p 是预测概率，o 是实际结果（1 表示正确，0 表示错误）。

    Args:
        predicted_probability: 预测胜率 (0-1)
        actual_outcome: 实际结果 (1.0 = 正确, 0.0 = 错误)

    Returns:
        Brier Score (0 = 完美, 1 = 最差)
    """
    return (predicted_probability - actual_outcome) ** 2


def calculate_brier_score_batch(
    predictions: list[tuple[float, float]],
) -> float:
    """批量计算 Brier Score。

    Args:
        predictions: [(probability, outcome), ...] 列表

    Returns:
        平均 Brier Score
    """
    if not predictions:
        return 0.0
    scores = [
        calculate_brier_score(p, o) for p, o in predictions
    ]
    return sum(scores) / len(scores)


def calculate_mfe_mae(
    direction: str,
    entry_price: float,
    candles: list[Candle],
) -> tuple[float, float]:
    """计算 MFE（最大有利偏移）和 MAE（最大不利偏移）。

    MFE: 入场后最大盈利（百分比）
    MAE: 入场后最大亏损（百分比）

    对于 long:
    - MFE = (high - entry) / entry * 100
    - MAE = (low - entry) / entry * 100（负值）

    对于 short:
    - MFE = (entry - low) / entry * 100
    - MAE = (entry - high) / entry * 100（负值）

    Args:
        direction: 方向 (long/short)
        entry_price: 入场价格
        candles: 窗口内的 K 线列表

    Returns:
        (mfe_pct, mae_pct) 元组
    """
    if not candles or entry_price <= 0:
        return 0.0, 0.0

    if direction == "long":
        max_high = max(c.high for c in candles)
        min_low = min(c.low for c in candles)
        mfe = (max_high - entry_price) / entry_price * 100
        mae = (min_low - entry_price) / entry_price * 100
    elif direction == "short":
        min_low = min(c.low for c in candles)
        max_high = max(c.high for c in candles)
        mfe = (entry_price - min_low) / entry_price * 100
        mae = (entry_price - max_high) / entry_price * 100
    else:
        # neutral 不计算 MFE/MAE
        return 0.0, 0.0

    return mfe, mae


def calculate_pnl(
    direction: str,
    entry_price: float,
    stop_price: float | None,
    target_price: float | None,
    candles: list[Candle],
) -> tuple[float, str]:
    """模拟盈亏计算。

    按入场/止损/止盈模拟：
    1. 检查是否先触达止损（亏损）
    2. 检查是否先触达止盈（盈利）
    3. 都未触达则使用窗口结束时的价格

    Args:
        direction: 方向 (long/short)
        entry_price: 入场价格
        stop_price: 止损价
        target_price: 止盈目标价
        candles: 窗口内 K 线列表

    Returns:
        (pnl_pct, exit_reason) 元组
    """
    if not candles or entry_price <= 0:
        return 0.0, "no_data"

    for candle in candles:
        if direction == "long":
            # 检查止损（low <= stop）
            if stop_price and candle.low <= stop_price:
                pnl = (stop_price - entry_price) / entry_price * 100
                return pnl, "stop_hit"
            # 检查止盈（high >= target）
            if target_price and candle.high >= target_price:
                pnl = (target_price - entry_price) / entry_price * 100
                return pnl, "target_hit"

        elif direction == "short":
            # 检查止损（high >= stop）
            if stop_price and candle.high >= stop_price:
                pnl = (entry_price - stop_price) / entry_price * 100
                return pnl, "stop_hit"
            # 检查止盈（low <= target）
            if target_price and candle.low <= target_price:
                pnl = (entry_price - target_price) / entry_price * 100
                return pnl, "target_hit"

    # 未触达止损/止盈，使用最后收盘价
    last_close = candles[-1].close
    if direction == "long":
        pnl = (last_close - entry_price) / entry_price * 100
    elif direction == "short":
        pnl = (entry_price - last_close) / entry_price * 100
    else:
        pnl = 0.0

    return pnl, "window_close"


def calculate_no_trade_baseline(
    open_price: float,
    close_price: float,
) -> float:
    """计算 No-Trade Baseline（不交易基准收益）。

    基准 = 持有现金的收益率 = 0%（不交易就不赚不亏）

    但如果以另一个维度衡量（如 buy and hold）：
    baseline = (close - open) / open * 100

    这里使用 buy and hold 作为基准（长期持有策略）。

    Args:
        open_price: 窗口开始价格
        close_price: 窗口结束价格

    Returns:
        基准收益百分比
    """
    if open_price <= 0:
        return 0.0
    return (close_price - open_price) / open_price * 100


def calculate_r_multiple(
    pnl_pct: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float | None,
) -> float | None:
    """计算 R 倍数（盈亏比）。

    R = 实际盈亏 / 单笔风险

    单笔风险 = |entry - stop| / entry * 100

    Args:
        pnl_pct: 盈亏百分比
        risk_pct: 风险占比（从分析中获取）
        entry_price: 入场价
        stop_price: 止损价

    Returns:
        R 倍数，或 None（无法计算）
    """
    if not stop_price or entry_price <= 0:
        return None

    risk_amount_pct = abs(entry_price - stop_price) / entry_price * 100
    if risk_amount_pct == 0:
        return None

    return pnl_pct / risk_amount_pct


# ===========================================================================
# 完整 Outcome 计算
# ===========================================================================

def compute_outcome(
    analysis_id: str,
    symbol: str,
    direction: str,
    horizon: str,
    created_at: datetime,
    predicted_probability: float,
    entry_price: float,
    stop_price: float | None,
    target_price: float | None,
    candles: list[Candle],
) -> OutcomeResult:
    """计算完整的 outcome。

    Args:
        analysis_id: 分析 ID
        symbol: 交易标的
        direction: 方向 (long/short/neutral)
        horizon: 分析周期
        created_at: 分析创建时间
        predicted_probability: 预测胜率
        entry_price: 入场价
        stop_price: 止损价
        target_price: 止盈目标价
        candles: 窗口内 K 线列表

    Returns:
        OutcomeResult: 完整的 outcome 结果
    """
    window_start, window_end = compute_maturity_window(created_at, horizon)

    result = OutcomeResult(
        analysis_id=analysis_id,
        symbol=symbol,
        direction=direction,
        window=horizon,
        window_start=window_start,
        window_end=window_end,
        predicted_probability=predicted_probability,
        scoring_status="pending",
    )

    if not candles:
        result.scoring_status = "unscoreable"
        result.unscoreable_reason = "no_candle_data"
        return result

    # 窗口价格
    result.open_price = candles[0].open
    result.high_price = max(c.high for c in candles)
    result.low_price = min(c.low for c in candles)
    result.close_price = candles[-1].close

    # 方向命中
    result.direction_hit = calculate_direction_hit(
        direction, result.open_price, result.close_price
    )

    # Brier Score
    actual_outcome = 1.0 if result.direction_hit else 0.0
    result.brier_score = calculate_brier_score(
        predicted_probability, actual_outcome
    )

    # MFE / MAE
    result.mfe, result.mae = calculate_mfe_mae(
        direction, entry_price, candles
    )

    # PnL
    pnl, exit_reason = calculate_pnl(
        direction, entry_price, stop_price, target_price, candles
    )
    result.pnl_pct = pnl

    # 目标/失效触达
    if target_price:
        if direction == "long":
            result.target_hit = result.high_price >= target_price
        elif direction == "short":
            result.target_hit = result.low_price <= target_price

    if stop_price:
        if direction == "long":
            result.invalidation_hit = result.low_price <= stop_price
        elif direction == "short":
            result.invalidation_hit = result.high_price >= stop_price

    # R 倍数
    result.r_multiple = calculate_r_multiple(
        pnl, 0, entry_price, stop_price
    )

    # No-Trade Baseline
    result.no_trade_baseline_pnl = calculate_no_trade_baseline(
        result.open_price, result.close_price
    )
    result.alpha = pnl - (result.no_trade_baseline_pnl if result.no_trade_baseline_pnl else 0)

    result.scoring_status = "scored"
    return result


# ===========================================================================
# 批量统计
# ===========================================================================

@dataclass
class OutcomeStats:
    """批量 outcome 统计。"""
    total: int = 0
    scored: int = 0
    unscoreable: int = 0
    direction_hits: int = 0
    target_hits: int = 0
    invalidation_hits: int = 0

    # 聚合指标
    hit_rate: float = 0.0
    avg_brier_score: float = 0.0
    avg_pnl: float = 0.0
    avg_mfe: float = 0.0
    avg_mae: float = 0.0
    avg_r_multiple: float = 0.0
    no_trade_baseline_avg: float = 0.0
    alpha_avg: float = 0.0

    # 分级门禁
    gate_stage: str = "pipeline_proof"  # pipeline_proof / beta / ga


def compute_stats(outcomes: list[OutcomeResult]) -> OutcomeStats:
    """计算批量统计。

    Args:
        outcomes: outcome 结果列表

    Returns:
        OutcomeStats: 聚合统计
    """
    stats = OutcomeStats(total=len(outcomes))

    scored = [o for o in outcomes if o.scoring_status == "scored"]
    stats.scored = len(scored)
    stats.unscoreable = len(outcomes) - len(scored)

    if not scored:
        return stats

    # 方向命中率
    hits = sum(1 for o in scored if o.direction_hit)
    stats.direction_hits = hits
    stats.hit_rate = hits / len(scored) * 100

    # 目标/失效触达
    target_hits = sum(1 for o in scored if o.target_hit)
    invalidation_hits = sum(1 for o in scored if o.invalidation_hit)
    stats.target_hits = target_hits
    stats.invalidation_hits = invalidation_hits

    # 平均指标
    brier_scores = [o.brier_score for o in scored if o.brier_score is not None]
    pnls = [o.pnl_pct for o in scored if o.pnl_pct is not None]
    mfes = [o.mfe for o in scored if o.mfe is not None]
    maes = [o.mae for o in scored if o.mae is not None]
    r_multiples = [o.r_multiple for o in scored if o.r_multiple is not None]
    baselines = [
        o.no_trade_baseline_pnl for o in scored if o.no_trade_baseline_pnl is not None
    ]
    alphas = [o.alpha for o in scored if o.alpha is not None]

    if brier_scores:
        stats.avg_brier_score = sum(brier_scores) / len(brier_scores)
    if pnls:
        stats.avg_pnl = sum(pnls) / len(pnls)
    if mfes:
        stats.avg_mfe = sum(mfes) / len(mfes)
    if maes:
        stats.avg_mae = sum(maes) / len(maes)
    if r_multiples:
        stats.avg_r_multiple = sum(r_multiples) / len(r_multiples)
    if baselines:
        stats.no_trade_baseline_avg = sum(baselines) / len(baselines)
    if alphas:
        stats.alpha_avg = sum(alphas) / len(alphas)

    # 分级门禁
    if stats.total >= 200:
        stats.gate_stage = "ga"
    elif stats.total >= 50:
        stats.gate_stage = "beta"
    else:
        stats.gate_stage = "pipeline_proof"

    return stats


def check_gate(stats: OutcomeStats) -> dict[str, Any]:
    """检查分级门禁是否通过。

    分级门禁：
    | 阶段     | 样本数 | 门禁内容                              |
    |----------|--------|---------------------------------------|
    | 管道证明 | 1      | 证明 outcome 采集管道可用              |
    | Beta     | 50+    | Hit Rate >= 55%, 无重大风控失误        |
    | GA       | 200+   | Hit Rate >= 60%, Brier < 0.25, 风控 100%|
    """
    if stats.gate_stage == "pipeline_proof":
        return {
            "stage": "pipeline_proof",
            "passed": stats.scored >= 1,
            "requirements": "证明 outcome 采集管道可用",
            "details": f"已采集 {stats.scored} 条 scored outcome",
        }
    elif stats.gate_stage == "beta":
        hit_rate_ok = stats.hit_rate >= 55.0
        return {
            "stage": "beta",
            "passed": hit_rate_ok,
            "requirements": "Hit Rate >= 55%, 无重大风控失误",
            "details": f"Hit Rate: {stats.hit_rate:.1f}%",
        }
    else:  # ga
        hit_rate_ok = stats.hit_rate >= 60.0
        brier_ok = stats.avg_brier_score < 0.25
        return {
            "stage": "ga",
            "passed": hit_rate_ok and brier_ok,
            "requirements": "Hit Rate >= 60%, Brier < 0.25, 风控 100%",
            "details": (
                f"Hit Rate: {stats.hit_rate:.1f}%, "
                f"Brier: {stats.avg_brier_score:.4f}"
            ),
        }


# ===========================================================================
# 历史 K 线获取（占位接口）
# ===========================================================================

async def fetch_historical_candles(
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str = "1H",
) -> list[Candle]:
    """获取历史 K 线数据。

    从 OKX 获取指定时间范围内的 K 线数据。
    Phase 5 占位实现：返回空列表，实际使用时需接入 OKX API。

    Args:
        symbol: 交易标的（如 BTC-USDT-SWAP）
        start: 开始时间
        end: 结束时间
        interval: K 线间隔（如 1H, 4H, 1D）

    Returns:
        Candle 列表
    """
    # TODO: 接入 OKX /api/v5/market/candles 接口
    # URL: GET /api/v5/market/candles?instId={symbol}&bar={interval}&after={start}&before={end}
    return []
