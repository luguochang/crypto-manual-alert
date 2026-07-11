import { productDisplayText } from "@/app/shared/product-copy";
import type { NotificationAttempt } from "@/lib/schemas/runs";

type NotificationHistoryProps = {
  items: NotificationAttempt[];
  latestStatus?: string | null;
};

function statusLabel(status: string | null | undefined): string {
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "发送失败";
  if (status === "disabled") return "通知未启用";
  return "未记录";
}

function statusTone(status: string | null | undefined): string {
  if (status === "sent") return "badge-success";
  if (status === "failed") return "badge-failed";
  if (status === "disabled") return "badge-pending";
  return "badge-neutral";
}

function channelLabel(channel: string | null | undefined): string {
  if (!channel) return "通知渠道";
  return channel.toLowerCase() === "bark" ? "Bark" : productDisplayText(channel);
}

function serviceResponseText(statusCode: number | null | undefined): string | null {
  return typeof statusCode === "number" ? `服务响应 ${statusCode}` : null;
}

function emptyStateText(status: string | null | undefined): string {
  if (status === "disabled") return "通知未启用";
  if (status === "sent") return "最新状态：Bark 已发送，发送明细待同步。";
  if (status === "failed") return "最新状态：发送失败，发送明细待同步。";
  return "暂无发送记录";
}

function emptyBadgeText(status: string | null | undefined): string {
  if (status === "disabled") return "未启用";
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "发送失败";
  return "暂无记录";
}

function emptyHeadingText(status: string | null | undefined): string {
  if (status === "sent") return "Bark 已发送";
  if (status === "failed") return "发送失败";
  return "暂无通知记录";
}

function formatNotificationTime(value: string | null | undefined): string {
  if (!value) return "时间未记录";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "时间未记录";
  const parts = new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).formatToParts(parsed);
  const pick = (type: string) => parts.find((part) => part.type === type)?.value ?? "--";
  return `${pick("month")}-${pick("day")} ${pick("hour")}:${pick("minute")}`;
}

function notificationFailureReason(error: string | null | undefined): string {
  if (!error) return "";
  const text = error.toLowerCase();
  if (/timeout|timed out|超时/.test(text)) return "Bark 发送超时";
  if (/401|403|unauthorized|forbidden|authorization|api[_-]?key|token|secret|device[_\s-]?key|bark[_\s-]?key/.test(text)) {
    return "通知配置或鉴权信息异常，原始错误已隐藏";
  }
  if (/5\d\d|server|bad gateway|unavailable/.test(text)) return "Bark 服务返回失败";
  if (/network|connection|econn|dns|socket/.test(text)) return "Bark 网络连接失败";
  return "通知发送失败，原始错误已隐藏";
}

export function NotificationHistory({ items, latestStatus }: NotificationHistoryProps) {
  const emptyLabel = emptyStateText(latestStatus);

  return (
    <section className="panel section-gap notification-history" aria-label="通知历史">
      <div className="panel-heading">
        <div>
          <h2>通知历史</h2>
          <p>记录本次提醒向 Bark 等渠道发送的状态，便于排查是否真正触达。</p>
        </div>
        <span className={`badge ${statusTone(items[0]?.status ?? latestStatus)}`}>
          {items.length > 0 ? statusLabel(items[0]?.status) : emptyBadgeText(latestStatus)}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="notification-empty">
          <strong>{emptyHeadingText(latestStatus)}</strong>
          <span>{emptyLabel}</span>
        </div>
      ) : (
        <ol className="notification-list">
          {items.map((item, index) => {
            const serviceResponse = serviceResponseText(item.status_code);
            const error = notificationFailureReason(item.error);
            return (
              <li key={`${item.created_at ?? "notification"}-${index}`} className="notification-item">
                <div className="notification-item-main">
                  <span className={`badge ${statusTone(item.status)}`}>{statusLabel(item.status)}</span>
                  <strong>{channelLabel(item.channel)}</strong>
                  <span>{formatNotificationTime(item.created_at)}</span>
                  {serviceResponse ? <span>{serviceResponse}</span> : null}
                </div>
                {error ? <p>失败原因：{error}</p> : null}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
