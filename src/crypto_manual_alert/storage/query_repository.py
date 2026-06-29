from __future__ import annotations

from typing import Any

from crypto_manual_alert.journal import Journal


class JournalQueryRepository:
    """面向 UI/API 的 Journal 查询门面。

    Journal 负责 SQLite 表和兼容迁移；Repository 负责把 UI 查询限制、脱敏边界
    和后续 PostgreSQL 替换点集中起来，避免路由层散落数据库细节。
    """

    def __init__(self, journal: Journal):
        self.journal = journal

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """返回最近运行摘要，并统一限制最大列表长度。"""

        return self.journal.list_traces(limit=self.normalize_limit(limit))

    def get_run_detail(self, trace_id: str, *, include_payloads: bool = False) -> dict[str, Any] | None:
        """返回单次运行详情，默认隐藏 LLM payload；复盘时可显式打开脱敏内容。"""

        return self.journal.get_trace_detail(trace_id, include_payloads=include_payloads)

    @staticmethod
    def normalize_limit(limit: int) -> int:
        """限制 UI 列表查询规模，避免误传大 limit 拖慢本地 SQLite。"""

        return max(1, min(int(limit), 100))
