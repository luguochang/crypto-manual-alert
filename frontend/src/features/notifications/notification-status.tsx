"use client";

import {
  Bell,
  BellRing,
  CircleCheck,
  CircleHelp,
  LoaderCircle,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  listNotifications,
  requestNotificationResend,
} from "@/lib/api/product-client";
import type { Notification, NotificationList, RunStatus } from "@/lib/schemas/product-api";
import { stableFingerprint } from "@/lib/stable-fingerprint";

interface NotificationStatusProps {
  taskId: string;
  requested: boolean;
  taskStatus: RunStatus;
  onStatusChange?: (taskId: string) => void;
}

const activeStatuses = new Set(["planned", "leased", "sending", "failed_retryable"]);
const maxEmptyPollAttempts = 20;

const statusLabels: Record<Notification["status"], string> = {
  planned: "待发送",
  leased: "已领取",
  sending: "发送中",
  delivered: "Provider 已接收",
  failed_retryable: "等待重试",
  failed_terminal: "发送失败",
  unknown: "结果待确认",
};

export function notificationStatusLabel(status: Notification["status"]): string {
  return statusLabels[status];
}

export function shouldPollNotifications(
  view: NotificationList | null,
  taskStatus: RunStatus = "queued",
  emptyPollAttempts = 0,
): boolean {
  const items = view?.items ?? [];
  if (items.some(
    (item) => activeStatuses.has(item.status) || item.manual_resend_pending,
  )) return true;
  return taskStatus === "succeeded"
    && items.length === 0
    && emptyPollAttempts < maxEmptyPollAttempts;
}

export function notificationProjectionFingerprint(view: NotificationList): string {
  return stableFingerprint(view.items.map((item) => ({
    notification_id: item.notification_id,
    status: item.status,
    attempt_count: item.attempt_count,
    manual_resend_pending: item.manual_resend_pending,
  })));
}

