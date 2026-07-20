"use client";

import { ArrowUpRight, BookOpen, CircleAlert, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listArtifacts, ProductApiError } from "@/lib/api/product-client";
import type { ArtifactLibraryItem } from "@/lib/schemas/product-api";

const actionLabels: Record<NonNullable<ArtifactLibraryItem["main_action"]>, string> = {
  open_long: "开多",
  open_short: "开空",
  hold_long: "持有多头",
  hold_short: "持有空头",
  close_long: "平多",
  close_short: "平空",
  flip_long_to_short: "多转空",
  flip_short_to_long: "空转多",
  trigger_long: "等待多头触发",
  trigger_short: "等待空头触发",
  no_trade: "暂不操作",
};

const statusLabels: Record<ArtifactLibraryItem["status"], string> = {
  draft: "草稿",
  streaming: "生成中",
  committed: "已保存",
  failed: "生成失败",
};

export function ArtifactLibrarySurface() {
  const [items, setItems] = useState<ArtifactLibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const response = await listArtifacts(50);
      setItems(response.items);
    } catch (reason) {
      setError(
        reason instanceof ProductApiError
          ? reason.message
          : "无法读取报告资料库，请稍后重试。",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void listArtifacts(50)
      .then((response) => {
        if (active) setItems(response.items);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof ProductApiError
            ? reason.message
            : "无法读取报告资料库，请稍后重试。",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="work-page runs-page library-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Library / Reports</p>
          <h1>报告资料库</h1>
          <p>回看已持久化的分析与深度研究报告，以及对应的完整来源。</p>
        </div>
        <span className="boundary-label list-meta-label">
          <BookOpen size={17} aria-hidden="true" />
          历史报告
        </span>
      </header>

      {loading ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>正在读取报告</h2><p>正在同步当前工作区的持久化 Artifact 版本。</p></div>
        </section>
      ) : null}

      {error ? (
        <section className="request-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div><h2>报告读取失败</h2><p>{error}</p></div>
          <button className="submit-button" type="button" onClick={() => void reload()}>
            <RefreshCw size={17} aria-hidden="true" />
            重新读取
          </button>
        </section>
      ) : null}

      {!loading && !error && items.length === 0 ? (
        <section className="empty-work-state" aria-label="暂无持久化报告">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>暂无持久化报告</h2><p>完成一项分析后，报告版本会自动出现在这里。</p></div>
        </section>
      ) : null}

      {!loading && !error && items.length > 0 ? (
        <section className="runs-list-section" aria-label="持久化报告列表">
          <div className="record-list-head" aria-hidden="true">
            <span>标的</span>
            <span>报告 / 版本</span>
            <span>状态 / 结果</span>
            <span>打开</span>
          </div>
          <ol className="runs-list">
            {items.map((item) => {
              const symbol = item.symbol.replace("-USDT-SWAP", "");
              return (
                <li key={item.artifact_version_id}>
                  <Link
                    className="run-row library-row"
                    href={`/artifacts/${item.artifact_id}?version_number=${item.version_number}`}
                    prefetch={false}
                    data-status={item.status}
                  >
                    <span className="run-symbol">{symbol}</span>
                    <span className="run-summary">
                      <strong>{item.horizon} · 报告 v{item.version_number}</strong>
                      <small>{formatDateTime(item.created_at)} · {item.schema_version}</small>
                    </span>
                    <span className="run-outcome">
                      <strong>{statusLabels[item.status]}</strong>
                      <small>{item.artifact_type === "deep_research_report"
                        ? "深度研究报告"
                        : item.main_action ? actionLabels[item.main_action] : "暂无最终动作"}</small>
                    </span>
                    <ArrowUpRight size={18} aria-hidden="true" />
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}
    </div>
  );
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
