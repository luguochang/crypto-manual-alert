from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from crypto_manual_alert.research_pipeline import SearchResult


@dataclass(frozen=True)
class FixtureShadowToolExecutor:
    """Offline shadow tool executor for LLM worker audit fixtures.

    It supports deterministic web_search fixtures only. It does not access the
    network, write journals, send notifications, or return raw snippets to
    worker contributions.
    """

    results_by_query: dict[str, list[SearchResult]]

    def execute(
        self,
        *,
        agent_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if tool_name != "web_search":
            return _failed_tool_result(
                tool_name=tool_name,
                error_type="ToolNotSupported",
                error_message=f"unsupported shadow tool: {tool_name}",
            )
        query = str(arguments.get("query") or "").strip()
        if not query:
            return _failed_tool_result(
                tool_name=tool_name,
                error_type="ToolArgumentError",
                error_message="web_search requires a non-empty query",
            )

        results = list(self.results_by_query.get(query, []))
        return {
            "tool_name": tool_name,
            "status": "ok",
            "result_ref": f"shadow_tool:web_search:{_stable_ref(agent_name, query)}",
            "result_count": len(results),
            "source_type": "fixture",
            "result_refs": [
                {
                    "title": result.title,
                    "url": result.url,
                    "source": result.source,
                    "snippet_ref": f"shadow_tool.web_search.{agent_name}[{index}].snippet_redacted",
                }
                for index, result in enumerate(results)
            ],
        }


def _failed_tool_result(*, tool_name: str, error_type: str, error_message: str) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "status": "failed",
        "source_type": "fixture",
        "error_type": error_type,
        "error_message": error_message,
    }


def _stable_ref(agent_name: str, query: str) -> str:
    payload = json.dumps({"agent_name": agent_name, "query": query}, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]
