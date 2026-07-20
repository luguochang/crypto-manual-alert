import type {
  MonitorCondition,
  MonitorSchedule,
  MonitorStatus,
  MonitorTrigger,
} from "@/lib/schemas/monitor-api";

export const monitorStatusLabels: Record<MonitorStatus, string> = {
  draft: "配置中",
  active: "运行中",
  paused: "已暂停",
  degraded: "需要处理",
  expired: "已过期",
  disabled: "已关闭",
};

export const triggerStatusLabels: Record<MonitorTrigger["status"], string> = {
  received: "已接收",
  suppressed: "已抑制",
  admitted: "已准入",
  failed: "触发失败",
};

export function describeMonitorCondition(condition: MonitorCondition): string {
  if (condition.kind === "price") {
    return `价格${condition.operator === "gte" ? "大于等于" : "小于等于"} ${formatNumber(condition.threshold)} USDT`;
  }
  if (condition.kind === "thesis") {
    return `结论检查：${condition.statement}`;
  }
  if (condition.kind === "provider_health") {
    const providerLabels = {
      okx: "OKX",
      tavily: "Tavily",
      builtin_web_search: "内置 Web Search",
    } as const;
    return `${providerLabels[condition.provider]} 连续失败 ${condition.consecutive_failures} 次`;
  }
  return "按计划复核报告结论";
}

export function describeMonitorSchedule(schedule: MonitorSchedule): string {
  const labels: Record<MonitorSchedule, string> = {
    "*/5 * * * *": "每 5 分钟",
    "*/15 * * * *": "每 15 分钟",
    "0 * * * *": "每小时",
    "0 */4 * * *": "每 4 小时",
    "0 0 * * *": "每天 00:00",
  };
  return labels[schedule];
}

export function formatMonitorDateTime(value: string | null): string {
  if (value === null) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 8 }).format(value);
}
