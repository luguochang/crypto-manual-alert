from __future__ import annotations

from fastapi import APIRouter, Request

from .schemas import success


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health(request: Request) -> dict:
    """返回 API 存活状态和当前轻量存储类型。"""

    return success(
        {
            "service": "jiami-crypto-alert",
            "storage": "sqlite",
            "mode": request.app.state.config.app.mode,
        }
    )
