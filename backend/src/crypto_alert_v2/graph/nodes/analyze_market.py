"""analyze_market 节点 - LLM 市场分析（核心节点）。

设计文档 7.3 节节点 5：使用 create_agent + system_prompt + Structured Output。

关键设计决策：
1. 使用 create_agent 创建 Agent（设计文档约束：不自定义 Agent Loop）
2. 使用 ChatOpenAI（不直接 httpx）
3. Structured Output 用 response_format=MarketAnalysis
4. 等待 collect_market_snapshot 和 research_events 都完成后执行（barrier 语义）
5. Phase 1 支持无 API key 的降级模式（返回 no_trade）

约束（设计文档 02）：
- 不自定义 while-loop Agent Loop，用 create_agent
- 不直接 httpx 调用 LLM API，用 ChatOpenAI
- Structured Output 用 Pydantic response_format

Python 3.10 兼容性：
- 节点为 sync，使用 asyncio.run() 调用异步 Agent
"""

import asyncio
import json
from typing import Any

from crypto_alert_v2.config import settings
from crypto_alert_v2.domain.models import MarketAnalysis
from crypto_alert_v2.graph.state import AnalysisState
from crypto_alert_v2.prompts.system_prompt import SYSTEM_PROMPT


def analyze_market(state: AnalysisState) -> dict[str, Any]:
    """LLM 市场分析节点。

    流程：
    1. 组装上下文：市场快照 + 研究结果 + 用户请求
    2. 创建 Agent（create_agent + ChatOpenAI + system_prompt + tools）
    3. 调用 Agent，获取 Structured Output（MarketAnalysis）
    4. 返回 decision_draft

    Phase 1 降级模式：
    - 如果 OPENAI_API_KEY 未配置，返回 no_trade + 降级原因
    - 如果市场快照为 None，返回 no_trade + 数据缺失

    节点为 sync，使用 asyncio.run() 调用异步 Agent。
    """
    request = state.get("request") or {}
    market_snapshot = state.get("market_snapshot")
    research_bundle = state.get("research_bundle")

    symbol = request.get("symbol", "BTC-USDT-SWAP")
    horizon = request.get("horizon", "4h")
    query_text = request.get("query_text", f"分析 {symbol} {horizon} 趋势")

    # 降级模式：无 API key
    if not settings.openai_api_key:
        return _build_degraded_result(
            symbol, horizon,
            reason="OPENAI_API_KEY 未配置，返回 no_trade 降级结果",
        )

    # 降级模式：无市场快照
    if market_snapshot is None:
        return _build_degraded_result(
            symbol, horizon,
            reason="市场快照为空，返回 no_trade 降级结果",
        )

    try:
        # 组装上下文消息
        context = _build_analysis_context(
            symbol, horizon, query_text, market_snapshot, research_bundle
        )

        # 创建 Agent 并调用
        analysis = asyncio.run(_run_analysis_agent(context))

        return {
            "decision_draft": analysis.model_dump(),
            "progress_events": [
                {
                    "stage": "analyze_market",
                    "status": "completed",
                    "symbol": symbol,
                    "main_action": analysis.main_action,
                    "total_score": analysis.total_score,
                    "probability": analysis.probability,
                },
            ],
        }
    except Exception as exc:
        # 分析失败，返回降级结果
        return _build_degraded_result(
            symbol, horizon,
            reason=f"LLM 分析失败：{type(exc).__name__}: {exc}",
            error=exc,
        )


def _build_analysis_context(
    symbol: str,
    horizon: str,
    query_text: str,
    market_snapshot: dict[str, Any],
    research_bundle: dict[str, Any] | None,
) -> str:
    """组装分析上下文消息。

    将市场快照和研究结果格式化为 LLM 可理解的文本。
    """
    parts = [f"分析请求：{query_text}", f"标的：{symbol}", f"时间跨度：{horizon}", ""]

    # 市场快照
    parts.append("=== 市场快照 ===")
    parts.append(json.dumps(market_snapshot, ensure_ascii=False, indent=2, default=str))
    parts.append("")

    # 研究结果
    if research_bundle:
        parts.append("=== 事件研究 ===")
        parts.append(json.dumps(research_bundle, ensure_ascii=False, indent=2, default=str))
        parts.append("")

    parts.append("请按照 8 步工作流分析，输出 MarketAnalysis 结构化结果。")

    return "\n".join(parts)


async def _run_analysis_agent(context: str) -> MarketAnalysis:
    """创建 Agent 并执行分析，返回 Structured Output。

    使用 create_agent + ChatOpenAI + response_format=MarketAnalysis。
    设计文档约束：不直接 httpx，用 ChatOpenAI。
    """
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI

    # 创建模型（ChatOpenAI，不直接 httpx）
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=30,
    )

    # 创建 Agent（设计文档约束：用 create_agent，不自定义 Agent Loop）
    agent = create_agent(
        model=model,
        tools=[],  # Phase 1 不给 Agent tool（数据已在 context 中）
        system_prompt=SYSTEM_PROMPT,
        response_format=MarketAnalysis,  # Structured Output
    )

    # 执行 Agent
    result = await agent.ainvoke({"messages": [{"role": "user", "content": context}]})

    # 从结果中提取 Structured Output
    # create_agent with response_format 会将最后一条 AI message 的 content 解析为 JSON
    last_message = result["messages"][-1]
    content = last_message.content if hasattr(last_message, "content") else str(last_message)

    # 解析为 MarketAnalysis
    if isinstance(content, str):
        # 尝试从 JSON 字符串解析
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # 如果不是 JSON，尝试从 content 中提取 JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError(f"无法从 LLM 输出解析 MarketAnalysis：{content[:200]}")
    elif isinstance(content, dict):
        data = content
    else:
        data = content

    return MarketAnalysis(**data)


def _build_degraded_result(
    symbol: str,
    horizon: str,
    reason: str,
    error: Exception | None = None,
) -> dict[str, Any]:
    """构建降级结果（no_trade）。

    当 LLM 分析不可用时，返回 no_trade 的 MarketAnalysis。
    """
    degraded = MarketAnalysis(
        regime="risk_off",
        factor_scores={},
        total_score=0,
        main_action="no_trade",
        instrument=symbol,
        horizon=horizon,
        reference_price=0.0,
        probability=0.0,
        position_size_class="light",
        max_leverage=1,
        risk_pct=0.0,
        root_cause_chain=[f"降级原因：{reason}"],
        why_not_opposite="降级模式，无法分析反向理由",
        invalidation="降级模式，无失效条件",
        unavailable_data=["llm_analysis"],
        manual_execution_required=True,
        expires_in_seconds=90,
    )

    result: dict[str, Any] = {
        "decision_draft": degraded.model_dump(),
        "warnings": [
            {
                "stage": "analyze_market",
                "code": "degraded",
                "message": reason,
            },
        ],
        "progress_events": [
            {
                "stage": "analyze_market",
                "status": "degraded",
                "symbol": symbol,
                "reason": reason,
            },
        ],
    }

    if error:
        result["errors"] = [{
            "stage": "analyze_market",
            "code": "analysis_failed",
            "message": str(error),
        }]

    return result
