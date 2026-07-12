"""complete_run 节点 - 完成节点（Phase 1）。

设计文档 7.3 节节点 11：固化状态、观测引用和结束时间。

Phase 1 实现：
- 标记运行完成状态
- 记录最终状态（completed / blocked / failed）
- 追加 progress_events

生产环境额外需要：
- 固化结束时间（agent_runs.completed_at）
- 写入观测 ID（langsmith_run_id, langfuse_trace_id）
- 通知由独立 Outbox worker 投递（设计文档 7.3 节）
"""

from datetime import datetime, timezone
from typing import Any

from crypto_alert_v2.graph.state import AnalysisState


def complete_run(state: AnalysisState) -> dict[str, Any]:
    """完成节点：标记运行完成。

    根据 state 中的 errors 和 approval_result 决定最终状态：
    - 无错误 + approved -> completed
    - 有 errors -> failed
    - rejected/blocked -> blocked
    """
    errors = state.get("errors", [])
    approval_result = state.get("approval_result") or {}
    final_result = state.get("final_result") or {}

    # 确定最终状态
    if errors:
        final_status = "failed"
    elif approval_result.get("action") == "reject":
        final_status = "blocked"
    elif final_result.get("status") == "blocked":
        final_status = "blocked"
    else:
        final_status = "completed"

    # 更新 final_result 状态
    updated_final_result = {
        **final_result,
        "status": final_status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "final_result": updated_final_result,
        "progress_events": [
            {
                "stage": "complete",
                "status": final_status,
                "completed_at": updated_final_result["completed_at"],
            },
        ],
    }
