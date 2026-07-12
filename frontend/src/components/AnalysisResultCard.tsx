"use client";

import { useState } from "react";
import type { AnalysisResult } from "@/types/analysis";

/**
 * 分析结论卡片
 *
 * 展示 Agent 生成的市场分析结论，包含：
 * - 方向徽章（做多/做空/观望）
 * - 动作 + 标的 + 周期 + 概率
 * - 价位表（参考价/入场/止损/目标1/目标2/过期时间）
 * - HITL 按钮：确认 / 拒绝 / 编辑后确认
 * - "系统不会自动下单" 安全提醒
 *
 * Props 接口来源：15-frontend-and-config-management.md 第 1.2 节
 */

export interface AnalysisResultCardProps {
  result: AnalysisResult;
  onApprove: () => void;
  onReject: () => void;
  onEdit: (edits: Partial<AnalysisResult>) => void;
  expiresAt: string;
  isExpired: boolean;
}

/** 方向 -> 徽章配置 */
const DIRECTION_BADGE: Record<
  string,
  { label: string; bg: string; text: string }
> = {
  long: { label: "做多", bg: "rgba(34, 197, 94, 0.15)", text: "#22c55e" },
  short: { label: "做空", bg: "rgba(239, 68, 68, 0.15)", text: "#ef4444" },
  neutral: { label: "观望", bg: "rgba(148, 163, 184, 0.15)", text: "#94a3b8" },
};

/** 动作中文标签 */
const ACTION_LABELS: Record<string, string> = {
  open_long: "开多",
  open_short: "开空",
  hold_long: "继续持多",
  hold_short: "继续持空",
  close_long: "平多",
  close_short: "平空",
  flip_long_to_short: "多转空",
  flip_short_to_long: "空转多",
  trigger_long: "触发做多",
  trigger_short: "触发做空",
  no_trade: "暂不操作",
};

/** 仓位等级中文标签 */
const POSITION_LABELS: Record<string, string> = {
  light: "轻仓",
  standard: "标准仓",
  heavy: "重仓",
};

