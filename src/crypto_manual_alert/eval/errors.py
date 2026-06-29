from __future__ import annotations


class EvalRunError(RuntimeError):
    """Eval 运行期错误，API/CLI 会把它映射成稳定错误响应。"""

    def __init__(self, message: str, *, code: str = "eval_run_failed"):
        super().__init__(message)
        self.code = code
