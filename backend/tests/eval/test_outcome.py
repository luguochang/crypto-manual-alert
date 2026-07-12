"""Outcome 追踪单元测试。

测试范围：
- 成熟窗口计算
- 方向命中率
- Brier Score 计算
- MFE/MAE 计算
- PnL 模拟
- No-Trade Baseline 对比
- 批量统计和门禁检查

来源：V2重构方案评审与补充建议_修订版.md 第 6.6 节。
"""

from datetime import datetime, timedelta, timezone

import pytest

from crypto_alert_v2.eval.outcome import (
    Candle,
    OutcomeResult,
    OutcomeStats,
    MaturityWindow,
    calculate_brier_score,
    calculate_brier_score_batch,
    calculate_direction_hit,
    calculate_mfe_mae,
    calculate_no_trade_baseline,
    calculate_pnl,
    calculate_r_multiple,
    check_gate,
    compute_maturity_window,
    compute_outcome,
    compute_stats,
    is_mature,
)


# ===========================================================================
# 固定测试数据
# ===========================================================================

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def _make_candles(
    start: datetime,
    count: int,
    base_price: float = 65000,
    trend: str = "up",
    volatility: float = 100,
) -> list[Candle]:
    """生成模拟 K 线数据。"""
    candles = []
    for i in range(count):
        ts = start + timedelta(hours=i)
        if trend == "up":
            o = base_price + i * volatility
            c = o + volatility * 0.5
            h = c + volatility * 0.3
            l = o - volatility * 0.2
        elif trend == "down":
            o = base_price - i * volatility
            c = o - volatility * 0.5
            h = o + volatility * 0.2
            l = c - volatility * 0.3
        else:  # ranging
            o = base_price + (i % 3 - 1) * volatility * 0.5
            c = o + volatility * 0.1
            h = o + volatility * 0.5
            l = o - volatility * 0.5
        candles.append(Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=100))
    return candles


# ===========================================================================
# 成熟窗口计算测试
# ===========================================================================

class TestMaturityWindow:
    """测试成熟窗口计算。"""

    def test_4h_window(self):
        """4h 成熟窗口。"""
        start, end = compute_maturity_window(NOW, "4h")
        assert start == NOW
        assert end == NOW + timedelta(hours=4)

    def test_12h_window(self):
        """12h 成熟窗口。"""
        start, end = compute_maturity_window(NOW, "12h")
        assert start == NOW
        assert end == NOW + timedelta(hours=12)

    def test_24h_window(self):
        """24h 成熟窗口。"""
        start, end = compute_maturity_window(NOW, "24h")
        assert start == NOW
        assert end == NOW + timedelta(hours=24)

    def test_invalid_horizon_defaults_4h(self):
        """无效 horizon 默认 4h。"""
        start, end = compute_maturity_window(NOW, "invalid")
        assert end == NOW + timedelta(hours=4)

    def test_is_mature_true(self):
        """已过成熟窗口。"""
        created = NOW - timedelta(hours=5)
        assert is_mature(created, "4h", now=NOW) is True

    def test_is_mature_false(self):
        """未过成熟窗口。"""
        created = NOW - timedelta(hours=2)
        assert is_mature(created, "4h", now=NOW) is False

    def test_is_mature_exact_boundary(self):
        """刚好到成熟窗口边界。"""
        created = NOW - timedelta(hours=4)
        assert is_mature(created, "4h", now=NOW) is True


# ===========================================================================
# 方向命中率测试
# ===========================================================================

class TestDirectionHit:
    """测试方向命中率。"""

    def test_long_correct(self):
        """做多方向正确（价格上涨）。"""
        assert calculate_direction_hit("long", 100, 105) is True

    def test_long_incorrect(self):
        """做多方向错误（价格下跌）。"""
        assert calculate_direction_hit("long", 100, 95) is False

    def test_short_correct(self):
        """做空方向正确（价格下跌）。"""
        assert calculate_direction_hit("short", 100, 95) is True

    def test_short_incorrect(self):
        """做空方向错误（价格上涨）。"""
        assert calculate_direction_hit("short", 100, 105) is False

    def test_neutral_always_correct(self):
        """观望总是正确。"""
        assert calculate_direction_hit("neutral", 100, 105) is True
        assert calculate_direction_hit("neutral", 100, 95) is True
        assert calculate_direction_hit("neutral", 100, 100) is True


