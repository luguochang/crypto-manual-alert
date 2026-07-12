"""State 测试 - 验证 AnalysisState 可以正确创建和更新。

测试范围（设计文档 17.1 节 - 领域单元测试）：
- State 字段完整性（设计文档 7.2 节所有字段）
- add_messages reducer 正确合并消息
- append-only reducer（progress_events / warnings / errors）正确拼接
"""

import operator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from crypto_alert_v2.graph.state import AnalysisState


def test_state_creation(sample_state):
    """测试 State 可以正确创建，所有字段有合理初始值。"""
    assert sample_state["messages"] == []
    assert sample_state["identity"] is None
    assert sample_state["request"] is None
    assert sample_state["run_context"] is None
    assert sample_state["market_snapshot"] is None
    assert sample_state["research_bundle"] is None
    assert sample_state["specialist_findings"] == []
    assert sample_state["decision_draft"] is None
    assert sample_state["evidence_verdict"] is None
    assert sample_state["risk_verdict"] is None
    assert sample_state["final_result"] is None
    assert sample_state["notification_plan"] is None
    assert sample_state["approval_result"] is None
    assert sample_state["progress_events"] == []
    assert sample_state["warnings"] == []
    assert sample_state["errors"] == []


def test_state_has_all_design_fields():
    """测试 State 包含设计文档 7.2 节的所有字段。"""
    fields = set(AnalysisState.__annotations__.keys())

    expected_fields = {
        "messages",
        "identity",
        "request",
        "run_context",
        "market_snapshot",
        "research_bundle",
        "specialist_findings",
        "decision_draft",
        "evidence_verdict",
        "risk_verdict",
        "final_result",
        "notification_plan",
        "approval_result",
        "progress_events",
        "warnings",
        "errors",
    }

    missing = expected_fields - fields
    assert not missing, f"State 缺少设计文档定义的字段: {missing}"


def test_messages_reducer_appends():
    """测试 add_messages reducer 正确合并消息列表。"""
    old_messages = [HumanMessage(content="分析 BTC-USDT-SWAP")]
    new_messages = [AIMessage(content="分析完成")]

    result = add_messages(old_messages, new_messages)

    assert len(result) == 2
    assert result[0].content == "分析 BTC-USDT-SWAP"
    assert result[1].content == "分析完成"


def test_append_only_reducer_concatenates():
    """测试 append-only reducer（operator.add）正确拼接列表。

    progress_events、warnings、errors 都使用 operator.add 作为 reducer，
    节点返回的列表会被拼接到已有列表末尾。
    """
    old_events = [{"stage": "bootstrap", "status": "completed"}]
    new_events = [{"stage": "agent", "status": "completed"}]

    result = operator.add(old_events, new_events)

    assert len(result) == 2
    assert result[0]["stage"] == "bootstrap"
    assert result[1]["stage"] == "agent"


def test_append_only_reducer_empty_list():
    """测试 append-only reducer 对空列表的处理。"""
    old = []
    new = [{"warning": "test"}]

    result = operator.add(old, new)

    assert len(result) == 1


def test_state_field_types():
    """测试 State 字段类型注解正确（Phase 0 用 dict | None 占位复杂类型）。"""
    from typing import get_args

    import operator

    annotations = AnalysisState.__annotations__

    # messages 使用 add_messages reducer（Annotated 第二个元素是 reducer 函数）
    msg_args = get_args(annotations["messages"])
    assert len(msg_args) >= 2, "messages 应有 Annotated reducer"
    assert callable(msg_args[1]), "messages 的 reducer 应是可调用函数"

    # progress_events / warnings / errors 使用 operator.add reducer
    for field in ["progress_events", "warnings", "errors"]:
        field_args = get_args(annotations[field])
        assert len(field_args) >= 2, f"{field} 应有 Annotated reducer"
        assert operator.add in field_args, f"{field} 应使用 operator.add reducer"
