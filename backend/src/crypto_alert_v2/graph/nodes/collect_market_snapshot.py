"""collect_market_snapshot 节点 - 采集市场快照。

设计文档 7.3 节节点 3：调用 fetch_market_data tool 获取 OKX 行情数据。
与 research_events 并行执行（设计文档 V2技术设计缺口补充.md 第一节）。

Python 3.10 兼容性：
- 节点为 sync，使用 asyncio.run() 调用异步 tool
- 确保 interrupt() 在 Python 3.10 下正常工作
"""

import asyncio
from typing import Any

from crypto_alert_v2.graph.state import AnalysisState
from crypto_alert_v2.tools.market import fetch_market_data


def collect_market_snapshot(state: AnalysisState) -> dict[str, Any]:
    """采集市场快照。

    调用 fetch_market_data tool 并发获取 7 个 OKX endpoint 数据。
    与 research_events 并行执行，两者都完成后 analyze_market 执行（barrier 语义）。

    设计要点：
    - 数据缺失不抛异常，标记为 unavailable_fields
    - 风控节点会检查 unavailable_fields 决定是否阻断
    - data_fetched_at 时间戳用于新鲜度检查
    - 节点为 sync，使用 asyncio.run() 调用异步 HTTP 请求
    """
    request = state.get("request") or {}
    symbol = request.get("symbol", "BTC-USDT-SWAP")

    try:
        # 调用 fetch_market_data tool 获取完整市场快照
        # 使用 asyncio.run() 在 sync 节点中调用异步 tool
        snapshot = asyncio.run(fetch_market_data.ainvoke({"symbol": symbol}))

        return {
            "market_snapshot": snapshot,
            "progress_events": [
                {
                    "stage": "collect_market_snapshot",
                    "status": "completed",
                    "symbol": symbol,
                    "unavailable_fields": snapshot.get("unavailable_fields", []),
                },
            ],
        }
    except Exception as exc:
        # 采集失败不阻断 Graph，标记为 None，后续节点处理
        return {
            "market_snapshot": None,
            "errors": [
                {
                    "stage": "collect_market_snapshot",
                    "code": "fetch_failed",
                    "message": f"市场数据采集失败：{type(exc).__name__}: {exc}",
                },
            ],
            "progress_events": [
                {
                    "stage": "collect_market_snapshot",
                    "status": "failed",
                    "symbol": symbol,
                    "error": str(exc),
                },
            ],
        }
