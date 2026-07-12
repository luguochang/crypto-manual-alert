"""评测集构建 - 100 条初始评测集，覆盖 8 个维度。

来源：V2重构方案评审与补充建议_修订版.md 第 6.2 节。

数据结构（LangSmith Dataset Example）：
    {
        "inputs": {
            "symbol": "BTC-USDT-SWAP",
            "horizon": "4h",
            "query_text": "当前是否有做空机会？",
            "market_snapshot": {...},
            "research_bundle": {...},
        },
        "outputs": {
            "expected_direction": "short",
            "expected_confidence_range": [0.55, 0.75],
            "expected_risk_blocked": False,
            "expected_risk_rules_hit": [],
            "must_include_evidence": ["funding_rate", "open_interest"],
            "must_not_include": ["auto_order"],
            "key_checks": {...},
        },
        "metadata": {
            "category": "market_analysis",
            "subcategory": "short_signal",
            "market_condition": "bearish",
            "difficulty": "medium",
            "source": "online_desensitized",
            "created_at": "2026-07-12",
        },
    }

8 维度覆盖（100 条）：
| 维度               | 数量 | 场景示例                         |
|--------------------|------|----------------------------------|
| 市场分析-做多       | 15   | BTC/ETH/SOL 上涨趋势，回调入场   |
| 市场分析-做空       | 15   | 下跌趋势，反弹做空               |
| 市场分析-观望       | 10   | 震荡行情，无明确信号              |
| 风险拦截            | 20   | 高杠杆/不允许标的/auto_order/过期 |
| 证据评估            | 10   | 证据充足/缺失/冲突/过期           |
| 降级处理            | 10   | OKX不可用/Search失败/模型超时     |
| 多轮对话            | 10   | 追问/修正/上下文切换              |
| 边界测试            | 10   | 空输入/超长query/极端行情/不支持  |
| 总计               | 100  |                                  |
"""

from copy import deepcopy
from typing import Any, Literal


# ===========================================================================
# 维度定义
# ===========================================================================

EvalCategory = Literal[
    "market_analysis_long",
    "market_analysis_short",
    "market_analysis_hold",
    "risk_intercept",
    "evidence_eval",
    "degradation",
    "multi_turn",
    "boundary",
]

# 8 维度分布
DIMENSION_DISTRIBUTION: dict[str, int] = {
    "market_analysis_long": 15,
    "market_analysis_short": 15,
    "market_analysis_hold": 10,
    "risk_intercept": 20,
    "evidence_eval": 10,
    "degradation": 10,
    "multi_turn": 10,
    "boundary": 10,
}

TOTAL_CASES = sum(DIMENSION_DISTRIBUTION.values())  # 100


# ===========================================================================
# 基础模板
# ===========================================================================

def _make_base_market_snapshot(symbol: str = "BTC-USDT-SWAP") -> dict[str, Any]:
    """创建基础市场快照（可回放）。"""
    return {
        "symbol": symbol,
        "ticker": {"last": "65000.5", "bid": "64995.0", "ask": "65005.0", "vol24h": "1234.56"},
        "mark_price": "65010.0",
        "index_price": "64990.0",
        "funding_rate": "0.0001",
        "open_interest": "1000.5",
        "data_fetched_at": "2026-07-12T00:00:00Z",
        "source_level": "exchange_native",
        "unavailable_fields": [],
    }


def _make_base_research_bundle() -> dict[str, Any]:
    """创建基础研究证据。"""
    return {
        "news_findings": [
            {
                "title": "BTC breaks key resistance",
                "summary": "Bitcoin broke above 65k resistance with strong volume",
                "source_url": "https://example.com/news1",
                "relevance": "high",
                "symbol": "BTC-USDT-SWAP",
            }
        ],
        "macro_findings": [
            {
                "title": "Fed holds rates steady",
                "summary": "Federal Reserve maintains current rate policy",
                "source_url": "https://example.com/macro1",
                "relevance": "high",
                "symbol": None,
            }
        ],
        "source_conflicts": [],
        "evidence_gaps": [],
        "overall_quality": "medium",
        "total_searches": 2,
        "total_tokens": 0,
    }


# ===========================================================================
# 测试用例生成器
# ===========================================================================

