"""结构化日志 - structlog 配置。

来源：V2技术设计缺口补充.md 第 9.1 节。

日志框架：structlog（结构化 JSON 日志）。

日志级别规范：
| 级别    | 使用场景                                                    |
|---------|-------------------------------------------------------------|
| ERROR   | 系统异常（DB 连接失败、Agent Server 不可用、未捕获异常）     |
| WARNING | 业务降级（数据缺失、搜索失败、通知失败、风控阻断）           |
| INFO    | 正常业务事件（Run 开始、阶段完成、Run 完成、HITL 中断）      |
| DEBUG   | 调试信息（LLM 输入/输出摘要、Tool 调用参数、State 变化）     |

禁止记录：API Key、Bark Key、Authorization、Cookie、完整 Prompt/Response。
"""

import sys
import uuid
from typing import Any

try:
    import structlog
except ImportError:
    # structlog 未安装时的降级处理
    structlog = None


# ===========================================================================
# 日志配置
# ===========================================================================

def configure_logging(json_output: bool = True) -> None:
    """配置 structlog。

    配置内容：
    1. contextvars 合并（correlation ID 注入）
    2. 日志级别添加
    3. ISO 时间戳
    4. JSON 格式渲染（生产）或 Console 渲染（开发）

    Args:
        json_output: True 使用 JSON 渲染（生产），False 使用 Console 渲染（开发）
    """
    if structlog is None:
        return

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO 级别
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """获取 structlog logger。

    Args:
        name: logger 名称（通常为模块名）

    Returns:
        structlog logger 实例
    """
    if structlog is None:
        return _FallbackLogger()
    return structlog.get_logger(name)


# ===========================================================================
# Correlation ID 注入
# ===========================================================================

def bind_request_context(
    request_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
) -> str:
    """注入请求上下文到 structlog contextvars。

    每次请求调用此函数，后续所有日志自动包含这些字段。

    Args:
        request_id: 请求 ID（不传则自动生成 UUID）
        tenant_id: 租户 ID
        user_id: 用户 ID
        thread_id: Thread ID
        run_id: Run ID

    Returns:
        生成的 request_id
    """
    if structlog is None:
        return request_id or str(uuid.uuid4())

    if not request_id:
        request_id = str(uuid.uuid4())

    kwargs: dict[str, str] = {"request_id": request_id}
    if tenant_id:
        kwargs["tenant_id"] = tenant_id
    if user_id:
        kwargs["user_id"] = user_id
    if thread_id:
        kwargs["thread_id"] = thread_id
    if run_id:
        kwargs["run_id"] = run_id

    structlog.contextvars.bind_contextvars(**kwargs)
    return request_id


def clear_request_context() -> None:
    """清除请求上下文。

    请求结束后调用，避免 contextvars 泄漏到下一个请求。
    """
    if structlog is None:
        return
    structlog.contextvars.clear_contextvars()


# ===========================================================================
# 敏感信息过滤器
# ===========================================================================

SENSITIVE_KEYS = frozenset({
    "api_key",
    "apikey",
    "openai_api_key",
    "tavily_api_key",
    "bark_key",
    "langsmith_api_key",
    "langfuse_secret_key",
    "authorization",
    "cookie",
    "password",
    "token",
    "secret",
})


def sanitize_log_data(data: dict[str, Any]) -> dict[str, Any]:
    """过滤敏感信息。

    将 API Key、Bark Key、Authorization 等敏感字段替换为 ***。
    """
    sanitized = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_KEYS:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)
        else:
            sanitized[key] = value
    return sanitized


# ===========================================================================
# 降级 Logger（structlog 未安装时使用）
# ===========================================================================

class _FallbackLogger:
    """structlog 未安装时的降级 logger。

    使用标准 print 输出，保持与 structlog 相同的接口。
    """

    def _log(self, level: str, event: str, **kwargs: Any) -> None:
        import json
        from datetime import datetime, timezone

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **sanitize_log_data(kwargs),
        }
        print(json.dumps(entry, ensure_ascii=False), file=sys.stderr)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log("debug", event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._log("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._log("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._log("error", event, **kwargs)

    def bind(self, **kwargs: Any) -> "_FallbackLogger":
        """返回自身（简化实现）。"""
        return self


# ===========================================================================
# 模块级初始化
# ===========================================================================

# 自动配置（模块导入时执行）
configure_logging(json_output=True)
