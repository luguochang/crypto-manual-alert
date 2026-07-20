"use client";

import {
  AlertTriangle,
  BellRing,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Clock3,
  ExternalLink,
  FileText,
  History,
  LoaderCircle,
  Pause,
  Play,
  Radar,
  RefreshCw,
  RotateCw,
  Trash2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  deleteMonitor,
  listMonitors,
  listMonitorTriggers,
  pauseMonitor,
  resumeMonitor,
  triggerMonitor,
} from "@/lib/api/monitor-client";
import type {
  Monitor,
  MonitorList,
  MonitorStatusFilter,
  MonitorTriggerList,
} from "@/lib/schemas/monitor-api";

import {
  describeMonitorCondition,
  describeMonitorSchedule,
  formatMonitorDateTime,
  monitorStatusLabels,
  triggerStatusLabels,
} from "./monitor-presenter";
import { idempotencyKeyFor, monitorErrorMessage, mutationIdentity } from "./monitor-state";
import styles from "./monitors.module.css";

const filters: Array<{ value: MonitorStatusFilter; label: string }> = [
  { value: "running", label: "运行中" },
  { value: "paused", label: "已暂停" },
  { value: "attention", label: "需要处理" },
  { value: "closed", label: "已关闭" },
  { value: "all", label: "全部" },
];

type TriggerState = {
  expanded: boolean;
  loading: boolean;
  error: string | null;
  view: MonitorTriggerList | null;
};

type MonitorAction = "pause" | "resume" | "trigger" | "delete";

