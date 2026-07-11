import Link from "next/link";
import { listRuns } from "@/lib/api/runs";
import { StatusBadge } from "@/app/shared/status-badge";
import { Icon } from "@/app/shared/icons";
import {
  productDecisionLabel,
  productDisplayItems,
  productDisplayText
} from "@/app/shared/product-copy";
import { DiagnosticDisabledNotice, diagnosticRoutesEnabled } from "@/app/shared/diagnostic-access";
import { getSystemConfig } from "@/lib/api/system";
import type { RunSummary } from "@/lib/schemas/runs";
import type { Readiness } from "@/lib/schemas/system";

export const dynamic = "force-dynamic";

type RunsPageProps = {
  searchParams: Promise<{
    allowed?: string;
    columns?: string;
    latest?: string;
    limit?: string;
    offset?: string;
    status?: string;
    symbol?: string;
  }>;
};

type ColumnMode = "business" | "observability";
type AllowedFilter = "all" | "allowed" | "blocked";

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;
const COLUMN_MODES: Array<{ id: ColumnMode; label: string; icon: "bell" | "activity" | "database" }> = [
  { id: "business", label: "提醒列", icon: "bell" },
  { id: "observability", label: "观测列", icon: "activity" }
];
const STATUS_FILTERS = ["all", "running", "allowed", "blocked", "failed", "ok"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];
const ALLOWED_FILTERS: Array<{ id: AllowedFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "allowed", label: "可复核" },
  { id: "blocked", label: "已阻断" }
];
const STATUS_FILTER_LABELS: Record<StatusFilter, string> = {
  all: "全部状态",
  running: "运行中",
  allowed: "可人工复核",
  blocked: "风控阻断",
  failed: "失败",
  ok: "完成"
};

