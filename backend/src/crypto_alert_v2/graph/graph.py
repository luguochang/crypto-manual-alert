"""Canonical StateGraph - V2 唯一顶层图（Phase 1 完整拓扑）。

设计文档 7.1 节：全系统只允许一个生产主图。
设计文档 V2技术设计缺口补充.md 第一节：完整拓扑定义。

关键约束（设计文档 7.1 节 + 评审建议第 3 条）：
- graph = builder.compile()，不配 checkpointer（Agent Server 自动注入）
- 不配 store（Agent Server 自动注入）

Phase 1 拓扑（11 节点）：

    START
      |
      v
    bootstrap_run
      |
      v
    validate_request
      |
      v (conditional: errors?)
      |-- [errors] --> complete_run (blocked) --> END
      |-- [ok]     --> [collect_market_snapshot, research_events] (并行)
                          |                    |
                          +--------+-----------+
                                   |
                                   v
                          analyze_market
                                   |
                                   v
                          validate_evidence
                                   |
                                   v
                          apply_risk_policy
                                   |
                                   v (conditional: allowed?)
                          |-- [blocked] --> complete_run (blocked) --> END
                          |-- [ok]      --> build_final_result
                                               |
                                               v
                                          confirm_analysis (HITL interrupt)
                                               |
                                               v (conditional: approval?)
                                          |-- [approve] --> commit_final_artifact --> complete_run --> END
                                          |-- [edit]    --> build_final_result (重新构建)
                                          |-- [reject]  --> complete_run (blocked) --> END
"""

from langgraph.graph import END, START, StateGraph

from crypto_alert_v2.graph.nodes.analyze_market import analyze_market
from crypto_alert_v2.graph.nodes.apply_risk_policy import apply_risk_policy
from crypto_alert_v2.graph.nodes.bootstrap import bootstrap_run
from crypto_alert_v2.graph.nodes.build_final_result import build_final_result
from crypto_alert_v2.graph.nodes.collect_market_snapshot import collect_market_snapshot
from crypto_alert_v2.graph.nodes.commit_final_artifact import commit_final_artifact
from crypto_alert_v2.graph.nodes.complete import complete_run
from crypto_alert_v2.graph.nodes.confirm_analysis import confirm_analysis
from crypto_alert_v2.graph.nodes.research_events import research_events
from crypto_alert_v2.graph.nodes.validate_evidence import validate_evidence
from crypto_alert_v2.graph.nodes.validate_request import validate_request
from crypto_alert_v2.graph.state import AnalysisState


# ===========================================================================
# 条件路由函数（设计文档 V2技术设计缺口补充.md 第 1.3 节）
# ===========================================================================

def route_after_validation(state: AnalysisState) -> str | list[str]:
    """validate_request 后的条件路由。

    - 有 errors：路由到 complete_run（blocked 路径）
    - 无 errors：路由到并行节点 [collect_market_snapshot, research_events]

    返回 list[str] 时 LangGraph 会并行执行多个节点（barrier 语义在汇聚节点生效）。
    """
    if state.get("errors"):
        return "complete_run"
    return ["collect_market_snapshot", "research_events"]


def route_after_risk(state: AnalysisState) -> str:
    """apply_risk_policy 后的条件路由。

    - risk_verdict.allowed=False：路由到 complete_run（blocked 路径）
    - risk_verdict.allowed=True：路由到 build_final_result
    """
    risk = state.get("risk_verdict") or {}
    if not risk.get("allowed", False):
        return "complete_run"
    return "build_final_result"


def route_after_confirm(state: AnalysisState) -> str:
    """confirm_analysis 后的条件路由（HITL 响应）。

    - approve：路由到 commit_final_artifact
    - edit：路由到 build_final_result（重新构建结果）
    - reject：路由到 complete_run（blocked 路径）
    """
    approval = state.get("approval_result") or {}
    action = approval.get("action", "reject")

    if action == "approve":
        return "commit_final_artifact"
    elif action == "edit":
        return "build_final_result"
    else:  # reject
        return "complete_run"


# ===========================================================================
# Graph 构建
# ===========================================================================

def build_graph(checkpointer=None):
    """构建 StateGraph。

    生产环境不传 checkpointer（Agent Server 自动注入）。
    测试环境可传入 MemorySaver 以测试 interrupt/resume（Agent Server 外无 checkpointer 时
    interrupt() 会报错）。

    Phase 1 完整拓扑：11 节点 + 并行边 + 条件路由。
    """
    builder = StateGraph(AnalysisState)

    # 注册所有节点
    builder.add_node("bootstrap_run", bootstrap_run)
    builder.add_node("validate_request", validate_request)
    builder.add_node("collect_market_snapshot", collect_market_snapshot)
    builder.add_node("research_events", research_events)
    builder.add_node("analyze_market", analyze_market)
    builder.add_node("validate_evidence", validate_evidence)
    builder.add_node("apply_risk_policy", apply_risk_policy)
    builder.add_node("build_final_result", build_final_result)
    builder.add_node("confirm_analysis", confirm_analysis)
    builder.add_node("commit_final_artifact", commit_final_artifact)
    builder.add_node("complete_run", complete_run)

    # === 线性边 ===
    builder.add_edge(START, "bootstrap_run")
    builder.add_edge("bootstrap_run", "validate_request")

    # === validate_request 后条件路由 ===
    # 返回 list 时并行执行，返回 str 时单节点
    builder.add_conditional_edges(
        "validate_request",
        route_after_validation,
    )

    # === collect_market_snapshot 和 research_events 并行，汇聚到 analyze_market ===
    # LangGraph 原生支持：两条边从不同节点指向同一节点时，目标节点等待所有前置完成（barrier）
    builder.add_edge("collect_market_snapshot", "analyze_market")
    builder.add_edge("research_events", "analyze_market")

    # === 分析 -> 证据 -> 风控 ===
    builder.add_edge("analyze_market", "validate_evidence")
    builder.add_edge("validate_evidence", "apply_risk_policy")

    # === apply_risk_policy 后条件路由 ===
    builder.add_conditional_edges(
        "apply_risk_policy",
        route_after_risk,
    )

    # === build_final_result -> confirm_analysis ===
    builder.add_edge("build_final_result", "confirm_analysis")

    # === confirm_analysis 后条件路由（HITL 响应）===
    builder.add_conditional_edges(
        "confirm_analysis",
        route_after_confirm,
    )

    # === commit_final_artifact -> complete_run ===
    builder.add_edge("commit_final_artifact", "complete_run")

    # === complete_run -> END ===
    builder.add_edge("complete_run", END)

    # 编译：生产环境不配 checkpointer/store（Agent Server 自动注入）
    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


# 导出编译后的 graph（不配 checkpointer，Agent Server 自动注入）
# langgraph.json 指向 graph/__init__.py:graph
graph = build_graph()
