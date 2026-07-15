"use client";

import {
  ArrowUpRight,
  CalendarClock,
  CircleAlert,
  Clock3,
  Inbox,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { listInbox, ProductApiError } from "@/lib/api/product-client";
import type {
  InboxItem,
  InboxItemStatus,
  InboxQueryStatus,
} from "@/lib/schemas/product-api";

type SurfaceFilter = Extract<InboxQueryStatus, "active" | "resolved" | "all">;

const pageSize = 20;

const filters: Array<{ value: SurfaceFilter; label: string }> = [
  { value: "active", label: "待处理" },
  { value: "resolved", label: "已解决" },
  { value: "all", label: "全部" },
];

const statusLabels: Record<InboxItemStatus, string> = {
  pending: "待审核",
  responding: "处理中",
  resolved: "已解决",
  expired: "已过期",
  cancelled: "已取消",
};

const actionLabels: Record<InboxItem["payload"]["artifact"]["analysis"]["main_action"], string> = {
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

const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function InboxSurface() {
  const searchParams = useSearchParams();
  const filter = surfaceFilter(searchParams.get("status"));
  const [items, setItems] = useState<InboxItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paginationError, setPaginationError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  useEffect(() => {
    let active = true;
    const version = requestVersion.current + 1;
    requestVersion.current = version;

    void listInbox({ status: filter, limit: pageSize })
      .then((view) => {
        if (!active || requestVersion.current !== version) return;
        setItems(view.items);
        setNextCursor(view.next_cursor);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!active || requestVersion.current !== version) return;
        setError(readableInboxError(reason));
      })
      .finally(() => {
        if (active && requestVersion.current === version) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [filter]);

  function selectFilter(nextFilter: SurfaceFilter) {
    if (nextFilter === filter) return;
    requestVersion.current += 1;
    setItems([]);
    setNextCursor(null);
    setError(null);
    setPaginationError(null);
    setLoading(true);
    setLoadingMore(false);
    window.history.pushState(
      null,
      "",
      nextFilter === "active" ? "/inbox" : `/inbox?status=${nextFilter}`,
    );
  }

  async function reload() {
    const version = requestVersion.current + 1;
    requestVersion.current = version;
    setItems([]);
    setNextCursor(null);
    setError(null);
    setPaginationError(null);
    setLoading(true);

    try {
      const view = await listInbox({ status: filter, limit: pageSize });
      if (requestVersion.current !== version) return;
      setItems(view.items);
      setNextCursor(view.next_cursor);
    } catch (reason) {
      if (requestVersion.current !== version) return;
      setError(readableInboxError(reason));
    } finally {
      if (requestVersion.current === version) setLoading(false);
    }
  }

  async function loadMore() {
    if (nextCursor === null || loadingMore) return;
    const version = requestVersion.current;
    const cursor = nextCursor;
    setLoadingMore(true);
    setPaginationError(null);

    try {
      const view = await listInbox({
        status: filter,
        limit: pageSize,
        cursor,
      });
      if (requestVersion.current !== version) return;
      setItems((currentItems) => [...currentItems, ...view.items]);
      setNextCursor(view.next_cursor);
    } catch (reason) {
      if (requestVersion.current !== version) return;
      setPaginationError(readableInboxError(reason));
    } finally {
      if (requestVersion.current === version) setLoadingMore(false);
    }
  }

  return (
    <div className="work-page inbox-page">
      <header className="work-header">
        <div>
          <p className="section-kicker">Inbox / Review queue</p>
          <h1>审核收件箱</h1>
          <p>人工审核队列与处理结果，按最新进入时间排列。</p>
        </div>
        <span className="boundary-label">
          <Inbox size={17} aria-hidden="true" />
          人工决策边界
        </span>
      </header>

      <section className="inbox-toolbar" aria-label="收件箱视图">
        <div className="inbox-segmented" role="group" aria-label="审核状态">
          {filters.map(({ value, label }) => (
            <button
              className={filter === value ? "is-active" : undefined}
              type="button"
              aria-pressed={filter === value}
              onClick={() => selectFilter(value)}
              key={value}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="inbox-loaded-count" aria-live="polite">
          {loading ? "正在同步" : `已载入 ${items.length} 项`}
        </span>
      </section>

      <section
        className="inbox-panel"
        id="inbox-panel"
        aria-label={`${filters.find(({ value }) => value === filter)?.label ?? "审核"}审核项`}
      >
        {loading ? (
          <div className="empty-work-state" aria-live="polite">
            <LoaderCircle className="spinning-icon" size={22} aria-hidden="true" />
            <div>
              <h2>正在读取审核队列</h2>
              <p>正在同步 Product Inbox 投影。</p>
            </div>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="request-error" role="alert">
            <CircleAlert size={20} aria-hidden="true" />
            <div className="inbox-state-copy">
              <h2>审核收件箱读取失败</h2>
              <p>{error}</p>
            </div>
            <button className="retry-button inbox-state-action" type="button" onClick={() => void reload()}>
              <RefreshCw size={17} aria-hidden="true" />
              重新读取
            </button>
          </div>
        ) : null}

        {!loading && !error && items.length === 0 ? (
          <div className="empty-work-state" aria-label="当前视图没有审核项">
            <span className="empty-state-line" aria-hidden="true" />
            <div>
              <h2>{emptyStateTitle(filter)}</h2>
              <p>{emptyStateDescription(filter)}</p>
            </div>
          </div>
        ) : null}

        {!loading && !error && items.length > 0 ? (
          <ol className="inbox-list" aria-label="审核项列表">
            {items.map((item) => (
              <InboxCard
                item={item}
                key={`${item.task_id}:${item.created_at}:${item.payload.review_iteration}`}
              />
            ))}
          </ol>
        ) : null}

        {!loading && !error && paginationError ? (
          <div className="request-error inbox-pagination-error" role="alert">
            <CircleAlert size={19} aria-hidden="true" />
            <div className="inbox-state-copy">
              <h2>更多审核项读取失败</h2>
              <p>{paginationError}</p>
            </div>
            <button className="retry-button inbox-state-action" type="button" onClick={() => void loadMore()}>
              <RefreshCw size={17} aria-hidden="true" />
              重试
            </button>
          </div>
        ) : null}

        {!loading && !error && !paginationError && nextCursor !== null ? (
          <div className="inbox-pagination">
            <button type="button" onClick={() => void loadMore()} disabled={loadingMore}>
              {loadingMore ? (
                <LoaderCircle className="spinning-icon" size={17} aria-hidden="true" />
              ) : (
                <RefreshCw size={17} aria-hidden="true" />
              )}
              {loadingMore ? "正在载入" : "加载更多"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function InboxCard({ item }: Readonly<{ item: InboxItem }>) {
  const analysis = item.payload.artifact.analysis;
  const shortSymbol = item.symbol.replace("-USDT-SWAP", "");
  const evidenceLabel = item.payload.artifact.evidence_verdict.sufficient
    ? "证据充分"
    : "证据待补充";
  const riskLabel = item.payload.artifact.risk_verdict.allowed
    ? "风险允许"
    : "风险受限";

  return (
    <li className="inbox-item" data-status={item.status}>
      <div className="inbox-item-header">
        <div className="inbox-item-title">
          <span className="inbox-symbol">{shortSymbol}</span>
          <div>
            <h2>{shortSymbol} / USDT 永续</h2>
            <p>第 {item.payload.review_iteration} 轮人工审核</p>
          </div>
        </div>
        <span className="inbox-status" data-status={item.status}>
          {statusLabels[item.status]}
        </span>
      </div>

      <dl className="inbox-facts">
        <div>
          <dt>状态</dt>
          <dd>{statusLabels[item.status]}</dd>
        </div>
        <div>
          <dt>标的</dt>
          <dd>{shortSymbol}</dd>
        </div>
        <div>
          <dt>周期</dt>
          <dd>{item.horizon}</dd>
        </div>
        <div>
          <dt>建议动作</dt>
          <dd>{actionLabels[analysis.main_action]}</dd>
        </div>
      </dl>

      <div className="inbox-review-summary">
        <div className="inbox-summary-heading">
          <h3>审核摘要</h3>
          <span>{evidenceLabel} · {riskLabel}</span>
        </div>
        <p>{analysis.root_cause_chain.slice(0, 2).join("；")}</p>
      </div>

      <div className="inbox-expiry">
        <CalendarClock size={17} aria-hidden="true" />
        <span>{expiryLabel(item)}</span>
        {item.expires_at !== null ? (
          <time dateTime={item.expires_at}>{formatDateTime(item.expires_at)}</time>
        ) : null}
      </div>

      <div className="inbox-item-footer">
        <span className="inbox-created-at">
          <Clock3 size={15} aria-hidden="true" />
          进入队列 <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
        </span>
        <Link
          className="inbox-open-task"
          href={`/work?task=${encodeURIComponent(item.task_id)}`}
          prefetch={false}
        >
          打开任务
          <ArrowUpRight size={17} aria-hidden="true" />
        </Link>
      </div>
    </li>
  );
}

function expiryLabel(item: InboxItem): string {
  if (item.expires_at === null) return "未设置截止时间";
  if (item.status === "expired") return "已过期";
  if (item.status === "resolved") return "审核窗口截止";
  if (item.status === "cancelled") return "原审核窗口截止";
  return "有效期至";
}

function formatDateTime(value: string): string {
  return dateTimeFormatter.format(new Date(value));
}

function readableInboxError(reason: unknown): string {
  if (reason instanceof ProductApiError) {
    if (reason.status === 502) {
      return "收件箱数据不完整或包含未知状态，已停止展示。请刷新后重试。";
    }
    return reason.message;
  }
  return "无法读取审核收件箱，请稍后重试。";
}

function emptyStateTitle(filter: SurfaceFilter): string {
  if (filter === "active") return "当前没有待处理审核";
  if (filter === "resolved") return "暂无已解决审核";
  return "收件箱暂无记录";
}

function emptyStateDescription(filter: SurfaceFilter): string {
  if (filter === "active") return "新的人工审核请求会出现在这里。";
  if (filter === "resolved") return "完成审核后，处理结果会保留在这里。";
  return "审核请求创建后会按时间显示在这里。";
}

function surfaceFilter(value: string | null): SurfaceFilter {
  if (value === "resolved" || value === "all") return value;
  return "active";
}
