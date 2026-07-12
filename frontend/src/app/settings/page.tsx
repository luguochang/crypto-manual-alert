"use client";

import { useState, useCallback } from "react";

/**
 * Settings 页面 - 风险参数配置 + 通知渠道 + Watchlist
 *
 * - 风险参数配置（max_leverage, risk_pct）
 * - 默认分析周期
 * - 通知渠道配置
 * - Watchlist 管理
 *
 * 设计文档 15-frontend-and-config-management.md 第四节。
 * Phase 2 使用本地状态，后续接入 API 持久化。
 */

// ===========================================================================
// 类型定义
// ===========================================================================

interface RiskConfig {
  max_leverage: number;
  risk_pct: number;
  default_horizon: string;
  confidence_threshold: number;
}

interface NotificationConfig {
  bark_enabled: boolean;
  bark_key: string;
  email_enabled: boolean;
  email_address: string;
  notify_on_analysis: boolean;
  notify_on_risk_block: boolean;
  notify_on_outcome: boolean;
}

interface WatchItem {
  symbol: string;
  label: string;
  enabled: boolean;
}

// ===========================================================================
// 初始配置
// ===========================================================================

const INITIAL_RISK: RiskConfig = {
  max_leverage: 2,
  risk_pct: 0.1,
  default_horizon: "4h",
  confidence_threshold: 0.55,
};

const INITIAL_NOTIFICATION: NotificationConfig = {
  bark_enabled: true,
  bark_key: "",
  email_enabled: false,
  email_address: "",
  notify_on_analysis: true,
  notify_on_risk_block: true,
  notify_on_outcome: false,
};

const INITIAL_WATCHLIST: WatchItem[] = [
  { symbol: "BTC-USDT-SWAP", label: "Bitcoin", enabled: true },
  { symbol: "ETH-USDT-SWAP", label: "Ethereum", enabled: true },
  { symbol: "SOL-USDT-SWAP", label: "Solana", enabled: true },
];

const HORIZONS = ["1h", "4h", "12h", "24h"];

// ===========================================================================
// 样式常量
// ===========================================================================

const cardStyle: React.CSSProperties = {
  backgroundColor: "var(--color-bg-secondary)",
  border: "1px solid var(--color-border)",
  borderRadius: "10px",
  padding: "1.25rem",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: "0.875rem",
  fontWeight: 600,
  color: "var(--color-text-primary)",
  marginBottom: "0.75rem",
  paddingBottom: "0.5rem",
  borderBottom: "1px solid var(--color-border)",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.75rem",
  color: "var(--color-text-secondary)",
  marginBottom: "0.25rem",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "0.375rem 0.625rem",
  backgroundColor: "var(--color-bg-tertiary)",
  color: "var(--color-text-primary)",
  border: "1px solid var(--color-border-light)",
  borderRadius: "6px",
  fontSize: "0.8125rem",
  outline: "none",
};

const buttonStyle: React.CSSProperties = {
  padding: "0.5rem 1.25rem",
  backgroundColor: "var(--color-brand)",
  color: "#0f172a",
  border: "none",
  borderRadius: "6px",
  fontWeight: 600,
  fontSize: "0.8125rem",
  cursor: "pointer",
};

// ===========================================================================
// 主组件
// ===========================================================================

