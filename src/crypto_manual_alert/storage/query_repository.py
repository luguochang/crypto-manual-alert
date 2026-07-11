from __future__ import annotations

from typing import Any

from crypto_manual_alert.config import Config
from crypto_manual_alert.storage.journal import Journal
from crypto_manual_alert.storage.result_review import build_result_review


class JournalQueryRepository:
    """面向 UI/API 的 Journal 查询门面。

    Journal 负责 SQLite 表和兼容迁移；Repository 负责把 UI 查询限制、脱敏边界
    和后续 PostgreSQL 替换点集中起来，避免路由层散落数据库细节。
    """

    def __init__(self, journal: Journal, outcome_store: Any | None = None, config: Config | None = None):
        self.journal = journal
        self.outcome_store = outcome_store
        self.config = config

    def list_runs(
        self,
        limit: int = 20,
        *,
        offset: int = 0,
        status: str | None = None,
        symbol: str | None = None,
        allowed: bool | None = None,
    ) -> list[dict[str, Any]]:
        """返回最近运行摘要，并统一限制最大列表长度。"""

        runs = self.journal.list_traces(
            limit=self.normalize_limit(limit),
            offset=self.normalize_offset(offset),
            status=self.normalize_status(status),
            symbol=self.normalize_symbol(symbol),
            allowed=allowed,
            include_business_summary=True,
            projection_config=self.config,
        )
        for run in runs:
            run["result_review"] = build_result_review(
                {
                    "trace": run,
                    "plan_run": {"plan_id": run.get("final_plan_id")},
                },
                self.outcome_store,
            )
        return runs

    def get_run_detail(self, trace_id: str, *, include_payloads: bool = False) -> dict[str, Any] | None:
        """返回单次运行详情，默认隐藏 LLM payload；复盘时可显式打开脱敏内容。"""

        detail = self.journal.get_trace_detail(
            trace_id,
            include_payloads=include_payloads,
            projection_config=self.config,
        )
        if detail is None:
            return None
        detail["result_review"] = build_result_review(detail, self.outcome_store)
        return detail

    @staticmethod
    def normalize_limit(limit: int) -> int:
        """限制 UI 列表查询规模，避免误传大 limit 拖慢本地 SQLite。"""

        return max(1, min(int(limit), 100))

    @staticmethod
    def normalize_offset(offset: int) -> int:
        """限制 UI 分页偏移，避免负数 offset 产生不稳定查询。"""

        return max(0, int(offset))

    @staticmethod
    def normalize_status(status: str | None) -> str | None:
        """空字符串和 all 不参与过滤，方便前端用 URL 参数表达全部状态。"""

        if status is None:
            return None
        normalized = status.strip().lower()
        return None if normalized in {"", "all"} else normalized

    @staticmethod
    def normalize_symbol(symbol: str | None) -> str | None:
        """空字符串不参与过滤；非空时由 Journal 做大小写无关模糊匹配。"""

        if symbol is None:
            return None
        normalized = symbol.strip()
        return normalized or None
