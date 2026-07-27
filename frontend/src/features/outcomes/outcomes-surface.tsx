"use client";

import { BarChart3, CircleAlert, Clock3, RefreshCw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listOutcomes, ProductApiError } from "@/lib/api/product-client";
import type { OutcomeList } from "@/lib/schemas/product-api";

const statusLabels: Record<OutcomeList["items"][number]["status"], string> = {
  scheduled: "等待到期",
  pending: "采集中",
  matured: "已成熟",
  insufficient: "数据不足",
  failed: "采集失败",
};

export function OutcomesSurface() {
  const [view, setView] = useState<OutcomeList | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setError(null);
    try { setView(await listOutcomes()); }
    catch (reason) { setError(reason instanceof ProductApiError ? reason.message : "无法读取结果评估。"); }
  }

  useEffect(() => {
    let active = true;
    void listOutcomes()
      .then((response) => { if (active) setView(response); })
      .catch((reason: unknown) => {
        if (active) setError(
          reason instanceof ProductApiError ? reason.message : "无法读取结果评估。",
        );
      });
    return () => { active = false; };
  }, []);

  return (
    <div className="work-page outcomes-page">
      <header className="work-header">
        <div><p className="section-kicker">Outcomes / Quality</p><h1>结果评估</h1><p>基于交易所原生事实评估已到期决策，不使用模型判断收益。</p></div>
        <span className="boundary-label list-meta-label"><BarChart3 size={17} aria-hidden="true" />{view?.sample_count ?? 0} 个成熟样本</span>
      </header>

      {error ? <section className="request-error" role="alert"><CircleAlert size={20} aria-hidden="true" /><div><h2>结果读取失败</h2><p>{error}</p></div><button className="submit-button" type="button" onClick={() => void reload()}><RefreshCw size={17} aria-hidden="true" />重新读取</button></section> : null}

      {view ? <section className={`quality-boundary${view.reportable ? " is-reportable" : ""}`} aria-live="polite">
        {view.reportable ? <ShieldCheck aria-hidden="true" /> : <Clock3 aria-hidden="true" />}
        <div><h2>{view.reportable ? "样本窗口达到报告条件" : "样本不足，暂不报告策略质量"}</h2><p>样本 {view.sample_count} · 窗口 {view.window_start ? formatDate(view.window_start) : "尚未形成"} · 来源 OKX exchange-native</p></div>
      </section> : null}

      {!view ? <section className="empty-work-state" aria-live="polite"><span className="empty-state-line" aria-hidden="true" /><div><h2>正在读取结果</h2><p>同步到期观察与质量边界。</p></div></section> : null}
      {view && view.items.length === 0 ? <section className="empty-work-state"><span className="empty-state-line" aria-hidden="true" /><div><h2>暂无结果观察</h2><p>分析报告到达时间窗口后会自动进入结果采集。</p></div></section> : null}

      {view && view.items.length > 0 ? <section className="outcome-list" aria-label="结果观察列表">
        {view.items.map((item) => <article className="outcome-row" key={item.id} data-status={item.status}>
          <div><span className="outcome-status">{statusLabels[item.status]}</span><h2>{item.action} · {item.horizon}</h2><p>{item.observed_at ? `观察于 ${formatDate(item.observed_at)}` : `到期于 ${formatDate(item.maturation_at)}`}</p></div>
          <dl><Metric label="Brier" value={formatMetric(item.metrics?.brier_score)} /><Metric label="净收益" value={formatPercent(item.metrics?.net_return)} /><Metric label="MFE / MAE" value={`${formatPercent(item.metrics?.mfe)} / ${formatPercent(item.metrics?.mae)}`} /></dl>
          <Link className="outcome-task-link" href={`/runs/${encodeURIComponent(item.run_id)}`} prefetch={false}>查看运行</Link>
        </article>)}
      </section> : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function formatMetric(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(4) : "--";
}

function formatPercent(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : "--";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}
