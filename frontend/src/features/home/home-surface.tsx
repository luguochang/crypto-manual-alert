"use client";

import {
  Activity,
  ArrowUpRight,
  BookOpen,
  CircleAlert,
  Inbox,
  RefreshCw,
  Star,
  StarOff,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { getHome, ProductApiError, setWatchlistSymbol } from "@/lib/api/product-client";
import type { HomeView, MarketSnapshot, ProductSymbol } from "@/lib/schemas/product-api";

const symbols: Array<{ short: string; value: ProductSymbol }> = [
  { short: "BTC", value: "BTC-USDT-SWAP" },
  { short: "ETH", value: "ETH-USDT-SWAP" },
  { short: "SOL", value: "SOL-USDT-SWAP" },
];

const activeTaskLabels: Record<HomeView["active_tasks"][number]["status"], string> = {
  queued: "排队中",
  running: "分析中",
  waiting_human: "等待人工确认",
};

const actionLabels: Record<string, string> = {
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

export interface HomeMarketSourceDisclosure {
  label: string;
  tone: "is-available" | "is-partial" | "is-unavailable";
  warning: string | null;
}

export function marketSourceDisclosure(
  snapshot: Pick<MarketSnapshot, "source_level">,
): HomeMarketSourceDisclosure {
  return ({
    exchange_native: {
      label: "交易所原生行情",
      tone: "is-available",
      warning: null,
    },
    web_search_verified: {
      label: "Web Search 已验证证据（降级）",
      tone: "is-partial",
      warning: "降级警示：交易所原生行情不可用；此快照来自带引用的 Web Search 市场证据，不等同于交易所原生行情。",
    },
    controlled_dependency: {
      label: "受控依赖（降级）",
      tone: "is-unavailable",
      warning: "降级警示：此快照来自受控依赖，不是交易所原生行情，不能视为交易所实时行情。",
    },
  } as Record<MarketSnapshot["source_level"], HomeMarketSourceDisclosure>)[snapshot.source_level];
}

export function HomeMarketSource({
  snapshot,
}: {
  snapshot: Pick<MarketSnapshot, "source_level" | "fetched_at">;
}) {
  const disclosure = marketSourceDisclosure(snapshot);

  return (
    <div className="watchlist-source" data-source-level={snapshot.source_level}>
      <span className={`research-state ${disclosure.tone}`}>
        {disclosure.warning ? <CircleAlert size={14} aria-hidden="true" /> : null}
        来源等级：{disclosure.label}
      </span>
      {disclosure.warning ? (
        <span className="watchlist-caption" role="note">{disclosure.warning}</span>
      ) : null}
      <span className="watchlist-caption">
        抓取时间：<time dateTime={snapshot.fetched_at}>{formatDateTime(snapshot.fetched_at)}</time>
      </span>
    </div>
  );
}

export function HomeSurface() {
  const [home, setHome] = useState<HomeView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingSymbol, setUpdatingSymbol] = useState<ProductSymbol | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHome(await getHome());
    } catch (reason) {
      setError(
        reason instanceof ProductApiError
          ? reason.message
          : "无法读取工作区概览，请稍后重试。",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void getHome()
      .then((value) => {
        if (active) setHome(value);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof ProductApiError
            ? reason.message
            : "无法读取工作区概览，请稍后重试。",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function toggleWatchlist(symbol: ProductSymbol, included: boolean) {
    setUpdatingSymbol(symbol);
    setError(null);
    try {
      setHome(await setWatchlistSymbol(symbol, included));
    } catch (reason) {
      setError(
        reason instanceof ProductApiError
          ? reason.message
          : "关注列表更新失败，请稍后重试。",
      );
    } finally {
      setUpdatingSymbol(null);
    }
  }

  return (
    <div className="work-page home-page">
      <header className="work-header home-header">
        <div>
          <p className="section-kicker">Home / Overview</p>
          <h1>市场工作台</h1>
          <p>从这里进入当前工作区的市场、任务和分析报告。</p>
        </div>
        <button
          className="home-refresh-button"
          type="button"
          onClick={() => void reload()}
          disabled={loading}
          aria-label="刷新工作区概览"
        >
          <RefreshCw size={17} aria-hidden="true" />
          刷新
        </button>
      </header>

      {loading ? (
        <section className="empty-work-state" aria-live="polite">
          <span className="empty-state-line" aria-hidden="true" />
          <div>
            <h2>正在读取工作区</h2>
            <p>正在同步已保存的市场和任务状态。</p>
          </div>
        </section>
      ) : null}

      {error ? (
        <section className="request-error" role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div>
            <h2>工作区读取失败</h2>
            <p>{error}</p>
          </div>
          <button className="submit-button" type="button" onClick={() => void reload()}>
            <RefreshCw size={17} aria-hidden="true" />
            重新读取
          </button>
        </section>
      ) : null}

      {!loading && home ? (
        <>
          <section className="home-summary-grid" aria-label="工作区概览">
            <Link className="home-summary-tile" href="/inbox" prefetch={false}>
              <span className="home-summary-label">
                <Inbox size={17} aria-hidden="true" />
                待处理审核
              </span>
              <strong>{home.pending_inbox_count}</strong>
              <span className="home-summary-link">
                打开 Inbox <ArrowUpRight size={15} aria-hidden="true" />
              </span>
            </Link>
            <Link className="home-summary-tile" href="/work" prefetch={false}>
              <span className="home-summary-label">
                <Activity size={17} aria-hidden="true" />
                进行中任务
              </span>
              <strong>{home.active_tasks.length}</strong>
              <span className="home-summary-link">
                开始分析 <ArrowUpRight size={15} aria-hidden="true" />
              </span>
            </Link>
            <Link className="home-summary-tile" href="/library" prefetch={false}>
              <span className="home-summary-label">
                <BookOpen size={17} aria-hidden="true" />
                最近报告
              </span>
              <strong>{home.recent_reports.length}</strong>
              <span className="home-summary-link">
                查看资料库 <ArrowUpRight size={15} aria-hidden="true" />
              </span>
            </Link>
          </section>

          <div className="home-dashboard-grid">
            <section className="home-section home-watchlist-section" aria-labelledby="watchlist-title">
            <header className="home-section-heading">
              <div>
                <p className="section-kicker">Watchlist</p>
                <h2 id="watchlist-title">关注市场</h2>
              </div>
              <span className="home-section-meta">{home.watchlist.length} / {symbols.length}</span>
            </header>
            <div className="watchlist-grid">
              {symbols.map(({ short, value }) => {
                const item = home.watchlist.find((candidate) => candidate.symbol === value);
                const price = item?.latest_snapshot?.ticker?.last
                  ?? item?.latest_snapshot?.mark_price
                  ?? null;
                const busy = updatingSymbol === value;
                return (
                  <article className="watchlist-item" key={value} data-watched={item !== undefined}>
                    <div className="watchlist-item-heading">
                      <div>
                        <strong>{short}</strong>
                        <span>永续合约</span>
                      </div>
                      <button
                        className="watchlist-toggle"
                        type="button"
                        onClick={() => void toggleWatchlist(value, item === undefined)}
                        disabled={busy}
                        aria-label={item ? `移除 ${short} 关注` : `关注 ${short}`}
                        title={item ? `移除 ${short} 关注` : `关注 ${short}`}
                      >
                        {item ? <Star size={17} fill="currentColor" aria-hidden="true" /> : <StarOff size={17} aria-hidden="true" />}
                      </button>
                    </div>
                    <strong className="watchlist-price">
                      {price === null ? "暂无已保存快照" : formatPrice(price)}
                    </strong>
                    {item?.latest_snapshot ? (
                      <HomeMarketSource snapshot={item.latest_snapshot} />
                    ) : (
                      <span className="watchlist-caption">
                        {item ? "暂无可用行情快照" : "尚未加入关注列表"}
                      </span>
                    )}
                  </article>
                );
              })}
            </div>
            </section>

            <section className="home-section home-active-section" aria-labelledby="active-tasks-title">
            <header className="home-section-heading">
              <div>
                <p className="section-kicker">Active work</p>
                <h2 id="active-tasks-title">进行中的任务</h2>
              </div>
              <Link className="home-section-link" href="/runs" prefetch={false}>
                全部运行 <ArrowUpRight size={15} aria-hidden="true" />
              </Link>
            </header>
            {home.active_tasks.length === 0 ? (
              <p className="home-empty-copy">当前没有进行中的任务。</p>
            ) : (
              <ul className="home-task-list">
                {home.active_tasks.map((task) => (
                  <li key={task.task_id}>
                    <Link
                      className="home-task-row"
                      href={`/work?task=${encodeURIComponent(task.task_id)}${task.run_id ? `&run=${encodeURIComponent(task.run_id)}` : ""}`}
                      prefetch={false}
                      data-status={task.status}
                    >
                      <span className="run-symbol">{task.symbol.replace("-USDT-SWAP", "")}</span>
                      <span className="run-summary">
                        <strong>{task.horizon} · {formatDateTime(task.created_at)}</strong>
                        <small>{task.run_id ? "已有运行实例" : "等待 Worker 创建运行"}</small>
                      </span>
                      <span className="run-outcome">
                        <strong>{activeTaskLabels[task.status]}</strong>
                        <small>打开任务</small>
                      </span>
                      <ArrowUpRight size={18} aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            </section>

            <section className="home-section home-reports-section" aria-labelledby="recent-reports-title">
            <header className="home-section-heading">
              <div>
                <p className="section-kicker">Recent reports</p>
                <h2 id="recent-reports-title">最近报告</h2>
              </div>
              <Link className="home-section-link" href="/library" prefetch={false}>
                全部报告 <ArrowUpRight size={15} aria-hidden="true" />
              </Link>
            </header>
            {home.recent_reports.length === 0 ? (
              <p className="home-empty-copy">完成第一项分析后，报告会出现在这里。</p>
            ) : (
              <ul className="home-task-list">
                {home.recent_reports.slice(0, 5).map((report) => (
                  <li key={report.artifact_version_id}>
                    <Link
                      className="home-task-row"
                      href={`/artifacts/${report.artifact_id}?version_number=${report.version_number}`}
                      prefetch={false}
                      data-status={report.status}
                      data-kind="artifact"
                    >
                      <span className="run-symbol">{report.symbol.replace("-USDT-SWAP", "")}</span>
                      <span className="run-summary">
                        <strong>{report.horizon} · 报告 v{report.version_number}</strong>
                        <small>{formatDateTime(report.created_at)} · {report.schema_version}</small>
                      </span>
                      <span className="run-outcome">
                        <strong>{report.status === "committed" ? "已保存" : report.status === "failed" ? "生成失败" : "处理中"}</strong>
                        <small>{report.main_action ? actionLabels[report.main_action] ?? report.main_action : "暂无最终动作"}</small>
                      </span>
                      <ArrowUpRight size={18} aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: value >= 100 ? 2 : 4,
  }).format(value);
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
