from __future__ import annotations

import os


DEFAULT_FORBIDDEN_ENV_NAMES = (
    "OKX_API_KEY",
    "OKX_API_SECRET",
    "OKX_API_PASSPHRASE",
    "OKX_TRADE_API_KEY",
    "OKX_WITHDRAW_API_KEY",
)


class EvalSafetyError(ValueError):
    """Eval 安全边界错误：当前环境不允许启动旁路测评。"""

    def __init__(self, message: str, *, code: str = "eval_forbidden_secret_env"):
        super().__init__(message)
        self.code = code


def assert_eval_environment_safe(forbidden_env_names: list[str] | tuple[str, ...] | None = None) -> None:
    """检查 eval 运行环境，避免带着交易/提现密钥进入旁路测评。"""

    names = _forbidden_names(forbidden_env_names)
    present = [name for name in names if os.getenv(name)]
    if present:
        raise EvalSafetyError(f"forbidden environment variable is set during eval: {', '.join(present)}")


def _forbidden_names(names: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    configured = tuple(name for name in (names or ()) if name)
    merged = [*DEFAULT_FORBIDDEN_ENV_NAMES, *configured]
    return tuple(dict.fromkeys(merged))
