"""Repository 模式 - 数据库写入。

设计文档 V2技术设计缺口补充.md 第四节 + 16 文档 Phase 1 交付清单。

Phase 1 实现：
- save_analysis_result：写入 analysis_results 表
- save_market_snapshot：写入 market_snapshots 表
- save_decision_result：写入 decision_results 表
- save_agent_run：写入/更新 agent_runs 表

设计要点：
1. 使用 SQLAlchemy 2.0 async（asyncpg）
2. 连接池由 Agent Server 管理，Repository 只负责 CRUD
3. 写入失败抛异常，由调用方（commit_final_artifact 节点）降级处理
4. Phase 1 简化：不实现读取方法（前端通过 Agent Server SDK 读取）
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from crypto_alert_v2.config import settings
from crypto_alert_v2.storage.models import (
    AgentRun,
    AnalysisResult,
    Base,
    DecisionResult,
    MarketSnapshot,
)

# ===========================================================================
# 引擎和 Session 管理
# ===========================================================================

# async engine（asyncpg 驱动）
_async_engine = None
_AsyncSessionLocal = None


def _get_async_engine():
    """获取或创建 async engine（单例）。

    将 postgresql:// 转为 postgresql+asyncpg://
    """
    global _async_engine
    if _async_engine is None:
        uri = settings.postgres_uri
        # 转换 URI 为 asyncpg 格式
        if uri.startswith("postgresql://"):
            uri = uri.replace("postgresql://", "postgresql+asyncpg://", 1)
        _async_engine = create_async_engine(uri, echo=False, pool_pre_ping=True)
    return _async_engine


def _get_session_factory():
    """获取或创建 async session factory（单例）。"""
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = sessionmaker(
            _get_async_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _AsyncSessionLocal


# ===========================================================================
# Repository
# ===========================================================================

class Repository:
    """数据库 Repository。

    Phase 1 实现：
    - save_analysis_result：写入分析结果
    - save_market_snapshot：写入市场快照
    - save_decision_result：写入风控结果
    - save_agent_run：写入/更新运行记录

    使用方式：
        repo = Repository()
        await repo.save_analysis_result(run_id=..., final_result=...)

    注意：所有方法都是 async，需要在 async 上下文中调用。
    如果 PostgreSQL 不可用，方法会抛异常，调用方应 try/except 降级。
    """

    def __init__(self):
        self._session_factory = _get_session_factory()

    async def save_analysis_result(
        self,
        run_id: str,
        tenant_id: str = "",
        user_id: str = "",
        final_result: dict[str, Any] | None = None,
    ) -> str:
        """写入分析结果到 analysis_results 表。

        Args:
            run_id: 运行 ID
            tenant_id: 租户 ID
            user_id: 用户 ID
            final_result: 最终结果字典

        Returns:
            创建的 analysis_result ID
        """
        final_result = final_result or {}

        # 从 main_action 推导 direction
        action = final_result.get("main_action", "no_trade")
        if "long" in action:
            direction = "long"
        elif "short" in action:
            direction = "short"
        else:
            direction = "neutral"

        # 解析 expires_at
        expires_at_str = final_result.get("expires_at")
        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        async with self._session_factory() as session:
            result = AnalysisResult(
                id=uuid.uuid4(),
                run_id=_parse_uuid(run_id),
                tenant_id=_parse_uuid(tenant_id),
                user_id=_parse_uuid(user_id),
                symbol=final_result.get("instrument", "BTC-USDT-SWAP"),
                horizon=final_result.get("horizon", "4h"),
                main_action=action,
                direction=direction,
                entry_trigger=final_result.get("entry_trigger"),
                stop_price=final_result.get("stop_price"),
                target_1=final_result.get("target_1"),
                target_2=final_result.get("target_2"),
                probability=final_result.get("probability"),
                position_size_class=final_result.get("position_size_class"),
                max_leverage=final_result.get("max_leverage"),
                risk_pct=final_result.get("risk_pct"),
                why_not_opposite=final_result.get("why_not_opposite"),
                invalidation=final_result.get("invalidation"),
                regime=final_result.get("regime"),
                factor_scores=final_result.get("factor_scores"),
                total_score=final_result.get("total_score"),
                root_cause_chain=final_result.get("root_cause_chain", []),
                unavailable_data=final_result.get("unavailable_data", []),
                manual_execution_required=final_result.get("manual_execution_required", True),
                expires_at=expires_at,
                warnings=final_result.get("risk_warnings"),
            )
            session.add(result)
            await session.commit()
            return str(result.id)

    async def save_market_snapshot(
        self,
        run_id: str,
        snapshot: dict[str, Any],
    ) -> str:
        """写入市场快照到 market_snapshots 表。

        Args:
            run_id: 运行 ID
            snapshot: 市场快照字典

        Returns:
            创建的 market_snapshot ID
        """
        # 解析 data_fetched_at
        fetched_at_str = snapshot.get("data_fetched_at")
        fetched_at = datetime.now(timezone.utc)
        if fetched_at_str:
            try:
                fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        async with self._session_factory() as session:
            record = MarketSnapshot(
                id=uuid.uuid4(),
                run_id=_parse_uuid(run_id),
                symbol=snapshot.get("symbol", "BTC-USDT-SWAP"),
                ticker=snapshot.get("ticker"),
                mark_price=snapshot.get("mark_price"),
                index_price=snapshot.get("index_price"),
                funding_rate=snapshot.get("funding_rate"),
                open_interest=snapshot.get("open_interest"),
                order_book=snapshot.get("order_book"),
                candles=snapshot.get("candles"),
                data_fetched_at=fetched_at,
                source_level=snapshot.get("source_level", "exchange_native"),
                unavailable_fields=snapshot.get("unavailable_fields", []),
            )
            session.add(record)
            await session.commit()
            return str(record.id)

    async def save_decision_result(
        self,
        run_id: str,
        risk_verdict: dict[str, Any],
    ) -> str:
        """写入风控结果到 decision_results 表。

        Args:
            run_id: 运行 ID
            risk_verdict: 风控裁决字典

        Returns:
            创建的 decision_result ID
        """
        async with self._session_factory() as session:
            record = DecisionResult(
                id=uuid.uuid4(),
                run_id=_parse_uuid(run_id),
                allowed=risk_verdict.get("allowed", False),
                blocked_reasons=risk_verdict.get("blocked_reasons", []),
                warnings=risk_verdict.get("warnings", []),
                confidence_cap=risk_verdict.get("confidence_cap", 1.0),
            )
            session.add(record)
            await session.commit()
            return str(record.id)

    async def save_agent_run(
        self,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        status: str = "running",
        mode: str = "market_analysis",
    ) -> str:
        """写入/更新 agent_runs 表。

        Args:
            run_id: 运行 ID
            tenant_id: 租户 ID
            user_id: 用户 ID
            thread_id: LangGraph Thread ID
            status: 运行状态
            mode: 运行模式

        Returns:
            创建/更新的 agent_run ID
        """
        async with self._session_factory() as session:
            record = AgentRun(
                id=_parse_uuid(run_id),
                tenant_id=_parse_uuid(tenant_id),
                user_id=_parse_uuid(user_id),
                thread_id=thread_id,
                status=status,
                mode=mode,
                started_at=datetime.now(timezone.utc),
            )
            session.add(record)
            await session.commit()
            return str(record.id)

    async def update_agent_run_status(
        self,
        run_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """更新 agent_runs 状态。

        Args:
            run_id: 运行 ID
            status: 新状态（succeeded/blocked/failed/cancelled）
            error_message: 错误信息（失败时）
        """
        async with self._session_factory() as session:
            record = await session.get(AgentRun, _parse_uuid(run_id))
            if record:
                record.status = status
                record.completed_at = datetime.now(timezone.utc)
                if error_message:
                    record.error_message = error_message
                await session.commit()


# ===========================================================================
# 辅助函数
# ===========================================================================

def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """将字符串解析为 UUID。

    如果解析失败，生成一个基于字符串的 UUID（确定性）。
    """
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        # 生成确定性 UUID（相同字符串 -> 相同 UUID）
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(value))
