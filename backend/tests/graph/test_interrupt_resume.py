"""Interrupt / Resume 测试 - 验证 HITL 中断和恢复（Phase 1）。

测试范围（设计文档 17.1 节 - Graph Contract Test + 第 12 节 HITL）：
- interrupt() 可以暂停执行（在 confirm_analysis 节点）
- Command(resume=...) 可以恢复执行
- 恢复后 graph 能完成到 END

注意：
1. interrupt() 需要 checkpointer 才能工作。
   生产环境由 Agent Server 自动注入 checkpointer，测试环境使用 MemorySaver。
2. Phase 1 所有节点为 sync，使用 sync invoke 测试。
   Python 3.10 下 sync invoke + sync 节点确保 interrupt() 正常工作。
3. 测试环境无 OKX/OpenAI/Tavily API，节点会降级处理：
   - collect_market_snapshot: 网络失败 -> market_snapshot=None
   - research_events: 无 Tavily key -> 空 bundle
   - analyze_market: 无 OpenAI key -> 降级 no_trade
4. no_trade 不在 OPENING_ACTIONS 中，风控规则不会阻断，graph 能到达 confirm_analysis 的 interrupt。
"""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from crypto_alert_v2.graph.graph import build_graph


@pytest.fixture
def graph_with_checkpointer():
    """带 MemorySaver 的 graph（测试 interrupt 需要 checkpointer）。

    生产环境的 graph 不配 checkpointer（Agent Server 自动注入）。
    测试环境需要 MemorySaver 才能测试 interrupt/resume。
    """
    return build_graph(checkpointer=MemorySaver())


def test_interrupt_pauses_execution(graph_with_checkpointer):
    """测试 interrupt() 可以暂停执行。

    调用 graph 后应该暂停在 confirm_analysis 的 interrupt()，
    不应到达 complete_run（final_result 不应被设置）。
    """
    config = {"configurable": {"thread_id": "test-interrupt-1"}}

    # 初始调用，应该暂停在 confirm_analysis 的 interrupt()
    result = graph_with_checkpointer.invoke(
        {"messages": [HumanMessage(content="分析 BTC 4h 趋势")]},
        config=config,
    )

    # 验证执行被暂停：state.next 有待执行的节点
    state = graph_with_checkpointer.get_state(config)
    assert state.next is not None
    assert len(state.next) > 0, "Graph 应该被 interrupt() 暂停，但 state.next 为空"

    # complete_run 尚未执行，final_result 的 status 不应是 completed
    final = result.get("final_result")
    if final is not None:
        # build_final_result 可能已设置 final_result，但 complete_run 未执行
        assert final.get("status") != "completed", (
            "interrupt 前 complete_run 不应执行"
        )


def test_command_resume_completes_execution(graph_with_checkpointer):
    """测试 Command(resume=...) 可以恢复执行并完成到 END。"""
    config = {"configurable": {"thread_id": "test-resume-1"}}

    # 第一次调用，暂停在 interrupt
    graph_with_checkpointer.invoke(
        {"messages": [HumanMessage(content="分析 BTC 4h 趋势")]},
        config=config,
    )

    # 验证确实被暂停了
    state_before = graph_with_checkpointer.get_state(config)
    assert len(state_before.next) > 0, "Graph 应该处于暂停状态"

    # 恢复执行（approve）
    result = graph_with_checkpointer.invoke(
        Command(resume={"action": "approve"}),
        config=config,
    )

    # 验证执行完成
    assert result is not None

    # complete_run 应已执行，final_result 应被设置
    final = result.get("final_result")
    assert final is not None, "恢复后 final_result 应被设置"
    assert final.get("status") in ("completed", "blocked", "failed"), (
        f"final_result 状态应为 completed/blocked/failed，实际为 {final.get('status')}"
    )

    # Graph 应到达 END，state.next 为空
    state_after = graph_with_checkpointer.get_state(config)
    assert state_after.next is not None
    assert len(state_after.next) == 0, "Graph 应已完成，state.next 应为空"


def test_resume_preserves_bootstrap_state(graph_with_checkpointer):
    """测试恢复后 bootstrap_run 注入的状态仍然存在。

    设计文档 9.1 节：开发身份在 bootstrap_run 注入，
    后续节点和恢复执行都应能看到这些值。
    """
    config = {"configurable": {"thread_id": "test-preserve-1"}}

    # 第一次调用
    graph_with_checkpointer.invoke(
        {"messages": [HumanMessage(content="分析 BTC 4h 趋势")]},
        config=config,
    )

    # 恢复执行
    result = graph_with_checkpointer.invoke(
        Command(resume={"action": "approve"}),
        config=config,
    )

    # bootstrap_run 注入的 identity 和 run_context 应仍然存在
    assert result.get("identity") is not None, "identity 应被 bootstrap_run 设置"
    assert result["identity"].get("tenant_id") is not None
    assert result["identity"].get("user_id") is not None

    assert result.get("run_context") is not None, "run_context 应被 bootstrap_run 设置"
    assert result["run_context"].get("run_id") is not None


def test_reject_routes_to_blocked(graph_with_checkpointer):
    """测试 reject 响应路由到 blocked 路径（complete_run）。"""
    config = {"configurable": {"thread_id": "test-reject-1"}}

    # 第一次调用，暂停在 interrupt
    graph_with_checkpointer.invoke(
        {"messages": [HumanMessage(content="分析 BTC 4h 趋势")]},
        config=config,
    )

    # 拒绝
    result = graph_with_checkpointer.invoke(
        Command(resume={"action": "reject"}),
        config=config,
    )

    # 应到达 complete_run，状态应为 blocked
    final = result.get("final_result")
    assert final is not None
    assert final.get("status") == "blocked", (
        f"reject 后状态应为 blocked，实际为 {final.get('status')}"
    )

    # Graph 应到达 END
    state_after = graph_with_checkpointer.get_state(config)
    assert len(state_after.next) == 0, "Graph 应已完成"
