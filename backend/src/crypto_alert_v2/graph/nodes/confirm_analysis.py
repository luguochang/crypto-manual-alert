"""confirm_analysis 节点 - HITL 人工确认。

设计文档 7.3 节节点 9 + 第 12 节 HITL：暂停等待人工确认分析结果。

关键设计（设计文档第 12 节）：
1. 使用 interrupt() 暂停 Graph
2. interrupt() 前的操作必须是幂等的（节点恢复时从头重新执行）
3. interrupt() 返回 resume 值（Command(resume=...) 传入的值）
4. route_after_confirm 根据返回值决定路由

三种响应：
- approve：确认分析结果，路由到 commit_final_artifact
- edit：编辑后重新构建，路由到 build_final_result
- reject：拒绝，路由到 blocked 路径
"""

from typing import Any

from langgraph.types import interrupt

from crypto_alert_v2.graph.state import AnalysisState


def confirm_analysis(state: AnalysisState) -> dict[str, Any]:
    """HITL 人工确认节点。

    使用 interrupt() 暂停 Graph，等待用户确认。
    interrupt() 的 payload 包含分析摘要供前端渲染确认 UI。

    注意（设计文档第 12 节）：
    - interrupt() 的节点恢复时会从头重新执行
    - interrupt() 前禁止非幂等副作用
    - 此节点只读 state，不修改任何外部状态

    Python 3.10 兼容性：
    - 节点为 sync，确保 interrupt() 在 Python 3.10 下正常工作
    - 生产环境使用 Python 3.12（Dockerfile），sync 节点同样兼容
    """
    final_result = state.get("final_result") or {}

    # 构建中断 payload（前端渲染确认 UI 用）
    interrupt_payload = {
        "type": "analysis_review",
        "summary": {
            "symbol": final_result.get("instrument"),
            "action": final_result.get("main_action"),
            "regime": final_result.get("regime"),
            "probability": final_result.get("probability"),
            "entry_trigger": final_result.get("entry_trigger"),
            "stop_price": final_result.get("stop_price"),
            "target_1": final_result.get("target_1"),
            "target_2": final_result.get("target_2"),
            "risk_pct": final_result.get("risk_pct"),
            "max_leverage": final_result.get("max_leverage"),
            "total_score": final_result.get("total_score"),
            "root_cause_chain": final_result.get("root_cause_chain", []),
            "why_not_opposite": final_result.get("why_not_opposite"),
            "invalidation": final_result.get("invalidation"),
            "expires_at": final_result.get("expires_at"),
            "risk_allowed": final_result.get("risk_allowed"),
            "risk_warnings": final_result.get("risk_warnings", []),
            "unavailable_data": final_result.get("unavailable_data", []),
        },
        "options": ["approve", "edit", "reject"],
        "reminder": "系统不会自动下单，确认后请在 OKX App 手动执行。",
    }

    # interrupt() 暂停 Graph，返回 payload 给调用方
    # 恢复时（Command(resume=...)），interrupt() 返回 resume 值
    approval = interrupt(interrupt_payload)

    # 处理 resume 值
    # approval 格式：{"action": "approve"|"edit"|"reject", "edits": {...}}
    if isinstance(approval, dict):
        action = approval.get("action", "reject")
    else:
        action = str(approval)

    return {
        "approval_result": {"action": action, "edits": approval.get("edits") if isinstance(approval, dict) else None},
        "progress_events": [
            {
                "stage": "confirm_analysis",
                "status": "completed",
                "approval_action": action,
            },
        ],
    }
