"use client";

import { useState, useMemo, useEffect } from "react";

/**
 * Library 页面 - Artifact 列表（分析报告）
 *
 * - Artifact 列表（分析报告）
 * - 按标的/时间/方向筛选
 * - 点击查看详情
 *
 * 设计文档 15-frontend-and-config-management.md 第二节。
 * Phase 2 使用占位数据，后续接入 API。
 */

// ===========================================================================
// 类型定义
// ===========================================================================

interface ArtifactItem {
  id: string;
  symbol: string;
  direction: "long" | "short" | "neutral";
  action: string;
  regime: string;
  probability: number;
  reference_price: number;
  entry_trigger: number | null;
  stop_price: number | null;
  target_1: number | null;
  total_score: number;
  root_cause_summary: string;
  created_at: string;
  status: "approved" | "rejected" | "expired" | "pending";
  risk_blocked: boolean;
}

// ===========================================================================
// 占位数据
// ===========================================================================

const ARTIFACTS: ArtifactItem[] = [
  {
    id: "art-001",
    symbol: "BTC-USDT-SWAP",
    direction: "long",
    action: "open_long",
    regime: "risk_on",
    probability: 0.65,
    reference_price: 65000,
    entry_trigger: 65100,
    stop_price: 64500,
    target_1: 66000,
    total_score: 8,
    root_cause_summary: "BTC 突破关键阻力位，衍生品指标偏多，宏观环境支撑风险资产",
    created_at: "2026-07-12T08:00:00Z",
    status: "approved",
    risk_blocked: false,
  },
  {
    id: "art-002",
    symbol: "ETH-USDT-SWAP",
    direction: "short",
    action: "open_short",
    regime: "risk_off",
    probability: 0.55,
    reference_price: 3200,
    entry_trigger: 3180,
    stop_price: 3280,
    target_1: 3050,
    total_score: -5,
    root_cause_summary: "ETH 资金费率转负，OI 下降，BTC 结构走弱拖累",
    created_at: "2026-07-11T14:00:00Z",
    status: "rejected",
    risk_blocked: false,
  },
  {
    id: "art-003",
    symbol: "SOL-USDT-SWAP",
    direction: "long",
    action: "no_trade",
    regime: "event_compression",
    probability: 0.45,
    reference_price: 145,
    entry_trigger: null,
    stop_price: null,
    target_1: null,
    total_score: 2,
    root_cause_summary: "SOL 震荡区间内，无明确方向信号，观望",
    created_at: "2026-07-11T10:00:00Z",
    status: "expired",
    risk_blocked: false,
  },
  {
    id: "art-004",
    symbol: "BTC-USDT-SWAP",
    direction: "neutral",
    action: "no_trade",
    regime: "surprise_repricing",
    probability: 0.3,
    reference_price: 63000,
    entry_trigger: null,
    stop_price: null,
    target_1: null,
    total_score: -1,
    root_cause_summary: "CPI 数据即将发布，事件压缩期不建议开仓",
    created_at: "2026-07-10T16:00:00Z",
    status: "expired",
    risk_blocked: true,
  },
  {
    id: "art-005",
    symbol: "ETH-USDT-SWAP",
    direction: "long",
    action: "trigger_long",
    regime: "risk_on",
    probability: 0.6,
    reference_price: 3100,
    entry_trigger: 3120,
    stop_price: 3050,
    target_1: 3250,
    total_score: 6,
    root_cause_summary: "ETH 反弹突破均线，成交量放大，BTC 稳定",
    created_at: "2026-07-10T09:00:00Z",
    status: "approved",
    risk_blocked: false,
  },
];

// ===========================================================================
// 辅助函数
// ===========================================================================

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function directionColor(dir: string): string {
  if (dir === "long") return "var(--color-success)";
  if (dir === "short") return "var(--color-error)";
  return "var(--color-text-muted)";
}

function statusColor(status: string): string {
  switch (status) {
    case "approved":
      return "var(--color-success)";
    case "rejected":
      return "var(--color-error)";
    case "expired":
      return "var(--color-text-muted)";
    case "pending":
      return "var(--color-brand)";
    default:
      return "var(--color-text-muted)";
  }
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    approved: "已确认",
    rejected: "已拒绝",
    expired: "已过期",
    pending: "待处理",
  };
  return labels[status] ?? status;
}

