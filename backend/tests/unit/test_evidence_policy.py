"""证据门禁单元测试 - check_evidence_sufficiency 完整测试。

测试范围（设计文档 14 第 2.5 节 + 17.1 节）：
- 必需证据完整时通过
- 缺核心执行数据时阻断
- 缺可选数据时降级置信度
- 新鲜度检查（行情 > 90s 阻断，衍生品 > 5min 降级）
- 开仓类动作需要宏观事件状态
- BTC 方向锚只在分析 ETH/SOL 时需要
"""

from datetime import datetime, timedelta, timezone

import pytest

from crypto_alert_v2.domain.evidence_policy import (
    OPTIONAL_FIELD_CAPS,
    REQUIRED_MACRO_FIELDS,
    REQUIRED_MARKET_FIELDS,
    STALE_DERIVATIVES_THRESHOLD,
    STALE_MACRO_THRESHOLD,
    STALE_MARKET_THRESHOLD,
    check_evidence_sufficiency,
)
from crypto_alert_v2.domain.models import EvidenceVerdict


# ===========================================================================
# 测试工具
# ===========================================================================

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def _make_complete_snapshot(**overrides) -> dict:
    """创建一个包含所有必需和可选字段的完整市场快照。

    默认所有字段都有值，确保证据门禁通过。
    每个测试通过 overrides 修改特定字段来触发特定场景。
    """
    defaults = {
        # 必需市场数据
        "ticker": {"last": 65000.0, "bid": 64995.0, "ask": 65005.0, "vol_24h": 1234.56},
        "mark_price": 65010.0,
        "index_price": 64990.0,
        "order_book": {"bids": [[64995, 1.5], [64990, 2.0]], "asks": [[65005, 1.2], [65010, 0.8]]},
        "candles": [{"ts": "2026-07-12T12:00:00Z", "o": 64900, "h": 65100, "l": 64850, "c": 65000, "vol": 100}],

        # 可选数据
        "funding_rate": {"value": 0.0001, "fetched_at": (NOW - timedelta(seconds=30)).isoformat()},
        "open_interest": {"value": 1000.5, "fetched_at": (NOW - timedelta(seconds=30)).isoformat()},
        "long_short_ratio": {"ratio": 1.2, "fetched_at": (NOW - timedelta(seconds=30)).isoformat()},
        "cvd_taker_delta": {"delta": -50.5},
        "liquidation_map": {"clusters": []},
        "etf_flows": {"net_flow": 50000000},
        "stablecoin_supply": {"total": 150000000000},
        "btc_anchor": {"direction": "bullish"},

        # 时间戳
        "data_fetched_at": (NOW - timedelta(seconds=10)).isoformat(),

        # 数据质量
        "unavailable_fields": [],
        "source_level": "exchange_native",
    }
    defaults.update(overrides)
    return defaults


def _make_research_bundle(**overrides) -> dict:
    """创建一个包含宏观研究发现的研究包。"""
    defaults = {
        "macro_findings": [
            {
                "title": "Fed 保持利率不变",
                "summary": "美联储 7 月会议维持利率不变，符合市场预期",
                "source_url": "https://example.com/fed",
                "fetched_at": NOW.isoformat(),
                "relevance": "high",
            }
        ],
        "news_findings": [],
        "overall_quality": "high",
    }
    defaults.update(overrides)
    return defaults


def _check(
    snapshot: dict | None = None,
    research: dict | None = None,
    main_action: str = "open_long",
    instrument: str = "BTC-USDT-SWAP",
    now: datetime = NOW,
) -> EvidenceVerdict:
    """调用 check_evidence_sufficiency，使用固定 NOW 时间。"""
    return check_evidence_sufficiency(
        market_snapshot=snapshot,
        research_bundle=research,
        main_action=main_action,
        instrument=instrument,
        now=now,
    )


# ===========================================================================
# 必需证据完整时通过
# ===========================================================================


