"use client";

import { useState } from "react";
import type { MarketSnapshot } from "@/types/analysis";

/**
 * 行情快照展示组件
 *
 * 展示当前市场行情数据，包含：
 * - 最新价、标记价、指数价
 * - 买卖盘摘要
 * - 资金费率、持仓量
 * - 数据来源等级和获取时间
 * - 可选的详细数据展开（K线、深度订单簿）
 * - 刷新按钮
 *
 * Props 接口来源：15-frontend-and-config-management.md 第 1.2 节
 */

export interface MarketSnapshotProps {
  snapshot: MarketSnapshot;
  showDetails?: boolean;
  onRefresh?: () => void;
}

function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function formatVolume(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(2)}K`;
  return value.toFixed(2);
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

const SOURCE_LABELS: Record<string, string> = {
  exchange_native: "交易所原生",
  web_derived: "网页推导",
};

export function MarketSnapshot({
  snapshot,
  showDetails: showDetailsProp,
  onRefresh,
}: MarketSnapshotProps) {
  const [internalShowDetails, setInternalShowDetails] = useState(false);
  const showDetails = showDetailsProp ?? internalShowDetails;

  const unavailable = new Set(snapshot.unavailable_fields ?? []);
  const isUnavailable = (field: string) => unavailable.has(field);

  // 基本数据点
  const dataPoints: Array<{ label: string; value: string; unavailable?: boolean }> = [
    {
      label: "最新价",
      value: formatPrice(snapshot.ticker?.last),
      unavailable: isUnavailable("ticker"),
    },
    {
      label: "标记价",
      value: formatPrice(snapshot.mark_price),
      unavailable: isUnavailable("mark_price"),
    },
    {
      label: "指数价",
      value: formatPrice(snapshot.index_price),
      unavailable: isUnavailable("index_price"),
    },
    {
      label: "买一价",
      value: formatPrice(snapshot.ticker?.bid),
      unavailable: isUnavailable("ticker"),
    },
    {
      label: "卖一价",
      value: formatPrice(snapshot.ticker?.ask),
      unavailable: isUnavailable("ticker"),
    },
    {
      label: "24h 成交量",
      value: formatVolume(snapshot.ticker?.vol_24h),
      unavailable: isUnavailable("ticker"),
    },
    {
      label: "资金费率",
      value: snapshot.funding_rate != null ? `${(snapshot.funding_rate * 100).toFixed(4)}%` : "-",
      unavailable: isUnavailable("funding_rate"),
    },
    {
      label: "持仓量",
      value: formatVolume(snapshot.open_interest),
      unavailable: isUnavailable("open_interest"),
    },
  ];

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
      {/* === 头部 === */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <h3 style={{ fontSize: "0.875rem", fontWeight: 600, margin: 0, color: "var(--color-text-primary)" }}>
            行情快照
          </h3>
          <span
            style={{
              fontSize: "0.75rem",
              color: "var(--color-brand)",
              fontFamily: "monospace",
            }}
          >
            {snapshot.symbol}
          </span>
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            style={{
              padding: "0.25rem 0.625rem",
              backgroundColor: "var(--color-bg-tertiary)",
              color: "var(--color-text-secondary)",
              border: "1px solid var(--color-border-light)",
              borderRadius: "4px",
              fontSize: "0.75rem",
              cursor: "pointer",
            }}
          >
            刷新
          </button>
        )}
      </div>

      {/* === 数据来源和时间 === */}
      <div style={{ display: "flex", gap: "0.75rem", fontSize: "0.7rem", color: "var(--color-text-muted)" }}>
        <span>来源：{SOURCE_LABELS[snapshot.source_level] ?? snapshot.source_level}</span>
        {snapshot.data_fetched_at && (
          <span>获取时间：{formatTime(snapshot.data_fetched_at)}</span>
        )}
      </div>

      {/* === 价格网格 === */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.5rem",
        }}
      >
        {dataPoints.map((dp) => (
          <div
            key={dp.label}
            style={{
              backgroundColor: "var(--color-bg-primary)",
              borderRadius: "6px",
              padding: "0.5rem 0.625rem",
            }}
          >
            <div style={{ fontSize: "0.7rem", color: "var(--color-text-muted)", marginBottom: "0.125rem" }}>
              {dp.label}
            </div>
            <div
              style={{
                fontSize: "0.875rem",
                fontWeight: 600,
                fontFamily: "monospace",
                color: dp.unavailable
                  ? "var(--color-text-muted)"
                  : "var(--color-text-primary)",
              }}
            >
              {dp.unavailable ? "不可用" : dp.value}
            </div>
          </div>
        ))}
      </div>

      {/* === 不可用字段提示 === */}
      {unavailable.size > 0 && (
        <div
          style={{
            fontSize: "0.7rem",
            color: "var(--color-warning)",
            padding: "0.375rem 0.5rem",
            backgroundColor: "rgba(245, 158, 11, 0.08)",
            borderRadius: "4px",
          }}
        >
          不可用字段：{Array.from(unavailable).join(", ")}
        </div>
      )}

      {/* === 详细数据展开 === */}
      {showDetailsProp === undefined && (
        <button
          onClick={() => setInternalShowDetails((v) => !v)}
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
          {internalShowDetails ? "收起详情" : "展开详情"}
        </button>
      )}

      {showDetails && (
        <>
          {/* 订单簿摘要 */}
          {!isUnavailable("order_book") && snapshot.order_book && (
            <div
              style={{
                backgroundColor: "var(--color-bg-primary)",
                borderRadius: "6px",
                padding: "0.625rem",
              }}
            >
              <div style={{ fontSize: "0.7rem", color: "var(--color-text-muted)", marginBottom: "0.375rem" }}>
                订单簿摘要
              </div>
              <div style={{ display: "flex", gap: "1rem", fontSize: "0.75rem" }}>
                <div>
                  <span style={{ color: "var(--color-success)" }}>买盘深度：</span>
                  <span style={{ fontFamily: "monospace", color: "var(--color-text-primary)" }}>
                    {snapshot.order_book.bids?.length ?? 0} 档
                  </span>
                  {snapshot.order_book.bids?.[0] && (
                    <span style={{ marginLeft: "0.375rem", fontFamily: "monospace", color: "var(--color-text-secondary)" }}>
                      买一：{formatPrice(snapshot.order_book.bids[0][0])} x {snapshot.order_book.bids[0][1]}
                    </span>
                  )}
                </div>
                <div>
                  <span style={{ color: "var(--color-error)" }}>卖盘深度：</span>
                  <span style={{ fontFamily: "monospace", color: "var(--color-text-primary)" }}>
                    {snapshot.order_book.asks?.length ?? 0} 档
                  </span>
                  {snapshot.order_book.asks?.[0] && (
                    <span style={{ marginLeft: "0.375rem", fontFamily: "monospace", color: "var(--color-text-secondary)" }}>
                      卖一：{formatPrice(snapshot.order_book.asks[0][0])} x {snapshot.order_book.asks[0][1]}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* K 线摘要 */}
          {!isUnavailable("candles") && snapshot.candles && snapshot.candles.length > 0 && (
            <div
              style={{
                backgroundColor: "var(--color-bg-primary)",
                borderRadius: "6px",
                padding: "0.625rem",
              }}
            >
              <div style={{ fontSize: "0.7rem", color: "var(--color-text-muted)", marginBottom: "0.375rem" }}>
                最近 K 线（共 {snapshot.candles.length} 根）
              </div>
              {snapshot.candles.slice(-3).map((c, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    gap: "0.75rem",
                    fontSize: "0.7rem",
                    fontFamily: "monospace",
                    color: "var(--color-text-secondary)",
                    marginBottom: "0.125rem",
                  }}
                >
                  <span>{formatTime(c.ts)}</span>
                  <span>O:{formatPrice(c.o)}</span>
                  <span>H:{formatPrice(c.h)}</span>
                  <span>L:{formatPrice(c.l)}</span>
                  <span>C:{formatPrice(c.c)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
