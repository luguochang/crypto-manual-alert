"""SQLAlchemy ORM Models - 13 张核心表。

来源：V2技术设计缺口补充.md 第四节 DDL 对应的 ORM。

表清单：
1.  tenants              - 租户
2.  users                - 用户
3.  agent_runs           - Agent 运行记录
4.  analysis_results     - 分析结果
5.  market_snapshots     - 市场快照
6.  evidence_items       - 证据
7.  decision_results     - 风控结果
8.  rule_hits            - 风控规则命中
9.  notification_attempts - 通知
10. run_feedback         - 用户反馈
11. outcomes             - Outcome（成熟窗口后的真实结果）
12. product_event_projections - 产品事件投影
13. interrupt_inbox      - Interrupt Inbox 投影
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ===========================================================================
# Base
# ===========================================================================

class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""
    pass


# ===========================================================================
# 1. tenants - 租户
# ===========================================================================

class Tenant(Base):
    """租户表（Phase 1 只有一个默认租户）。"""
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


# ===========================================================================
# 2. users - 用户
# ===========================================================================

class User(Base):
    """用户表。"""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    risk_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default='{"max_leverage": 2, "risk_pct": 0.25}'
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default='{"default_horizon": "4h", "notify_channels": ["inbox", "bark"]}'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="users")


# ===========================================================================
# 3. agent_runs - Agent 运行记录
# ===========================================================================

class AgentRun(Base):
    """Agent 运行记录。

    每次 Graph 执行对应一条记录。
    status 流转：queued -> running -> waiting_human -> succeeded/blocked/failed/cancelled
    """
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    server_run_id: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(50), nullable=False, default="market_analysis")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_of_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resume_of_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    langsmith_run_id: Mapped[str | None] = mapped_column(Text)
    langfuse_trace_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 4. analysis_results - 分析结果
# ===========================================================================

class AnalysisResult(Base):
    """分析结果表。

    每次 LLM 分析的完整结构化输出。
    包含 main_action, entry/stop/target, probability, factor_scores 等。
    """
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    horizon: Mapped[str] = mapped_column(String(20), nullable=False)
    query_text: Mapped[str | None] = mapped_column(Text)

    # 结构化业务结果
    main_action: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_trigger: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    target_1: Mapped[float | None] = mapped_column(Float)
    target_2: Mapped[float | None] = mapped_column(Float)
    probability: Mapped[float | None] = mapped_column(Float)
    position_size_class: Mapped[str | None] = mapped_column(String(20))
    max_leverage: Mapped[int | None] = mapped_column(Integer)
    risk_pct: Mapped[float | None] = mapped_column(Float)
    why_not_opposite: Mapped[str | None] = mapped_column(Text)
    invalidation: Mapped[str | None] = mapped_column(Text)
    regime: Mapped[str | None] = mapped_column(String(30))
    factor_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    total_score: Mapped[int | None] = mapped_column(Integer)
    root_cause_chain: Mapped[list[str] | None] = mapped_column(JSONB)
    unavailable_data: Mapped[list[str] | None] = mapped_column(JSONB)
    manual_execution_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 完成范围
    completion_scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    warnings: Mapped[list[Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 5. market_snapshots - 市场快照
# ===========================================================================

class MarketSnapshot(Base):
    """市场快照表。

    每次 OKX 行情采集的完整数据。
    """
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)

    # 原生数据
    ticker: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mark_price: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    index_price: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    funding_rate: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    open_interest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    order_book: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    candles: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # 新鲜度和来源
    data_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_level: Mapped[str] = mapped_column(String(30), nullable=False, default="exchange_native")
    unavailable_fields: Mapped[list[str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 6. evidence_items - 证据
# ===========================================================================

class EvidenceItem(Base):
    """证据表。

    研究子图发现的事件、新闻、数据等。
    """
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    symbol: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 7. decision_results - 风控结果
# ===========================================================================

class DecisionResult(Base):
    """风控结果表。

    14 条风控规则的聚合判定。
    """
    __tablename__ = "decision_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocked_reasons: Mapped[list[str] | None] = mapped_column(JSONB)
    warnings: Mapped[list[str] | None] = mapped_column(JSONB)
    confidence_cap: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 8. rule_hits - 风控规则命中
# ===========================================================================

class RuleHit(Base):
    """风控规则命中表。

    每条风控规则的单独命中记录。
    """
    __tablename__ = "rule_hits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)  # blocking/warn
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 9. notification_attempts - 通知
# ===========================================================================

class NotificationAttempt(Base):
    """通知尝试表。

    Bark 推送的发送记录。
    """
    __tablename__ = "notification_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)  # bark/inbox/web_push/email
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 10. run_feedback - 用户反馈
# ===========================================================================

class RunFeedback(Base):
    """用户反馈表。

    用户对分析结果的 approve/reject/edit/correct/comment。
    """
    __tablename__ = "run_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(30), nullable=False)
    feedback_content: Mapped[str | None] = mapped_column(Text)
    edits: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 11. outcomes - Outcome（成熟窗口后的真实结果）
# ===========================================================================

class Outcome(Base):
    """Outcome 表。

    分析结果在成熟窗口后的真实市场结果。
    用于计算 hit_rate, Brier score, PnL 等。
    """
    __tablename__ = "outcomes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[float | None] = mapped_column(Float)
    high_price: Mapped[float | None] = mapped_column(Float)
    low_price: Mapped[float | None] = mapped_column(Float)
    close_price: Mapped[float | None] = mapped_column(Float)
    direction_hit: Mapped[bool | None] = mapped_column(Boolean)
    target_hit: Mapped[bool | None] = mapped_column(Boolean)
    invalidation_hit: Mapped[bool | None] = mapped_column(Boolean)
    pnl_pct: Mapped[float | None] = mapped_column(Float)
    r_multiple: Mapped[float | None] = mapped_column(Float)
    brier_score: Mapped[float | None] = mapped_column(Float)
    no_trade_baseline_pnl: Mapped[float | None] = mapped_column(Float)
    scoring_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    unscoreable_reason: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 12. product_event_projections - 产品事件投影
# ===========================================================================

class ProductEventProjection(Base):
    """产品事件投影表。

    可分页的时间线，用于前端展示。
    """
    __tablename__ = "product_event_projections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence_num: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ===========================================================================
# 13. interrupt_inbox - Interrupt Inbox 投影
# ===========================================================================

class InterruptInbox(Base):
    """Interrupt Inbox 投影表。

    HITL 中断的收件箱投影，用于 Inbox 页面展示。
    """
    __tablename__ = "interrupt_inbox"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    interrupt_id: Mapped[str] = mapped_column(Text, nullable=False)
    interrupt_type: Mapped[str] = mapped_column(String(50), nullable=False)
    interrupt_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    checkpoint_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
