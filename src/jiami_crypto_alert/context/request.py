from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RUN_TYPES = {"manual", "scheduled", "eval", "replay", "postmortem"}


@dataclass(frozen=True)
class DecisionRequest:
    """归一化一次决策请求的业务语义。

    该对象只描述“用户想让系统评估什么”，不拉行情、不调用 LLM、不做交易判断。
    manual_only 是手动提醒系统的硬边界，不能被外部输入关闭。
    """

    run_type: str = "manual"
    symbol: str = "BTC-USDT-SWAP"
    query_text: str = ""
    horizon: str | None = None
    session_id: str | None = None
    manual_only: bool = True
    alert_channel: str | None = "bark"

    def __post_init__(self) -> None:
        if self.run_type not in RUN_TYPES:
            raise ValueError(f"run_type must be one of: {', '.join(sorted(RUN_TYPES))}")
        normalized_symbol = (self.symbol or "BTC-USDT-SWAP").strip().upper()
        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "query_text", (self.query_text or "").strip())
        object.__setattr__(self, "manual_only", True)


def build_manual_decision_request(payload: dict[str, Any] | Any) -> DecisionRequest:
    """将手动 API 请求归一化为 DecisionRequest。

    首版兼容历史 `query` 字段，但内部统一使用 `query_text`，便于后续接入意图识别、
    query 改写和会话记忆。这里不接触行情、LLM 或通知副作用。
    """

    data = _to_mapping(payload)
    query_text = str(data.get("query_text") or data.get("query") or "")
    return DecisionRequest(
        run_type="manual",
        symbol=str(data.get("symbol") or "BTC-USDT-SWAP"),
        query_text=query_text,
        horizon=_optional_text(data.get("horizon")),
        session_id=_optional_text(data.get("session_id")),
        manual_only=True,
        alert_channel=_optional_text(data.get("alert_channel")) or "bark",
    )


def _to_mapping(payload: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        return dict(payload.model_dump())
    if hasattr(payload, "dict"):
        return dict(payload.dict())
    return {}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
