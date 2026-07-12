/**
 * 分析相关类型定义
 * 来源：15-frontend-and-config-management.md 第一节
 *
 * 这些类型对应后端 domain/models.py 的 Pydantic 模型，
 * 但做了前端友好的转换（如 direction 从 main_action 派生）。
 */

/** 市场快照 */
export interface MarketSnapshot {
  symbol: string;
  ticker: {
    last: number;
    bid: number;
    ask: number;
    vol_24h: number;
  };
  mark_price: number;
  index_price: number;
  funding_rate: number;
  open_interest: number;
  order_book: {
    bids: [number, number][]; // [price, size]
    asks: [number, number][];
  };
  candles: Array<{
    ts: string;
    o: number;
    h: number;
    l: number;
    c: number;
    vol: number;
  }>;
  data_fetched_at: string;
  source_level: "exchange_native" | "web_derived";
  unavailable_fields: string[];
}

/** 分析结果 - 对应后端 MarketAnalysis */
export interface AnalysisResult {
  main_action:
    | "open_long"
    | "open_short"
    | "hold_long"
    | "hold_short"
    | "close_long"
    | "close_short"
    | "flip_long_to_short"
    | "flip_short_to_long"
    | "trigger_long"
    | "trigger_short"
    | "no_trade";
  direction: "long" | "short" | "neutral";
  symbol: string;
  horizon: string;
  reference_price: number;
  entry_trigger: number | null;
  stop_price: number | null;
  target_1: number | null;
  target_2: number | null;
  probability: number;
  position_size_class: "light" | "standard" | "heavy";
  max_leverage: number;
  risk_pct: number;
  regime: "risk_on" | "risk_off" | "event_compression" | "surprise_repricing";
  factor_scores: Record<string, number>;
  total_score: number;
  root_cause_chain: string[];
  why_not_opposite: string;
  invalidation: string;
  unavailable_data: string[];
  manual_execution_required: boolean;
  expires_at: string;
}

/** 证据项 */
export interface EvidenceItem {
  source_type: "web_search" | "exchange_native" | "official";
  source_url: string | null;
  source_title: string | null;
  published_at: string | null;
  fetched_at: string;
  summary: string;
  relevance_score: number;
  symbol: string | null;
}

/** 风险门禁结果 - 对应后端 RiskVerdict */
export interface RiskVerdict {
  allowed: boolean;
  blocked_reasons: string[];
  warnings: string[];
  confidence_cap: number;
}

/** HITL 中断数据 */
export interface InterruptData {
  type: "analysis_confirmation" | "notification_approval";
  data: AnalysisResult;
}

/** Thread 摘要 */
export interface ThreadSummary {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string;
  status: "idle" | "running" | "awaiting_confirmation" | "completed";
}
