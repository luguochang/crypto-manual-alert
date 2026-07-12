"use client";

import { useStream } from "@langchain/react";
import { useState, type FormEvent, useCallback, useMemo } from "react";
import type { AnalysisState, InterruptInfo } from "@/types";
import {
  type AnalysisResult,
  type EvidenceItem,
  type MarketSnapshot,
  type RiskVerdict,
  type ThreadSummary,
} from "@/types/analysis";
import { AnalysisResultCard } from "@/components/AnalysisResultCard";
import { MarketSnapshot as MarketSnapshotPanel } from "@/components/MarketSnapshot";
import { EvidenceTimeline } from "@/components/EvidenceTimeline";
import { RiskInspector } from "@/components/RiskInspector";

/**
 * Work 页面 - Phase 1 核心工作界面
 *
 * 三栏布局：
 * - 左栏：Thread 列表 + 新建按钮
 * - 中栏：对话时间线 + 分析结论卡片 + HITL 确认/拒绝/编辑按钮
 * - 右栏：行情快照 + 证据列表 + 风险门禁
 *
 * useStream 是唯一状态源，连接 Agent Server。
 * Thread 列表使用本地状态管理（Phase 1 简化，后续可接入 API）。
 */

// ===========================================================================
// 辅助函数
// ===========================================================================

/** 从 main_action 派生方向 */
function deriveDirection(action: string | undefined): "long" | "short" | "neutral" {
  if (!action) return "neutral";
  const lower = action.toLowerCase();
  if (lower.includes("long") && !lower.includes("flip_long_to_short") && !lower.includes("close_long")) {
    if (lower === "close_long" || lower === "flip_long_to_short") return "short";
    return "long";
  }
  if (lower.includes("short") && !lower.includes("flip_short_to_long") && !lower.includes("close_short")) {
    if (lower === "close_short" || lower === "flip_short_to_long") return "long";
    return "short";
  }
  // Special cases
  if (lower === "close_long" || lower === "flip_long_to_short") return "short";
  if (lower === "close_short" || lower === "flip_short_to_long") return "long";
  return "neutral";
}

/** 从后端 state 提取 AnalysisResult */
function extractAnalysisResult(values: Record<string, unknown> | undefined): AnalysisResult | null {
  if (!values) return null;

  // 尝试从 final_result 或 decision_draft 获取
  const raw = (values.final_result ?? values.decision_draft ?? values.market_analysis) as
    | Record<string, unknown>
    | undefined
    | null;

  if (!raw || typeof raw !== "object") return null;

  const main_action = (raw.main_action as string) ?? "no_trade";
  const expires_in_seconds = (raw.expires_in_seconds as number) ?? 90;

  // 计算过期时间
  const createdAt = (raw.created_at as string) ?? new Date().toISOString();
  const expiresAt = new Date(
    new Date(createdAt).getTime() + expires_in_seconds * 1000
  ).toISOString();

  return {
    main_action: main_action as AnalysisResult["main_action"],
    direction: deriveDirection(main_action),
    symbol: (raw.instrument as string) ?? "",
    horizon: (raw.horizon as string) ?? "",
    reference_price: (raw.reference_price as number) ?? 0,
    entry_trigger: (raw.entry_trigger as number | null) ?? null,
    stop_price: (raw.stop_price as number | null) ?? null,
    target_1: (raw.target_1 as number | null) ?? null,
    target_2: (raw.target_2 as number | null) ?? null,
    probability: (raw.probability as number) ?? 0,
    position_size_class: (raw.position_size_class as AnalysisResult["position_size_class"]) ?? "standard",
    max_leverage: (raw.max_leverage as number) ?? 1,
    risk_pct: (raw.risk_pct as number) ?? 0,
    regime: (raw.regime as AnalysisResult["regime"]) ?? "risk_off",
    factor_scores: (raw.factor_scores as Record<string, number>) ?? {},
    total_score: (raw.total_score as number) ?? 0,
    root_cause_chain: (raw.root_cause_chain as string[]) ?? [],
    why_not_opposite: (raw.why_not_opposite as string) ?? "",
    invalidation: (raw.invalidation as string) ?? "",
    unavailable_data: (raw.unavailable_data as string[]) ?? [],
    manual_execution_required: (raw.manual_execution_required as boolean) ?? true,
    expires_at: expiresAt,
  };
}

