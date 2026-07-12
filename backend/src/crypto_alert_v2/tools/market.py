"""OKX 行情 Tool - 交易所原生数据采集。

来源：V2技术设计缺口补充.md 第三节 + V1 okx_snapshot.py 迁移。

设计要点：
1. @tool 装饰器：Agent 通过 create_agent 自动调用
2. 并发调用 7 个 OKX endpoint（ticker/mark/index/funding_rate/open_interest/order_book/candles）
3. asyncio.Semaphore(5) 限频：OKX 公开 API 限制 20 req/2s
4. 每个数据附带 fetched_at 时间戳（风控新鲜度检查依赖此时间戳）
5. 缺失数据标记为 unavailable_fields（不抛异常，让风控决定是否阻断）
6. Phase 1 先不做 Redis 缓存（设计文档说缓存可选）

OKX API 文档：
- GET /api/v5/market/ticker?instId=BTC-USDT-SWAP
- GET /api/v5/public/mark-price?instType=SWAP&instId=BTC-USDT-SWAP
- GET /api/v5/market/index-tickers?instId=BTC-USDT
- GET /api/v5/public/funding-rate?instId=BTC-USDT-SWAP
- GET /api/v5/public/open-interest?instId=BTC-USDT-SWAP
- GET /api/v5/market/books?instId=BTC-USDT-SWAP&sz=20
- GET /api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1H&limit=48
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from langchain_core.tools import tool

from crypto_alert_v2.config import settings

# 全局信号量：限制同时发出的 OKX 请求数
# OKX 公开 API 限制 20 req/2s，7 个 endpoint 并发完全安全
_okx_semaphore = asyncio.Semaphore(5)

# OKX API 单次超时（秒）
OKX_TIMEOUT = 10

# 默认请求的 7 类数据
DEFAULT_DATA_TYPES = [
    "ticker",
    "mark_price",
    "index_price",
    "funding_rate",
    "open_interest",
    "order_book",
    "candles",
]


@tool
async def fetch_market_data(symbol: str, data_types: list[str] | None = None) -> dict[str, Any]:
    """获取交易所原生市场数据（OKX 公开 API）。

    并发调用 7 个 OKX endpoint 获取完整市场快照。
    数据来源等级：exchange_native（最高可信度）。

    Args:
        symbol: 交易标的，如 BTC-USDT-SWAP、ETH-USDT-SWAP
        data_types: 需要获取的数据类型列表，默认全部 7 类

    Returns:
        包含所有市场数据的字典，每个字段附带 fetched_at 时间戳。
        失败的 endpoint 标记为 None，并加入 unavailable_fields 列表。
    """
    types = data_types or DEFAULT_DATA_TYPES
    base_url = settings.okx_base_url.rstrip("/")
    fetched_at = datetime.now(timezone.utc)

    # 并发获取所有数据类型
    async with httpx.AsyncClient(timeout=OKX_TIMEOUT) as client:
        tasks = [_fetch_one(client, base_url, symbol, dt) for dt in types]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 组装快照
    snapshot: dict[str, Any] = {
        "symbol": symbol,
        "data_fetched_at": fetched_at.isoformat(),
        "source_level": "exchange_native",
        "unavailable_fields": [],
    }

    for data_type, result in zip(types, results):
        if isinstance(result, Exception) or result is None:
            # 请求失败或返回 None，标记为不可用
            snapshot["unavailable_fields"].append(data_type)
            snapshot[data_type] = None
        else:
            snapshot[data_type] = result

    return snapshot


async def _fetch_one(
    client: httpx.AsyncClient,
    base_url: str,
    symbol: str,
    data_type: str,
) -> dict[str, Any] | None:
    """获取单个数据类型。

    使用信号量限频，失败返回 None（不抛异常）。
    """
    async with _okx_semaphore:
        try:
            url, params = _build_request(base_url, symbol, data_type)
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            # OKX API 返回格式：{"code": "0", "data": [...], "msg": ""}
            if data.get("code") != "0":
                return None

            return {
                "raw": data.get("data", []),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "okx_public",
            }
        except Exception:
            # 任何异常都返回 None，不阻断其他 endpoint 的获取
            return None


def _build_request(
    base_url: str,
    symbol: str,
    data_type: str,
) -> tuple[str, dict[str, str]]:
    """构建 OKX API 请求 URL 和参数。

    根据数据类型映射到对应的 OKX endpoint。
    """
    # 从 SWAP 合约中提取现货 ID（用于 index ticker）
    # BTC-USDT-SWAP -> BTC-USDT
    index_id = symbol.replace("-SWAP", "") if symbol.endswith("-SWAP") else symbol

    endpoints: dict[str, tuple[str, dict[str, str]]] = {
        "ticker": (
            f"{base_url}/api/v5/market/ticker",
            {"instId": symbol},
        ),
        "mark_price": (
            f"{base_url}/api/v5/public/mark-price",
            {"instType": "SWAP", "instId": symbol},
        ),
        "index_price": (
            f"{base_url}/api/v5/market/index-tickers",
            {"instId": index_id},
        ),
        "funding_rate": (
            f"{base_url}/api/v5/public/funding-rate",
            {"instId": symbol},
        ),
        "open_interest": (
            f"{base_url}/api/v5/public/open-interest",
            {"instId": symbol},
        ),
        "order_book": (
            f"{base_url}/api/v5/market/books",
            {"instId": symbol, "sz": "20"},  # 前 20 档
        ),
        "candles": (
            f"{base_url}/api/v5/market/candles",
            {"instId": symbol, "bar": "1H", "limit": "48"},  # 48 根 1H K线
        ),
    }

    if data_type not in endpoints:
        raise ValueError(f"未知数据类型：{data_type}")

    return endpoints[data_type]


@tool
async def fetch_btc_anchor() -> dict[str, Any]:
    """获取 BTC 方向锚数据（分析 ETH/SOL 时需要）。

    BTC 是加密市场的方向锚，分析 ETH/SOL 时必须先获取 BTC 的关键数据
    作为方向参照（设计文档 14 第 5 步）。

    Returns:
        BTC-USDT-SWAP 的简化快照（ticker + mark_price）
    """
    # 复用 fetch_market_data 的逻辑，只获取关键数据
    result = await fetch_market_data.ainvoke({
        "symbol": "BTC-USDT-SWAP",
        "data_types": ["ticker", "mark_price"],
    })
    return {"btc_anchor": result}
