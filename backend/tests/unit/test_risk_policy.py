"""风控规则单元测试 - 14 条确定性规则的完整测试。

测试范围（设计文档 17.1 节 - 领域单元测试）：
- 每条规则的通过和阻断场景
- 规则 1-13 阻断场景
- 规则 14 警告场景（不阻断）
- 多规则同时命中场景
- 全部通过场景

设计原则：
- 每个测试只修改一个变量，确保测试隔离性
- 使用 _make_analysis 工厂函数创建有效 baseline，通过 overrides 触发特定规则
- now 参数注入固定时间，确保数据新鲜度测试确定性
"""

from datetime import datetime, timedelta, timezone

import pytest

from crypto_alert_v2.domain.models import MarketAnalysis, RiskVerdict
from crypto_alert_v2.domain.risk_policy import (
    DEFAULT_RISK_CONFIG,
    check_plan,
)


# ===========================================================================
# 测试工具
# ===========================================================================

# 固定时间基准，用于数据新鲜度测试
NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def _make_analysis(**overrides) -> MarketAnalysis:
    """创建一个通过所有 14 条规则的有效 MarketAnalysis（open_long 动作）。

    默认值经过精心设计，确保所有规则都通过：
    - manual_execution_required=True（规则 1）
    - instrument 在白名单（规则 2）
    - expires_in_seconds=90 > 0（规则 3）
    - 开仓动作有 stop/entry/invalidation（规则 4-6）
    - 无缺失核心数据（规则 7）
    - risk_pct=0.10 <= 0.25（规则 8）
    - max_leverage=2 <= 2（规则 9）
    - probability=0.6，无 unavailable_data（规则 10）
    - 需配合 _make_fresh_snapshot 使用（规则 11）
    - 默认 config auto_order_enabled=False（规则 12）
    - 默认 config app_mode=development（规则 13）
    - unavailable_data 为空（规则 14 无警告）
    """
    defaults = {
        "regime": "risk_on",
        "factor_scores": {
            "btc_structure": 1,
            "macro_bridge": 0,
            "derivatives": 1,
            "flows": 0,
            "event_calendar": 0,
            "surprise_factor": 0,
            "cross_asset": 1,
            "regime_shift": 0,
            "positioning": 0,
            "volatility": 1,
            "fundamental": 0,
        },
        "total_score": 5,
        "main_action": "open_long",
        "instrument": "BTC-USDT-SWAP",
        "horizon": "4h",
        "reference_price": 65000.0,
        "entry_trigger": 65100.0,
        "stop_price": 64500.0,
        "target_1": 66000.0,
        "target_2": 67000.0,
        "probability": 0.6,
        "position_size_class": "standard",
        "max_leverage": 2,
        "risk_pct": 0.10,
        "root_cause_chain": ["BTC 突破阻力位", "成交量确认上行"],
        "why_not_opposite": "下行趋势线已破，做空逆势",
        "invalidation": "跌破 64500 则计划失效",
        "unavailable_data": [],
        "manual_execution_required": True,
        "expires_in_seconds": 90,
    }
    defaults.update(overrides)
    return MarketAnalysis(**defaults)


def _make_fresh_snapshot(**overrides) -> dict:
    """创建一个新鲜的 market_snapshot（data_fetched_at 在 90s 内）。

    默认不包含 unavailable_fields，确保规则 7 和 14 不触发。
    """
    defaults = {
        "data_fetched_at": (NOW - timedelta(seconds=10)).isoformat(),
        "unavailable_fields": [],
    }
    defaults.update(overrides)
    return defaults


def _check(analysis: MarketAnalysis, config: dict | None = None, snapshot: dict | None = None) -> RiskVerdict:
    """调用 check_plan，使用固定 NOW 时间。"""
    return check_plan(analysis, config=config, market_snapshot=snapshot, now=NOW)


# ===========================================================================
# 全部通过场景
# ===========================================================================