function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function AnalysisResultCard({
  result,
  onApprove,
  onReject,
  onEdit,
  expiresAt,
  isExpired,
}: AnalysisResultCardProps) {
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState<{
    entry_trigger: string;
    stop_price: string;
    target_1: string;
    target_2: string;
  }>({
    entry_trigger: result.entry_trigger?.toString() ?? "",
    stop_price: result.stop_price?.toString() ?? "",
    target_1: result.target_1?.toString() ?? "",
    target_2: result.target_2?.toString() ?? "",
  });

  const badge = DIRECTION_BADGE[result.direction] ?? DIRECTION_BADGE.neutral;
  const actionLabel = ACTION_LABELS[result.main_action] ?? result.main_action;
  const positionLabel = POSITION_LABELS[result.position_size_class] ?? result.position_size_class;

  const handleSaveEdit = () => {
    const edits: Partial<AnalysisResult> = {};
    if (editValues.entry_trigger) edits.entry_trigger = parseFloat(editValues.entry_trigger);
    if (editValues.stop_price) edits.stop_price = parseFloat(editValues.stop_price);
    if (editValues.target_1) edits.target_1 = parseFloat(editValues.target_1);
    if (editValues.target_2) edits.target_2 = parseFloat(editValues.target_2);
    onEdit(edits);
    setEditing(false);
  };

  // 价位表行
  const priceRows: Array<{ label: string; value: string; color?: string }> = [
    { label: "参考价", value: formatPrice(result.reference_price) },
    { label: "入场触发", value: formatPrice(result.entry_trigger) },
    { label: "止损价", value: formatPrice(result.stop_price), color: "#ef4444" },
    { label: "目标 1", value: formatPrice(result.target_1), color: "#22c55e" },
    { label: "目标 2", value: formatPrice(result.target_2), color: "#22c55e" },
    {
      label: "过期时间",
      value: formatDateTime(expiresAt),
      color: isExpired ? "#ef4444" : "#94a3b8",
    },
  ];

  return (
    <div
      style={{
        backgroundColor: "var(--color-bg-secondary)",
        border: "1px solid var(--color-border)",
        borderRadius: "12px",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      {/* === 头部：方向徽章 + 动作 + 标的 === */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <span
          style={{
            backgroundColor: badge.bg,
            color: badge.text,
            padding: "0.25rem 0.625rem",
            borderRadius: "6px",
            fontSize: "0.875rem",
            fontWeight: 700,
          }}
        >
          {badge.label}
        </span>
        <span style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
          {actionLabel}
        </span>
        <span style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)" }}>
          {result.symbol}
        </span>
        <span
          style={{
            fontSize: "0.75rem",
            color: "var(--color-text-muted)",
            backgroundColor: "var(--color-bg-tertiary)",
            padding: "0.125rem 0.375rem",
            borderRadius: "4px",
          }}
        >
          {result.horizon}
        </span>
        {/* 概率 */}
        <span
          style={{
            marginLeft: "auto",
            fontSize: "0.875rem",
            fontWeight: 600,
            color: "var(--color-brand)",
          }}
        >
          胜率 {formatPercent(result.probability)}
        </span>
      </div>

      {/* === 体制分类 + 仓位 + 杠杆 === */}
      <div style={{ display: "flex", gap: "1rem", fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
        <span>体制：{result.regime}</span>
        <span>仓位：{positionLabel}</span>
        <span>最大杠杆：{result.max_leverage}x</span>
        <span>风险占比：{formatPercent(result.risk_pct)}</span>
      </div>

      {/* === 价位表 === */}
      <div
        style={{
          backgroundColor: "var(--color-bg-primary)",
          borderRadius: "8px",
          padding: "0.75rem",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
          <tbody>
            {priceRows.map((row) => (
              <tr key={row.label} style={{ borderBottom: "1px solid var(--color-border)" }}>
                <td
                  style={{
                    padding: "0.375rem 0.5rem",
                    color: "var(--color-text-muted)",
                    width: "40%",
                  }}
                >
                  {row.label}
                </td>
                <td
                  style={{
                    padding: "0.375rem 0.5rem",
                    color: row.color ?? "var(--color-text-primary)",
                    fontWeight: 500,
                    fontFamily: "monospace",
                  }}
                >
                  {row.value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* === 编辑模式 === */}
      {editing && (
        <div
          style={{
            backgroundColor: "var(--color-bg-primary)",
            borderRadius: "8px",
            padding: "0.75rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
          }}
        >
          <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text-secondary)" }}>
            编辑价位参数
          </div>
          {(
            [
              ["entry_trigger", "入场触发"],
              ["stop_price", "止损价"],
              ["target_1", "目标 1"],
              ["target_2", "目标 2"],
            ] as const
          ).map(([key, label]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <label style={{ fontSize: "0.75rem", color: "var(--color-text-muted)", width: "5rem" }}>
                {label}
              </label>
              <input
                type="number"
                value={editValues[key]}
                onChange={(e) =>
                  setEditValues((prev) => ({ ...prev, [key]: e.target.value }))
                }
                style={{
                  flex: 1,
                  padding: "0.375rem 0.5rem",
                  backgroundColor: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border-light)",
                  borderRadius: "4px",
                  color: "var(--color-text-primary)",
                  fontSize: "0.8125rem",
                  fontFamily: "monospace",
                  outline: "none",
                }}
              />
            </div>
          ))}
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.25rem" }}>
            <button
              onClick={handleSaveEdit}
              style={{
                padding: "0.375rem 0.875rem",
                backgroundColor: "var(--color-brand)",
                color: "#0f172a",
                border: "none",
                borderRadius: "4px",
                fontWeight: 600,
                fontSize: "0.8125rem",
                cursor: "pointer",
              }}
            >
              保存编辑
            </button>
            <button
              onClick={() => setEditing(false)}
              style={{
                padding: "0.375rem 0.875rem",
                backgroundColor: "var(--color-bg-tertiary)",
                color: "var(--color-text-primary)",
                border: "1px solid var(--color-border-light)",
                borderRadius: "4px",
                fontSize: "0.8125rem",
                cursor: "pointer",
              }}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* === HITL 操作按钮 === */}
      {!editing && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            onClick={onApprove}
            disabled={isExpired}
            style={{
              flex: 1,
              padding: "0.5rem",
              backgroundColor: isExpired ? "var(--color-bg-tertiary)" : "var(--color-success)",
              color: isExpired ? "var(--color-text-muted)" : "#0f172a",
              border: "none",
              borderRadius: "6px",
              fontWeight: 600,
              fontSize: "0.875rem",
              cursor: isExpired ? "not-allowed" : "pointer",
              opacity: isExpired ? 0.6 : 1,
            }}
          >
            确认
          </button>
          <button
            onClick={onReject}
            style={{
              flex: 1,
              padding: "0.5rem",
              backgroundColor: "rgba(239, 68, 68, 0.15)",
              color: "var(--color-error)",
              border: "1px solid var(--color-error)",
              borderRadius: "6px",
              fontWeight: 600,
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            拒绝
          </button>
          <button
            onClick={() => setEditing(true)}
            disabled={isExpired}
            style={{
              flex: 1,
              padding: "0.5rem",
              backgroundColor: "var(--color-bg-tertiary)",
              color: isExpired ? "var(--color-text-muted)" : "var(--color-text-primary)",
              border: "1px solid var(--color-border-light)",
              borderRadius: "6px",
              fontWeight: 500,
              fontSize: "0.875rem",
              cursor: isExpired ? "not-allowed" : "pointer",
              opacity: isExpired ? 0.6 : 1,
            }}
          >
            编辑后确认
          </button>
        </div>
      )}

      {/* === 安全提醒 === */}
      <div
        style={{
          padding: "0.5rem 0.75rem",
          backgroundColor: "rgba(245, 158, 11, 0.08)",
          border: "1px solid rgba(245, 158, 11, 0.3)",
          borderRadius: "6px",
          fontSize: "0.75rem",
          color: "var(--color-brand)",
          display: "flex",
          alignItems: "center",
          gap: "0.375rem",
        }}
      >
        <span>⚠</span>
        <span>系统不会自动下单。请在 OKX 人工核对后手动操作。</span>
      </div>

      {/* === 过期提示 === */}
      {isExpired && (
        <div
          style={{
            padding: "0.5rem 0.75rem",
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            border: "1px solid var(--color-error)",
            borderRadius: "6px",
            fontSize: "0.75rem",
            color: "var(--color-error)",
          }}
        >
          此分析已过期，请重新触发分析获取最新建议。
        </div>
      )}
    </div>
  );
}
