"use client";

import { useEffect, useState, useCallback } from "react";

/**
 * Inbox 页面 - 待确认 Interrupt 列表 + 提醒通知
 *
 * - 待确认 Interrupt 列表（每条可展开详情 + [确认] [拒绝] 按钮）
 * - 提醒通知列表
 *
 * 设计文档 15-frontend-and-config-management.md 第二节。
 * Phase 2 使用占位数据，后续接入 Agent Server interrupts API。
 */

// ===========================================================================
// 类型定义
// ===========================================================================

interface InterruptItem {
  id: string;
  thread_id: string;
  run_id: string;
  type: "analysis_confirmation";
  symbol: string;
  action: string;
  direction: "long" | "short" | "neutral";
  reference_price: number;
  entry_trigger: number | null;
  stop_price: number | null;
  target_1: number | null;
  probability: number;
  created_at: string;
  expires_at: string;
  expanded: boolean;
}

interface NotificationItem {
  id: string;
  type: "analysis_completed" | "risk_blocked" | "notification_sent" | "system";
  title: string;
  message: string;
  created_at: string;
  read: boolean;
}

// ===========================================================================
// 占位数据
// ===========================================================================

const INITIAL_INTERRUPTS: InterruptItem[] = [
  {
    id: "interrupt-001",
    thread_id: "thread-abc123",
    run_id: "run-xyz789",
    type: "analysis_confirmation",
    symbol: "BTC-USDT-SWAP",
    action: "open_long",
    direction: "long",
    reference_price: 65000,
    entry_trigger: 65100,
    stop_price: 64500,
    target_1: 66000,
    probability: 0.65,
    created_at: "2026-07-12T10:30:00Z",
    expires_at: "2026-07-12T10:31:30Z",
    expanded: false,
  },
];

const NOTIFICATIONS: NotificationItem[] = [
  {
    id: "notif-001",
    type: "analysis_completed",
    title: "BTC 分析完成",
    message: "BTC-USDT-SWAP 分析已完成，等待确认",
    created_at: "2026-07-12T10:30:00Z",
    read: false,
  },
  {
    id: "notif-002",
    type: "risk_blocked",
    title: "风控拦截",
    message: "ETH-USDT-SWAP 因数据过期被风控阻断",
    created_at: "2026-07-12T09:15:00Z",
    read: false,
  },
  {
    id: "notif-003",
    type: "notification_sent",
    title: "Bark 通知已发送",
    message: "SOL-USDT-SWAP 分析结果已推送到手机",
    created_at: "2026-07-11T16:00:00Z",
    read: true,
  },
];

// ===========================================================================
// 辅助函数
// ===========================================================================

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

function isExpired(expiresAt: string): boolean {
  return new Date(expiresAt).getTime() < Date.now();
}

function directionColor(dir: string): string {
  if (dir === "long") return "var(--color-success)";
  if (dir === "short") return "var(--color-error)";
  return "var(--color-text-muted)";
}

// ===========================================================================
// 样式常量
// ===========================================================================