// ===========================================================================
// 样式常量
// ===========================================================================

const cardStyle: React.CSSProperties = {
  backgroundColor: "var(--color-bg-secondary)",
  border: "1px solid var(--color-border)",
  borderRadius: "10px",
};

const selectStyle: React.CSSProperties = {
  padding: "0.375rem 0.625rem",
  backgroundColor: "var(--color-bg-tertiary)",
  color: "var(--color-text-primary)",
  border: "1px solid var(--color-border-light)",
  borderRadius: "6px",
  fontSize: "0.75rem",
  outline: "none",
  cursor: "pointer",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  marginBottom: "0.75rem",
};

// ===========================================================================
// 主组件
// ===========================================================================

export default function LibraryPage() {
  const [symbolFilter, setSymbolFilter] = useState<string>("all");
  const [directionFilter, setDirectionFilter] = useState<string>("all");
  const [timeFilter, setTimeFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => setHydrated(true), []);

  // 筛选
  const filtered = useMemo(() => {
    return ARTIFACTS.filter((a) => {
      if (symbolFilter !== "all" && a.symbol !== symbolFilter) return false;
      if (directionFilter !== "all" && a.direction !== directionFilter)
        return false;
      if (timeFilter !== "all") {
        const now = new Date();
        const created = new Date(a.created_at);
        const diffHours = (now.getTime() - created.getTime()) / 3600000;
        if (timeFilter === "24h" && diffHours > 24) return false;
        if (timeFilter === "7d" && diffHours > 168) return false;
        if (timeFilter === "30d" && diffHours > 720) return false;
      }
      return true;
    });
  }, [symbolFilter, directionFilter, timeFilter]);

  // 获取唯一 symbol 列表
  const symbols = useMemo(
    () => Array.from(new Set(ARTIFACTS.map((a) => a.symbol))),
    []
  );

  const selected = selectedId
    ? ARTIFACTS.find((a) => a.id === selectedId)
    : null;

  return (
    <div
      style={{
        padding: "1.5rem 2rem",
        maxWidth: "1100px",
        margin: "0 auto",
      }}
    >
      <h1
        style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          color: "var(--color-text-primary)",
          marginBottom: "0.25rem",
        }}
      >
        分析库
      </h1>
      <p
        style={{
          fontSize: "0.8125rem",
          color: "var(--color-text-secondary)",
          marginBottom: "1.5rem",
        }}
      >
        浏览历史分析报告 - 共 {filtered.length} 条记录
      </p>

      {/* 筛选栏 */}
      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        <select
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="all">全部标的</option>
          {symbols.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          value={directionFilter}
          onChange={(e) => setDirectionFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="all">全部方向</option>
          <option value="long">做多</option>
          <option value="short">做空</option>
          <option value="neutral">观望</option>
        </select>

        <select
          value={timeFilter}
          onChange={(e) => setTimeFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="all">全部时间</option>
          <option value="24h">最近 24 小时</option>
          <option value="7d">最近 7 天</option>
          <option value="30d">最近 30 天</option>
        </select>
      </div>

      {/* 列表 + 详情双栏 */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: selected ? "1fr 400px" : "1fr",
          gap: "1rem",
        }}
      >
        {/* 列表 */}
        <div>
          <h2 style={sectionTitleStyle}>分析报告</h2>
          {filtered.length === 0 ? (
            <div
              style={{
                ...cardStyle,
                padding: "2rem",
                textAlign: "center",
                color: "var(--color-text-muted)",
                fontSize: "0.8125rem",
              }}
            >
              没有符合条件的分析报告
            </div>
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {filtered.map((a) => (
                <div
                  key={a.id}
                  onClick={() =>
                    setSelectedId(selectedId === a.id ? null : a.id)
                  }
                  style={{
                    ...cardStyle,
                    padding: "0.875rem 1rem",
                    cursor: "pointer",
                    borderColor:
                      selectedId === a.id
                        ? "var(--color-brand)"
                        : "var(--color-border)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 700,
                        color: directionColor(a.direction),
                        textTransform: "uppercase",
                        width: "44px",
                      }}
                    >
                      {a.direction}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--color-text-primary)",
                          fontWeight: 500,
                        }}
                      >
                        {a.symbol} - {a.action}
                      </div>
                      <div
                        style={{
                          fontSize: "0.7rem",
                          color: "var(--color-text-muted)",
                          marginTop: "0.125rem",
                        }}
                      >
                        {a.root_cause_summary}
                      </div>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-end",
                        gap: "0.125rem",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "0.7rem",
                          color: statusColor(a.status),
                        }}
                      >
                        {statusLabel(a.status)}
                      </span>
                      <span
                        style={{
                          fontSize: "0.65rem",
                          color: "var(--color-text-muted)",
                        }}
                      >
                        {hydrated ? formatDate(a.created_at) : ""}
                      </span>
                    </div>
                  </div>
                  {a.risk_blocked && (
                    <div
                      style={{
                        marginTop: "0.5rem",
                        fontSize: "0.65rem",
                        color: "var(--color-error)",
                      }}
                    >
                      风控拦截
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 详情面板 */}
        {selected && (
          <div>
            <h2 style={sectionTitleStyle}>详情</h2>
            <div
              style={{
                ...cardStyle,
                padding: "1rem 1.25rem",
                position: "sticky",
                top: "1rem",
              }}
            >
              {/* 标题 */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  marginBottom: "0.75rem",
                }}
              >
                <span
                  style={{
                    fontSize: "0.7rem",
                    fontWeight: 700,
                    color: directionColor(selected.direction),
                    textTransform: "uppercase",
                  }}
                >
                  {selected.direction}
                </span>
                <span
                  style={{
                    fontSize: "0.875rem",
                    fontWeight: 600,
                    color: "var(--color-text-primary)",
                  }}
                >
                  {selected.symbol}
                </span>
                <span
                  style={{
                    fontSize: "0.7rem",
                    color: statusColor(selected.status),
                    marginLeft: "auto",
                  }}
                >
                  {statusLabel(selected.status)}
                </span>
              </div>

              {/* 参数 */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "0.5rem",
                  fontSize: "0.75rem",
                  marginBottom: "0.75rem",
                }}
              >
                <Field label="动作" value={selected.action} />
                <Field label="体制" value={selected.regime} />
                <Field
                  label="参考价"
                  value={`$${selected.reference_price.toLocaleString()}`}
                />
                <Field
                  label="胜率"
                  value={`${(selected.probability * 100).toFixed(0)}%`}
                />
                <Field
                  label="入场"
                  value={
                    selected.entry_trigger
                      ? `$${selected.entry_trigger.toLocaleString()}`
                      : "-"
                  }
                />
                <Field
                  label="止损"
                  value={
                    selected.stop_price
                      ? `$${selected.stop_price.toLocaleString()}`
                      : "-"
                  }
                />
                <Field
                  label="目标1"
                  value={
                    selected.target_1
                      ? `$${selected.target_1.toLocaleString()}`
                      : "-"
                  }
                />
                <Field
                  label="因子总分"
                  value={String(selected.total_score)}
                />
              </div>

              {/* 根因摘要 */}
              <div
                style={{
                  fontSize: "0.7rem",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  marginBottom: "0.25rem",
                }}
              >
                根因摘要
              </div>
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--color-text-secondary)",
                  lineHeight: 1.5,
                  marginBottom: "0.75rem",
                }}
              >
                {selected.root_cause_summary}
              </div>

              {/* 时间 */}
              <div
                style={{
                  fontSize: "0.7rem",
                  color: "var(--color-text-muted)",
                  paddingTop: "0.5rem",
                  borderTop: "1px solid var(--color-border)",
                }}
              >
                创建时间: {hydrated ? formatDate(selected.created_at) : ""}
              </div>

              <button
                onClick={() => setSelectedId(null)}
                style={{
                  width: "100%",
                  marginTop: "0.75rem",
                  padding: "0.375rem",
                  backgroundColor: "var(--color-bg-tertiary)",
                  color: "var(--color-text-secondary)",
                  border: "1px solid var(--color-border-light)",
                  borderRadius: "6px",
                  fontSize: "0.75rem",
                  cursor: "pointer",
                }}
              >
                关闭详情
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ===========================================================================
// 子组件
// ===========================================================================

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span style={{ color: "var(--color-text-muted)" }}>{label}: </span>
      <span
        style={{
          color: "var(--color-text-primary)",
          fontFamily: "monospace",
        }}
      >
        {value}
      </span>
    </div>
  );
}
