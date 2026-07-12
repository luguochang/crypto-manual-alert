"use client";

import { useMemo } from "react";
import type { EvidenceItem } from "@/types/analysis";

/**
 * 证据时间线组件
 *
 * 展示 Agent 收集的证据列表，支持分组：
 * - source_type: 按数据来源类型分组
 * - symbol: 按交易标的分组
 * - time: 按时间排序（默认）
 *
 * Props 接口来源：15-frontend-and-config-management.md 第 1.2 节
 */

export interface EvidenceTimelineProps {
  evidence: EvidenceItem[];
  onItemClick?: (item: EvidenceItem) => void;
  groupBy?: "source_type" | "symbol" | "time";
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  web_search: "网络搜索",
  exchange_native: "交易所原生",
  official: "官方公告",
};

const SOURCE_TYPE_COLORS: Record<string, string> = {
  web_search: "#3b82f6",
  exchange_native: "#22c55e",
  official: "#f59e0b",
};

const RELEVANCE_LABELS: Record<number, string> = {
  0: "低",
  1: "中",
  2: "高",
};

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function getRelevanceLabel(score: number): string {
  if (score >= 0.7) return "高";
  if (score >= 0.4) return "中";
  return "低";
}

function getRelevanceColor(score: number): string {
  if (score >= 0.7) return "#22c55e";
  if (score >= 0.4) return "#f59e0b";
  return "#64748b";
}

export function EvidenceTimeline({
  evidence,
  onItemClick,
  groupBy = "time",
}: EvidenceTimelineProps) {
  // 分组逻辑
  const grouped = useMemo(() => {
    if (groupBy === "time") {
      // 按时间倒序排列，不分组
      return [
        {
          key: "全部证据",
          items: [...evidence].sort(
            (a, b) =>
              new Date(b.fetched_at).getTime() - new Date(a.fetched_at).getTime()
          ),
        },
      ];
    }

    const groups: Record<string, EvidenceItem[]> = {};
    for (const item of evidence) {
      let key: string;
      if (groupBy === "source_type") {
        key = SOURCE_TYPE_LABELS[item.source_type] ?? item.source_type;
      } else {
        key = item.symbol ?? "通用";
      }
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    }

    return Object.entries(groups).map(([key, items]) => ({
      key,
      items: items.sort(
        (a, b) =>
          new Date(b.fetched_at).getTime() - new Date(a.fetched_at).getTime()
      ),
    }));
  }, [evidence, groupBy]);

  if (!evidence || evidence.length === 0) {
    return (
      <div
        style={{
          backgroundColor: "var(--color-bg-secondary)",
          border: "1px solid var(--color-border)",
          borderRadius: "10px",
          padding: "2rem",
          textAlign: "center",
          color: "var(--color-text-muted)",
          fontSize: "0.875rem",
        }}
      >
        暂无证据数据
      </div>
    );
  }

  return (
    <div
      style={{
        backgroundColor: "var(--color-bg-secondary)",
        border: "1px solid var(--color-border)",
        borderRadius: "10px",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
      }}
    >
      {/* 头部 */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ fontSize: "0.875rem", fontWeight: 600, margin: 0, color: "var(--color-text-primary)" }}>
          证据列表
        </h3>
        <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
          {evidence.length} 条
        </span>
      </div>

      {/* 分组列表 */}
      {grouped.map((group) => (
        <div key={group.key}>
          {groupBy !== "time" && (
            <div
              style={{
                fontSize: "0.7rem",
                fontWeight: 600,
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: "0.375rem",
                paddingBottom: "0.25rem",
                borderBottom: "1px solid var(--color-border)",
              }}
            >
              {group.key}（{group.items.length}）
            </div>
          )}

          {/* 证据项时间线 */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.375rem",
            }}
          >
            {group.items.map((item, idx) => {
              const sourceColor = SOURCE_TYPE_COLORS[item.source_type] ?? "#64748b";
              const relevanceColor = getRelevanceColor(item.relevance_score);

              return (
                <div
                  key={idx}
                  onClick={() => onItemClick?.(item)}
                  style={{
                    backgroundColor: "var(--color-bg-primary)",
                    borderRadius: "6px",
                    padding: "0.625rem 0.75rem",
                    borderLeft: `3px solid ${sourceColor}`,
                    cursor: onItemClick ? "pointer" : "default",
                    transition: "background-color 0.15s",
                  }}
                  onMouseEnter={(e) => {
                    if (onItemClick) {
                      e.currentTarget.style.backgroundColor = "var(--color-bg-tertiary)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "var(--color-bg-primary)";
                  }}
                >
                  {/* 来源标签 + 时间 */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      marginBottom: "0.25rem",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 600,
                        color: sourceColor,
                      }}
                    >
                      {SOURCE_TYPE_LABELS[item.source_type] ?? item.source_type}
                    </span>
                    {item.symbol && (
                      <span
                        style={{
                          fontSize: "0.7rem",
                          color: "var(--color-text-muted)",
                          fontFamily: "monospace",
                        }}
                      >
                        {item.symbol}
                      </span>
                    )}
                    <span
                      style={{
                        marginLeft: "auto",
                        fontSize: "0.7rem",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {formatTime(item.fetched_at)}
                    </span>
                  </div>

                  {/* 摘要 */}
                  <div
                    style={{
                      fontSize: "0.8125rem",
                      color: "var(--color-text-primary)",
                      lineHeight: 1.4,
                      marginBottom: "0.25rem",
                    }}
                  >
                    {item.summary}
                  </div>

                  {/* 底部：来源标题 + 相关性 */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      fontSize: "0.7rem",
                    }}
                  >
                    {item.source_title && (
                      <span
                        style={{
                          color: "var(--color-text-secondary)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          maxWidth: "60%",
                        }}
                      >
                        {item.source_title}
                      </span>
                    )}
                    {item.source_url && (
                      <a
                        href={item.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          color: "var(--color-info)",
                          textDecoration: "underline",
                          fontSize: "0.7rem",
                        }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        查看原文
                      </a>
                    )}
                    <span
                      style={{
                        marginLeft: "auto",
                        padding: "0.125rem 0.375rem",
                        borderRadius: "3px",
                        fontSize: "0.65rem",
                        fontWeight: 600,
                        color: relevanceColor,
                        backgroundColor: `${relevanceColor}20`,
                      }}
                    >
                      相关性：{getRelevanceLabel(item.relevance_score)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
