from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiError(BaseModel):
    """前端可稳定解析的错误结构，避免依赖中文错误文本。"""

    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ApiEnvelope(BaseModel, Generic[T]):
    """所有 API 的统一响应外壳。"""

    ok: bool
    data: T | None = None
    error: ApiError | None = None
    trace_id: str | None = None


class ManualRunRequest(BaseModel):
    """手动运行请求。

    API 兼容旧字段 query，但后端会统一映射为 DecisionRequest.query_text。
    """

    symbol: str = "BTC-USDT-SWAP"
    query: str | None = None
    query_text: str | None = None
    horizon: str | None = None
    session_id: str | None = None
    alert_channel: str | None = "bark"


class EvalRunRequest(BaseModel):
    """旁路 eval 运行请求。

    该请求只选择历史 badcase/case，不允许触发实时行情、Bark 或生产 plan runner。
    """

    dataset_name: str | None = None
    badcase_ids: list[int] | None = None
    mode: str = "judge_only_fixture"
    limit: int = 50


def success(data: Any, trace_id: str | None = None) -> dict[str, Any]:
    """构造成功响应，保持 FastAPI 与前端契约一致。"""

    return {"ok": True, "data": data, "error": None, "trace_id": trace_id}


def failure(
    *,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """构造失败响应，错误码用于前端分支处理。"""

    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "detail": detail or {}},
        "trace_id": trace_id,
    }