class TestAllRulesPass:
    """测试所有规则同时通过的场景。"""

    def test_all_pass_open_long(self):
        """open_long 动作所有 14 条规则通过。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot()
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is True
        assert verdict.blocked_reasons == []
        assert verdict.warnings == []

    def test_all_pass_no_trade(self):
        """no_trade 动作所有规则通过（不需要开仓相关数据）。"""
        analysis = _make_analysis(
            main_action="no_trade",
            entry_trigger=None,
            stop_price=None,
            target_1=None,
            target_2=None,
        )
        # no_trade 不需要 data_fetched_at（规则 11 只检查开仓动作）
        verdict = _check(analysis, snapshot={})

        assert verdict.allowed is True
        assert verdict.blocked_reasons == []

    def test_all_pass_hold_long(self):
        """hold_long 动作所有规则通过。"""
        analysis = _make_analysis(
            main_action="hold_long",
            entry_trigger=None,
            stop_price=None,
        )
        verdict = _check(analysis, snapshot={})

        assert verdict.allowed is True
        assert verdict.blocked_reasons == []


# ===========================================================================
# 规则 1：必须人工执行
# ===========================================================================


class TestRule1ManualExecution:
    """规则 1：manual_execution_required 必须为 True。"""

    def test_block_when_false(self):
        """manual_execution_required=False 时阻断。"""
        analysis = _make_analysis(manual_execution_required=False)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("manual_execution_required" in r for r in verdict.blocked_reasons)

    def test_pass_when_true(self):
        """manual_execution_required=True 时通过。"""
        analysis = _make_analysis(manual_execution_required=True)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 2：交易品种白名单
# ===========================================================================


class TestRule2AllowedSymbol:
    """规则 2：instrument 必须在 allowed_symbols 白名单中。"""

    def test_block_disallowed_symbol(self):
        """不在白名单的 symbol 阻断。"""
        analysis = _make_analysis(instrument="DOGE-USDT-SWAP")
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("DOGE-USDT-SWAP" in r for r in verdict.blocked_reasons)

    def test_pass_allowed_symbol(self):
        """在白名单的 symbol 通过。"""
        analysis = _make_analysis(instrument="ETH-USDT-SWAP")
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_pass_with_custom_allowed_symbols(self):
        """自定义 allowed_symbols 配置时，新 symbol 通过。"""
        analysis = _make_analysis(instrument="DOGE-USDT-SWAP")
        config = {"allowed_symbols": ["DOGE-USDT-SWAP"]}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 3：计划未过期
# ===========================================================================


class TestRule3PlanNotExpired:
    """规则 3：expires_in_seconds 必须为正值。"""

    def test_block_when_expired(self):
        """expires_in_seconds <= 0 时阻断。"""
        analysis = _make_analysis(expires_in_seconds=0)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("过期" in r for r in verdict.blocked_reasons)

    def test_block_when_negative(self):
        """expires_in_seconds < 0 时阻断。"""
        analysis = _make_analysis(expires_in_seconds=-1)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False

    def test_pass_when_valid(self):
        """expires_in_seconds > 0 时通过。"""
        analysis = _make_analysis(expires_in_seconds=90)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 4：开仓必须有止损价
# ===========================================================================


class TestRule4OpeningHasStop:
    """规则 4：开仓类动作必须提供 stop_price。"""

    def test_block_opening_missing_stop(self):
        """open_long 缺 stop_price 时阻断。"""
        analysis = _make_analysis(stop_price=None)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("止损" in r for r in verdict.blocked_reasons)

    def test_pass_opening_with_stop(self):
        """open_long 有 stop_price 时通过。"""
        analysis = _make_analysis(stop_price=64500.0)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_pass_non_opening_without_stop(self):
        """no_trade 不需要 stop_price。"""
        analysis = _make_analysis(
            main_action="no_trade",
            stop_price=None,
            entry_trigger=None,
        )
        verdict = _check(analysis, snapshot={})

        assert verdict.allowed is True

    def test_block_short_missing_stop(self):
        """open_short 缺 stop_price 时阻断。"""
        analysis = _make_analysis(
            main_action="open_short",
            stop_price=None,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False

    def test_block_trigger_missing_stop(self):
        """trigger_long 缺 stop_price 时阻断。"""
        analysis = _make_analysis(
            main_action="trigger_long",
            stop_price=None,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False

    def test_block_flip_missing_stop(self):
        """flip_long_to_short 缺 stop_price 时阻断。"""
        analysis = _make_analysis(
            main_action="flip_long_to_short",
            stop_price=None,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False


# ===========================================================================
# 规则 5：开仓必须有入场触发价
# ===========================================================================


class TestRule5OpeningHasEntry:
    """规则 5：开仓类动作必须提供 entry_trigger。"""

    def test_block_opening_missing_entry(self):
        """open_long 缺 entry_trigger 时阻断。"""
        analysis = _make_analysis(entry_trigger=None)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("触发价" in r for r in verdict.blocked_reasons)

    def test_pass_opening_with_entry(self):
        """open_long 有 entry_trigger 时通过。"""
        analysis = _make_analysis(entry_trigger=65100.0)
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_pass_non_opening_without_entry(self):
        """hold_long 不需要 entry_trigger。"""
        analysis = _make_analysis(
            main_action="hold_long",
            entry_trigger=None,
            stop_price=None,
        )
        verdict = _check(analysis, snapshot={})

        assert verdict.allowed is True


# ===========================================================================
# 规则 6：开仓必须有失效条件
# ===========================================================================


class TestRule6OpeningHasInvalidation:
    """规则 6：开仓类动作必须提供 invalidation 描述。"""

    def test_block_opening_missing_invalidation(self):
        """open_long invalidation 为空字符串时阻断。"""
        analysis = _make_analysis(invalidation="")
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("失效条件" in r for r in verdict.blocked_reasons)

    def test_block_opening_whitespace_invalidation(self):
        """open_long invalidation 只有空白字符时阻断。"""
        analysis = _make_analysis(invalidation="   ")
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False

    def test_pass_opening_with_invalidation(self):
        """open_long 有有效 invalidation 时通过。"""
        analysis = _make_analysis(invalidation="跌破 64500 则计划失效")
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 7：开仓必须有核心执行数据
# ===========================================================================


class TestRule7CoreExecutionData:
    """规则 7：开仓类动作不能缺失核心执行行情数据。"""

    def test_block_missing_ticker(self):
        """缺失 ticker 时阻断。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(unavailable_fields=["ticker"])
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is False
        assert any("ticker" in r for r in verdict.blocked_reasons)

    def test_block_missing_multiple_core_fields(self):
        """缺失多个核心字段时阻断。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(
            unavailable_fields=["mark_price", "order_book"]
        )
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is False
        assert any("mark_price" in r and "order_book" in r for r in verdict.blocked_reasons)

    def test_block_missing_via_analysis_unavailable_data(self):
        """通过 analysis.unavailable_data 标记缺失时也阻断。"""
        analysis = _make_analysis(unavailable_data=["candles"])
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("candles" in r for r in verdict.blocked_reasons)

    def test_pass_all_core_data_present(self):
        """所有核心数据齐全时通过。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(unavailable_fields=[])
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is True

    def test_pass_non_opening_with_missing_data(self):
        """no_trade 动作不检查核心执行数据。"""
        analysis = _make_analysis(
            main_action="no_trade",
            entry_trigger=None,
            stop_price=None,
        )
        snapshot = _make_fresh_snapshot(unavailable_fields=["ticker", "candles"])
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is True