# ===========================================================================
# Brier Score 测试
# ===========================================================================

class TestBrierScore:
    """测试 Brier Score 计算。"""

    def test_perfect_prediction(self):
        """完美预测（p=1, o=1）。"""
        score = calculate_brier_score(1.0, 1.0)
        assert score == 0.0

    def test_worst_prediction(self):
        """最差预测（p=1, o=0）。"""
        score = calculate_brier_score(1.0, 0.0)
        assert score == 1.0

    def test_half_prediction_correct(self):
        """50% 预测且正确。"""
        score = calculate_brier_score(0.5, 1.0)
        assert score == pytest.approx(0.25)

    def test_half_prediction_incorrect(self):
        """50% 预测且错误。"""
        score = calculate_brier_score(0.5, 0.0)
        assert score == pytest.approx(0.25)

    def test_65pct_correct(self):
        """65% 预测且正确。"""
        score = calculate_brier_score(0.65, 1.0)
        assert score == pytest.approx(0.1225)

    def test_65pct_incorrect(self):
        """65% 预测且错误。"""
        score = calculate_brier_score(0.65, 0.0)
        assert score == pytest.approx(0.4225)

    def test_batch_average(self):
        """批量平均。"""
        predictions = [(1.0, 1.0), (0.0, 0.0), (0.5, 1.0)]
        avg = calculate_brier_score_batch(predictions)
        # (0 + 0 + 0.25) / 3
        assert avg == pytest.approx(0.0833, abs=0.01)

    def test_batch_empty(self):
        """空批量返回 0。"""
        assert calculate_brier_score_batch([]) == 0.0


# ===========================================================================
# MFE/MAE 测试
# ===========================================================================

class TestMFE_MAE:
    """测试 MFE/MAE 计算。"""

    def test_long_mfe_mae(self):
        """做多 MFE/MAE。"""
        candles = _make_candles(NOW, 4, base_price=65000, trend="up", volatility=100)
        mfe, mae = calculate_mfe_mae("long", 65000, candles)
        assert mfe > 0  # 有利偏移为正
        assert mae <= 0  # 不利偏移为负或零

    def test_short_mfe_mae(self):
        """做空 MFE/MAE。"""
        candles = _make_candles(NOW, 4, base_price=65000, trend="down", volatility=100)
        mfe, mae = calculate_mfe_mae("short", 65000, candles)
        assert mfe > 0  # 有利偏移为正
        assert mae <= 0  # 不利偏移为负或零

    def test_neutral_mfe_mae_zero(self):
        """观望 MFE/MAE 为 0。"""
        candles = _make_candles(NOW, 4, base_price=65000, trend="up")
        mfe, mae = calculate_mfe_mae("neutral", 65000, candles)
        assert mfe == 0.0
        assert mae == 0.0

    def test_empty_candles(self):
        """空 K 线返回 0。"""
        mfe, mae = calculate_mfe_mae("long", 65000, [])
        assert mfe == 0.0
        assert mae == 0.0

    def test_zero_entry_price(self):
        """入场价为 0 返回 0。"""
        candles = _make_candles(NOW, 4, base_price=65000)
        mfe, mae = calculate_mfe_mae("long", 0, candles)
        assert mfe == 0.0
        assert mae == 0.0


# ===========================================================================
# PnL 模拟测试
# ===========================================================================