class TestEvidenceSufficient:
    """测试必需证据齐全时证据门禁通过。"""

    def test_all_evidence_present_open_long(self):
        """所有必需和可选证据齐全时，开仓动作通过。"""
        snapshot = _make_complete_snapshot()
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research, main_action="open_long")

        assert verdict.sufficient is True
        assert verdict.missing_required == []
        assert verdict.confidence_cap == 1.0

    def test_all_evidence_present_no_trade(self):
        """no_trade 动作不需要宏观事件状态，通过。"""
        snapshot = _make_complete_snapshot()
        # no_trade 不需要 research_bundle
        verdict = _check(snapshot=snapshot, research=None, main_action="no_trade")

        assert verdict.sufficient is True

    def test_sufficient_with_missing_optional(self):
        """可选数据缺失时 sufficient=True（只降级 confidence_cap）。"""
        snapshot = _make_complete_snapshot(funding_rate=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research, main_action="open_long")

        assert verdict.sufficient is True
        assert "funding_rate" in verdict.missing_optional
        assert verdict.confidence_cap < 1.0


# ===========================================================================
# 缺核心执行数据时阻断
# ===========================================================================


class TestMissingRequiredEvidence:
    """测试必需证据缺失时证据门禁阻断。"""

    def test_block_missing_ticker(self):
        """缺 ticker 时阻断。"""
        snapshot = _make_complete_snapshot(ticker=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert "ticker" in verdict.missing_required

    def test_block_missing_mark_price(self):
        """缺 mark_price 时阻断。"""
        snapshot = _make_complete_snapshot(mark_price=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert "mark_price" in verdict.missing_required

    def test_block_missing_index_price(self):
        """缺 index_price 时阻断。"""
        snapshot = _make_complete_snapshot(index_price=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert "index_price" in verdict.missing_required

    def test_block_missing_order_book(self):
        """缺 order_book 时阻断。"""
        snapshot = _make_complete_snapshot(order_book=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert "order_book" in verdict.missing_required

    def test_block_missing_candles(self):
        """缺 candles 时阻断。"""
        snapshot = _make_complete_snapshot(candles=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert "candles" in verdict.missing_required

    def test_block_missing_multiple_required(self):
        """缺多个必需字段时阻断，全部收集到 missing_required。"""
        snapshot = _make_complete_snapshot(ticker=None, mark_price=None, candles=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert "ticker" in verdict.missing_required
        assert "mark_price" in verdict.missing_required
        assert "candles" in verdict.missing_required

    def test_block_missing_macro_for_opening(self):
        """开仓动作缺宏观事件状态时阻断。"""
        snapshot = _make_complete_snapshot()
        research = _make_research_bundle(macro_findings=[])
        verdict = _check(snapshot=snapshot, research=research, main_action="open_long")

        assert verdict.sufficient is False
        assert "macro_event_status" in verdict.missing_required

    def test_block_no_research_bundle_for_opening(self):
        """开仓动作 research_bundle=None 时阻断。"""
        snapshot = _make_complete_snapshot()
        verdict = _check(snapshot=snapshot, research=None, main_action="open_long")

        assert verdict.sufficient is False
        assert "macro_event_status" in verdict.missing_required

    def test_no_macro_required_for_non_opening(self):
        """no_trade 动作不需要宏观事件状态。"""
        snapshot = _make_complete_snapshot()
        verdict = _check(snapshot=snapshot, research=None, main_action="no_trade")

        assert verdict.sufficient is True

    def test_no_macro_required_for_hold(self):
        """hold_long 动作不需要宏观事件状态。"""
        snapshot = _make_complete_snapshot()
        verdict = _check(snapshot=snapshot, research=None, main_action="hold_long")

        assert verdict.sufficient is True


# ===========================================================================
# 缺可选数据时降级置信度
# ===========================================================================


class TestOptionalDataDowngrade:
    """测试可选数据缺失时 confidence_cap 降级。"""

    def test_funding_rate_missing_cap_070(self):
        """缺 funding_rate 时 cap 降至 0.70。"""
        snapshot = _make_complete_snapshot(funding_rate=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert "funding_rate" in verdict.missing_optional
        assert verdict.confidence_cap == 0.70

    def test_open_interest_missing_cap_070(self):
        """缺 open_interest 时 cap 降至 0.70。"""
        snapshot = _make_complete_snapshot(open_interest=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert verdict.confidence_cap == 0.70

    def test_long_short_ratio_missing_cap_065(self):
        """缺 long_short_ratio 时 cap 降至 0.65。"""
        snapshot = _make_complete_snapshot(long_short_ratio=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert verdict.confidence_cap == 0.65

    def test_liquidation_map_missing_cap_058(self):
        """缺 liquidation_map 时 cap 降至 0.58。"""
        snapshot = _make_complete_snapshot(liquidation_map=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert verdict.confidence_cap == 0.58

    def test_btc_anchor_missing_for_eth_cap_060(self):
        """分析 ETH 时缺 btc_anchor，cap 降至 0.60。"""
        snapshot = _make_complete_snapshot(btc_anchor=None)
        research = _make_research_bundle()
        verdict = _check(
            snapshot=snapshot, research=research,
            instrument="ETH-USDT-SWAP",
        )

        assert verdict.sufficient is True
        assert "btc_anchor" in verdict.missing_optional
        assert verdict.confidence_cap == 0.60

    def test_btc_anchor_not_checked_for_btc(self):
        """分析 BTC 时不检查 btc_anchor。"""
        snapshot = _make_complete_snapshot(btc_anchor=None)
        research = _make_research_bundle()
        verdict = _check(
            snapshot=snapshot, research=research,
            instrument="BTC-USDT-SWAP",
        )

        assert verdict.sufficient is True
        assert "btc_anchor" not in verdict.missing_optional
        assert verdict.confidence_cap == 1.0

    def test_multiple_optional_missing_takes_min_cap(self):
        """多个可选数据缺失时取最低 cap。"""
        # funding_rate -> 0.70, liquidation_map -> 0.58
        # min = 0.58
        snapshot = _make_complete_snapshot(
            funding_rate=None,
            liquidation_map=None,
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert verdict.confidence_cap == 0.58

    def test_all_optional_missing(self):
        """所有可选数据缺失时取最低 cap。"""
        snapshot = _make_complete_snapshot(
            funding_rate=None,
            open_interest=None,
            long_short_ratio=None,
            cvd_taker_delta=None,
            liquidation_map=None,
            etf_flows=None,
            stablecoin_supply=None,
            btc_anchor=None,
        )
        research = _make_research_bundle()
        verdict = _check(
            snapshot=snapshot, research=research,
            instrument="ETH-USDT-SWAP",
        )

        assert verdict.sufficient is True
        # liquidation_map cap = 0.58 is the lowest
        assert verdict.confidence_cap == 0.58
        assert len(verdict.missing_optional) == 8

    def test_warnings_generated_for_missing_optional(self):
        """缺失可选数据时生成警告。"""
        snapshot = _make_complete_snapshot(funding_rate=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert any("funding_rate" in w for w in verdict.warnings)


# ===========================================================================
# 新鲜度检查
# ===========================================================================


class TestDataFreshness:
    """测试数据新鲜度检查。"""

    def test_block_stale_market_data(self):
        """行情数据超过 90s 时阻断。"""
        snapshot = _make_complete_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=120)).isoformat()
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert "data_freshness" in verdict.missing_required

    def test_pass_fresh_market_data(self):
        """行情数据在 90s 内时通过。"""
        snapshot = _make_complete_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=30)).isoformat()
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True

    def test_block_no_data_fetched_at_for_opening(self):
        """开仓动作缺 data_fetched_at 时阻断。"""
        snapshot = _make_complete_snapshot()
        snapshot.pop("data_fetched_at")
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research, main_action="open_long")

        assert verdict.sufficient is False
        assert "data_fetched_at" in verdict.missing_required

    def test_no_data_fetched_at_needed_for_non_opening(self):
        """非开仓动作不需要 data_fetched_at（但已存在不会触发阻断）。"""
        snapshot = _make_complete_snapshot()
        snapshot.pop("data_fetched_at")
        verdict = _check(snapshot=snapshot, research=None, main_action="no_trade")

        assert verdict.sufficient is True

    def test_stale_derivatives_downgrade_not_block(self):
        """衍生品数据超过 5min 时降级置信度，不阻断。"""
        stale_ts = (NOW - timedelta(seconds=STALE_DERIVATIVES_THRESHOLD + 60)).isoformat()
        snapshot = _make_complete_snapshot(
            funding_rate={"value": 0.0001, "fetched_at": stale_ts},
            open_interest={"value": 1000.5, "fetched_at": stale_ts},
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert verdict.confidence_cap <= 0.70
        assert any("陈旧" in w for w in verdict.warnings)

    def test_fresh_derivatives_no_downgrade(self):
        """衍生品数据在 5min 内时不降级。"""
        fresh_ts = (NOW - timedelta(seconds=60)).isoformat()
        snapshot = _make_complete_snapshot(
            funding_rate={"value": 0.0001, "fetched_at": fresh_ts},
            open_interest={"value": 1000.5, "fetched_at": fresh_ts},
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert verdict.confidence_cap == 1.0

    def test_boundary_at_exact_90s(self):
        """数据年龄刚好等于 90s 时不阻断（> 90s 才阻断）。"""
        snapshot = _make_complete_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=90)).isoformat()
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True

    def test_stale_warning_message_contains_age(self):
        """陈旧数据警告包含数据年龄信息。"""
        snapshot = _make_complete_snapshot(
            data_fetched_at=(NOW - timedelta(seconds=150)).isoformat()
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert any("150" in w or "陈旧" in w for w in verdict.warnings)


# ===========================================================================
# EvidenceVerdict 结构验证
# ===========================================================================


class TestEvidenceVerdictStructure:
    """验证 EvidenceVerdict 的结构完整性。"""

    def test_verdict_has_all_fields(self):
        """EvidenceVerdict 包含所有定义的字段。"""
        snapshot = _make_complete_snapshot()
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert hasattr(verdict, "sufficient")
        assert hasattr(verdict, "confidence_cap")
        assert hasattr(verdict, "missing_required")
        assert hasattr(verdict, "missing_optional")
        assert hasattr(verdict, "warnings")

    def test_sufficient_verdict_has_empty_missing_required(self):
        """sufficient=True 时 missing_required 为空。"""
        snapshot = _make_complete_snapshot()
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True
        assert verdict.missing_required == []

    def test_insufficient_verdict_has_zero_confidence_cap(self):
        """sufficient=False 时 confidence_cap=0.0。"""
        snapshot = _make_complete_snapshot(ticker=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        assert verdict.confidence_cap == 0.0

    def test_insufficient_verdict_skips_optional_check(self):
        """必需数据缺失时不检查可选数据（直接返回）。"""
        snapshot = _make_complete_snapshot(ticker=None, funding_rate=None)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is False
        # missing_optional 应为空（因为必需数据缺失时跳过可选检查）
        assert verdict.missing_optional == []


# ===========================================================================
# 边界场景
# ===========================================================================


class TestEdgeCases:
    """测试边界场景。"""

    def test_none_snapshot_and_research_for_non_opening(self):
        """非开仓动作 + snapshot=None + research=None 时通过（无必需数据检查）。"""
        verdict = _check(snapshot=None, research=None, main_action="no_trade")

        # snapshot=None -> 所有必需字段缺失 -> 阻断
        # 但 no_trade 不需要 data_fetched_at
        # 实际上 ticker/mark_price/index_price/order_book/candles 仍然检查
        assert verdict.sufficient is False

    def test_empty_snapshot_for_non_opening(self):
        """非开仓动作 + 空快照 -> 必需市场数据缺失阻断。"""
        verdict = _check(snapshot={}, research=None, main_action="no_trade")

        # ticker, mark_price, index_price, order_book, candles 全部缺失
        assert verdict.sufficient is False
        assert len(verdict.missing_required) >= 5

    def test_datetime_object_as_fetched_at(self):
        """data_fetched_at 为 datetime 对象时正常解析。"""
        snapshot = _make_complete_snapshot(
            data_fetched_at=NOW - timedelta(seconds=10)
        )
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True

    def test_unix_timestamp_as_fetched_at(self):
        """data_fetched_at 为 Unix 时间戳时正常解析。"""
        ts = int((NOW - timedelta(seconds=10)).timestamp())
        snapshot = _make_complete_snapshot(data_fetched_at=ts)
        research = _make_research_bundle()
        verdict = _check(snapshot=snapshot, research=research)

        assert verdict.sufficient is True

    def test_close_action_does_not_need_macro(self):
        """close_long 动作不需要宏观事件状态。"""
        snapshot = _make_complete_snapshot()
        verdict = _check(snapshot=snapshot, research=None, main_action="close_long")

        assert verdict.sufficient is True

    def test_hold_action_does_not_need_macro(self):
        """hold_short 动作不需要宏观事件状态。"""
        snapshot = _make_complete_snapshot()
        verdict = _check(snapshot=snapshot, research=None, main_action="hold_short")

        assert verdict.sufficient is True