def _make_case(
    case_id: str,
    category: EvalCategory,
    symbol: str,
    horizon: str,
    query_text: str,
    expected_direction: str,
    expected_confidence_range: list[float],
    expected_risk_blocked: bool = False,
    expected_risk_rules_hit: list[str] | None = None,
    must_include_evidence: list[str] | None = None,
    must_not_include: list[str] | None = None,
    key_checks: dict[str, bool] | None = None,
    market_condition: str = "neutral",
    difficulty: str = "medium",
    source: str = "manual",
    market_snapshot: dict[str, Any] | None = None,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建一条评测用例。"""
    return {
        "id": case_id,
        "inputs": {
            "symbol": symbol,
            "horizon": horizon,
            "query_text": query_text,
            "market_snapshot": market_snapshot or _make_base_market_snapshot(symbol),
            "research_bundle": research_bundle or _make_base_research_bundle(),
        },
        "outputs": {
            "expected_direction": expected_direction,
            "expected_confidence_range": expected_confidence_range,
            "expected_risk_blocked": expected_risk_blocked,
            "expected_risk_rules_hit": expected_risk_rules_hit or [],
            "must_include_evidence": must_include_evidence or [],
            "must_not_include": must_not_include or ["auto_order"],
            "key_checks": key_checks
            or {
                "has_stop_loss": True,
                "has_entry_range": True,
                "has_invalidation": True,
                "manual_execution_required": True,
            },
        },
        "metadata": {
            "category": category,
            "subcategory": f"{category}_{expected_direction}",
            "market_condition": market_condition,
            "difficulty": difficulty,
            "source": source,
            "created_at": "2026-07-12",
        },
    }


# ===========================================================================
# 维度 1：市场分析-做多（15 条）
# ===========================================================================

def _gen_long_cases() -> list[dict[str, Any]]:
    """做多场景：上涨趋势，回调入场。"""
    cases = []
    symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]
    horizons = ["1h", "4h", "12h", "24h"]
    queries = [
        "BTC 是否有做多机会？",
        "当前上涨趋势能否入场做多？",
        "ETH 回调到位了吗？可以做多吗？",
        "SOL 突破后做多机会如何？",
        "做多 BTC 风险收益比分析",
    ]

    for i in range(15):
        symbol = symbols[i % len(symbols)]
        horizon = horizons[i % len(horizons)]
        query = queries[i % len(queries)]
        cases.append(
            _make_case(
                case_id=f"long_{i+1:03d}",
                category="market_analysis_long",
                symbol=symbol,
                horizon=horizon,
                query_text=query,
                expected_direction="long",
                expected_confidence_range=[0.55, 0.75],
                market_condition="bullish",
                difficulty="medium" if i < 10 else "hard",
            )
        )
    return cases


# ===========================================================================
# 维度 2：市场分析-做空（15 条）
# ===========================================================================

def _gen_short_cases() -> list[dict[str, Any]]:
    """做空场景：下跌趋势，反弹做空。"""
    cases = []
    symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]
    horizons = ["1h", "4h", "12h", "24h"]
    queries = [
        "当前是否有做空机会？",
        "BTC 下跌趋势中可以反弹做空吗？",
        "ETH 做空风险收益比分析",
        "SOL 跌破支撑后做空机会",
        "做空 BTC 的止损应该设在哪里？",
    ]

    for i in range(15):
        symbol = symbols[i % len(symbols)]
        horizon = horizons[i % len(horizons)]
        query = queries[i % len(queries)]
        cases.append(
            _make_case(
                case_id=f"short_{i+1:03d}",
                category="market_analysis_short",
                symbol=symbol,
                horizon=horizon,
                query_text=query,
                expected_direction="short",
                expected_confidence_range=[0.55, 0.75],
                market_condition="bearish",
                difficulty="medium" if i < 10 else "hard",
            )
        )
    return cases


# ===========================================================================
# 维度 3：市场分析-观望（10 条）
# ===========================================================================

def _gen_hold_cases() -> list[dict[str, Any]]:
    """观望场景：震荡行情，无明确信号。"""
    cases = []
    queries = [
        "当前行情适合交易吗？",
        "BTC 震荡区间内应该如何操作？",
        "没有明确方向时该怎么办？",
        "ETH 横盘整理中需要观望吗？",
        "市场信号矛盾时是否应该观望？",
    ]

    for i in range(10):
        symbol = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"][i % 3]
        cases.append(
            _make_case(
                case_id=f"hold_{i+1:03d}",
                category="market_analysis_hold",
                symbol=symbol,
                horizon="4h",
                query_text=queries[i % len(queries)],
                expected_direction="neutral",
                expected_confidence_range=[0.3, 0.5],
                market_condition="ranging",
                difficulty="easy" if i < 5 else "medium",
                key_checks={
                    "has_stop_loss": False,
                    "has_entry_range": False,
                    "has_invalidation": False,
                    "manual_execution_required": True,
                },
            )
        )
    return cases


# ===========================================================================
# 维度 4：风险拦截（20 条）
# ===========================================================================

def _gen_risk_intercept_cases() -> list[dict[str, Any]]:
    """风险拦截场景：高杠杆/不允许标的/auto_order/数据过期等。"""
    cases = []

    # 4a. 高杠杆拦截（5 条）
    for i in range(5):
        cases.append(
            _make_case(
                case_id=f"risk_leverage_{i+1:03d}",
                category="risk_intercept",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text=f"用 5x 杠杆做多 BTC",
                expected_direction="long",
                expected_confidence_range=[0.5, 0.7],
                expected_risk_blocked=True,
                expected_risk_rules_hit=["leverage_exceeds_max"],
                market_condition="bullish",
                difficulty="easy",
                source="bad_case",
            )
        )

    # 4b. 不允许标的（5 条）
    for i in range(5):
        cases.append(
            _make_case(
                case_id=f"risk_symbol_{i+1:03d}",
                category="risk_intercept",
                symbol=f"UNKNOWN-USDT-SWAP",
                horizon="4h",
                query_text=f"分析 UNKNOWN-USDT-SWAP 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.0, 0.3],
                expected_risk_blocked=True,
                expected_risk_rules_hit=["symbol_not_in_whitelist"],
                market_condition="unknown",
                difficulty="easy",
                source="bad_case",
            )
        )

    # 4c. 数据过期（5 条）
    for i in range(5):
        snapshot = _make_base_market_snapshot()
        snapshot["data_fetched_at"] = "2026-07-11T00:00:00Z"  # 1 天前
        cases.append(
            _make_case(
                case_id=f"risk_stale_{i+1:03d}",
                category="risk_intercept",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="long",
                expected_confidence_range=[0.5, 0.7],
                expected_risk_blocked=True,
                expected_risk_rules_hit=["data_freshness_expired"],
                market_snapshot=snapshot,
                market_condition="unknown",
                difficulty="medium",
                source="bad_case",
            )
        )

    # 4d. auto_order 请求（5 条）
    for i in range(5):
        cases.append(
            _make_case(
                case_id=f"risk_auto_{i+1:03d}",
                category="risk_intercept",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="自动下单买入 BTC",
                expected_direction="long",
                expected_confidence_range=[0.0, 0.3],
                expected_risk_blocked=True,
                expected_risk_rules_hit=["auto_order_disabled"],
                must_not_include=["auto_order", "automatic_execution"],
                market_condition="neutral",
                difficulty="easy",
                source="bad_case",
            )
        )

    return cases


# ===========================================================================
# 维度 5：证据评估（10 条）
# ===========================================================================

def _gen_evidence_cases() -> list[dict[str, Any]]:
    """证据评估场景：证据充足/缺失/冲突/过期。"""
    cases = []

    # 5a. 证据充足（3 条）
    for i in range(3):
        cases.append(
            _make_case(
                case_id=f"evidence_sufficient_{i+1:03d}",
                category="evidence_eval",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="long",
                expected_confidence_range=[0.6, 0.8],
                must_include_evidence=["funding_rate", "open_interest", "order_book"],
                market_condition="bullish",
                difficulty="medium",
            )
        )

    # 5b. 证据缺失（3 条）
    for i in range(3):
        snapshot = _make_base_market_snapshot()
        snapshot["unavailable_fields"] = ["funding_rate", "open_interest"]
        cases.append(
            _make_case(
                case_id=f"evidence_missing_{i+1:03d}",
                category="evidence_eval",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.3, 0.5],
                must_include_evidence=["funding_rate", "open_interest"],
                market_snapshot=snapshot,
                market_condition="unknown",
                difficulty="hard",
            )
        )

    # 5c. 证据冲突（2 条）
    for i in range(2):
        bundle = _make_base_research_bundle()
        bundle["source_conflicts"] = [
            {
                "type": "directional_conflict",
                "description": "新闻偏多但衍生品数据偏空",
            }
        ]
        cases.append(
            _make_case(
                case_id=f"evidence_conflict_{i+1:03d}",
                category="evidence_eval",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.3, 0.5],
                research_bundle=bundle,
                market_condition="conflicting",
                difficulty="hard",
            )
        )

    # 5d. 证据过期（2 条）
    for i in range(2):
        bundle = _make_base_research_bundle()
        bundle["overall_quality"] = "low"
        bundle["evidence_gaps"] = ["stale_news", "stale_macro"]
        cases.append(
            _make_case(
                case_id=f"evidence_stale_{i+1:03d}",
                category="evidence_eval",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.3, 0.5],
                research_bundle=bundle,
                market_condition="unknown",
                difficulty="medium",
            )
        )

    return cases


# ===========================================================================
# 维度 6：降级处理（10 条）
# ===========================================================================

def _gen_degradation_cases() -> list[dict[str, Any]]:
    """降级处理场景：OKX不可用/Search失败/模型超时。"""
    cases = []

    # 6a. OKX 数据不可用（4 条）
    for i in range(4):
        snapshot = _make_base_market_snapshot()
        snapshot["unavailable_fields"] = ["ticker", "mark_price", "index_price"]
        snapshot["source_level"] = "web_derived"
        cases.append(
            _make_case(
                case_id=f"degrade_okx_{i+1:03d}",
                category="degradation",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.2, 0.4],
                market_snapshot=snapshot,
                market_condition="degraded",
                difficulty="hard",
                key_checks={
                    "has_stop_loss": False,
                    "has_entry_range": False,
                    "has_invalidation": False,
                    "manual_execution_required": True,
                },
            )
        )

    # 6b. Search 失败（3 条）
    for i in range(3):
        bundle = _make_base_research_bundle()
        bundle["news_findings"] = []
        bundle["macro_findings"] = []
        bundle["overall_quality"] = "unavailable"
        bundle["evidence_gaps"] = ["search_failed"]
        cases.append(
            _make_case(
                case_id=f"degrade_search_{i+1:03d}",
                category="degradation",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.2, 0.4],
                research_bundle=bundle,
                market_condition="degraded",
                difficulty="hard",
            )
        )

    # 6c. 模型超时（3 条）
    for i in range(3):
        cases.append(
            _make_case(
                case_id=f"degrade_timeout_{i+1:03d}",
                category="degradation",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.0, 0.3],
                expected_risk_blocked=True,
                expected_risk_rules_hit=["model_timeout"],
                market_condition="degraded",
                difficulty="hard",
            )
        )

    return cases


# ===========================================================================
# 维度 7：多轮对话（10 条）
# ===========================================================================

def _gen_multi_turn_cases() -> list[dict[str, Any]]:
    """多轮对话场景：追问/修正/上下文切换。"""
    cases = []
    queries = [
        "分析 BTC 走势",
        "你说的支撑位具体是多少？",
        "如果跌破这个支撑位怎么办？",
        "改用 12h 周期重新分析",
        "ETH 也有类似的机会吗？",
        "止损应该设在哪里？",
        "为什么不做空？",
        "资金费率对分析有什么影响？",
        "如果 FOMC 结果出乎意料呢？",
        "总结一下你的分析逻辑",
    ]

    for i in range(10):
        symbol = "BTC-USDT-SWAP" if i < 5 else "ETH-USDT-SWAP"
        is_followup = i > 0  # 第 0 条是初始请求，其余是追问
        cases.append(
            _make_case(
                case_id=f"multiturn_{i+1:03d}",
                category="multi_turn",
                symbol=symbol,
                horizon="4h",
                query_text=queries[i],
                expected_direction="long" if i % 3 == 0 else "neutral",
                expected_confidence_range=[0.5, 0.7] if i % 3 == 0 else [0.3, 0.5],
                market_condition="neutral",
                difficulty="hard",
                source="manual",
            )
        )
    return cases


# ===========================================================================
# 维度 8：边界测试（10 条）
# ===========================================================================

def _gen_boundary_cases() -> list[dict[str, Any]]:
    """边界测试场景：空输入/超长query/极端行情/不支持的标的。"""
    cases = []

    # 8a. 空输入（2 条）
    for i in range(2):
        cases.append(
            _make_case(
                case_id=f"boundary_empty_{i+1:03d}",
                category="boundary",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="",
                expected_direction="neutral",
                expected_confidence_range=[0.0, 0.2],
                expected_risk_blocked=True,
                expected_risk_rules_hit=["empty_request"],
                market_condition="unknown",
                difficulty="easy",
            )
        )

    # 8b. 超长 query（2 条）
    long_query = "分析 BTC 走势 " + "请详细分析" * 200
    for i in range(2):
        cases.append(
            _make_case(
                case_id=f"boundary_long_{i+1:03d}",
                category="boundary",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text=long_query,
                expected_direction="neutral",
                expected_confidence_range=[0.0, 0.3],
                market_condition="unknown",
                difficulty="medium",
            )
        )

    # 8c. 极端行情（3 条）
    for i in range(3):
        snapshot = _make_base_market_snapshot()
        if i == 0:
            snapshot["ticker"] = {"last": "1000000", "bid": "999900", "ask": "1000100", "vol24h": "99999"}
        elif i == 1:
            snapshot["ticker"] = {"last": "100", "bid": "99", "ask": "101", "vol24h": "99999"}
        else:
            snapshot["funding_rate"] = "0.05"  # 极端资金费率
        cases.append(
            _make_case(
                case_id=f"boundary_extreme_{i+1:03d}",
                category="boundary",
                symbol="BTC-USDT-SWAP",
                horizon="4h",
                query_text="分析 BTC 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.2, 0.4],
                market_snapshot=snapshot,
                market_condition="extreme",
                difficulty="hard",
            )
        )

    # 8d. 不支持的标的（3 条）
    for i in range(3):
        cases.append(
            _make_case(
                case_id=f"boundary_unsupported_{i+1:03d}",
                category="boundary",
                symbol=f"UNKNOWN{i}-USDT-SWAP",
                horizon="4h",
                query_text=f"分析 UNKNOWN{i} 走势",
                expected_direction="neutral",
                expected_confidence_range=[0.0, 0.2],
                expected_risk_blocked=True,
                expected_risk_rules_hit=["symbol_not_in_whitelist"],
                market_condition="unknown",
                difficulty="easy",
            )
        )

    return cases


# ===========================================================================
# 评测集加载
# ===========================================================================

def generate_dataset() -> list[dict[str, Any]]:
    """生成完整的 100 条评测集。

    按维度顺序生成，确保覆盖 8 个维度。
    """
    cases = []
    cases.extend(_gen_long_cases())          # 15
    cases.extend(_gen_short_cases())         # 15
    cases.extend(_gen_hold_cases())          # 10
    cases.extend(_gen_risk_intercept_cases())  # 20
    cases.extend(_gen_evidence_cases())      # 10
    cases.extend(_gen_degradation_cases())   # 10
    cases.extend(_gen_multi_turn_cases())    # 10
    cases.extend(_gen_boundary_cases())      # 10
    # Total: 100
    return cases


def get_dimension_distribution(cases: list[dict[str, Any]]) -> dict[str, int]:
    """统计评测集的维度分布。"""
    distribution: dict[str, int] = {}
    for case in cases:
        category = case["metadata"]["category"]
        distribution[category] = distribution.get(category, 0) + 1
    return distribution


def filter_by_dimension(
    cases: list[dict[str, Any]], dimension: str
) -> list[dict[str, Any]]:
    """按维度筛选测试用例。"""
    return [c for c in cases if c["metadata"]["category"] == dimension]


# ===========================================================================
# 模块级缓存（避免重复生成）
# ===========================================================================

_cached_dataset: list[dict[str, Any]] | None = None


def load_dataset() -> list[dict[str, Any]]:
    """加载评测集（带缓存）。"""
    global _cached_dataset
    if _cached_dataset is None:
        _cached_dataset = generate_dataset()
    return _cached_dataset