class TestPnL:
    """测试 PnL 模拟。"""

    def test_long_target_hit(self):
        """做多触达止盈。"""
        candles = [
            Candle(NOW, 65000, 65500, 64800, 65400, 100),
            Candle(NOW + timedelta(hours=1), 65400, 66000, 65300, 65900, 100),
        ]
        pnl, reason = calculate_pnl("long", 65000, 64500, 66000, candles)
        assert reason == "target_hit"
        assert pnl > 0

    def test_long_stop_hit(self):
        """做多触达止损。"""
        candles = [
            Candle(NOW, 65000, 65100, 64400, 64500, 100),
        ]
        pnl, reason = calculate_pnl("long", 65000, 64500, 66000, candles)
        assert reason == "stop_hit"
        assert pnl < 0

    def test_long_window_close(self):
        """做未触达，窗口收盘。"""
        candles = [
            Candle(NOW, 65000, 65200, 64900, 65100, 100),
            Candle(NOW + timedelta(hours=1), 65100, 65300, 65000, 65200, 100),
        ]
        pnl, reason = calculate_pnl("long", 65000, 64500, 66000, candles)
        assert reason == "window_close"
        assert pnl > 0  # 从 65000 涨到 65200

    def test_short_target_hit(self):
        """做空触达止盈。"""
        candles = [
            Candle(NOW, 65000, 65100, 64400, 64500, 100),
        ]
        pnl, reason = calculate_pnl("short", 65000, 65500, 64500, candles)
        assert reason == "target_hit"
        assert pnl > 0

    def test_short_stop_hit(self):
        """做空触达止损。"""
        candles = [
            Candle(NOW, 65000, 65600, 64900, 65500, 100),
        ]
        pnl, reason = calculate_pnl("short", 65000, 65500, 64500, candles)
        assert reason == "stop_hit"
        assert pnl < 0

    def test_no_candles(self):
        """无 K 线数据。"""
        pnl, reason = calculate_pnl("long", 65000, 64500, 66000, [])
        assert pnl == 0.0
        assert reason == "no_data"


# ===========================================================================
# No-Trade Baseline 测试
# ===========================================================================

class TestNoTradeBaseline:
    """测试 No-Trade Baseline。"""

    def test_positive_baseline(self):
        """正基准（价格上涨）。"""
        baseline = calculate_no_trade_baseline(100, 105)
        assert baseline == pytest.approx(5.0)

    def test_negative_baseline(self):
        """负基准（价格下跌）。"""
        baseline = calculate_no_trade_baseline(100, 95)
        assert baseline == pytest.approx(-5.0)

    def test_zero_baseline(self):
        """零基准（价格不变）。"""
        baseline = calculate_no_trade_baseline(100, 100)
        assert baseline == 0.0

    def test_zero_open_price(self):
        """开盘价为 0。"""
        baseline = calculate_no_trade_baseline(0, 100)
        assert baseline == 0.0


# ===========================================================================
# R 倍数测试
# ===========================================================================

class TestRMultiple:
    """测试 R 倍数计算。"""

    def test_positive_r(self):
        """正 R 倍数（盈利）。"""
        # entry=100, stop=95, risk=5%, pnl=10%
        r = calculate_r_multiple(10.0, 0.05, 100, 95)
        assert r is not None
        assert r == pytest.approx(2.0)  # 10% / 5% = 2R

    def test_negative_r(self):
        """负 R 倍数（亏损）。"""
        r = calculate_r_multiple(-5.0, 0.05, 100, 95)
        assert r is not None
        assert r == pytest.approx(-1.0)  # -5% / 5% = -1R

    def test_no_stop_price(self):
        """无止损价返回 None。"""
        r = calculate_r_multiple(10.0, 0.05, 100, None)
        assert r is None

    def test_zero_risk(self):
        """风险为 0 返回 None。"""
        r = calculate_r_multiple(10.0, 0.05, 100, 100)
        assert r is None


# ===========================================================================
# 完整 Outcome 计算测试
# ===========================================================================