/** 从后端 state 提取 MarketSnapshot */
function extractMarketSnapshot(values: Record<string, unknown> | undefined): MarketSnapshot | null {
  if (!values) return null;
  const raw = values.market_snapshot as Record<string, unknown> | undefined;
  if (!raw || typeof raw !== "object") return null;

  const ticker = raw.ticker as Record<string, number> | undefined;
  const orderBook = raw.order_book as Record<string, [number, number][]> | undefined;
  const candles = raw.candles as Array<Record<string, unknown>> | undefined;

  return {
    symbol: (raw.symbol as string) ?? "",
    ticker: {
      last: ticker?.last ?? 0,
      bid: ticker?.bid ?? 0,
      ask: ticker?.ask ?? 0,
      vol_24h: ticker?.vol_24h ?? ticker?.vol24h ?? 0,
    },
    mark_price: (raw.mark_price as number) ?? 0,
    index_price: (raw.index_price as number) ?? 0,
    funding_rate: (raw.funding_rate as number) ?? 0,
    open_interest: (raw.open_interest as number) ?? 0,
    order_book: {
      bids: orderBook?.bids ?? [],
      asks: orderBook?.asks ?? [],
    },
    candles: (candles ?? []).map((c) => ({
      ts: (c.ts as string) ?? "",
      o: (c.o as number) ?? 0,
      h: (c.h as number) ?? 0,
      l: (c.l as number) ?? 0,
      c: (c.c as number) ?? 0,
      vol: (c.vol as number) ?? 0,
    })),
    data_fetched_at: (raw.data_fetched_at as string) ?? "",
    source_level: (raw.source_level as "exchange_native" | "web_derived") ?? "exchange_native",
    unavailable_fields: (raw.unavailable_fields as string[]) ?? [],
  };
}

/** 从后端 state 提取证据列表 */
function extractEvidence(values: Record<string, unknown> | undefined): EvidenceItem[] {
  if (!values) return [];
  const research = values.research_bundle as Record<string, unknown> | undefined;
  if (!research) return [];

  const items: EvidenceItem[] = [];
  const newsFindings = (research.news_findings as Array<Record<string, unknown>>) ?? [];
  const macroFindings = (research.macro_findings as Array<Record<string, unknown>>) ?? [];

  for (const finding of [...newsFindings, ...macroFindings]) {
    items.push({
      source_type: "web_search",
      source_url: (finding.source_url as string | null) ?? null,
      source_title: (finding.title as string | null) ?? null,
      published_at: (finding.published_at as string | null) ?? null,
      fetched_at: (finding.fetched_at as string) ?? new Date().toISOString(),
      summary: (finding.summary as string) ?? "",
      relevance_score: finding.relevance === "high" ? 0.8 : finding.relevance === "medium" ? 0.5 : 0.2,
      symbol: (finding.symbol as string | null) ?? null,
    });
  }

  return items;
}

/** 从后端 state 提取 RiskVerdict */
function extractRiskVerdict(values: Record<string, unknown> | undefined): RiskVerdict | null {
  if (!values) return null;
  const raw = values.risk_verdict as Record<string, unknown> | undefined;
  if (!raw || typeof raw !== "object") return null;

  return {
    allowed: (raw.allowed as boolean) ?? false,
    blocked_reasons: (raw.blocked_reasons as string[]) ?? [],
    warnings: (raw.warnings as string[]) ?? [],
    confidence_cap: (raw.confidence_cap as number) ?? 1.0,
  };
}

// ===========================================================================
// 主组件
// ===========================================================================