export function MonitorListSurface({ status }: { status: MonitorStatusFilter }) {
  const [view, setView] = useState<MonitorList | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, MonitorAction | undefined>>({});
  const [rowErrors, setRowErrors] = useState<Record<string, string | undefined>>({});
  const [triggerStates, setTriggerStates] = useState<Record<string, TriggerState | undefined>>({});
  const mutationKeys = useRef(new Map<string, { identity: string; key: string }>());

  async function load(activeStatus: MonitorStatusFilter = status) {
    setLoading(true);
    setLoadError(null);
    try {
      setView(await listMonitors(activeStatus));
    } catch (reason) {
      setLoadError(monitorErrorMessage(reason, "无法读取持续监控，请稍后重试。"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    void listMonitors(status)
      .then((response) => {
        if (active) setView(response);
      })
      .catch((reason: unknown) => {
        if (active) {
          setLoadError(monitorErrorMessage(reason, "无法读取持续监控，请稍后重试。"));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [status]);

  function applyMonitorUpdate(updated: Monitor) {
    setView((current) => {
      if (!current) return current;
      const staysVisible = monitorMatchesFilter(updated, status);
      const items = staysVisible
        ? current.items.map((item) => item.id === updated.id ? updated : item)
        : current.items.filter((item) => item.id !== updated.id);
      return { ...current, items };
    });
  }

  function keyFor(identity: string): string {
    const next = idempotencyKeyFor(mutationKeys.current.get(identity) ?? null, identity);
    mutationKeys.current.set(identity, next);
    return next.key;
  }

  async function runAction(monitor: Monitor, action: MonitorAction) {
    if (
      action === "delete"
      && !window.confirm(`关闭“${monitor.name}”？历史触发记录会保留。`)
    ) return;

    const identity = mutationIdentity(action, {
      monitor_id: monitor.id,
      version: monitor.version,
    });
    const idempotencyKey = keyFor(identity);
    setBusy((current) => ({ ...current, [monitor.id]: action }));
    setRowErrors((current) => ({ ...current, [monitor.id]: undefined }));
    try {
      if (action === "trigger") {
        const updated = await triggerMonitor(monitor.id, idempotencyKey);
        applyMonitorUpdate(updated);
        setTriggerStates((current) => ({
          ...current,
          [monitor.id]: current[monitor.id]?.expanded
            ? { expanded: true, loading: true, error: null, view: null }
            : current[monitor.id],
        }));
        if (triggerStates[monitor.id]?.expanded) {
          await loadTriggers(monitor.id, true);
        }
      } else {
        const input = { expected_version: monitor.version };
        const updated = action === "pause"
          ? await pauseMonitor(monitor.id, input, idempotencyKey)
          : action === "resume"
            ? await resumeMonitor(monitor.id, input, idempotencyKey)
            : await deleteMonitor(monitor.id, input, idempotencyKey);
        applyMonitorUpdate(updated);
      }
      mutationKeys.current.delete(identity);
    } catch (reason) {
      setRowErrors((current) => ({
        ...current,
        [monitor.id]: monitorErrorMessage(reason, "操作失败，请稍后重试。"),
      }));
    } finally {
      setBusy((current) => ({ ...current, [monitor.id]: undefined }));
    }
  }

  async function loadTriggers(monitorId: string, keepExpanded = true) {
    setTriggerStates((current) => ({
      ...current,
      [monitorId]: { expanded: keepExpanded, loading: true, error: null, view: null },
    }));
    try {
      const triggers = await listMonitorTriggers(monitorId);
      setTriggerStates((current) => ({
        ...current,
        [monitorId]: { expanded: keepExpanded, loading: false, error: null, view: triggers },
      }));
    } catch (reason) {
      setTriggerStates((current) => ({
        ...current,
        [monitorId]: {
          expanded: keepExpanded,
          loading: false,
          error: monitorErrorMessage(reason, "无法读取触发记录。"),
          view: null,
        },
      }));
    }
  }

  function toggleTriggers(monitorId: string) {
    const current = triggerStates[monitorId];
    if (current?.expanded) {
      setTriggerStates((states) => ({
        ...states,
        [monitorId]: { ...current, expanded: false },
      }));
      return;
    }
    if (current?.view) {
      setTriggerStates((states) => ({
        ...states,
        [monitorId]: { ...current, expanded: true },
      }));
      return;
    }
    void loadTriggers(monitorId);
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.kicker}>Scheduled monitors</p>
          <h1>持续监控</h1>
          <p>周期检查已提交报告的关键条件，并保留每次触发与实时任务记录。</p>
        </div>
        <div className={styles.headerMeta} aria-label="监控总数">
          <Radar size={18} aria-hidden="true" />
          <strong>{view?.items.length ?? "-"}</strong>
          <span>条监控</span>
        </div>
      </header>

      <nav className={styles.filters} aria-label="按状态筛选持续监控">
        {filters.map((filter) => (
          <Link
            key={filter.value}
            className={filter.value === status ? styles.activeFilter : styles.filter}
            href={`/monitors?status=${filter.value}`}
            prefetch={false}
            aria-current={filter.value === status ? "page" : undefined}
          >
            {filter.label}
          </Link>
        ))}
      </nav>

      {loading ? (
        <section className={styles.statePanel} aria-live="polite">
          <LoaderCircle className={styles.spinner} size={22} aria-hidden="true" />
          <div><h2>正在读取持续监控</h2><p>正在同步调度状态和最近触发记录。</p></div>
        </section>
      ) : null}

      {!loading && loadError ? (
        <section className={`${styles.statePanel} ${styles.errorPanel}`} role="alert">
          <CircleAlert size={22} aria-hidden="true" />
          <div><h2>持续监控读取失败</h2><p>{loadError}</p></div>
          <button type="button" onClick={() => void load()}>
            <RefreshCw size={17} aria-hidden="true" /> 重新读取
          </button>
        </section>
      ) : null}

      {!loading && !loadError && view?.items.length === 0 ? (
        <section className={styles.emptyState}>
          <Radar size={24} aria-hidden="true" />
          <div>
            <h2>当前筛选下没有监控</h2>
            <p>请从已提交报告的详情页选择“持续关注”创建监控。</p>
          </div>
          <Link href="/library" prefetch={false}>前往报告资料库</Link>
        </section>
      ) : null}

      {!loading && !loadError && view && view.items.length > 0 ? (
        <section className={styles.list} aria-label="持续监控列表">
          {view.items.map((monitor) => (
            <MonitorRow
              key={monitor.id}
              monitor={monitor}
              busyAction={busy[monitor.id]}
              rowError={rowErrors[monitor.id]}
              triggerState={triggerStates[monitor.id]}
              onAction={runAction}
              onToggleTriggers={toggleTriggers}
              onRetryTriggers={(monitorId) => void loadTriggers(monitorId)}
            />
          ))}
        </section>
      ) : null}
    </div>
  );
}

function MonitorRow({
  monitor,
  busyAction,
  rowError,
  triggerState,
  onAction,
  onToggleTriggers,
  onRetryTriggers,
}: {
  monitor: Monitor;
  busyAction: MonitorAction | undefined;
  rowError: string | undefined;
  triggerState: TriggerState | undefined;
  onAction: (monitor: Monitor, action: MonitorAction) => Promise<void>;
  onToggleTriggers: (monitorId: string) => void;
  onRetryTriggers: (monitorId: string) => void;
}) {
  const historyId = `monitor-triggers-${monitor.id}`;
  const quietHours = monitor.quiet_hours
    ? `${monitor.quiet_hours.start}-${monitor.quiet_hours.end}`
    : "未设置";
  return (
    <article className={styles.row} data-status={monitor.status}>
      <div className={`${styles.cell} ${styles.identityCell}`}>
        <div className={styles.titleLine}>
          <MonitorStatusIcon status={monitor.status} />
          <span className={styles.statusText}>{monitorStatusLabels[monitor.status]}</span>
        </div>
        <h2>{monitor.name}</h2>
        <Link
          className={styles.sourceLink}
          href={`/artifacts/${monitor.artifact_id}`}
          prefetch={false}
        >
          <FileText size={15} aria-hidden="true" />
          {monitor.symbol.replace("-USDT-SWAP", "")} {monitor.horizon} 报告
          <ExternalLink size={13} aria-hidden="true" />
        </Link>
        {!monitor.cron_configured && monitor.status !== "disabled" ? (
          <p className={styles.attentionReason}><AlertTriangle size={15} aria-hidden="true" />调度配置尚未就绪</p>
        ) : null}
      </div>

      <MonitorCell label="条件" icon={<BellRing size={15} aria-hidden="true" />}>
        {describeMonitorCondition(monitor.condition)}
      </MonitorCell>
      <MonitorCell label="频率 / 时区" icon={<Clock3 size={15} aria-hidden="true" />}>
        {describeMonitorSchedule(monitor.schedule)}<small>{monitor.timezone}</small>
      </MonitorCell>
      <MonitorCell label="静默 / 有效期" icon={<CalendarClock size={15} aria-hidden="true" />}>
        静默 {quietHours}<small>截至 {formatMonitorDateTime(monitor.expires_at)}</small>
      </MonitorCell>
      <MonitorCell label="下次 / 最近触发" icon={<History size={15} aria-hidden="true" />}>
        {isClosedMonitor(monitor) ? "已停止调度" : formatMonitorDateTime(monitor.next_run_at)}
        <small>{monitor.latest_trigger
          ? `${triggerStatusLabels[monitor.latest_trigger.status]} · ${formatMonitorDateTime(monitor.latest_trigger.triggered_at)}`
          : "尚无触发记录"}</small>
      </MonitorCell>

      <div className={styles.actions} aria-label={`${monitor.name} 操作`}>
        {monitor.status === "paused" ? (
          <ActionButton
            label="恢复"
            icon={<Play size={16} aria-hidden="true" />}
            busy={busyAction === "resume"}
            disabled={busyAction !== undefined}
            onClick={() => void onAction(monitor, "resume")}
          />
        ) : canPause(monitor) ? (
          <ActionButton
            label="暂停"
            icon={<Pause size={16} aria-hidden="true" />}
            busy={busyAction === "pause"}
            disabled={busyAction !== undefined}
            onClick={() => void onAction(monitor, "pause")}
          />
        ) : null}
        {!isClosedMonitor(monitor) ? (
          <ActionButton
            label="立即检查"
            icon={<RotateCw size={16} aria-hidden="true" />}
            busy={busyAction === "trigger"}
            disabled={busyAction !== undefined || !canTrigger(monitor)}
            onClick={() => void onAction(monitor, "trigger")}
          />
        ) : null}
        <button
          className={styles.actionButton}
          type="button"
          aria-expanded={triggerState?.expanded ?? false}
          aria-controls={historyId}
          onClick={() => onToggleTriggers(monitor.id)}
        >
          <History size={16} aria-hidden="true" />
          触发记录
          {triggerState?.expanded
            ? <ChevronUp size={15} aria-hidden="true" />
            : <ChevronDown size={15} aria-hidden="true" />}
        </button>
        {monitor.status !== "disabled" ? (
          <ActionButton
            label="关闭"
            icon={<Trash2 size={16} aria-hidden="true" />}
            busy={busyAction === "delete"}
            danger
            disabled={busyAction !== undefined}
            onClick={() => void onAction(monitor, "delete")}
          />
        ) : null}
      </div>

      {rowError ? (
        <div className={styles.rowError} role="alert">
          <CircleAlert size={17} aria-hidden="true" />
          <span>{rowError}</span>
        </div>
      ) : null}

      <div id={historyId} className={triggerState?.expanded ? styles.triggerPanel : styles.hidden}>
        {triggerState?.expanded ? (
          <TriggerHistory
            state={triggerState}
            onRetry={() => onRetryTriggers(monitor.id)}
          />
        ) : null}
      </div>
    </article>
  );
}

function MonitorCell({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.cell}>
      <span className={styles.cellLabel}>{icon}{label}</span>
      <strong className={styles.cellValue}>{children}</strong>
    </div>
  );
}

function ActionButton({
  label,
  icon,
  busy,
  danger = false,
  disabled,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  busy: boolean;
  danger?: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={danger ? styles.dangerButton : styles.actionButton}
      type="button"
      disabled={disabled}
      aria-busy={busy}
      onClick={onClick}
    >
      {busy ? <LoaderCircle className={styles.spinner} size={16} aria-hidden="true" /> : icon}
      {busy ? "处理中" : label}
    </button>
  );
}

function TriggerHistory({ state, onRetry }: { state: TriggerState; onRetry: () => void }) {
  if (state.loading) {
    return <div className={styles.triggerState} aria-live="polite"><LoaderCircle className={styles.spinner} size={18} aria-hidden="true" />正在读取触发记录</div>;
  }
  if (state.error) {
    return (
      <div className={`${styles.triggerState} ${styles.triggerError}`} role="alert">
        <CircleAlert size={18} aria-hidden="true" /><span>{state.error}</span>
        <button type="button" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" />重试</button>
      </div>
    );
  }
  if (!state.view || state.view.items.length === 0) {
    return <div className={styles.triggerState}><History size={18} aria-hidden="true" />暂无触发记录</div>;
  }
  return (
    <div className={styles.triggerList}>
      {state.view.items.map((trigger) => (
        <div className={styles.triggerItem} key={trigger.id}>
          <TriggerStatusIcon status={trigger.status} />
          <div><strong>{triggerStatusLabels[trigger.status]}</strong><span>{trigger.reason ?? "调度记录已保存"}</span></div>
          <time dateTime={trigger.triggered_at}>{formatMonitorDateTime(trigger.triggered_at)}</time>
          {trigger.task_id ? <Link href={`/work?task=${encodeURIComponent(trigger.task_id)}`} prefetch={false}>打开任务<ExternalLink size={13} aria-hidden="true" /></Link> : null}
        </div>
      ))}
    </div>
  );
}

function MonitorStatusIcon({ status }: { status: Monitor["status"] }) {
  if (status === "active") return <CheckCircle2 className={styles.runningIcon} size={17} aria-hidden="true" />;
  if (status === "paused") return <Pause className={styles.pausedIcon} size={17} aria-hidden="true" />;
  if (status === "draft" || status === "degraded") return <AlertTriangle className={styles.attentionIcon} size={17} aria-hidden="true" />;
  return <XCircle className={styles.closedIcon} size={17} aria-hidden="true" />;
}

function TriggerStatusIcon({ status }: { status: MonitorTriggerList["items"][number]["status"] }) {
  if (status === "admitted") return <CheckCircle2 className={styles.runningIcon} size={17} aria-hidden="true" />;
  if (status === "failed") return <XCircle className={styles.closedIcon} size={17} aria-hidden="true" />;
  if (status === "suppressed") return <Pause className={styles.pausedIcon} size={17} aria-hidden="true" />;
  return <Clock3 className={styles.attentionIcon} size={17} aria-hidden="true" />;
}

function monitorMatchesFilter(monitor: Monitor, filter: MonitorStatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "running") return monitor.status === "draft" || monitor.status === "active";
  if (filter === "attention") return monitor.status === "degraded";
  if (filter === "closed") return monitor.status === "expired" || monitor.status === "disabled";
  return monitor.status === "paused";
}

function isClosedMonitor(monitor: Monitor): boolean {
  return monitor.status === "expired" || monitor.status === "disabled";
}

function canPause(monitor: Monitor): boolean {
  return monitor.status === "active" || monitor.status === "degraded";
}

function canTrigger(monitor: Monitor): boolean {
  return monitor.status === "active" || monitor.status === "degraded";
}
