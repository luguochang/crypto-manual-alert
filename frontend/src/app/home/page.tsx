"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

/**
 * Home 页面 - 仪表盘
 *
 * 市场简报卡片（BTC/ETH/SOL 占位）
 * 活跃任务列表
 * 待处理事项（Inbox 未读数）
 * 最近分析摘要
 * 快捷入口（发起分析、查看历史）
 *
 * 设计文档 15-frontend-and-config-management.md 第二节。
 */

// ===========================================================================
// 类型定义
// ===========================================================================

interface MarketBrief {
  symbol: string;
  name: string;
  price: number;
  change24h: number; // 百分比
}

interface ActiveTask {
  id: string;
  symbol: string;
  action: string;
  status: "running" | "awaiting_confirmation" | "completed";
  created_at: string;
}

interface RecentAnalysis {
  id: string;
  symbol: string;
  direction: "long" | "short" | "neutral";
  action: string;
  probability: number;
  created_at: string;
  status: "approved" | "rejected" | "expired" | "pending";
}

// ===========================================================================
// 占位数据（Phase 2，后续接入 API）
// ===========================================================================

const MARKET_BRIEFS: MarketBrief[] = [
  { symbol: "BTC-USDT-SWAP", name: "Bitcoin", price: 65000, change24h: 2.3 },
  { symbol: "ETH-USDT-SWAP", name: "Ethereum", price: 3200, change24h: -1.2 },
  { symbol: "SOL-USDT-SWAP", name: "Solana", price: 145, change24h: 5.8 },
];

const ACTIVE_TASKS: ActiveTask[] = [
  {
    id: "task-001",
    symbol: "BTC-USDT-SWAP",
    action: "open_long",
    status: "awaiting_confirmation",
    created_at: "2026-07-12T10:30:00Z",
  },
];

const RECENT_ANALYSES: RecentAnalysis[] = [
  {
    id: "analysis-001",
    symbol: "BTC-USDT-SWAP",
    direction: "long",
    action: "open_long",
    probability: 0.65,
    created_at: "2026-07-12T08:00:00Z",
    status: "approved",
  },
  {
    id: "analysis-002",
    symbol: "ETH-USDT-SWAP",
    direction: "short",
    action: "open_short",
    probability: 0.55,
    created_at: "2026-07-11T14:00:00Z",
    status: "rejected",
  },
];

const INBOX_UNREAD = 1;

// ===========================================================================
// 辅助函数
// ===========================================================================

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "刚刚";
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
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
    running: "执行中",
    awaiting_confirmation: "等待确认",
    completed: "已完成",
  };
  return labels[status] ?? status;
}

// ===========================================================================
// 卡片样式
// ===========================================================================