export default function WorkPage() {
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | undefined>();
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | undefined>();

  // useStream - 唯一状态源
  const stream = useStream<AnalysisState>({
    apiUrl: "http://localhost:2024",
    assistantId: "agent",
    threadId: activeThreadId,
    onThreadId: (id: string) => {
      setThreadId(id);
      // 新 thread 加入列表
      setThreads((prev) => {
        if (prev.some((t) => t.id === id)) return prev;
        const now = new Date().toISOString();
        return [
          {
            id,
            title: `分析 ${prev.length + 1}`,
            created_at: now,
            last_message_at: now,
            status: "running",
          },
          ...prev,
        ];
      });
      setActiveThreadId(id);
    },
    reconnectOnMount: true,
  } as any);

  // 从 stream.values 提取数据
  const values = stream.values as unknown as Record<string, unknown> | undefined;
  const analysisResult = useMemo(() => extractAnalysisResult(values), [values]);
  const marketSnapshot = useMemo(() => extractMarketSnapshot(values), [values]);
  const evidence = useMemo(() => extractEvidence(values), [values]);
  const riskVerdict = useMemo(() => extractRiskVerdict(values), [values]);

  // 中断检测
  const interrupts: InterruptInfo[] = stream.interrupts ?? [];
  const hasInterrupt = interrupts.length > 0;

  // 过期检查
  const isExpired = useMemo(() => {
    if (!analysisResult) return false;
    return new Date(analysisResult.expires_at).getTime() < Date.now();
  }, [analysisResult]);

  // === 事件处理 ===

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    stream.submit({ messages: [{ role: "user", content: input.trim() }] } as any);
    setInput("");
  };

  const handleNewThread = () => {
    setActiveThreadId(undefined);
    setThreadId(undefined);
    setInput("");
  };

  const handleSelectThread = (id: string) => {
    setActiveThreadId(id);
  };

  const handleApprove = useCallback(() => {
    stream.respond({ action: "approve" });
  }, [stream]);

  const handleReject = useCallback(() => {
    stream.respond({ action: "reject" });
  }, [stream]);

  const handleEdit = useCallback(
    (edits: Partial<AnalysisResult>) => {
      stream.respond({ action: "approve", edits });
    },
    [stream]
  );

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "var(--color-bg-primary)", color: "var(--color-text-primary)" }}>
      {/* 顶部栏 */}
      <header
        style={{
          padding: "0.75rem 1.5rem",
          borderBottom: "1px solid var(--color-border)",
          display: "flex",
          alignItems: "center",
          gap: "1rem",
        }}
      >
        <h1 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--color-brand)", margin: 0 }}>
          Crypto Alert V2 - 工作台
        </h1>
        <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
          Thread: <code style={{ color: "var(--color-brand-light)" }}>{threadId ?? "(未创建)"}</code>
        </span>
        <span
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.375rem",
            fontSize: "0.75rem",
            color: "var(--color-text-secondary)",
          }}
        >
          <span
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              backgroundColor: stream.isLoading
                ? "var(--color-brand)"
                : stream.error
                  ? "var(--color-error)"
                  : "var(--color-success)",
            }}
          />
          {stream.isLoading ? "执行中..." : stream.error ? "连接错误" : "已就绪"}
        </span>
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
          Agent Server: localhost:2024
        </span>
      </header>

      {/* 三栏布局 */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "240px 1fr 360px",
          gap: "1px",
          backgroundColor: "var(--color-border)",
          minHeight: "calc(100vh - 49px)",
        }}
      >
        {/* === 左栏：Thread 列表 === */}
        <aside
          style={{
            backgroundColor: "var(--color-bg-secondary)",
            padding: "1rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
            overflowY: "auto",
          }}
        >
          <button
            onClick={handleNewThread}
            style={{
              padding: "0.5rem",
              backgroundColor: "var(--color-brand)",
              color: "#0f172a",
              border: "none",
              borderRadius: "6px",
              fontWeight: 600,
              fontSize: "0.8125rem",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.375rem",
            }}
          >
            + 新建分析
          </button>

          <div
            style={{
              fontSize: "0.7rem",
              fontWeight: 600,
              color: "var(--color-text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginTop: "0.5rem",
            }}
          >
            会话列表（{threads.length}）
          </div>

          {threads.length === 0 ? (
            <div
              style={{
                padding: "1rem",
                textAlign: "center",
                color: "var(--color-text-muted)",
                fontSize: "0.75rem",
              }}
            >
              暂无会话。输入消息开始新分析。
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              {threads.map((t) => (
                <div
                  key={t.id}
                  onClick={() => handleSelectThread(t.id)}
                  style={{
                    padding: "0.5rem 0.625rem",
                    backgroundColor:
                      activeThreadId === t.id
                        ? "var(--color-bg-tertiary)"
                        : "transparent",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontSize: "0.75rem",
                    color:
                      activeThreadId === t.id
                        ? "var(--color-text-primary)"
                        : "var(--color-text-secondary)",
                    border:
                      activeThreadId === t.id
                        ? "1px solid var(--color-border-light)"
                        : "1px solid transparent",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.125rem",
                  }}
                >
                  <span style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {t.title}
                  </span>
                  <span style={{ fontSize: "0.65rem", color: "var(--color-text-muted)", fontFamily: "monospace" }}>
                    {t.id.slice(0, 8)}...
                  </span>
                </div>
              ))}
            </div>
          )}
        </aside>

        {/* === 中栏：对话 + 分析 + HITL === */}
        <main
          style={{
            backgroundColor: "var(--color-bg-primary)",
            padding: "1rem 1.5rem",
            display: "flex",
            flexDirection: "column",
            gap: "1rem",
            overflowY: "auto",
            maxHeight: "calc(100vh - 49px)",
          }}
        >
          {/* 错误提示 */}
          {!!stream.error && (
            <div
              style={{
                padding: "0.75rem 1rem",
                backgroundColor: "rgba(239, 68, 68, 0.1)",
                border: "1px solid var(--color-error)",
                borderRadius: "8px",
                fontSize: "0.8125rem",
                color: "var(--color-error)",
              }}
            >
              连接错误：{stream.error instanceof Error ? stream.error.message : String(stream.error)}
              <div style={{ fontSize: "0.7rem", marginTop: "0.25rem", color: "var(--color-text-muted)" }}>
                请确认 Agent Server 已启动：langgraph dev（端口 2024）
              </div>
            </div>
          )}

          {/* 对话时间线 */}
          <section>
            <h2
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                color: "var(--color-text-muted)",
                marginBottom: "0.5rem",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              对话时间线（{(stream.messages ?? []).length}）
            </h2>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
                maxHeight: "350px",
                overflowY: "auto",
              }}
            >
              {(stream.messages ?? []).length === 0 ? (
                <div
                  style={{
                    padding: "2rem",
                    textAlign: "center",
                    color: "var(--color-text-muted)",
                    backgroundColor: "var(--color-bg-secondary)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "8px",
                    fontSize: "0.8125rem",
                  }}
                >
                  输入消息（如"分析 BTC 当前走势"）开始与 Agent 交互。
                </div>
              ) : (
                (stream.messages ?? []).map((msg: any, idx: number) => {
                  const role = (msg.role as string) ?? (msg.type as string) ?? "unknown";
                  const content =
                    typeof msg.content === "string"
                      ? msg.content
                      : Array.isArray(msg.content)
                        ? (msg.content as Array<Record<string, unknown>>)
                            .map((c) =>
                              typeof c === "string" ? c : (c.text as string) ?? JSON.stringify(c)
                            )
                            .join("")
                        : JSON.stringify(msg.content);

                  const isHuman = role === "human" || role === "user";
                  const isAI = role === "ai" || role === "assistant";
                  const roleLabel = isHuman ? "用户" : isAI ? "Agent" : role === "tool" ? "工具" : role;
                  const roleColor = isHuman
                    ? "var(--color-info)"
                    : isAI
                      ? "var(--color-brand)"
                      : role === "tool"
                        ? "var(--color-success)"
                        : "var(--color-text-muted)";

                  return (
                    <div
                      key={(msg.id as string) ?? idx}
                      style={{
                        padding: "0.5rem 0.75rem",
                        backgroundColor: "var(--color-bg-secondary)",
                        border: "1px solid var(--color-border)",
                        borderRadius: "8px",
                        borderLeft: `3px solid ${roleColor}`,
                      }}
                    >
                      <span
                        style={{
                          fontSize: "0.7rem",
                          fontWeight: 600,
                          color: roleColor,
                          display: "block",
                          marginBottom: content ? "0.25rem" : 0,
                        }}
                      >
                        {roleLabel}
                      </span>
                      {content && (
                        <div
                          style={{
                            fontSize: "0.8125rem",
                            color: "var(--color-text-primary)",
                            lineHeight: 1.5,
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}
                        >
                          {content}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </section>

          {/* 输入栏 */}
          <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem" }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入消息（如「分析 BTC 当前走势」）..."
              disabled={stream.isLoading}
              style={{
                flex: 1,
                padding: "0.5rem 0.75rem",
                backgroundColor: "var(--color-bg-secondary)",
                border: "1px solid var(--color-border-light)",
                borderRadius: "8px",
                color: "var(--color-text-primary)",
                fontSize: "0.8125rem",
                outline: "none",
                opacity: stream.isLoading ? 0.6 : 1,
              }}
            />
            <button
              type="submit"
              disabled={stream.isLoading || !input.trim()}
              style={{
                padding: "0.5rem 1.25rem",
                backgroundColor: "var(--color-brand)",
                color: "#0f172a",
                border: "none",
                borderRadius: "8px",
                fontWeight: 600,
                fontSize: "0.8125rem",
                cursor: stream.isLoading || !input.trim() ? "not-allowed" : "pointer",
                opacity: stream.isLoading || !input.trim() ? 0.5 : 1,
              }}
            >
              提交
            </button>
            {stream.isLoading && (
              <button
                type="button"
                onClick={() => stream.stop()}
                style={{
                  padding: "0.5rem 1rem",
                  backgroundColor: "var(--color-bg-tertiary)",
                  color: "var(--color-text-primary)",
                  border: "1px solid var(--color-border-light)",
                  borderRadius: "8px",
                  fontSize: "0.8125rem",
                  cursor: "pointer",
                }}
              >
                停止
              </button>
            )}
          </form>

          {/* HITL 中断提示 */}
          {hasInterrupt && (
            <div
              style={{
                padding: "0.625rem 0.875rem",
                backgroundColor: "rgba(245, 158, 11, 0.1)",
                border: "1px solid var(--color-brand)",
                borderRadius: "8px",
                fontSize: "0.8125rem",
                color: "var(--color-brand)",
                display: "flex",
                alignItems: "center",
                gap: "0.375rem",
              }}
            >
              <span>⏸</span>
              <span>等待人工确认 - 请审阅下方分析结论并做出决策</span>
            </div>
          )}

          {/* 分析结论卡片 */}
          {analysisResult && (
            <section>
              <h2
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  marginBottom: "0.5rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                分析结论
              </h2>
              <AnalysisResultCard
                result={analysisResult}
                onApprove={handleApprove}
                onReject={handleReject}
                onEdit={handleEdit}
                expiresAt={analysisResult.expires_at}
                isExpired={isExpired}
              />
            </section>
          )}

          {/* 根因链 */}
          {analysisResult && analysisResult.root_cause_chain.length > 0 && (
            <section>
              <h2
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  marginBottom: "0.5rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                根因链
              </h2>
              <div
                style={{
                  backgroundColor: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "8px",
                  padding: "0.75rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.25rem",
                }}
              >
                {analysisResult.root_cause_chain.map((step, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      fontSize: "0.8125rem",
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    <span
                      style={{
                        color: "var(--color-brand)",
                        fontWeight: 600,
                        flexShrink: 0,
                      }}
                    >
                      {idx + 1}.
                    </span>
                    <span>{step}</span>
                  </div>
                ))}
                {analysisResult.why_not_opposite && (
                  <div
                    style={{
                      marginTop: "0.5rem",
                      padding: "0.5rem 0.625rem",
                      backgroundColor: "var(--color-bg-primary)",
                      borderRadius: "4px",
                      fontSize: "0.75rem",
                      color: "var(--color-text-muted)",
                    }}
                  >
                    <span style={{ fontWeight: 600, color: "var(--color-text-secondary)" }}>
                      对抗性审查：
                    </span>
                    {analysisResult.why_not_opposite}
                  </div>
                )}
              </div>
            </section>
          )}
        </main>

        {/* === 右栏：行情 + 证据 + 风控 === */}
        <aside
          style={{
            backgroundColor: "var(--color-bg-secondary)",
            padding: "1rem",
            display: "flex",
            flexDirection: "column",
            gap: "1rem",
            overflowY: "auto",
            maxHeight: "calc(100vh - 49px)",
          }}
        >
          {/* 行情快照 */}
          {marketSnapshot ? (
            <MarketSnapshotPanel snapshot={marketSnapshot} showDetails={true} />
          ) : (
            <div
              style={{
                padding: "1rem",
                textAlign: "center",
                color: "var(--color-text-muted)",
                fontSize: "0.75rem",
                backgroundColor: "var(--color-bg-secondary)",
                border: "1px solid var(--color-border)",
                borderRadius: "10px",
              }}
            >
              等待行情数据...
            </div>
          )}

          {/* 证据列表 */}
          <EvidenceTimeline evidence={evidence} groupBy="source_type" />

          {/* 风险门禁 */}
          {riskVerdict ? (
            <RiskInspector
              verdict={riskVerdict}
              ruleHits={[]}
              expanded={true}
            />
          ) : (
            <div
              style={{
                padding: "1rem",
                textAlign: "center",
                color: "var(--color-text-muted)",
                fontSize: "0.75rem",
                backgroundColor: "var(--color-bg-secondary)",
                border: "1px solid var(--color-border)",
                borderRadius: "10px",
              }}
            >
              等待风控裁决...
            </div>
          )}

          {/* Graph State JSON（调试用） */}
          {values && Object.keys(values).length > 0 && (
            <details
              style={{
                backgroundColor: "var(--color-bg-secondary)",
                border: "1px solid var(--color-border)",
                borderRadius: "8px",
                padding: "0.5rem",
              }}
            >
              <summary
                style={{
                  fontSize: "0.7rem",
                  color: "var(--color-text-muted)",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
              >
                Graph State JSON
              </summary>
              <pre
                className="json-block"
                style={{
                  color: "var(--color-text-secondary)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  margin: "0.5rem 0 0",
                  maxHeight: "200px",
                  overflowY: "auto",
                  fontSize: "0.7rem",
                }}
              >
                {JSON.stringify(values, null, 2)}
              </pre>
            </details>
          )}
        </aside>
      </div>
    </div>
  );
}