export default function SettingsPage() {
  const [risk, setRisk] = useState<RiskConfig>(INITIAL_RISK);
  const [notif, setNotif] = useState<NotificationConfig>(INITIAL_NOTIFICATION);
  const [watchlist, setWatchlist] = useState<WatchItem[]>(INITIAL_WATCHLIST);
  const [newSymbol, setNewSymbol] = useState("");
  const [saved, setSaved] = useState(false);

  const handleSave = useCallback(() => {
    // Phase 2 占位：后续调用 API 持久化
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }, []);

  const handleAddSymbol = useCallback(() => {
    if (!newSymbol.trim()) return;
    const symbol = newSymbol.trim().toUpperCase();
    if (watchlist.some((w) => w.symbol === symbol)) return;
    setWatchlist((prev) => [
      ...prev,
      { symbol, label: symbol.replace("-USDT-SWAP", ""), enabled: true },
    ]);
    setNewSymbol("");
  }, [newSymbol, watchlist]);

  const handleRemoveSymbol = useCallback((symbol: string) => {
    setWatchlist((prev) => prev.filter((w) => w.symbol !== symbol));
  }, []);

  const handleToggleSymbol = useCallback((symbol: string) => {
    setWatchlist((prev) =>
      prev.map((w) =>
        w.symbol === symbol ? { ...w, enabled: !w.enabled } : w
      )
    );
  }, []);

  return (
    <div
      style={{
        padding: "1.5rem 2rem",
        maxWidth: "800px",
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
            设置
          </h1>
          <p
            style={{
              fontSize: "0.8125rem",
              color: "var(--color-text-secondary)",
            }}
          >
            风险参数、通知渠道、Watchlist 管理
          </p>
        </div>
        <button
          onClick={handleSave}
          style={{
            ...buttonStyle,
            backgroundColor: saved
              ? "var(--color-success)"
              : "var(--color-brand)",
          }}
        >
          {saved ? "已保存" : "保存配置"}
        </button>
      </div>

      {/* 风险参数 */}
      <section style={{ ...cardStyle, marginBottom: "1rem" }}>
        <h2 style={sectionTitleStyle}>风险参数</h2>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "1rem",
          }}
        >
          {/* Max Leverage */}
          <div>
            <div style={labelStyle}>
              最大杠杆（硬性上限 2x）
            </div>
            <select
              value={risk.max_leverage}
              onChange={(e) =>
                setRisk({ ...risk, max_leverage: Number(e.target.value) })
              }
              style={inputStyle}
            >
              <option value={1}>1x（无杠杆）</option>
              <option value={2}>2x</option>
            </select>
          </div>

          {/* Risk Pct */}
          <div>
            <div style={labelStyle}>
              单笔风险占比（上限 25%）
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <input
                type="range"
                min={0.01}
                max={0.25}
                step={0.01}
                value={risk.risk_pct}
                onChange={(e) =>
                  setRisk({ ...risk, risk_pct: Number(e.target.value) })
                }
                style={{ flex: 1 }}
              />
              <span
                style={{
                  fontSize: "0.8125rem",
                  color: "var(--color-text-primary)",
                  fontFamily: "monospace",
                  minWidth: "45px",
                  textAlign: "right",
                }}
              >
                {(risk.risk_pct * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          {/* Default Horizon */}
          <div>
            <div style={labelStyle}>默认分析周期</div>
            <select
              value={risk.default_horizon}
              onChange={(e) =>
                setRisk({ ...risk, default_horizon: e.target.value })
              }
              style={inputStyle}
            >
              {HORIZONS.map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </div>

          {/* Confidence Threshold */}
          <div>
            <div style={labelStyle}>最低置信度阈值</div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <input
                type="range"
                min={0.3}
                max={0.9}
                step={0.05}
                value={risk.confidence_threshold}
                onChange={(e) =>
                  setRisk({
                    ...risk,
                    confidence_threshold: Number(e.target.value),
                  })
                }
                style={{ flex: 1 }}
              />
              <span
                style={{
                  fontSize: "0.8125rem",
                  color: "var(--color-text-primary)",
                  fontFamily: "monospace",
                  minWidth: "45px",
                  textAlign: "right",
                }}
              >
                {(risk.confidence_threshold * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 通知渠道 */}
      <section style={{ ...cardStyle, marginBottom: "1rem" }}>
        <h2 style={sectionTitleStyle}>通知渠道</h2>

        {/* Bark */}
        <div style={{ marginBottom: "1rem" }}>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              cursor: "pointer",
              marginBottom: "0.5rem",
            }}
          >
            <input
              type="checkbox"
              checked={notif.bark_enabled}
              onChange={(e) =>
                setNotif({ ...notif, bark_enabled: e.target.checked })
              }
            />
            <span
              style={{
                fontSize: "0.8125rem",
                color: "var(--color-text-primary)",
              }}
            >
              Bark 推送（iOS）
            </span>
          </label>
          {notif.bark_enabled && (
            <input
              type="text"
              value={notif.bark_key}
              onChange={(e) =>
                setNotif({ ...notif, bark_key: e.target.value })
              }
              placeholder="Bark Device Key"
              style={inputStyle}
            />
          )}
        </div>

        {/* Email */}
        <div style={{ marginBottom: "1rem" }}>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              cursor: "pointer",
              marginBottom: "0.5rem",
            }}
          >
            <input
              type="checkbox"
              checked={notif.email_enabled}
              onChange={(e) =>
                setNotif({ ...notif, email_enabled: e.target.checked })
              }
            />
            <span
              style={{
                fontSize: "0.8125rem",
                color: "var(--color-text-primary)",
              }}
            >
              邮件通知
            </span>
          </label>
          {notif.email_enabled && (
            <input
              type="email"
              value={notif.email_address}
              onChange={(e) =>
                setNotif({ ...notif, email_address: e.target.value })
              }
              placeholder="your@email.com"
              style={inputStyle}
            />
          )}
        </div>

        {/* 通知事件类型 */}
        <div>
          <div style={labelStyle}>通知事件</div>
          {[
            {
              key: "notify_on_analysis" as const,
              label: "分析完成时通知",
            },
            {
              key: "notify_on_risk_block" as const,
              label: "风控拦截时通知",
            },
            {
              key: "notify_on_outcome" as const,
              label: "成熟窗口结果通知",
            },
          ].map((item) => (
            <label
              key={item.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: "pointer",
                marginBottom: "0.375rem",
              }}
            >
              <input
                type="checkbox"
                checked={notif[item.key]}
                onChange={(e) =>
                  setNotif({ ...notif, [item.key]: e.target.checked })
                }
              />
              <span
                style={{
                  fontSize: "0.75rem",
                  color: "var(--color-text-secondary)",
                }}
              >
                {item.label}
              </span>
            </label>
          ))}
        </div>
      </section>

      {/* Watchlist 管理 */}
      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Watchlist 管理</h2>

        {/* 添加新标的 */}
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            marginBottom: "0.75rem",
          }}
        >
          <input
            type="text"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAddSymbol();
            }}
            placeholder="如 BTC-USDT-SWAP"
            style={inputStyle}
          />
          <button
            onClick={handleAddSymbol}
            style={{
              ...buttonStyle,
              padding: "0.375rem 0.875rem",
              whiteSpace: "nowrap",
            }}
          >
            添加
          </button>
        </div>

        {/* Watchlist 列表 */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.375rem",
          }}
        >
          {watchlist.map((w) => (
            <div
              key={w.symbol}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                padding: "0.5rem 0.625rem",
                backgroundColor: "var(--color-bg-primary)",
                borderRadius: "6px",
              }}
            >
              <input
                type="checkbox"
                checked={w.enabled}
                onChange={() => handleToggleSymbol(w.symbol)}
              />
              <div style={{ flex: 1 }}>
                <span
                  style={{
                    fontSize: "0.8125rem",
                    color: "var(--color-text-primary)",
                  }}
                >
                  {w.label}
                </span>
                <span
                  style={{
                    fontSize: "0.7rem",
                    color: "var(--color-text-muted)",
                    marginLeft: "0.5rem",
                    fontFamily: "monospace",
                  }}
                >
                  {w.symbol}
                </span>
              </div>
              <button
                onClick={() => handleRemoveSymbol(w.symbol)}
                style={{
                  padding: "0.25rem 0.5rem",
                  backgroundColor: "transparent",
                  color: "var(--color-error)",
                  border: "1px solid var(--color-error)",
                  borderRadius: "4px",
                  fontSize: "0.7rem",
                  cursor: "pointer",
                }}
              >
                移除
              </button>
            </div>
          ))}
        </div>

        <div
          style={{
            fontSize: "0.65rem",
            color: "var(--color-text-muted)",
            marginTop: "0.75rem",
            paddingTop: "0.75rem",
            borderTop: "1px solid var(--color-border)",
          }}
        >
          白名单中的标的才允许分析。移除后该标的将无法发起新分析。
        </div>
      </section>
    </div>
  );
}
