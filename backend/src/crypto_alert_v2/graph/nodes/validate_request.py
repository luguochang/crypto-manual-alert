"""validate_request 节点 - 校验分析请求。

设计文档 7.3 节节点 2：校验 symbol/horizon/query 的合法性。
校验失败则写入 errors，route_after_validation 会路由到 blocked 路径。
"""

from typing import Any

from crypto_alert_v2.graph.state import AnalysisState

# 允许的交易标的
ALLOWED_SYMBOLS = {"BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"}

# 允许的时间跨度
ALLOWED_HORIZONS = {"immediate", "1h", "4h", "1d", "event"}


def validate_request(state: AnalysisState) -> dict[str, Any]:
    """校验分析请求。

    从 state.messages 中提取用户请求，解析 symbol 和 horizon。
    如果 state.request 已有值（外部传入），直接校验。

    校验规则：
    - symbol 必须在 ALLOWED_SYMBOLS 中
    - horizon 必须在 ALLOWED_HORIZONS 中（默认 4h）
    - query_text 可选
    """
    request = state.get("request") or {}
    errors: list[dict[str, Any]] = []

    # 如果 request 为空，尝试从 messages 中提取
    if not request and state.get("messages"):
        last_message = state["messages"][-1]
        content = getattr(last_message, "content", "") if last_message else ""
        if isinstance(content, str) and content.strip():
            request = _parse_request_from_message(content)

    # 设置默认值
    symbol = request.get("symbol", "")
    horizon = request.get("horizon", "4h")
    query_text = request.get("query_text", "")

    # 校验 symbol
    if not symbol:
        errors.append({
            "stage": "validate_request",
            "code": "symbol.missing",
            "message": "缺少交易标的（symbol）",
        })
    elif symbol not in ALLOWED_SYMBOLS:
        errors.append({
            "stage": "validate_request",
            "code": "symbol.not_allowed",
            "message": f"交易品种 {symbol} 不在允许列表：{sorted(ALLOWED_SYMBOLS)}",
        })

    # 校验 horizon
    if horizon not in ALLOWED_HORIZONS:
        errors.append({
            "stage": "validate_request",
            "code": "horizon.invalid",
            "message": f"时间跨度 {horizon} 无效，允许：{sorted(ALLOWED_HORIZONS)}",
        })

    # 如果有错误，返回错误状态
    if errors:
        return {
            "request": request,
            "errors": errors,
            "progress_events": [
                {
                    "stage": "validate_request",
                    "status": "failed",
                    "errors": [e["code"] for e in errors],
                },
            ],
        }

    # 校验通过
    return {
        "request": {
            "symbol": symbol,
            "horizon": horizon,
            "query_text": query_text,
            "notify": request.get("notify", True),
        },
        "progress_events": [
            {
                "stage": "validate_request",
                "status": "completed",
                "symbol": symbol,
                "horizon": horizon,
            },
        ],
    }


def _parse_request_from_message(content: str) -> dict[str, Any]:
    """从用户消息中解析请求参数。

    Phase 1 简化实现：从消息文本中提取 symbol 和 horizon。
    生产环境可用 LLM 做意图理解。
    """
    content_upper = content.upper()
    symbol = "BTC-USDT-SWAP"  # 默认

    # 简单关键词匹配
    if "ETH" in content_upper:
        symbol = "ETH-USDT-SWAP"
    elif "SOL" in content_upper:
        symbol = "SOL-USDT-SWAP"
    elif "BTC" in content_upper or "BITCOIN" in content_upper:
        symbol = "BTC-USDT-SWAP"

    # 时间跨度匹配
    horizon = "4h"  # 默认
    if "1H" in content_upper and "4H" not in content_upper:
        horizon = "1h"
    elif "4H" in content_upper:
        horizon = "4h"
    elif "1D" in content_upper or "DAILY" in content_upper:
        horizon = "1d"
    elif "IMMEDIATE" in content_upper or "NOW" in content_upper:
        horizon = "immediate"

    return {
        "symbol": symbol,
        "horizon": horizon,
        "query_text": content,
        "notify": True,
    }
