"use client";

import { useState } from "react";
import type { RiskVerdict } from "@/types/analysis";

/**
 * 风险门禁检查器组件
 *
 * 展示风控裁决结果，包含：
 * - 整体裁决状态（通过/阻断）
 * - 阻断原因列表
 * - 警告列表
 * - 置信度上限
 * - 可展开的规则命中详情
 *
 * Props 接口来源：15-frontend-and-config-management.md 第 1.2 节
 */

export interface RiskInspectorProps {
  verdict: RiskVerdict;
  ruleHits: Array<{
    rule_id: string;
    rule_type: "blocking" | "warn";
    reason: string;
    details: Record<string, unknown>;
  }>;
  expanded?: boolean;
}

/** 规则中文名称映射 */
const RULE_LABELS: Record<string, string> = {
  manual_execution_required: "规则 1：人工执行",
  allowed_symbol: "规则 2：品种白名单",
  plan_not_expired: "规则 3：计划未过期",
  opening_has_stop: "规则 4：开仓有止损",
  opening_has_entry: "规则 5：开仓有入场价",
  opening_has_invalidation: "规则 6：开仓有失效条件",
  core_execution_data: "规则 7：核心执行数据",
  risk_pct_max: "规则 8：风险占比",
  leverage_max: "规则 9：杠杆上限",
  confidence_cap: "规则 10：置信度上限",
  data_freshness: "规则 11：数据新鲜度",
  auto_order_disabled: "规则 12：禁止自动下单",
  app_mode: "规则 13：应用模式",
  market_data_unavailable: "规则 14：数据缺失警告",
};