const cardStyle: React.CSSProperties = {
  backgroundColor: "var(--color-bg-secondary)",
  border: "1px solid var(--color-border)",
  borderRadius: "10px",
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

export default function InboxPage() {
  const [interrupts, setInterrupts] = useState<InterruptItem[]>(INITIAL_INTERRUPTS);
  const [notifications, setNotifications] = useState<NotificationItem[]>(NOTIFICATIONS);

  const toggleExpand = useCallback((id: string) => {
    setInterrupts((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, expanded: !item.expanded } : item
      )
    );
  }, []);

  const handleConfirm = useCallback((id: string) => {
    // Phase 2 占位：后续调用 stream.respond({ action: "approve" })
    setInterrupts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const handleReject = useCallback((id: string) => {
    setInterrupts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;
  const pendingCount = interrupts.length;

  return (
    <div
      style={{
        padding: "1.5rem 2rem",
        maxWidth: "900px",
        margin: "0 auto",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1.5rem",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "1.5rem",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              marginBottom: "0.25rem",
            }}
          >
            收件箱
          </h1>
          <p
            style={{
              fontSize: "0.8125rem",
              color: "var(--color-text-secondary)",
            }}
          >
            {pendingCount} 项待确认 - {unreadCount} 条未读通知
          </p>
        </div>
        {unreadCount > 0 && (
          <button
            onClick={markAllRead}
            style={{
              padding: "0.375rem 0.75rem",
              backgroundColor: "var(--color-bg-tertiary)",
              color: "var(--color-text-secondary)",
              border: "1px solid var(--color-border-light)",
              borderRadius: "6px",
              fontSize: "0.75rem",
              cursor: "pointer",
            }}
          >
            全部已读
          </button>
        )}
      </div>

      {/* 待确认 Interrupt 列表 */}
      <section style={{ marginBottom: "2rem" }}>
        <h2 style={sectionTitleStyle}>待确认分析（{pendingCount}）</h2>
        {pendingCount === 0 ? (
          <div
            style={{
              ...cardStyle,
              padding: "2rem",
              textAlign: "center",
              color: "var(--color-text-muted)",
              fontSize: "0.8125rem",
            }}
          >
            暂无待确认的分析
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {interrupts.map((item) => {
              const expired = isExpired(item.expires_at);
              return (
                <div key={item.id} style={cardStyle}>
                  {/* 摘要行 */}
                  <div
                    onClick={() => toggleExpand(item.id)}
                    style={{
                      padding: "0.875rem 1rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      cursor: "pointer",
                    }}
                  >
                    <span
                      style={{
                        width: "8px",
                        height: "8px",
                        borderRadius: "50%",
                        backgroundColor: expired
                          ? "var(--color-text-muted)"
                          : "var(--color-brand)",
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 700,
                        color: directionColor(item.direction),
                        textTransform: "uppercase",
                        width: "44px",
                      }}
                    >
                      {item.direction}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--color-text-primary)",
                        }}
                      >
                        {item.symbol} - {item.action}
                      </div>
                      <div
                        style={{
                          fontSize: "0.7rem",
                          color: "var(--color-text-muted)",
                        }}
                      >
                        {formatTime(item.created_at)}
                        {expired && (
                          <span style={{ color: "var(--color-error)" }}>
                            {" "}
                            - 已过期
                          </span>
                        )}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {item.expanded ? "收起" : "展开"}
                    </span>
                  </div>

                  {/* 展开详情 */}
                  {item.expanded && (
                    <div
                      style={{
                        padding: "0.75rem 1rem 1rem",
                        borderTop: "1px solid var(--color-border)",
                      }}
                    >
                      {/* 参数表格 */}
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "1fr 1fr",
                          gap: "0.5rem",
                          marginBottom: "1rem",
                        }}
                      >
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          参考价格:{" "}
                          <span
                            style={{
                              color: "var(--color-text-primary)",
                              fontFamily: "monospace",
                            }}
                          >
                            ${item.reference_price.toLocaleString()}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          入场触发:{" "}
                          <span
                            style={{
                              color: "var(--color-text-primary)",
                              fontFamily: "monospace",
                            }}
                          >
                            {item.entry_trigger
                              ? `$${item.entry_trigger.toLocaleString()}`
                              : "-"}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          止损价:{" "}
                          <span
                            style={{
                              color: "var(--color-error)",
                              fontFamily: "monospace",
                            }}
                          >
                            {item.stop_price
                              ? `$${item.stop_price.toLocaleString()}`
                              : "-"}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          目标1:{" "}
                          <span
                            style={{
                              color: "var(--color-success)",
                              fontFamily: "monospace",
                            }}
                          >
                            {item.target_1
                              ? `$${item.target_1.toLocaleString()}`
                              : "-"}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          胜率:{" "}
                          <span
                            style={{
                              color: "var(--color-brand)",
                              fontFamily: "monospace",
                            }}
                          >
                            {(item.probability * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--color-text-muted)",
                          }}
                        >
                          Thread:{" "}
                          <code style={{ fontSize: "0.65rem" }}>
                            {item.thread_id.slice(0, 12)}
                          </code>
                        </div>
                      </div>

                      {/* 安全提示 */}
                      <div
                        style={{
                          fontSize: "0.7rem",
                          color: "var(--color-text-muted)",
                          padding: "0.5rem 0.625rem",
                          backgroundColor: "var(--color-bg-primary)",
                          borderRadius: "4px",
                          marginBottom: "0.75rem",
                        }}
                      >
                        系统不会自动下单。请手动在交易所执行。
                        分析结果有效期 90 秒。
                      </div>

                      {/* 操作按钮 */}
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button
                          onClick={() => handleConfirm(item.id)}
                          disabled={expired}
                          style={{
                            flex: 1,
                            padding: "0.5rem",
                            backgroundColor: expired
                              ? "var(--color-bg-tertiary)"
                              : "var(--color-success)",
                            color: expired
                              ? "var(--color-text-muted)"
                              : "#0f172a",
                            border: "none",
                            borderRadius: "6px",
                            fontWeight: 600,
                            fontSize: "0.8125rem",
                            cursor: expired ? "not-allowed" : "pointer",
                            opacity: expired ? 0.5 : 1,
                          }}
                        >
                          确认
                        </button>
                        <button
                          onClick={() => handleReject(item.id)}
                          style={{
                            flex: 1,
                            padding: "0.5rem",
                            backgroundColor: "transparent",
                            color: "var(--color-error)",
                            border: "1px solid var(--color-error)",
                            borderRadius: "6px",
                            fontWeight: 600,
                            fontSize: "0.8125rem",
                            cursor: "pointer",
                          }}
                        >
                          拒绝
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* 提醒通知列表 */}
      <section>
        <h2 style={sectionTitleStyle}>通知（{notifications.length}）</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {notifications.map((n) => (
            <div
              key={n.id}
              style={{
                ...cardStyle,
                padding: "0.75rem 1rem",
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                opacity: n.read ? 0.6 : 1,
              }}
            >
              <span
                style={{
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  backgroundColor: n.read
                    ? "var(--color-text-muted)"
                    : "var(--color-brand)",
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontSize: "0.8125rem",
                    color: "var(--color-text-primary)",
                    fontWeight: n.read ? 400 : 600,
                  }}
                >
                  {n.title}
                </div>
                <div
                  style={{
                    fontSize: "0.7rem",
                    color: "var(--color-text-muted)",
                  }}
                >
                  {n.message} - {formatTime(n.created_at)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