# ===========================================================================
# 规则 8：单笔风险占比不超限
# ===========================================================================


class TestRule8RiskPctMax:
    """规则 8：risk_pct 不得超过配置的 max_risk_pct。"""

    def test_block_risk_pct_exceeds_config(self):
        """risk_pct 超过配置的 max_risk_pct 时阻断。"""
        analysis = _make_analysis(risk_pct=0.20)
        config = {"max_risk_pct": 0.15}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("risk_pct" in r for r in verdict.blocked_reasons)

    def test_pass_risk_pct_within_config(self):
        """risk_pct 在配置限制内时通过。"""
        analysis = _make_analysis(risk_pct=0.10)
        config = {"max_risk_pct": 0.25}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_pass_risk_pct_equal_to_config(self):
        """risk_pct 等于 max_risk_pct 时通过（边界值）。"""
        analysis = _make_analysis(risk_pct=0.20)
        config = {"max_risk_pct": 0.20}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 9：最大杠杆不超限
# ===========================================================================


class TestRule9LeverageMax:
    """规则 9：max_leverage 不得超过配置的 max_leverage。"""

    def test_block_leverage_exceeds_config(self):
        """max_leverage 超过配置限制时阻断。"""
        analysis = _make_analysis(max_leverage=2)
        config = {"max_leverage": 1}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("leverage" in r.lower() for r in verdict.blocked_reasons)

    def test_pass_leverage_within_config(self):
        """max_leverage 在配置限制内时通过。"""
        analysis = _make_analysis(max_leverage=1)
        config = {"max_leverage": 2}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_pass_leverage_equal_to_config(self):
        """max_leverage 等于配置限制时通过（边界值）。"""
        analysis = _make_analysis(max_leverage=2)
        config = {"max_leverage": 2}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 10：置信度不超上限
