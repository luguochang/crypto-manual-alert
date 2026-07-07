export type Direction = "long" | "short" | "wait" | "unknown";

export function classifyDirection(action: string | undefined | null): Direction {
  const value = (action ?? "").toLowerCase();
  if (!value) return "unknown";
  if (value.includes("long")) return "long";
  if (value.includes("short")) return "short";
  if (
    value.includes("no trade") ||
    value.includes("hold") ||
    value.includes("wait") ||
    value.includes("close")
  ) {
    return "wait";
  }
  return "unknown";
}

export const DIRECTION_LABEL: Record<Direction, string> = {
  long: "做多 LONG",
  short: "做空 SHORT",
  wait: "观望 / 平仓",
  unknown: "未明确"
};

export const DIRECTION_TONE: Record<Direction, string> = {
  long: "tone-long",
  short: "tone-short",
  wait: "tone-wait",
  unknown: "tone-unknown"
};

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(0)}%`;
}