export function RiskInspector({
  verdict,
  ruleHits,
  expanded: expandedProp,
}: RiskInspectorProps) {
  const [internalExpanded, setInternalExpanded] = useState(false);
  const expanded = expandedProp ?? internalExpanded;

  const blockingHits = ruleHits.filter((h) => h.rule_type === "blocking");
  const warnHits = ruleHits.filter((h) => h.rule_type === "warn");

  // 整体状态
  const statusConfig = verdict.allowed
    ? {
        label: "风控通过",
        color: "#22c55e",
        bgColor: "rgba(34, 197, 94, 0.1)",
        borderColor: "rgba(34, 197, 94, 0.3)",
        icon: "✓",
      }
    : {
        label: "风控阻断",
        color: "#ef4444",
        bgColor: "rgba(239, 68, 68, 0.1)",
        borderColor: "rgba(239, 68, 68, 0.3)",
        icon: "✕",
      };

  return (
    <div
      style={{
        backgroundColor: "var(--color-bg-secondary)",
        border: `1px solid ${statusConfig.borderColor}`,
        borderRadius: "10px",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
      }}
    >
      {/* === 头部：整体裁决 === */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.625rem",
          padding: "0.625rem 0.75rem",
          backgroundColor: statusConfig.bgColor,
          borderRadius: "6px",
        }}
      >
        <span
          style={{
            fontSize: "1.125rem",
            fontWeight: 700,
            color: statusConfig.color,
            width: "1.5rem",
            height: "1.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: "50%",
            backgroundColor: `${statusConfig.color}20`,
          }}
        >
          {statusConfig.icon}
        </span>
        <span
          style={{
            fontSize: "0.9375rem",
            fontWeight: 600,
            color: statusConfig.color,
          }}
        >
          {statusConfig.label}
        </span>
        {/* 置信度上限 */}
        <span
          style={{
            marginLeft: "auto",
            fontSize: "0.75rem",
            color: "var(--color-text-muted)",
          }}
        >
          置信度上限：
          <span
            style={{
              fontFamily: "monospace",
              fontWeight: 600,
              color:
                verdict.confidence_cap < 0.7
                  ? "var(--color-warning)"
                  : "var(--color-text-primary)",
            }}
          >
            {(verdict.confidence_cap * 100).toFixed(0)}%
          </span>
        </span>
      </div>

      {/* === 阻断原因 === */}
      {verdict.blocked_reasons.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "var(--color-error)",
              marginBottom: "0.375rem",
              display: "flex",
              alignItems: "center",
              gap: "0.25rem",
            }}
          >
            <span>阻断原因（{verdict.blocked_reasons.length}）</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {verdict.blocked_reasons.map((reason, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  gap: "0.5rem",
                  padding: "0.375rem 0.5rem",
                  backgroundColor: "rgba(239, 68, 68, 0.06)",
                  borderRadius: "4px",
                  fontSize: "0.75rem",
                  color: "var(--color-text-secondary)",
                  lineHeight: 1.4,
                }}
              >
                <span style={{ color: "var(--color-error)", flexShrink: 0 }}>✕</span>
                <span>{reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* === 警告 === */}
      {verdict.warnings.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "var(--color-warning)",
              marginBottom: "0.375rem",
            }}
          >
            警告（{verdict.warnings.length}）
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {verdict.warnings.map((warning, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  gap: "0.5rem",
                  padding: "0.375rem 0.5rem",
                  backgroundColor: "rgba(245, 158, 11, 0.06)",
                  borderRadius: "4px",
                  fontSize: "0.75rem",
                  color: "var(--color-text-secondary)",
                  lineHeight: 1.4,
                }}
              >
                <span style={{ color: "var(--color-warning)", flexShrink: 0 }}>⚠</span>
                <span>{warning}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* === 规则命中详情（可展开） === */}
      {ruleHits.length > 0 && expandedProp === undefined && (
        <button
          onClick={() => setInternalExpanded((v) => !v)}
          style={{
            padding: "0.375rem",
            backgroundColor: "transparent",
            color: "var(--color-text-secondary)",
            border: "1px solid var(--color-border)",
            borderRadius: "4px",
            fontSize: "0.75rem",
            cursor: "pointer",
            textAlign: "center",
          }}
        >
          {internalExpanded ? "收起规则详情" : `查看规则详情（${ruleHits.length} 条命中）`}
        </button>
      )}

      {expanded && ruleHits.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "0.7rem",
              fontWeight: 600,
              color: "var(--color-text-muted)",
              marginBottom: "0.375rem",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            规则命中详情
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {ruleHits.map((hit, idx) => {
              const isBlock = hit.rule_type === "blocking";
              const ruleLabel = RULE_LABELS[hit.rule_id] ?? hit.rule_id;

              return (
                <div
                  key={idx}
                  style={{
                    padding: "0.5rem 0.625rem",
                    backgroundColor: "var(--color-bg-primary)",
                    borderRadius: "4px",
                    borderLeft: `3px solid ${isBlock ? "var(--color-error)" : "var(--color-warning)"}`,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.375rem",
                      marginBottom: "0.25rem",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "0.65rem",
                        fontWeight: 700,
                        padding: "0.0625rem 0.3rem",
                        borderRadius: "3px",
                        textTransform: "uppercase",
                        color: isBlock ? "var(--color-error)" : "var(--color-warning)",
                        backgroundColor: isBlock
                          ? "rgba(239, 68, 68, 0.15)"
                          : "rgba(245, 158, 11, 0.15)",
                      }}
                    >
                      {isBlock ? "阻断" : "警告"}
                    </span>
                    <span
                      style={{
                        fontSize: "0.75rem",
                        fontWeight: 500,
                        color: "var(--color-text-primary)",
                      }}
                    >
                      {ruleLabel}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: "0.7rem",
                      color: "var(--color-text-secondary)",
                      lineHeight: 1.4,
                    }}
                  >
                    {hit.reason}
                  </div>
                  {Object.keys(hit.details).length > 0 && (
                    <pre
                      className="json-block"
                      style={{
                        fontSize: "0.65rem",
                        color: "var(--color-text-muted)",
                        marginTop: "0.25rem",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {JSON.stringify(hit.details, null, 2)}
                    </pre>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* === 无命中时显示全通过 === */}
      {ruleHits.length === 0 && verdict.allowed && (
        <div
          style={{
            padding: "0.625rem",
            textAlign: "center",
            fontSize: "0.75rem",
            color: "var(--color-text-muted)",
          }}
        >
          所有 14 条规则均通过，无命中记录。
        </div>
      )}
    </div>
  );
}
