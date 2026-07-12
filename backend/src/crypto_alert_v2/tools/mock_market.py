"""Mock 市场数据 Tool - Phase 0 验证用。

验证 Tool 可以被 Agent 调用（Agent Loop: model -> tool -> model）。
生产环境替换为真实 OKX 交易所数据 tool（设计文档 7.6 节）。
"""

from langchain_core.tools import tool


@tool
def get_market_snapshot(symbol: str) -> dict:
    """获取指定交易标的的市场数据快照。

    Phase 0 返回固定 mock 数据，验证 Tool 调用链路。
    生产环境替换为交易所原生接口（OKX 公开 API），数据来源等级为 exchange_native。

    Args:
        symbol: 交易标的，如 BTC-USDT-SWAP、ETH-USDT-SWAP。
    """
    return {
        "symbol": symbol,
        "ticker": {
            "last": "65000.5",
            "bid": "64995.0",
            "ask": "65005.0",
            "vol24h": "1234.56",
        },
        "mark_price": "65010.0",
        "index_price": "64990.0",
        "funding_rate": "0.0001",
        "open_interest": "1000.5",
        "data_fetched_at": "2026-07-12T00:00:00Z",
        "source_level": "exchange_native",
        "unavailable_fields": [],
    }
