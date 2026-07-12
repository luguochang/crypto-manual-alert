"""Bark 通知 Tool - 推送分析结果到用户手机。

来源：V1 notification/sinks.py 的 BarkNotificationSink 迁移。

设计要点：
1. @tool 装饰器：Graph 节点调用（非 Agent 自动调用）
2. 通知标题格式：{symbol} {action} {probability}%
3. 通知正文包含：入场/止损/目标/风险/反向理由/有效期
4. "系统不会自动下单" 强提醒（产品核心约束）
5. 失败重试 1 次（V1 是多次重试，V2 Phase 1 简化为 1 次）

Bark 是 iOS 推送通知服务，通过 URL GET 请求发送推送：
  https://api.day.app/{device_key}/{title}/{body}
"""

import asyncio
from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from crypto_alert_v2.config import settings

# Bark API 超时（秒）
BARK_TIMEOUT = 8

# 重试次数（Phase 1：失败重试 1 次）
BARK_MAX_RETRIES = 1

# Bark 基础 URL
BARK_BASE_URL = "https://api.day.app"


@tool
async def send_bark_notification(
    symbol: str,
    action: str,
    probability: float,
    entry_trigger: float | None = None,
    stop_price: float | None = None,
    target_1: float | None = None,
    target_2: float | None = None,
    risk_pct: float | None = None,
    max_leverage: int | None = None,
    why_not_opposite: str = "",
    expires_in_seconds: int = 90,
    risk_allowed: bool = True,
    blocked_reasons: list[str] | None = None,
    warnings: list[str] | None = None,
    unavailable_data: list[str] | None = None,
) -> dict[str, Any]:
    """发送 Bark 推送通知。

    将分析结果推送到用户手机，包含完整的交易参数和风控状态。
    用户收到通知后手动在 OKX App 执行交易。

    Args:
        symbol: 交易标的，如 BTC-USDT-SWAP
        action: 主动作，如 open_long
        probability: 胜率 0-1
        entry_trigger: 入场触发价
        stop_price: 止损价
        target_1: 目标价 1
        target_2: 目标价 2
        risk_pct: 单笔风险占比
        max_leverage: 最大杠杆
        why_not_opposite: 反向理由（对抗性审查）
        expires_in_seconds: 有效期（秒）
        risk_allowed: 风控是否通过
        blocked_reasons: 风控阻断原因列表
        warnings: 警告列表
        unavailable_data: 不可用数据列表

    Returns:
        发送结果字典：{"ok": bool, "status_code": int, "error": str | None}
    """
    bark_key = settings.bark_key
    if not bark_key:
        return {"ok": False, "status_code": None, "error": "BARK_KEY 未配置"}

    # 构建通知标题和正文
    title = _build_title(symbol, action, probability)
    body = _build_body(
        symbol=symbol,
        action=action,
        entry_trigger=entry_trigger,
        stop_price=stop_price,
        target_1=target_1,
        target_2=target_2,
        risk_pct=risk_pct,
        max_leverage=max_leverage,
        why_not_opposite=why_not_opposite,
        expires_in_seconds=expires_in_seconds,
        risk_allowed=risk_allowed,
        blocked_reasons=blocked_reasons or [],
        warnings=warnings or [],
        unavailable_data=unavailable_data or [],
    )

    # 构建 Bark URL
    url = (
        f"{BARK_BASE_URL}/{quote(bark_key, safe='')}"
        f"/{quote(title, safe='')}"
        f"/{quote(body, safe='')}"
    )

    # 发送请求（失败重试 1 次）
    last_error: str | None = None
    for attempt in range(BARK_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=BARK_TIMEOUT) as client:
                resp = await client.get(url)
                if resp.status_code < 400:
                    return {"ok": True, "status_code": resp.status_code, "error": None}
                last_error = f"HTTP {resp.status_code}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        # 重试前等待（指数退避）
        if attempt < BARK_MAX_RETRIES:
            await asyncio.sleep(2 ** attempt)

    return {"ok": False, "status_code": None, "error": last_error}


def _build_title(symbol: str, action: str, probability: float) -> str:
    """构建通知标题。

    格式：{symbol} {action} {probability}%
    """
    prob_pct = round(probability * 100) if probability is not None else 0
    return f"{symbol} {action} {prob_pct}%"


def _build_body(
    symbol: str,
    action: str,
    entry_trigger: float | None,
    stop_price: float | None,
    target_1: float | None,
    target_2: float | None,
    risk_pct: float | None,
    max_leverage: int | None,
    why_not_opposite: str,
    expires_in_seconds: int,
    risk_allowed: bool,
    blocked_reasons: list[str],
    warnings: list[str],
    unavailable_data: list[str],
) -> str:
    """构建通知正文。

    包含完整交易参数、风控状态和强提醒。
    """
    status_text = "可手动执行" if risk_allowed else "风控阻断"
    lines = [
        f"状态：{status_text}",
        "强提醒：系统不会自动下单，请打开 OKX App 手动核对。",
        f"有效期：{expires_in_seconds} 秒",
        f"入场/触发：{entry_trigger}",
        f"止损：{stop_price}",
        f"T1/T2：{target_1} / {target_2}",
        f"风险：{risk_pct} 杠杆≤{max_leverage}",
        f"反向理由：{why_not_opposite}",
    ]

    if blocked_reasons:
        lines.append("阻断原因：" + "; ".join(blocked_reasons))
    if warnings:
        lines.append("警告：" + "; ".join(warnings))
    if unavailable_data:
        lines.append("数据缺口：" + ", ".join(unavailable_data))

    return "\n".join(lines)