export default async function RunsPage({ searchParams }: RunsPageProps) {
  const params = await searchParams;
  const limit = parsePositiveInt(params.limit, DEFAULT_LIMIT, MAX_LIMIT);
  const offset = parseOffset(params.offset);
  const columnMode = parseColumnMode(params.columns);
  const status = parseStatus(params.status);
  const symbol = (params.symbol ?? "").trim();
  const latestTraceId = (params.latest ?? "").trim();
  const allowedFilter = parseAllowedFilter(params.allowed);
  const allowed = allowedFilter === "all" ? undefined : allowedFilter === "allowed";
  const showingBusiness = columnMode === "business";
  const showingObservability = columnMode === "observability";
  const defaultTab = columnMode === "observability" ? "matrix" : "summary";

  if (showingObservability) {
    const config = await getSystemConfig();
    if (!diagnosticRoutesEnabled(config)) {
      return <DiagnosticDisabledNotice backHref="/runs" backLabel="返回提醒记录" />;
    }
  }

  const result = await listRuns({
    limit,
    offset,
    status: status === "all" ? undefined : status,
    symbol: symbol || undefined,
    allowed
  });
  const items = result.ok ? result.data.items : [];
  const hasNext = result.ok ? result.data.has_more === true : false;
  const hasPrevious = offset > 0;
  const nextOffset = result.ok && result.data.next_offset != null ? result.data.next_offset : offset + limit;
  const previousOffset = Math.max(0, offset - limit);
  const latestRun = latestTraceId ? items.find((run) => run.trace_id === latestTraceId) : undefined;
  const emptyConfig = result.ok && items.length === 0 ? await getSystemConfig() : null;
  const emptyReadiness = emptyConfig?.ok ? emptyConfig.data.readiness : undefined;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>提醒记录</h1>
          <p className="muted">默认展示人工复核所需的提醒建议、交易对、状态和通知结果；诊断数据可切换到观测列查看。</p>
        </div>
        <Link className="button" href="/manual-run" prefetch={false}>
          <Icon name="plus" size={16} /> 新建提醒
        </Link>
      </header>

      <section className="toolbar runs-toolbar" aria-label="提醒记录过滤">
        <RunsFilterForm
          allowedFilter={allowedFilter}
          columnMode={columnMode}
          latestTraceId={latestTraceId}
          limit={limit}
          status={status}
          symbol={symbol}
          variant="desktop"
        />
        <details className="runs-mobile-filter">
          <summary>
            <span>筛选条件</span>
            <strong>{filterSummary({ allowedFilter, limit, status, symbol })}</strong>
          </summary>
          <RunsFilterForm
            allowedFilter={allowedFilter}
            columnMode={columnMode}
            latestTraceId={latestTraceId}
            limit={limit}
            status={status}
            symbol={symbol}
            variant="mobile"
          />
        </details>
      </section>

      <section className="toolbar runs-toolbar">
        {showingObservability ? (
          <nav className="tabs compact-tabs" aria-label="列显示">
            {COLUMN_MODES.map((mode) => (
              <Link
                key={mode.id}
                href={buildRunsHref({ columns: mode.id, status, symbol, allowed: allowedFilter, latest: latestTraceId, limit })}
                prefetch={false}
                className={`tab ${columnMode === mode.id ? "active" : ""}`}
                aria-current={columnMode === mode.id ? "page" : undefined}
              >
                <Icon name={mode.icon} size={15} /> {mode.label}
              </Link>
            ))}
          </nav>
        ) : (
          <span className="muted">业务视图</span>
        )}
        <div className="pagination">
          <span className="muted">第 {Math.floor(offset / limit) + 1} 页 · 每页 {limit}</span>
          <Link
            className={`button button-secondary ${hasPrevious ? "" : "disabled-link"}`}
            href={buildRunsHref({ columns: columnMode, status, symbol, allowed: allowedFilter, latest: latestTraceId, limit, offset: previousOffset })}
            prefetch={false}
            aria-disabled={!hasPrevious}
            tabIndex={hasPrevious ? undefined : -1}
          >
            上一页
          </Link>
          <Link
            className={`button button-secondary ${hasNext ? "" : "disabled-link"}`}
            href={buildRunsHref({ columns: columnMode, status, symbol, allowed: allowedFilter, latest: latestTraceId, limit, offset: nextOffset })}
            prefetch={false}
            aria-disabled={!hasNext}
            tabIndex={hasNext ? undefined : -1}
          >
            下一页
          </Link>
        </div>
      </section>

      {showingObservability ? (
        <section className="mode-notice" aria-label="工程诊断说明">
          <strong>工程诊断</strong>
          <span>这是工程诊断视图，不是普通提醒记录；用于核对 trace、span、模型调用次数和排障线索，业务复核请切回提醒列。</span>
        </section>
      ) : null}

      {latestTraceId ? (
        <section className={`mode-notice latest-run-notice ${latestRun ? "" : "latest-run-missing"}`} aria-label="刚生成的提醒">
          <strong>{latestRun ? "刚生成的提醒" : "刚生成的提醒未显示"}</strong>
          <span>
            {latestRun
              ? "刚生成的提醒已显示在列表中，可继续打开详情核对价格、风险和通知状态。"
              : "刚生成的提醒不在当前页或被筛选条件隐藏；清空筛选或返回详情继续核对。"}
          </span>
        </section>
      ) : null}

      {!result.ok ? (
        <div className="error-state" role="alert">提醒记录暂时无法加载，请稍后重试。无法确认本次请求是否写入，请返回后重新核对记录。</div>
      ) : items.length === 0 ? (
        <div className="empty-state" aria-label="当前记录状态">
          <div className="empty-state-heading">
            <h2>当前没有可审计提醒</h2>
            <p>{emptyReadinessSummary(emptyReadiness)}</p>
          </div>
          <div className="empty-readiness-grid">
            {emptyReadinessItems(emptyReadiness).map((item) => (
              <article className="risk-summary-item" key={item.label}>
                <span>{item.label}</span>
                <strong className={`badge ${readinessTone(item.status)}`}>{readinessShortLabel(item.status)}</strong>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
          <div className="empty-actions">
            <Link className="button button-secondary" href={buildRunsHref({ columns: columnMode })} prefetch={false}>
              <Icon name="refresh" size={16} /> 清空筛选
            </Link>
            <Link className="button button-secondary" href="/config" prefetch={false}>
              <Icon name="settings" size={16} /> 查看配置检查
            </Link>
            <Link className="button" href="/manual-run" prefetch={false}>
              <Icon name="plus" size={16} /> 新建提醒
            </Link>
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {showingBusiness ? <th>提醒时间</th> : <th>提醒编号</th>}
                <th>交易对</th>
                {showingObservability ? <th>状态</th> : null}
                {showingBusiness ? (
                  <>
                    <th>建议动作</th>
                    <th>复核结果</th>
                    <th>模型结论</th>
                    <th>后续复盘</th>
                    <th>风险摘要</th>
                    <th>通知</th>
                  </>
                ) : null}
                {showingObservability ? (
                  <>
                    <th>Spans</th>
                    <th>LLM</th>
                    <th>类型</th>
                  </>
                ) : null}
                {showingObservability ? <th>创建时间</th> : null}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((run) => {
                const isLatestRun = latestTraceId === run.trace_id;
                return (
                <tr
                  key={run.trace_id}
                  className={isLatestRun ? "latest-run-row" : undefined}
                  data-latest-run={isLatestRun ? "true" : undefined}
                >
                  <td className={showingBusiness ? "" : "mono-cell"}>
                    {showingBusiness ? formatRunTime(run.created_at) : shortId(run.trace_id)}
                  </td>
                  <td className="mono-cell">{run.symbol}</td>
                  {showingObservability ? <td><StatusBadge status={run.status} /></td> : null}
                  {showingBusiness ? (
                    <>
                      <td>
                        <strong>{businessAction(run)}</strong>
                        <span className="table-subtext">{productDisplayText(run.business_summary?.confidence_text) || "概率未记录"}</span>
                      </td>
                      <td>
                        <span className={`badge ${reviewTone(run)}`}>
                          {reviewLabel(run)}
                        </span>
                      </td>
                      <td className="runs-model-cell">{modelConclusionSummary(run)}</td>
                      <td>
                        <span className={`badge ${resultReviewTone(run)}`}>
                          {resultReviewLabel(run)}
                        </span>
                        <span className="table-subtext">{resultReviewHint(run)}</span>
                      </td>
                      <td className="runs-risk-cell">{riskSummary(run)}</td>
                      <td>
                        <span className={`badge ${notificationTone(run.business_summary?.notification?.status)}`}>
                          {notificationLabel(run.business_summary?.notification?.status)}
                        </span>
                      </td>
                    </>
                  ) : null}
                  {showingObservability ? (
                    <>
                      <td className="mono-cell">{run.span_count}</td>
                      <td className="mono-cell">{run.llm_interaction_count}</td>
                      <td>{run.run_type}</td>
                    </>
                  ) : null}
                  {showingObservability ? <td className="mono-cell">{run.created_at}</td> : null}
                  <td>
                    <Link
	                      className="button-ghost button"
	                      href={`/runs/${encodeURIComponent(run.trace_id)}?tab=${defaultTab}${columnMode === "observability" ? "&columns=observability" : ""}`}
	                      prefetch={false}
	                      aria-label={`查看 ${run.symbol} 提醒详情`}
	                      title="查看详情"
	                    >
                      <Icon name="chevron-right" size={14} />
                    </Link>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function RunsFilterForm(props: {
  allowedFilter: AllowedFilter;
  columnMode: ColumnMode;
  latestTraceId: string;
  limit: number;
  status: StatusFilter;
  symbol: string;
  variant: "desktop" | "mobile";
}) {
  const suffix = props.variant === "mobile" ? "-mobile" : "";
  return (
    <form className={`runs-filter-form runs-filter-form-${props.variant}`} action="/runs">
      <input type="hidden" name="columns" value={props.columnMode} />
      {props.latestTraceId ? <input type="hidden" name="latest" value={props.latestTraceId} /> : null}
      <div className="field">
        <label htmlFor={`symbol${suffix}`}>交易对</label>
        <input id={`symbol${suffix}`} name="symbol" defaultValue={props.symbol} placeholder="ETH / BTC / USDT" />
      </div>
      <div className="field">
        <label htmlFor={`status${suffix}`}>状态</label>
        <select id={`status${suffix}`} name="status" defaultValue={props.status}>
          {STATUS_FILTERS.map((item) => (
            <option key={item} value={item}>{STATUS_FILTER_LABELS[item]}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`allowed${suffix}`}>风控</label>
        <select id={`allowed${suffix}`} name="allowed" defaultValue={props.allowedFilter}>
          {ALLOWED_FILTERS.map((item) => (
            <option key={item.id} value={item.id}>{item.label}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`limit${suffix}`}>每页</label>
        <select id={`limit${suffix}`} name="limit" defaultValue={String(props.limit)}>
          {[10, 20, 50].map((item) => (
            <option key={item} value={String(item)}>{item}</option>
          ))}
        </select>
      </div>
      <button className="button" type="submit">
        <Icon name="search" size={16} /> 筛选
      </button>
      <Link className="button button-secondary" href={buildRunsHref({ columns: props.columnMode })} prefetch={false}>
        <Icon name="refresh" size={16} /> 重置
      </Link>
    </form>
  );
}

function parsePositiveInt(value: string | undefined, fallback: number, max: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return fallback;
  }
  return Math.min(parsed, max);
}

function parseOffset(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function parseColumnMode(value: string | undefined): ColumnMode {
  return value === "observability" ? value : "business";
}

function parseStatus(value: string | undefined): (typeof STATUS_FILTERS)[number] {
  return STATUS_FILTERS.includes(value as (typeof STATUS_FILTERS)[number])
    ? value as (typeof STATUS_FILTERS)[number]
    : "all";
}

function parseAllowedFilter(value: string | undefined): AllowedFilter {
  return value === "allowed" || value === "blocked" ? value : "all";
}

function readinessTone(status: string | undefined): string {
  if (status === "ready") return "badge-success";
  if (status === "unsafe" || status === "missing_env" || status === "main_path_blocked") return "badge-failed";
  if (status === "fixture_only" || status === "disabled") return "badge-pending";
  return "badge-neutral";
}

function readinessShortLabel(status: string | undefined): string {
  const labels: Record<string, string> = {
    ready: "已满足",
    fixture_only: "仅演练",
    missing_env: "未配置",
    disabled: "未启用",
    unsafe: "需处理",
    main_path_blocked: "需恢复默认主链"
  };
  return labels[status ?? ""] ?? "未知";
}

function emptyReadinessSummary(readiness: Readiness | undefined): string {
  if (!readiness) {
    return "没有找到符合条件的提醒；配置状态暂时不可用。清空筛选或新建一次手动提醒后，请回到配置检查核对生产 readiness。";
  }
  if (readiness.prod_actionable.prod_actionable_ready) {
    return "当前筛选下没有提醒记录；生产配置看起来齐全，但仍必须以 hosted smoke、视觉门禁和 real-outcome proof 为准。";
  }
  return "当前只是本地演练或空数据状态，不是生产成功证明。生成提醒前不会产生任何交易副作用；真实交付还需要补齐模型、行情、通知和事件状态。";
}

function emptyReadinessItems(readiness: Readiness | undefined) {
  return [
    {
      label: "真实模型",
      status: readiness?.decision_engine.status,
      detail: "需要真实 OpenAI-compatible 地址、模型名和密钥；本地演练只证明调用链路。"
    },
    {
      label: "真实行情",
      status: readiness?.market_data.status,
      detail: "生产提醒必须使用 OKX 公开行情；演练行情不能证明可行动提醒。"
    },
    {
      label: "Bark 通知",
      status: readiness?.notification.status,
      detail: "生产提醒必须真实发送到手机；未启用通知时只能验证页面和记录链路。"
    },
    {
      label: "宏观事件状态",
      status: readiness?.event_status.status,
      detail: "开仓、触发或翻转类提醒需要确认本窗口没有活跃宏观事件影响。"
    }
  ];
}

function filterSummary(options: {
  allowedFilter: AllowedFilter;
  limit: number;
  status: StatusFilter;
  symbol: string;
}): string {
  const parts = [
    options.symbol || "全部交易对",
    STATUS_FILTER_LABELS[options.status],
    ALLOWED_FILTERS.find((item) => item.id === options.allowedFilter)?.label ?? "全部",
    `每页 ${options.limit}`
  ];
  return parts.join(" · ");
}

function buildRunsHref(options: {
  allowed?: AllowedFilter;
  columns?: ColumnMode;
  latest?: string;
  limit?: number;
  offset?: number;
  status?: string;
  symbol?: string;
}): string {
  const params = new URLSearchParams();
  if (options.columns && options.columns !== "business") {
    params.set("columns", options.columns);
  }
  if (options.status && options.status !== "all") {
    params.set("status", options.status);
  }
  if (options.symbol) {
    params.set("symbol", options.symbol);
  }
  if (options.allowed && options.allowed !== "all") {
    params.set("allowed", options.allowed);
  }
  if (options.latest) {
    params.set("latest", options.latest);
  }
  if (options.limit && options.limit !== DEFAULT_LIMIT) {
    params.set("limit", String(options.limit));
  }
  if (options.offset && options.offset > 0) {
    params.set("offset", String(options.offset));
  }
  const query = params.toString();
  return `/runs${query ? `?${query}` : ""}`;
}

function shortId(value: string): string {
  return value.length > 18 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

function businessAction(run: RunSummary): string {
  return productDisplayText(run.business_summary?.action_text ?? run.final_action) || "未明确";
}

function modelConclusionSummary(run: RunSummary): string {
  const summary = run.business_summary?.generation_summary;
  const conclusion = productDisplayText(summary?.response_summary);
  if (conclusion) return conclusion;
  return productDisplayText(summary?.status_label) || "模型结论暂未形成可读摘录。";
}

function reviewLabel(run: RunSummary): string {
  return productDecisionLabel(run.business_summary?.decision_label) ?? (
    run.allowed == null ? "待复核" : run.allowed ? "可人工复核" : "已阻断"
  );
}

function reviewTone(run: RunSummary): string {
  if (run.allowed === true) return "badge-success";
  if (run.allowed === false) return "badge-failed";
  return "badge-neutral";
}

function riskSummary(run: RunSummary): string {
  const summary = run.business_summary;
  const items = productDisplayItems([...(summary?.risk_bullets ?? []), ...(summary?.data_gap_bullets ?? [])], 2);
  return items.length > 0 ? items.join("；") : "暂无额外风险摘要，仍需人工核对。";
}

function resultReviewLabel(run: RunSummary): string {
  const review = run.result_review;
  if (!review) return "未记录";
  if (review.status === "not_collected") return "结果尚未生成";
  if (review.status === "pending") return "等待窗口成熟";
  if (review.status === "mock_visibility_only") return "本地展示样本";
  if (review.status === "scorable" || review.status === "mixed_quality_scope") return "可用于质量复盘";
  if (review.status === "unscorable") return "不可评分";
  return productDisplayText(review.label) || "状态已记录";
}

function resultReviewTone(run: RunSummary): string {
  const status = run.result_review?.status;
  if (status === "scorable" || status === "mixed_quality_scope") return "badge-success";
  if (status === "unscorable") return "badge-failed";
  if (status === "not_collected") return "badge-neutral";
  return "badge-pending";
}

function resultReviewHint(run: RunSummary): string {
  const review = run.result_review;
  if (!review) return "复盘状态未记录";
  if (review.status === "not_collected") return "等待观察窗口成熟后采集";
  if (review.sample_count > 0) return `结果样本 ${review.sample_count} 条`;
  return productDisplayText(review.message) || "查看详情了解复盘状态";
}

function notificationTone(status: string | undefined): string {
  if (status === "sent") return "badge-success";
  if (status === "failed") return "badge-failed";
  return "badge-pending";
}

function notificationLabel(status: string | undefined): string {
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "发送失败";
  if (status === "disabled") return "通知未启用";
  return "未记录";
}

function formatRunTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}