# ===========================================================================


class TestRule10ConfidenceCap:
    """规则 10：probability 不得超过 unavailable_data 导致的置信度上限。"""

    def test_block_funding_rate_missing_high_prob(self):
        """缺 funding_rate 时 cap=0.70，probability=0.75 超限阻断。"""
        analysis = _make_analysis(
            unavailable_data=["funding_rate"],
            probability=0.75,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("置信度上限" in r for r in verdict.blocked_reasons)

    def test_pass_funding_rate_missing_low_prob(self):
        """缺 funding_rate 时 cap=0.70，probability=0.65 在限内通过。"""
        analysis = _make_analysis(
            unavailable_data=["funding_rate"],
            probability=0.65,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_block_liquidation_map_missing_high_prob(self):
        """缺 liquidation_map 时 cap=0.58，probability=0.60 超限阻断。"""
        analysis = _make_analysis(
            unavailable_data=["liquidation_map"],
            probability=0.60,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False

    def test_block_btc_anchor_missing_for_eth(self):
        """分析 ETH 时缺 btc_anchor，cap=0.60，probability=0.65 超限阻断。"""
        analysis = _make_analysis(
            instrument="ETH-USDT-SWAP",
            unavailable_data=["btc_anchor"],
            probability=0.65,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("BTC 方向锚" in r for r in verdict.blocked_reasons)

    def test_pass_btc_anchor_not_required_for_btc(self):
        """分析 BTC 时 btc_anchor 缺失不触发降级。"""
        analysis = _make_analysis(
            instrument="BTC-USDT-SWAP",
            unavailable_data=["btc_anchor"],
            probability=0.80,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_block_multiple_missing_takes_min_cap(self):
        """多个数据缺失时取最低 cap。"""
        # funding_rate -> 0.70, liquidation_map -> 0.58
        # min cap = 0.58, probability=0.60 > 0.58 阻断
        analysis = _make_analysis(
            unavailable_data=["funding_rate", "liquidation_map"],
            probability=0.60,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False

    def test_pass_no_unavailable_data_no_cap(self):
        """无缺失数据时不触发置信度上限。"""
        analysis = _make_analysis(
            unavailable_data=[],
            probability=0.90,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 11：数据新鲜度检查
# ===========================================================================


class TestRule11DataFreshness:
    """规则 11：行情数据超过 90 秒视为陈旧，阻断开仓。"""

    def test_block_stale_data(self):
        """数据年龄超过 90s 时阻断开仓。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=120)).isoformat()
        )
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is False
        assert any("陈旧" in r for r in verdict.blocked_reasons)

    def test_pass_fresh_data(self):
        """数据年龄在 90s 内时通过。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=30)).isoformat()
        )
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is True

    def test_block_no_data_fetched_at_for_opening(self):
        """开仓动作缺 data_fetched_at 时阻断。"""
        analysis = _make_analysis()
        snapshot = {"unavailable_fields": []}  # 无 data_fetched_at
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is False
        assert any("data_fetched_at" in r for r in verdict.blocked_reasons)

    def test_pass_no_data_fetched_at_for_non_opening(self):
        """非开仓动作不需要 data_fetched_at。"""
        analysis = _make_analysis(
            main_action="no_trade",
            entry_trigger=None,
            stop_price=None,
        )
        snapshot = {}  # 无 data_fetched_at
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is True

    def test_block_unparseable_timestamp(self):
        """data_fetched_at 格式无法解析时阻断。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(data_fetched_at="not-a-timestamp")
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is False

    def test_pass_datetime_object_timestamp(self):
        """data_fetched_at 为 datetime 对象时正常解析。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(
            data_fetched_at=NOW - timedelta(seconds=10)
        )
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is True

    def test_block_at_exact_threshold(self):
        """数据年龄刚好等于 90s 时不阻断（> 90s 才阻断）。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=90)).isoformat()
        )
        verdict = _check(analysis, snapshot=snapshot)

        # age_seconds = 90.0, threshold = 90, 90 > 90 is False -> pass
        assert verdict.allowed is True

    def test_block_custom_stale_threshold(self):
        """自定义 stale_market_data_seconds 配置生效。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=30)).isoformat()
        )
        config = {"stale_market_data_seconds": 20}
        verdict = _check(analysis, config=config, snapshot=snapshot)

        assert verdict.allowed is False


# ===========================================================================
# 规则 12：禁止自动下单
# ===========================================================================


class TestRule12AutoOrderDisabled:
    """规则 12：config.auto_order_enabled 必须为 False。"""

    def test_block_auto_order_enabled(self):
        """auto_order_enabled=True 时阻断。"""
        analysis = _make_analysis()
        config = {"auto_order_enabled": True}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("自动下单" in r for r in verdict.blocked_reasons)

    def test_pass_auto_order_disabled(self):
        """auto_order_enabled=False 时通过。"""
        analysis = _make_analysis()
        config = {"auto_order_enabled": False}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 13：应用模式检查
# ===========================================================================


class TestRule13AppMode:
    """规则 13：app_mode 为 "off" 时禁止生成可执行操作。"""

    def test_block_app_mode_off(self):
        """app_mode=off 时阻断。"""
        analysis = _make_analysis()
        config = {"app_mode": "off"}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert any("OFF" in r or "off" in r.lower() for r in verdict.blocked_reasons)

    def test_pass_app_mode_development(self):
        """app_mode=development 时通过。"""
        analysis = _make_analysis()
        config = {"app_mode": "development"}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True

    def test_pass_app_mode_production(self):
        """app_mode=production 时通过。"""
        analysis = _make_analysis()
        config = {"app_mode": "production"}
        verdict = _check(analysis, config=config, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True


# ===========================================================================
# 规则 14：数据缺失警告（warn only，不阻断）
# ===========================================================================


class TestRule14MarketDataUnavailable:
    """规则 14：数据缺失只警告不阻断。"""

    def test_warn_only_does_not_block(self):
        """有不可用数据时产生警告但不阻断。"""
        analysis = _make_analysis(
            unavailable_data=["some_non_core_field"],
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        # 不阻断（some_non_core_field 不是核心执行数据，不触发规则 7）
        assert verdict.allowed is True
        assert len(verdict.warnings) > 0
        assert any("不可用行情数据" in w for w in verdict.warnings)

    def test_warn_includes_snapshot_unavailable_fields(self):
        """警告包含 snapshot.unavailable_fields 中的字段。"""
        analysis = _make_analysis()
        snapshot = _make_fresh_snapshot(
            unavailable_fields=["non_core_indicator"]
        )
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.allowed is True
        assert any("non_core_indicator" in w for w in verdict.warnings)

    def test_no_warning_when_all_data_available(self):
        """所有数据齐全时无警告。"""
        analysis = _make_analysis(unavailable_data=[])
        snapshot = _make_fresh_snapshot(unavailable_fields=[])
        verdict = _check(analysis, snapshot=snapshot)

        assert verdict.warnings == []


# ===========================================================================
# 多规则组合场景
# ===========================================================================


class TestMultipleRules:
    """测试多条规则同时命中的场景。"""

    def test_multiple_blocking_rules(self):
        """多条 blocking 规则同时命中，全部收集到 blocked_reasons。"""
        analysis = _make_analysis(
            manual_execution_required=False,  # 规则 1 阻断
            instrument="DOGE-USDT-SWAP",      # 规则 2 阻断
            expires_in_seconds=0,             # 规则 3 阻断
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert len(verdict.blocked_reasons) >= 3

    def test_blocking_and_warning_coexist(self):
        """blocking 和 warn 规则可以同时命中。"""
        analysis = _make_analysis(
            manual_execution_required=False,      # 规则 1 阻断
            unavailable_data=["non_core_field"],  # 规则 14 警告
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is False
        assert len(verdict.blocked_reasons) >= 1
        assert len(verdict.warnings) >= 1

    def test_warnings_do_not_affect_allowed(self):
        """只有警告没有阻断时 allowed=True。"""
        analysis = _make_analysis(
            unavailable_data=["non_core_field"],
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True
        assert len(verdict.warnings) > 0
        assert len(verdict.blocked_reasons) == 0

    def test_all_blocking_rules_simultaneously(self):
        """所有 13 条 blocking 规则同时命中。"""
        analysis = _make_analysis(
            manual_execution_required=False,          # 规则 1
            instrument="DOGE-USDT-SWAP",              # 规则 2
            expires_in_seconds=-1,                    # 规则 3
            stop_price=None,                          # 规则 4
            entry_trigger=None,                       # 规则 5
            invalidation="",                          # 规则 6
            unavailable_data=["ticker", "mark_price", "index_price", "order_book", "candles"],  # 规则 7 + 10
            risk_pct=0.25,                            # 规则 8 (config max_risk_pct=0.10)
            max_leverage=2,                           # 规则 9 (config max_leverage=1)
            probability=0.90,                         # 规则 10 (cap from missing data)
        )
        config = {
            "max_risk_pct": 0.10,
            "max_leverage": 1,
            "auto_order_enabled": True,               # 规则 12
            "app_mode": "off",                        # 规则 13
        }
        # 规则 11: stale data
        snapshot = _make_fresh_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=200)).isoformat(),
            unavailable_fields=["ticker", "mark_price", "index_price", "order_book", "candles"],
        )
        verdict = _check(analysis, config=config, snapshot=snapshot)

        assert verdict.allowed is False
        # 应有多条 blocked_reasons（至少 10 条不同规则命中）
        assert len(verdict.blocked_reasons) >= 10


# ===========================================================================
# RiskVerdict 结构验证
# ===========================================================================


class TestRiskVerdictStructure:
    """验证 RiskVerdict 的结构完整性。"""

    def test_verdict_has_all_fields(self):
        """RiskVerdict 包含所有定义的字段。"""
        analysis = _make_analysis()
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert hasattr(verdict, "allowed")
        assert hasattr(verdict, "blocked_reasons")
        assert hasattr(verdict, "warnings")
        assert hasattr(verdict, "confidence_cap")

    def test_confidence_cap_always_1_from_risk_policy(self):
        """风控规则不修改 confidence_cap，始终为 1.0（由证据门禁设置）。"""
        analysis = _make_analysis(
            unavailable_data=["funding_rate"],
            probability=0.60,
        )
        verdict = _check(analysis, snapshot=_make_fresh_snapshot())

        assert verdict.confidence_cap == 1.0

    def test_default_config_used_when_none(self):
        """config=None 时使用 DEFAULT_RISK_CONFIG。"""
        analysis = _make_analysis()
        verdict = _check(analysis, config=None, snapshot=_make_fresh_snapshot())

        assert verdict.allowed is True
