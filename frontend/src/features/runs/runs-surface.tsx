"use client";

import { ArrowUpRight, CircleAlert, History, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listRuns, ProductApiError } from "@/lib/api/product-client";
import type { ProductRunSummary } from "@/lib/schemas/product-api";

const statusLabels: Record<ProductRunSummary["status"], string> = {
  queued: "已排队",
  running: "分析中",
  waiting_human: "等待人工确认",
  succeeded: "分析完成",
  blocked: "门禁阻断",
  failed: "分析失败",
  cancelled: "已取消",
};

const actionLabels: Record<NonNullable<ProductRunSummary["main_action"]>, string> = {
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

export function RunsSurface() {
  const [runs, setRuns] = useState<ProductRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const response = await listRuns(25);
      setRuns(response.items);
    } catch (reason) {
      setError(
        reason instanceof ProductApiError
          ? reason.message
          : "无法读取分析记录，请稍后重试。",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    void listRuns(25)
      .then((response) => {
        if (active) setRuns(response.items);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof ProductApiError
            ? reason.message
            : "无法读取分析记录，请稍后重试。",
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
    <div className="work-page runs-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Runs / History</p>
          <h1>分析记录</h1>
          <p>查看当前工作区内已持久化的分析运行和最终状态。</p>
        </div>
        <span className="boundary-label">
          <History size={17} aria-hidden="true" />
          最近 25 条
        </span>
      </header>

      {loading ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>正在读取分析记录</h2><p>正在同步 Product 数据库中的持久投影。</p></div>
        </section>
      ) : null}

      {error ? (
        <section className="request-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div><h2>分析记录读取失败</h2><p>{error}</p></div>
          <button className="submit-button" type="button" onClick={() => void reload()}>
            <RefreshCw size={17} aria-hidden="true" />
            重新读取
          </button>
        </section>
      ) : null}

      {!loading && !error && runs.length === 0 ? (
        <section className="empty-work-state" aria-label="暂无分析记录">
          <span className="empty-state-line" aria-hidden="true" />
          <div><h2>暂无分析记录</h2><p>完成第一项分析后，持久化运行会显示在这里。</p></div>
        </section>
      ) : null}

      {!loading && !error && runs.length > 0 ? (
        <section className="runs-list-section" aria-label="分析运行列表">
          <ol className="runs-list">
            {runs.map((run) => {
              const shortSymbol = run.symbol.replace("-USDT-SWAP", "");
              return (
                <li key={run.run_id}>
                  <Link
                    className="run-row"
                    href={`/work?task=${encodeURIComponent(run.task_id)}&run=${encodeURIComponent(run.run_id)}`}
                    prefetch={false}
                    data-status={run.status}
                  >
                    <span className="run-symbol">{shortSymbol}</span>
                    <span className="run-summary">
                      <strong>{run.horizon} · 第 {run.attempt} 次运行</strong>
                      <small>{formatDateTime(run.finished_at ?? run.created_at)}</small>
                    </span>
                    <span className="run-outcome">
                      <strong>{statusLabels[run.status]}</strong>
                      <small>{run.main_action ? actionLabels[run.main_action] : "暂无最终动作"}</small>
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