export function NotificationStatus({
  taskId,
  requested,
  taskStatus,
  onStatusChange,
}: NotificationStatusProps) {
  const [view, setView] = useState<NotificationList | null>(null);
  const [loading, setLoading] = useState(true);
  const [emptyPollAttempts, setEmptyPollAttempts] = useState(0);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const notificationFingerprint = useRef<string | null>(null);

  const applyNotificationView = useCallback((next: NotificationList) => {
    const nextFingerprint = notificationProjectionFingerprint(next);
    const changed = notificationFingerprint.current !== nextFingerprint;
    notificationFingerprint.current = nextFingerprint;
    setView(next);
    if (changed && next.items.length > 0) onStatusChange?.(taskId);
  }, [onStatusChange, taskId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await listNotifications(taskId);
      applyNotificationView(next);
      setEmptyPollAttempts((current) =>
        taskStatus === "succeeded" && next.items.length === 0
          ? current + 1
          : 0
      );
      setError(null);
      return next;
    } catch (cause) {
      if (taskStatus === "succeeded") {
        setEmptyPollAttempts((current) => current + 1);
      }
      setError(cause instanceof Error ? cause.message : "通知状态暂时不可用。");
      return null;
    } finally {
      setLoading(false);
    }
  }, [applyNotificationView, taskId, taskStatus]);

  useEffect(() => {
    let active = true;
    void listNotifications(taskId)
      .then((next) => {
        if (!active) return;
        applyNotificationView(next);
        setEmptyPollAttempts(
          taskStatus === "succeeded" && next.items.length === 0 ? 1 : 0,
        );
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        if (taskStatus === "succeeded") setEmptyPollAttempts(1);
        setError(cause instanceof Error ? cause.message : "通知状态暂时不可用。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [applyNotificationView, taskId, taskStatus]);

  useEffect(() => {
    if (loading || !shouldPollNotifications(view, taskStatus, emptyPollAttempts)) return;
    const timer = window.setTimeout(() => void refresh(), 1_500);
    return () => window.clearTimeout(timer);
  }, [emptyPollAttempts, loading, refresh, taskStatus, view]);

  const resend = useCallback(async (notification: Notification) => {
    if (!notification.manual_resend_available || resendingId !== null) return;
    setResendingId(notification.notification_id);
    setError(null);
    try {
      const queued = await requestNotificationResend(
        notification.notification_id,
        { reason: "User confirmed a single delivery retry." },
      );
      setView((current) => current === null
        ? current
        : {
            ...current,
            items: current.items.map((item) =>
              item.notification_id === queued.notification_id ? queued : item
            ),
          });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "通知重发请求未被接受。");
    } finally {
      setResendingId(null);
    }
  }, [resendingId]);

  const items = view?.items ?? [];
  const outboxUnavailable = requested
    && taskStatus === "succeeded"
    && items.length === 0
    && emptyPollAttempts >= maxEmptyPollAttempts;
  if (!requested && !loading && items.length === 0) return null;

  return (
    <section className="notification-panel" aria-labelledby={`notification-title-${taskId}`}>
      <div className="notification-heading">
        <div>
          <BellRing size={18} aria-hidden="true" />
          <h2 id={`notification-title-${taskId}`}>通知</h2>
        </div>
        <button
          type="button"
          className="notification-refresh"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="刷新通知状态"
          title="刷新通知状态"
        >
          <RefreshCw size={16} className={loading ? "spinning-icon" : undefined} />
        </button>
      </div>

      {loading && items.length === 0 ? (
        <div className="notification-empty" role="status">
          <LoaderCircle size={17} className="spinning-icon" aria-hidden="true" />
          <span>读取通知状态</span>
        </div>
      ) : items.length === 0 ? (
        <div className="notification-empty" role="status">
          <Bell size={17} aria-hidden="true" />
          <span>等待通知记录</span>
        </div>
      ) : (
        <div className="notification-list">
          {items.map((notification) => {
            const latest = notification.attempts.at(-1) ?? null;
            const statusLabel = notification.status === "delivered"
              && latest?.provider_receipt === null
              ? "回执待核对"
              : notificationStatusLabel(notification.status);
            return (
              <article
                key={notification.notification_id}
                className="notification-item"
                data-status={notification.status}
              >
                <div className="notification-item-status">
                  <span aria-hidden="true">{statusIcon(notification.status)}</span>
                  <div>
                    <strong>{statusLabel}</strong>
                    <small>{notification.channel.toUpperCase()} · 第 {notification.decision_version} 版决策</small>
                  </div>
                </div>
                <dl className="notification-metadata">
                  <div><dt>尝试</dt><dd>{notification.attempt_count} / 5</dd></div>
                  <div><dt>更新时间</dt><dd>{formatTime(notification.updated_at)}</dd></div>
                  {latest?.provider_receipt ? (
                    <div><dt>Provider 回执</dt><dd>{latest.provider_receipt}</dd></div>
                  ) : null}
                  {latest?.error_code ? (
                    <div><dt>状态码</dt><dd>{latest.error_code}</dd></div>
                  ) : null}
                </dl>
                {notification.manual_resend_pending ? (
                  <p className="notification-pending" role="status">人工重发已排队</p>
                ) : null}
                {notification.manual_resend_available ? (
                  <button
                    type="button"
                    className="notification-resend"
                    onClick={() => void resend(notification)}
                    disabled={resendingId !== null}
                  >
                    <RefreshCw size={15} aria-hidden="true" />
                    {resendingId === notification.notification_id ? "正在排队" : "重发一次"}
                  </button>
                ) : null}
              </article>
            );
          })}
        </div>
      )}

      {error ? (
        <p className="notification-error" role="alert">
          <TriangleAlert size={15} aria-hidden="true" />
          {error}
        </p>
      ) : null}
      {!error && outboxUnavailable ? (
        <p className="notification-error" role="alert">
          <TriangleAlert size={15} aria-hidden="true" />
          分析已完成，但通知记录仍未出现。请手动刷新状态并检查通知配置。
        </p>
      ) : null}
    </section>
  );
}

function statusIcon(status: Notification["status"]) {
  if (status === "delivered") return <CircleCheck size={17} />;
  if (status === "unknown") return <CircleHelp size={17} />;
  if (status === "failed_terminal") return <TriangleAlert size={17} />;
  if (activeStatuses.has(status)) return <LoaderCircle size={17} className="spinning-icon" />;
  return <Bell size={17} />;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
