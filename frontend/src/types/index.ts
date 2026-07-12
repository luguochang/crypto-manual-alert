/**
 * Phase 0 基础类型定义
 * Phase 1 会补全完整的 Graph State 类型
 */

/**
 * 分析状态 - 对应 Agent 的 Graph State
 * Phase 0 仅定义基础字段，后续阶段逐步补全
 */
export interface AnalysisState {
  /** 消息列表（Agent 对话历史） */
  messages: BaseMessage[];
  /** 线程 ID（LangGraph 会话标识） */
  thread_id?: string;
  /** 市场快照（当前行情数据） */
  market_snapshot?: MarketSnapshot;
  /** 决策草稿（Agent 生成的提醒决策） */
  decision_draft?: DecisionDraft;
  // ... Phase 1 会补全更多字段
}

/**
 * 基础消息类型
 */
export interface BaseMessage {
  id?: string;
  role: "human" | "ai" | "system" | "tool";
  content: string;
  name?: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

/**
 * 工具调用
 */
export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

/**
 * 市场快照（Phase 1 补全详细字段）
 */
export interface MarketSnapshot {
  symbol?: string;
  price?: number;
  timestamp?: string;
  [key: string]: unknown;
}

/**
 * 决策草稿（Phase 1 补全详细字段）
 */
export interface DecisionDraft {
  alert_type?: string;
  message?: string;
  confidence?: number;
  [key: string]: unknown;
}

/**
 * HITL 中断类型
 */
export interface InterruptInfo {
  /** 中断类型标识 */
  type?: string;
  /** 中断时的描述信息 */
  description?: string;
  /** 中断携带的数据 */
  value?: unknown;
}
