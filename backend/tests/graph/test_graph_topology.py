"""Graph 拓扑测试 - 验证 Graph 结构正确（Phase 1）。

测试范围（设计文档 17.1 节 - Graph Contract Test）：
- graph 是编译后的 CompiledGraph
- graph 有正确的 11 个节点（Phase 1 完整拓扑）
- graph 没有配置 checkpointer（Agent Server 自动注入）
- 条件路由函数存在且返回正确类型
"""

from crypto_alert_v2.graph.graph import graph


def test_graph_is_compiled():
    """graph 必须是编译后的 CompiledStateGraph，不是未编译的 StateGraph builder。"""
    # StateGraph.compile() 返回 CompiledStateGraph
    assert type(graph).__name__ == "CompiledStateGraph", (
        f"graph 应为 CompiledStateGraph，实际为 {type(graph).__name__}"
    )


def test_graph_has_all_phase1_nodes():
    """graph 包含 Phase 1 的所有 11 个节点。"""
    node_names = set(graph.nodes.keys())

    expected_nodes = {
        "bootstrap_run",
        "validate_request",
        "collect_market_snapshot",
        "research_events",
        "analyze_market",
        "validate_evidence",
        "apply_risk_policy",
        "build_final_result",
        "confirm_analysis",
        "commit_final_artifact",
        "complete_run",
    }

    missing = expected_nodes - node_names
    assert not missing, f"缺少 Phase 1 节点: {missing}"


def test_graph_does_not_have_old_phase0_nodes():
    """Phase 1 不应包含 Phase 0 的 agent_node（已拆分为 analyze_market + confirm_analysis）。"""
    node_names = set(graph.nodes.keys())
    assert "agent_node" not in node_names, "Phase 1 不应包含 Phase 0 的 agent_node"


def test_graph_has_no_checkpointer():
    """不配 checkpointer（设计文档约束：Agent Server 自动注入）。"""
    # builder.compile() 不传 checkpointer，graph.checkpointer 应为 None
    checkpointer = getattr(graph, "checkpointer", None)
    assert checkpointer is None, (
        f"graph 不应配置 checkpointer（Agent Server 自动注入），但发现: {checkpointer}"
    )


def test_graph_has_no_store():
    """不配 store（设计文档约束：Agent Server 自动注入）。"""
    store = getattr(graph, "store", None)
    assert store is None, (
        f"graph 不应配置 store（Agent Server 自动注入），但发现: {store}"
    )


def test_graph_is_invokable():
    """graph 可以被调用（有 invoke 和 ainvoke 方法）。"""
    assert hasattr(graph, "invoke"), "graph 缺少 invoke 方法"
    assert hasattr(graph, "ainvoke"), "graph 缺少 ainvoke 方法"


def test_build_graph_accepts_checkpointer():
    """build_graph 函数可以接受 checkpointer 参数（测试用）。"""
    from langgraph.checkpoint.memory import MemorySaver
    from crypto_alert_v2.graph.graph import build_graph

    graph_with_cp = build_graph(checkpointer=MemorySaver())
    assert graph_with_cp is not None
    assert type(graph_with_cp).__name__ == "CompiledStateGraph"
