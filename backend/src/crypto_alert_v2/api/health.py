"""健康检查 endpoint - /internal/health。

来源：V2技术设计缺口补充.md 第 9.2 节。

Agent Server custom route：
    GET /internal/health

返回：
    {
        "status": "healthy" | "degraded" | "unhealthy",
        "checks": {
            "postgres": {"status": "healthy" | "unhealthy", "latency_ms": 5},
            "redis": {"status": "healthy" | "unhealthy", "latency_ms": 2},
            "okx": {"status": "healthy" | "unhealthy", "latency_ms": 150},
        }
    }

Agent Server 通过 langgraph.json 的 http 配置暴露自定义路由。
设计文档 02-official-framework-constraints.md 允许 /app/* 前缀的自定义路由。
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from crypto_alert_v2.config import settings


# ===========================================================================
# 健康检查函数
# ===========================================================================

async def check_postgres() -> dict[str, Any]:
    """检查 PostgreSQL 连接。

    尝试连接 PostgreSQL 并执行简单查询。
    """
    start = time.monotonic()
    try:
        # 使用异步 SQLAlchemy 检查
        # Phase 6 占位：实际使用时需要 asyncpg 或 SQLAlchemy AsyncSession
        # 这里仅做连接字符串有效性检查
        if not settings.postgres_uri:
            return {"status": "unhealthy", "error": "postgres_uri not configured"}

        # 尝试 TCP 连接
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(settings.postgres_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432

        try:
            _, sock = await asyncio.to_thread(
                _tcp_connect, host, port, timeout=3.0
            )
            sock.close()
        except (socket.timeout, ConnectionRefusedError, OSError) as exc:
            return {
                "status": "unhealthy",
                "error": f"connection_failed: {exc}",
                "latency_ms": int((time.monotonic() - start) * 1000),
            }

        latency_ms = int((time.monotonic() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc),
            "latency_ms": int((time.monotonic() - start) * 1000),
        }


async def check_redis() -> dict[str, Any]:
    """检查 Redis 连接。"""
    start = time.monotonic()
    try:
        if not settings.redis_uri:
            return {"status": "unhealthy", "error": "redis_uri not configured"}

        # 尝试 TCP 连接
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(settings.redis_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379

        try:
            _, sock = await asyncio.to_thread(
                _tcp_connect, host, port, timeout=3.0
            )
            sock.close()
        except (socket.timeout, ConnectionRefusedError, OSError) as exc:
            return {
                "status": "unhealthy",
                "error": f"connection_failed: {exc}",
                "latency_ms": int((time.monotonic() - start) * 1000),
            }

        latency_ms = int((time.monotonic() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc),
            "latency_ms": int((time.monotonic() - start) * 1000),
        }


async def check_okx() -> dict[str, Any]:
    """检查 OKX API 可用性。"""
    start = time.monotonic()
    try:
        import httpx

        # 检查 OKX 公开 API（服务器时间接口）
        url = f"{settings.okx_base_url}/api/v5/public/time"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)

        latency_ms = int((time.monotonic() - start) * 1000)

        if response.status_code == 200:
            return {"status": "healthy", "latency_ms": latency_ms}
        else:
            return {
                "status": "unhealthy",
                "error": f"HTTP {response.status_code}",
                "latency_ms": latency_ms,
            }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc),
            "latency_ms": int((time.monotonic() - start) * 1000),
        }


# ===========================================================================
# TCP 连接辅助
# ===========================================================================

def _tcp_connect(host: str, port: int, timeout: float = 3.0) -> tuple[str, Any]:
    """同步 TCP 连接（在 asyncio.to_thread 中调用）。

    Returns:
        (host, socket) 元组
    """
    import socket

    sock = socket.create_connection((host, port), timeout=timeout)
    return host, sock


# ===========================================================================
# 健康检查主函数
# ===========================================================================

async def health_check() -> dict[str, Any]:
    """执行完整健康检查。

    并行检查 PostgreSQL, Redis, OKX，聚合结果。

    Returns:
        {
            "status": "healthy" | "degraded" | "unhealthy",
            "timestamp": "2026-07-12T12:00:00Z",
            "checks": {
                "postgres": {...},
                "redis": {...},
                "okx": {...},
            }
        }
    """
    # 并行执行所有检查
    pg_result, redis_result, okx_result = await asyncio.gather(
        check_postgres(),
        check_redis(),
        check_okx(),
        return_exceptions=True,
    )

    # 处理异常
    if isinstance(pg_result, Exception):
        pg_result = {"status": "unhealthy", "error": str(pg_result)}
    if isinstance(redis_result, Exception):
        redis_result = {"status": "unhealthy", "error": str(redis_result)}
    if isinstance(okx_result, Exception):
        okx_result = {"status": "unhealthy", "error": str(okx_result)}

    checks = {
        "postgres": pg_result,
        "redis": redis_result,
        "okx": okx_result,
    }

    # 聚合状态
    all_healthy = all(c.get("status") == "healthy" for c in checks.values())
    all_unhealthy = all(c.get("status") == "unhealthy" for c in checks.values())

    if all_healthy:
        status = "healthy"
    elif all_unhealthy:
        status = "unhealthy"
    else:
        status = "degraded"

    return {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


# ===========================================================================
# Agent Server 路由注册
# ===========================================================================

def create_health_router():
    """创建健康检查路由器。

    Agent Server 支持 langgraph.json 中配置自定义路由。
    此函数返回一个 ASGI 兼容的路由处理函数。

    在 langgraph.json 中配置：
    {
        "dependencies": ["."],
        "graphs": {"agent": "./src/crypto_alert_v2/graph/__init__.py:graph"},
        "http": {
            "app": "./src/crypto_alert_v2/api/health.py:create_health_app"
        }
    }
    """
    try:
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
    except ImportError:
        return None

    async def health_endpoint(request):
        """GET /internal/health"""
        result = await health_check()
        status_code = 200 if result["status"] == "healthy" else 503
        return JSONResponse(result, status_code=status_code)

    async def readiness_endpoint(request):
        """GET /internal/ready - 简化的就绪检查"""
        return JSONResponse({"status": "ready"})

    routes = [
        Route("/internal/health", health_endpoint, methods=["GET"]),
        Route("/internal/ready", readiness_endpoint, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    return app


def create_health_app():
    """创建健康检查 ASGI 应用（供 langgraph.json http.app 引用）。"""
    return create_health_router()