class TestComputeOutcome:
    """测试完整 outcome 计算。"""

    def test_long_correct_outcome(self):
        """做多正确的完整 outcome。"""
        candles = _make_candles(NOW, 4, base_price=65000, trend="up", volatility=100)
        result = compute_outcome(
            analysis_id="test-001",
            symbol="BTC-USDT-SWAP",
            direction="long",
            horizon="4h",
            created_at=NOW,
            predicted_probability=0.65,
            entry_price=65000,
            stop_price=64500,
            target_price=66000,
            candles=candles,
        )
        assert result.scoring_status == "scored"
        assert result.direction_hit is True
        assert result.brier_score is not None
        assert result.mfe > 0
        assert result.pnl_pct is not None

    def test_short_correct_outcome(self):
        """做空正确的完整 outcome。"""
        candles = _make_candles(NOW, 4, base_price=65000, trend="down", volatility=100)
        result = compute_outcome(
            analysis_id="test-002",
            symbol="BTC-USDT-SWAP",
            direction="short",
            horizon="4h",
            created_at=NOW,
            predicted_probability=0.55,
            entry_price=65000,
            stop_price=65500,
            target_price=64000,
            candles=candles,
        )
        assert result.scoring_status == "scored"
        assert result.direction_hit is True

    def test_no_candle_data(self):
        """无 K 线数据。"""
        result = compute_outcome(
            analysis_id="test-003",
            symbol="BTC-USDT-SWAP",
            direction="long",
            horizon="4h",
            created_at=NOW,
            predicted_probability=0.6,
            entry_price=65000,
            stop_price=64500,
            target_price=66000,
            candles=[],
        )
        assert result.scoring_status == "unscoreable"
        assert result.unscoreable_reason == "no_candle_data"


# ===========================================================================
# 批量统计和门禁测试
# ===========================================================================

class TestBatchStats:
    """测试批量统计和门禁检查。"""

    def test_empty_stats(self):
        """空统计。"""
        stats = compute_stats([])
        assert stats.total == 0
        assert stats.scored == 0
        assert stats.hit_rate == 0.0

    def test_pipeline_proof_gate(self):
        """管道证明阶段门禁。"""
        stats = OutcomeStats(total=1, scored=1, hit_rate=100.0)
        stats.gate_stage = "pipeline_proof"
        gate = check_gate(stats)
        assert gate["stage"] == "pipeline_proof"
        assert gate["passed"] is True

    def test_beta_gate_pass(self):
        """Beta 阶段通过。"""
        stats = OutcomeStats(total=50, scored=50, hit_rate=60.0)
        stats.gate_stage = "beta"
        gate = check_gate(stats)
        assert gate["passed"] is True

    def test_beta_gate_fail(self):
        """Beta 阶段不通过。"""
        stats = OutcomeStats(total=50, scored=50, hit_rate=45.0)
        stats.gate_stage = "beta"
        gate = check_gate(stats)
        assert gate["passed"] is False

    def test_ga_gate_pass(self):
        """GA 阶段通过。"""
        stats = OutcomeStats(
            total=200, scored=200, hit_rate=65.0, avg_brier_score=0.2
        )
        stats.gate_stage = "ga"
        gate = check_gate(stats)
        assert gate["passed"] is True

    def test_ga_gate_fail_brier(self):
        """GA 阶段 Brier 不达标。"""
        stats = OutcomeStats(
            total=200, scored=200, hit_rate=65.0, avg_brier_score=0.3
        )
        stats.gate_stage = "ga"
        gate = check_gate(stats)
        assert gate["passed"] is False

    def test_stats_with_outcomes(self):
        """带 outcome 的统计。"""
        outcomes = [
            OutcomeResult(
                analysis_id="t1",
                symbol="BTC-USDT-SWAP",
                direction="long",
                window="4h",
                window_start=NOW,
                window_end=NOW + timedelta(hours=4),
                direction_hit=True,
                brier_score=0.1225,
                pnl_pct=5.0,
                mfe=3.0,
                mae=-1.0,
                r_multiple=1.0,
                no_trade_baseline_pnl=2.0,
                alpha=3.0,
                scoring_status="scored",
            ),
            OutcomeResult(
                analysis_id="t2",
                symbol="BTC-USDT-SWAP",
                direction="long",
                window="4h",
                window_start=NOW,
                window_end=NOW + timedelta(hours=4),
                direction_hit=False,
                brier_score=0.4225,
                pnl_pct=-3.0,
                mfe=1.0,
                mae=-2.0,
                r_multiple=-0.6,
                no_trade_baseline_pnl=-1.0,
                alpha=-2.0,
                scoring_status="scored",
            ),
        ]
        stats = compute_stats(outcomes)
        assert stats.total == 2
        assert stats.scored == 2
        assert stats.hit_rate == 50.0  # 1/2
        assert stats.direction_hits == 1
