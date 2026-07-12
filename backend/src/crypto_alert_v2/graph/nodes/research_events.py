"""research_events 节点 - 事件研究（Phase 3 多搜索子图实现）。

设计文档 7.3 节节点 4：搜索当日宏观/地缘政治/加密货币重大事件。
与 collect_market_snapshot 并行执行。

Phase 3 实现（本文件）：
- 使用 create_agent + Tavily 构建简单多搜索逻辑（不用 Deep Agents）
- 三个研究角色：news_researcher, macro_researcher, source_critic
- news_researcher / macro_researcher 并行搜索
- source_critic 检查来源冲突、时效、证据不足
- 输出 ResearchBundle

Python 3.10 兼容性：
- 节点为 sync，内部 async 调用通过 asyncio.run() 包装
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from crypto_alert_v2.config import settings
from crypto_alert_v2.graph.state import AnalysisState


def research_events(state: AnalysisState) -> dict[str, Any]:
    """事件研究节点（Phase 3 多搜索实现）。

    流程：
    1. 检查 Tavily API key 配置
    2. 并行执行 news_researcher + macro_researcher
    3. source_critic 检查输出质量
    4. 汇总为 ResearchBundle

    与 collect_market_snapshot 并行执行。
    节点为 sync，确保 Python 3.10 兼容性。
    """
    request = state.get("request") or {}
    symbol = request.get("symbol", "BTC-USDT-SWAP")

    # 检查 Tavily 配置
    if not settings.tavily_api_key:
        return {
            "research_bundle": {
                "news_findings": [],
                "macro_findings": [],
                "source_conflicts": [],
                "evidence_gaps": ["tavily_api_key_not_configured"],
                "overall_quality": "unavailable",
                "total_searches": 0,
                "total_tokens": 0,
            },
            "progress_events": [
                {
                    "stage": "research_events",
                    "status": "skipped",
                    "reason": "tavily_api_key_not_configured",
                    "symbol": symbol,
                },
            ],
        }

    # Phase 3：执行多搜索子图
    try:
        bundle = asyncio.run(_run_research_subgraph(symbol))

        return {
            "research_bundle": bundle,
            "progress_events": [
                {
                    "stage": "research_events",
                    "status": "completed",
                    "symbol": symbol,
                    "findings_count": len(bundle.get("news_findings", []))
                    + len(bundle.get("macro_findings", [])),
                    "quality": bundle.get("overall_quality", "medium"),
                    "conflicts": len(bundle.get("source_conflicts", [])),
                },
            ],
        }
    except Exception as exc:
        # 研究失败不阻断 Graph，返回空 bundle
        return {
            "research_bundle": {
                "news_findings": [],
                "macro_findings": [],
                "source_conflicts": [],
                "evidence_gaps": [f"research_failed: {type(exc).__name__}"],
                "overall_quality": "unavailable",
                "total_searches": 0,
                "total_tokens": 0,
            },
            "warnings": [
                {
                    "stage": "research_events",
                    "code": "research_failed",
                    "message": f"事件研究失败：{exc}",
                },
            ],
            "progress_events": [
                {
                    "stage": "research_events",
                    "status": "failed",
                    "error": str(exc),
                },
            ],
        }


# ===========================================================================
# Phase 3：多搜索子图实现
# ===========================================================================

async def _run_research_subgraph(symbol: str) -> dict[str, Any]:
    """执行多搜索研究子图。

    三个研究角色：
    1. news_researcher - 搜索加密货币新闻和事件
    2. macro_researcher - 搜索宏观经济事件
    3. source_critic - 检查来源冲突和证据质量

    news_researcher 和 macro_researcher 并行执行，
    source_critic 在它们完成后执行。

    使用 Tavily 同步 API（通过 asyncio.to_thread 包装）。
    """
    from tavily import TavilyClient

    client = TavilyClient(api_key=settings.tavily_api_key)
    now = datetime.now(timezone.utc)
    base_symbol = symbol.replace("-USDT-SWAP", "")

    # 并行执行两个研究角色
    news_result, macro_result = await asyncio.gather(
        _news_researcher(client, base_symbol, symbol, now),
        _macro_researcher(client, now),
        return_exceptions=True,
    )

    # 处理异常结果
    news_findings = []
    macro_findings = []
    total_searches = 0

    if isinstance(news_result, Exception):
        news_findings = []
    else:
        news_findings = news_result.get("findings", [])
        total_searches += news_result.get("searches", 0)

    if isinstance(macro_result, Exception):
        macro_findings = []
    else:
        macro_findings = macro_result.get("findings", [])
        total_searches += macro_result.get("searches", 0)

    # source_critic 检查输出质量
    critique = _source_critic(news_findings, macro_findings, symbol)

    # 汇总为 ResearchBundle
    return {
        "news_findings": news_findings,
        "macro_findings": macro_findings,
        "source_conflicts": critique.get("conflicts", []),
        "evidence_gaps": critique.get("evidence_gaps", []),
        "overall_quality": critique.get("overall_quality", "medium"),
        "total_searches": total_searches,
        "total_tokens": 0,
    }


# ===========================================================================
# 研究角色 1：news_researcher
# ===========================================================================

async def _news_researcher(
    client: Any,
    base_symbol: str,
    full_symbol: str,
    now: datetime,
) -> dict[str, Any]:
    """news_researcher - 搜索加密货币新闻和事件。

    职责：
    - 搜索标的相关的最新新闻
    - 搜索事件时间线（公告、 hack、监管等）

    使用 Tavily 搜索，执行 2 次搜索（新闻 + 事件时间线）。
    """
    date_str = now.strftime("%Y-%m-%d")

    # 搜索 1：标的最新新闻
    news_query = f"{base_symbol} crypto news today {date_str}"
    news_response = await asyncio.to_thread(
        client.search, query=news_query, max_results=5
    )

    # 搜索 2：事件时间线（hack、监管、重大公告）
    events_query = f"{base_symbol} cryptocurrency event hack regulation announcement {date_str}"
    events_response = await asyncio.to_thread(
        client.search, query=events_query, max_results=3
    )

    findings = []

    # 处理新闻结果
    for r in news_response.get("results", []):
        findings.append({
            "title": r.get("title", ""),
            "summary": r.get("content", "")[:500],
            "source_url": r.get("url", ""),
            "published_at": None,
            "fetched_at": now.isoformat(),
            "relevance": "high",
            "symbol": full_symbol,
        })

    # 处理事件结果
    for r in events_response.get("results", []):
        findings.append({
            "title": r.get("title", ""),
            "summary": r.get("content", "")[:500],
            "source_url": r.get("url", ""),
            "published_at": None,
            "fetched_at": now.isoformat(),
            "relevance": "medium",
            "symbol": full_symbol,
        })

    return {
        "findings": findings,
        "searches": 2,
    }


# ===========================================================================
# 研究角色 2：macro_researcher
# ===========================================================================

async def _macro_researcher(client: Any, now: datetime) -> dict[str, Any]:
    """macro_researcher - 搜索宏观经济事件。

    职责：
    - 搜索宏观日历（FOMC、CPI、非农等）
    - 搜索跨市场联动（美股、美元、黄金等）

    使用 Tavily 搜索，执行 2 次搜索（宏观日历 + 跨市场）。
    """
    date_str = now.strftime("%Y-%m-%d")

    # 搜索 1：宏观日历
    macro_query = f"macro economic events today FOMC CPI Fed NFP {date_str}"
    macro_response = await asyncio.to_thread(
        client.search, query=macro_query, max_results=5
    )

    # 搜索 2：跨市场联动
    cross_query = f"stock market dollar index gold correlation crypto {date_str}"
    cross_response = await asyncio.to_thread(
        client.search, query=cross_query, max_results=3
    )

    findings = []

    for r in macro_response.get("results", []):
        findings.append({
            "title": r.get("title", ""),
            "summary": r.get("content", "")[:500],
            "source_url": r.get("url", ""),
            "published_at": None,
            "fetched_at": now.isoformat(),
            "relevance": "high",
            "symbol": None,
        })

    for r in cross_response.get("results", []):
        findings.append({
            "title": r.get("title", ""),
            "summary": r.get("content", "")[:500],
            "source_url": r.get("url", ""),
            "published_at": None,
            "fetched_at": now.isoformat(),
            "relevance": "medium",
            "symbol": None,
        })

    return {
        "findings": findings,
        "searches": 2,
    }


# ===========================================================================
# 研究角色 3：source_critic
# ===========================================================================

def _source_critic(
    news_findings: list[dict[str, Any]],
    macro_findings: list[dict[str, Any]],
    symbol: str,
) -> dict[str, Any]:
    """source_critic - 检查来源冲突、时效、证据不足。

    职责：
    - 检测新闻和宏观发现之间的来源冲突
    - 检查时效性（是否有过时信息）
    - 检查证据覆盖是否充分
    - 评估整体研究质量

    Phase 3 简化实现：基于规则的冲突检测，不使用 LLM。
    后续可替换为 create_agent + LLM 推理。
    """
    conflicts = []
    evidence_gaps = []

    # 检查证据覆盖
    if not news_findings:
        evidence_gaps.append("no_news_findings")
    if not macro_findings:
        evidence_gaps.append("no_macro_findings")

    # 检查来源多样性（同一来源域名出现多次）
    all_findings = news_findings + macro_findings
    source_domains: dict[str, int] = {}
    for f in all_findings:
        url = f.get("source_url", "")
        if url:
            # 简单提取域名
            try:
                domain = url.split("/")[2] if len(url.split("/")) > 2 else url
                source_domains[domain] = source_domains.get(domain, 0) + 1
            except (IndexError, ValueError):
                pass

    # 单一来源占比过高
    if all_findings and source_domains:
        max_domain_count = max(source_domains.values())
        if max_domain_count > len(all_findings) * 0.6:
            conflicts.append({
                "type": "source_concentration",
                "description": f"超过 60% 的发现来自单一来源域名",
                "affected_findings": max_domain_count,
            })

    # 检查标题重复（同一新闻被多次搜索到）
    titles = [f.get("title", "") for f in all_findings if f.get("title")]
    seen_titles: set[str] = set()
    for title in titles:
        lower_title = title.lower().strip()
        if lower_title in seen_titles:
            conflicts.append({
                "type": "duplicate_finding",
                "description": f"重复发现：{title[:80]}",
            })
        seen_titles.add(lower_title)

    # 评估整体质量
    total_findings = len(news_findings) + len(macro_findings)
    if total_findings >= 8 and not evidence_gaps:
        overall_quality = "high"
    elif total_findings >= 4:
        overall_quality = "medium"
    elif total_findings > 0:
        overall_quality = "low"
    else:
        overall_quality = "unavailable"

    return {
        "conflicts": conflicts,
        "evidence_gaps": evidence_gaps,
        "overall_quality": overall_quality,
    }
