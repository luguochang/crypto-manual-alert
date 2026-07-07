from __future__ import annotations

from fastapi import APIRouter, Request

from .schemas import success


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health(request: Request) -> dict:
    """返回 API 存活状态和当前轻量存储类型。"""

    return success(
        {
            "service": "crypto-manual-alert",
            "storage": "sqlite",
            "mode": request.app.state.config.app.mode,
        }
    )


@router.get("/config")
def get_config(request: Request) -> dict:
    """返回脱敏后的当前配置快照（只读）。

    用于前端配置界面展示 effective 值、env 状态和安全边界。不暴露任何
    secret 原文（safe_dict 已对 bark key 等做 <redacted>/<unset> 处理），
    也不允许写入——配置变更仍需改 YAML 并重启，避免运行时绕过安全校验。
    """

    return success(request.app.state.config.safe_dict())