const cardStyle: React.CSSProperties = {
  backgroundColor: "var(--color-bg-secondary)",
  border: "1px solid var(--color-border)",
  borderRadius: "10px",
  padding: "1rem 1.25rem",
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

export default function HomePage() {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  return (
    <div
      style={{
        padding: "1.5rem 2rem",
        maxWidth: "1200px",
        margin: "0 auto",
      }}
    >
      {/* 页面标题 */}
      <h1
        style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          color: "var(--color-text-primary)",
          marginBottom: "0.25rem",
        }}
      >
        仪表盘
      </h1>
      <p
        style={{
          fontSize: "0.8125rem",
          color: "var(--color-text-secondary)",
          marginBottom: "1.5rem",
        }}
      >
        加密货币提醒 Agent - 市场概览与任务管理
      </p>

      {/* 快捷入口 */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "0.75rem",
          marginBottom: "1.5rem",
        }}
      >
        <Link
          href="/work"
          style={{
            ...cardStyle,
            textDecoration: "none",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            cursor: "pointer",
            transition: "border-color 0.2s",
          }}
        >
          <span
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "8px",
              backgroundColor: "rgba(245, 158, 11, 0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-brand)",
              fontSize: "1.125rem",
              fontWeight: 700,
            }}
          >
            +
          </span>
          <div>
            <div
              style={{
                fontSize: "0.875rem",
                fontWeight: 600,
                color: "var(--color-text-primary)",
              }}
            >
              发起分析
            </div>
            <div
              style={{
                fontSize: "0.7rem",
                color: "var(--color-text-muted)",
              }}
            >
              新建市场分析请求
            </div>
          </div>
        </Link>

        <Link
          href="/library"
          style={{
            ...cardStyle,
            textDecoration: "none",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            cursor: "pointer",
          }}
        >
          <span
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "8px",
              backgroundColor: "rgba(59, 130, 246, 0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-info)",
              fontSize: "1rem",
              fontWeight: 700,
            }}
          >
            {"<>"}
          </span>
          <div>
            <div
              style={{
                fontSize: "0.875rem",
                fontWeight: 600,
                color: "var(--color-text-primary)",
              }}
            >
              查看历史
            </div>
            <div
              style={{
                fontSize: "0.7rem",
                color: "var(--color-text-muted)",
              }}
            >
              浏览分析报告库
            </div>
          </div>
        </Link>

        <Link
          href="/inbox"
          style={{
            ...cardStyle,
            textDecoration: "none",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            cursor: "pointer",
          }}
        >
          <span
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "8px",
              backgroundColor: "rgba(239, 68, 68, 0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--color-error)",
              fontSize: "1rem",
              fontWeight: 700,
            }}
          >
            !
          </span>
          <div>
            <div
              style={{
                fontSize: "0.875rem",
                fontWeight: 600,
                color: "var(--color-text-primary)",
              }}
            >
              收件箱
            </div>
            <div
              style={{
                fontSize: "0.7rem",
                color: "var(--color-text-muted)",
              }}
            >
              {INBOX_UNREAD > 0
                ? `${INBOX_UNREAD} 项待处理`
                : "无待处理事项"}
            </div>
          </div>
        </Link>
      </div>

      {/* 市场简报 */}
      <section style={{ marginBottom: "1.5rem" }}>
        <h2 style={sectionTitleStyle}>市场简报</h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "0.75rem",
          }}
        >
          {MARKET_BRIEFS.map((m) => (
            <div key={m.symbol} style={cardStyle}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.5rem",
                }}
              >
                <span
                  style={{
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    color: "var(--color-text-primary)",
                  }}
                >
                  {m.name}
                </span>
                <span
                  style={{
                    fontSize: "0.65rem",
                    color: "var(--color-text-muted)",
                    fontFamily: "monospace",
                  }}
                >
                  {m.symbol}
                </span>
              </div>
              <div
                style={{
                  fontSize: "1.25rem",
                  fontWeight: 700,
                  color: "var(--color-text-primary)",
                  marginBottom: "0.25rem",
                }}
              >
                ${m.price.toLocaleString()}
              </div>
              <div
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color:
                    m.change24h >= 0
                      ? "var(--color-success)"
                      : "var(--color-error)",
                }}
              >
                {m.change24h >= 0 ? "+" : ""}
                {m.change24h}%
              </div>
            </div>
          ))}
        </div>
        <div
          style={{
            fontSize: "0.65rem",
            color: "var(--color-text-muted)",
            marginTop: "0.5rem",
          }}
        >
          价格为占位数据，后续接入 OKX 实时行情
        </div>
      </section>

      {/* 两列：活跃任务 + 最近分析 */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1rem",
        }}
      >
        {/* 活跃任务 */}
        <section>
          <h2 style={sectionTitleStyle}>活跃任务</h2>
          <div style={cardStyle}>
            {ACTIVE_TASKS.length === 0 ? (
              <div
                style={{
                  padding: "1.5rem",
                  textAlign: "center",
                  color: "var(--color-text-muted)",
                  fontSize: "0.8125rem",
                }}
              >
                暂无活跃任务
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.625rem",
                }}
              >
                {ACTIVE_TASKS.map((task) => (
                  <div
                    key={task.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      padding: "0.5rem 0",
                      borderBottom: "1px solid var(--color-border)",
                    }}
                  >
                    <span
                      style={{
                        width: "8px",
                        height: "8px",
                        borderRadius: "50%",
                        backgroundColor:
                          task.status === "awaiting_confirmation"
                            ? "var(--color-brand)"
                            : "var(--color-info)",
                        flexShrink: 0,
                      }}
                    />
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--color-text-primary)",
                        }}
                      >
                        {task.symbol}
                      </div>
                      <div
                        style={{
                          fontSize: "0.7rem",
                          color: "var(--color-text-muted)",
                        }}
                      >
                        {task.action} - {formatTime(task.created_at)}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--color-brand)",
                      }}
                    >
                      {statusLabel(task.status)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* 最近分析 */}
        <section>
          <h2 style={sectionTitleStyle}>最近分析</h2>
          <div style={cardStyle}>
            {RECENT_ANALYSES.length === 0 ? (
              <div
                style={{
                  padding: "1.5rem",
                  textAlign: "center",
                  color: "var(--color-text-muted)",
                  fontSize: "0.8125rem",
                }}
              >
                暂无分析记录
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.625rem",
                }}
              >
                {RECENT_ANALYSES.map((a) => (
                  <Link
                    key={a.id}
                    href="/library"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      padding: "0.5rem 0",
                      borderBottom: "1px solid var(--color-border)",
                      textDecoration: "none",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 700,
                        color: directionColor(a.direction),
                        textTransform: "uppercase",
                        width: "40px",
                      }}
                    >
                      {a.direction}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--color-text-primary)",
                        }}
                      >
                        {a.symbol}
                      </div>
                      <div
                        style={{
                          fontSize: "0.7rem",
                          color: "var(--color-text-muted)",
                        }}
                      >
                        {a.action} - {formatTime(a.created_at)}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: "0.7rem",
                        color: statusColor(a.status),
                      }}
                    >
                      {statusLabel(a.status)}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* 待处理事项提示 */}
      {hydrated && INBOX_UNREAD > 0 && (
        <div
          style={{
            ...cardStyle,
            marginTop: "1.5rem",
            borderLeft: "3px solid var(--color-brand)",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <span
            style={{
              fontSize: "1rem",
              color: "var(--color-brand)",
            }}
          >
            {"!!"}
          </span>
          <div style={{ flex: 1 }}>
            <span
              style={{
                fontSize: "0.8125rem",
                color: "var(--color-text-primary)",
              }}
            >
              {INBOX_UNREAD} 项待确认中断
            </span>
            <div
              style={{
                fontSize: "0.7rem",
                color: "var(--color-text-muted)",
              }}
            >
              请前往收件箱确认或拒绝分析结果
            </div>
          </div>
          <Link
            href="/inbox"
            style={{
              fontSize: "0.75rem",
              color: "var(--color-brand)",
              textDecoration: "none",
              fontWeight: 600,
            }}
          >
            查看 -&gt;
          </Link>
        </div>
      )}
    </div>
  );
}
