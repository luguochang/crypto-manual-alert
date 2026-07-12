"""Pydantic 业务模型 - LLM 结构化输出 Schema 和风控/证据裁决。

来源：14-system-prompt-and-evidence-gates.md 第一节 + V2技术设计缺口补充.md 第六节。

设计要点：
1. MarketAnalysis 是 LLM 的 Structured Output Schema，用 response_format=MarketAnalysis
2. RiskVerdict 是 14 条风控规则的聚合结果
3. EvidenceVerdict 是证据门禁的判定结果
4. 所有模型用 Pydantic v2，支持 JSON 序列化和运行时校验
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ===========================================================================
# MarketAnalysis - LLM 结构化输出 Schema
# ===========================================================================

class MarketAnalysis(BaseModel):
    """LLM 结构化输出。

    通过 ChatOpenAI 的 response_format=MarketAnalysis 强制模型输出此结构。
    每个字段都有明确语义和约束，确保风控规则可以确定性检查。

    设计文档 14 第一节定义的完整 schema。
    """

    # === 市场体制分类 ===
    regime: Literal["risk_on", "risk_off", "event_compression", "surprise_repricing"]

    # === 11 因子评分（-2 到 +2）===
    factor_scores: dict[str, int] = Field(
        description="11个因子评分：btc_structure, macro_bridge, derivatives, flows, "
        "event_calendar, surprise_factor, cross_asset, regime_shift, "
        "positioning, volatility, fundamental"
    )

    # === 因子总分 ===
    total_score: int

    # === 唯一动作枚举 ===
    main_action: Literal[
        "open_long", "open_short", "hold_long", "hold_short",
        "close_long", "close_short", "flip_long_to_short", "flip_short_to_long",
        "trigger_long", "trigger_short", "no_trade",
    ]

    # === 交易标的和时间跨度 ===
    instrument: str
    horizon: str

    # === 价格参数 ===
    reference_price: float
    entry_trigger: float | None = None
    stop_price: float | None = None
    target_1: float | None = None
    target_2: float | None = None

    # === 概率和仓位 ===
    probability: float = Field(ge=0, le=1, description="主观胜率 0-1")
    position_size_class: Literal["light", "standard", "heavy", "none"] = "none"
    max_leverage: int = Field(ge=1, le=2, description="最大杠杆，硬性上限 2x")
    risk_pct: float = Field(ge=0, le=0.25, description="单笔风险占比，硬性上限 25%")

    # === 分析推理 ===
    root_cause_chain: list[str] = Field(description="根因链，因果推导链条")
    why_not_opposite: str = Field(description="对抗性审查：为什么不做相反方向")
    invalidation: str = Field(description="失效条件：什么情况下此分析作废")

    # === 数据质量 ===
    unavailable_data: list[str] = []

    # === 执行约束（固定值，不可由模型修改）===
    manual_execution_required: bool = True
    expires_in_seconds: int = 90


# ===========================================================================
# RiskVerdict - 风控裁决结果
# ===========================================================================

class RiskVerdict(BaseModel):
    """风控结果。

    14 条确定性风控规则的聚合输出。
    - allowed=False 时 blocked_reasons 非空，阻断开仓类动作
    - warnings 是非阻断警告（如数据缺失但不阻断当前动作）
    - confidence_cap 是证据门禁设置的置信度上限
    """

    allowed: bool
    blocked_reasons: list[str] = []
    warnings: list[str] = []
    confidence_cap: float = 1.0


# ===========================================================================
# EvidenceVerdict - 证据门禁裁决
# ===========================================================================

class EvidenceVerdict(BaseModel):
    """证据门禁结果。

    检查必需证据是否齐全、可选证据缺失情况。
    - sufficient=False 时阻断开仓类动作
    - confidence_cap 根据缺失的可选证据降级
    - missing_required / missing_optional 分别记录缺失项
    """

    sufficient: bool
    confidence_cap: float = 1.0
    missing_required: list[str] = []
    missing_optional: list[str] = []
    warnings: list[str] = []


# ===========================================================================
# 辅助类型 - 开仓类动作集合
# ===========================================================================

# 开仓类动作：需要完整的入场/止损/失效条件
# hold/no_trade/close 类动作不需要这些
OPENING_ACTIONS = frozenset({
    "open_long", "open_short",
    "trigger_long", "trigger_short",
    "flip_long_to_short", "flip_short_to_long",
})

# 所有合法动作
ALL_ACTIONS = frozenset({
    "open_long", "open_short", "hold_long", "hold_short",
    "close_long", "close_short", "flip_long_to_short", "flip_short_to_long",
    "trigger_long", "trigger_short", "no_trade",
})


# ===========================================================================
# ResearchBundle - 研究子图输出（Phase 1 简化版）
# ===========================================================================

class ResearchFinding(BaseModel):
    """单条研究发现。"""
    title: str
    summary: str
    source_url: str = ""
    published_at: datetime | None = None
    fetched_at: datetime
    relevance: Literal["high", "medium", "low"] = "medium"
    symbol: str | None = None


class ResearchBundle(BaseModel):
    """研究子图输出，传入 analyze_market 节点。

    Phase 1 简化实现：research_events 节点可能返回空 bundle（skip 模式）
    或简单的 Tavily 搜索结果。Phase 3 替换为完整 Deep Agents 子图。
    """
    news_findings: list[ResearchFinding] = []
    macro_findings: list[ResearchFinding] = []
    source_conflicts: list[dict] = []
    evidence_gaps: list[str] = []
    overall_quality: Literal["high", "medium", "low", "unavailable"] = "unavailable"
    total_searches: int = 0
    total_tokens: int = 0
