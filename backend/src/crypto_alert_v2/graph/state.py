"""Graph 状态定义 - AnalysisState

按照 V2 设计文档 7.2 节定义所有状态字段。
Phase 0 使用 dict | None 占位复杂业务类型，后续阶段替换为 Pydantic Model。

设计原则（设计文档 7.2 节）：
- State 只保存节点间真正需要的数据
- 大对象（完整网页正文、Provider 原始 Response 等）不放入 State
- 只保存稳定 ID、摘要和校验后的结构
"""

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AnalysisState(TypedDict):
    """Canonical Graph 状态。

    所有节点间传递的数据都在这里定义。
    messages 使用 add_messages reducer 自动合并消息；
    progress_events / warnings / errors 使用 operator.add 做列表拼接（append-only）。
    """

    # 消息列表（Agent 对话历史，add_messages reducer 自动合并）
    messages: Annotated[list, add_messages]

    # 身份上下文（ActorContext：tenant_id, user_id, auth_mode）
    identity: dict[str, Any] | None

    # 分析请求（AnalysisRequest：symbol, horizon, query_text, notify）
    request: dict[str, Any] | None

    # 运行上下文 ID（RunContextIds：run_id, thread_id, tenant_id, user_id）
    run_context: dict[str, Any] | None

    # 市场快照（MarketSnapshot | null）
    market_snapshot: dict[str, Any] | None

    # 研究结果（ResearchBundle | null）
    research_bundle: dict[str, Any] | None

    # 专家发现列表（list[SpecialistFinding]）
    specialist_findings: list[dict[str, Any]]

    # 决策草稿（DecisionDraft | null）
    decision_draft: dict[str, Any] | None

    # 证据裁决（EvidenceVerdict | null）
    evidence_verdict: dict[str, Any] | None

    # 风险裁决（RiskVerdict | null）
    risk_verdict: dict[str, Any] | None

    # 最终结果（FinalAnalysisResult | null）
    final_result: dict[str, Any] | None

    # 通知计划（NotificationPlan | null）
    notification_plan: dict[str, Any] | None

    # HITL 审批结果（approve / reject / edit，confirm_analysis 节点写入）
    approval_result: dict[str, Any] | None

    # 阶段事件（append-only，operator.add 做列表拼接）
    progress_events: Annotated[list[dict[str, Any]], operator.add]

    # 警告（append-only）
    warnings: Annotated[list[dict[str, Any]], operator.add]

    # 分类错误（append-only）
    errors: Annotated[list[dict[str, Any]], operator.add]
