from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LlmTelemetry:
    """LLM 调用观测字段，保持为可空值以兼容不同 OpenAI-compatible 网关。"""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    cost_usd: float | None = None


def extract_chat_completion_telemetry(payload: dict[str, Any]) -> LlmTelemetry:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    choice = _first_dict(payload.get("choices")) if isinstance(payload, dict) else None
    return LlmTelemetry(
        prompt_tokens=_int_or_none(_dict_get(usage, "prompt_tokens")),
        completion_tokens=_int_or_none(_dict_get(usage, "completion_tokens")),
        total_tokens=_int_or_none(_dict_get(usage, "total_tokens")),
        finish_reason=_str_or_none(choice.get("finish_reason") if choice else None),
        # 模型价格依赖网关和模型版本；未配置定价表时宁可留空，不写错误成本。
        cost_usd=None,
    )


def extract_responses_telemetry(payload: dict[str, Any]) -> LlmTelemetry:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    return LlmTelemetry(
        prompt_tokens=_int_or_none(_dict_get(usage, "input_tokens") or _dict_get(usage, "prompt_tokens")),
        completion_tokens=_int_or_none(_dict_get(usage, "output_tokens") or _dict_get(usage, "completion_tokens")),
        total_tokens=_int_or_none(_dict_get(usage, "total_tokens")),
        finish_reason=_responses_finish_reason(payload),
        cost_usd=None,
    )


def _first_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    return first if isinstance(first, dict) else None


def _dict_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _responses_finish_reason(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("finish_reason") is not None:
        return str(payload["finish_reason"])
    for item in payload.get("output") or []:
        if isinstance(item, dict) and item.get("finish_reason") is not None:
            return str(item["finish_reason"])
    return None
